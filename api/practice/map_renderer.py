"""
Map IR v2 — IELTS-style map question pipeline.

The AI emits a structured JSON IR; this module validates it and renders to
self-contained HTML that looks like a real IELTS Task 1 map (regions filled
as ground colors, roads as dual-stroke stripes, buildings as labeled
rectangles, candidate sites as colored A/B/C markers).

Schema (v2):

  {
    "irVersion": 2,
    "scenarioType": "geographical_change" | "site_selection",
    "viewModel":   "before_after" | "single",
    "environment": "indoor" | "outdoor",
    "locationName": "<short name>",
    "title": {"before": "...", "after": "..."}   # for before_after
             | "<string>"                        # for single
    "prompt": "<IELTS prompt sentence>",
    "layoutSummary": "<2-4 lines about spatial logic>",
    "compositionHint": "cross_road"|"river_bisected"|"campus_quad"
                      |"site_plan"|"linear_strip"|"coastal",

    # viewModel == "before_after":
    "mapA": <MapBlock>, "mapB": <MapBlock>, "changes": [...]

    # viewModel == "single":
    "map": <MapBlock>
  }

  MapBlock = {
    "regions":   [{id, name, kind, polygon: [[col,row], ...]}],
    "roads":     [{id, name, kind, points:  [[col,row], ...]}],
    "buildings": [{id, name, kind, footprint: [col,row,w,h]}],
    "landmarks": [{id, label, icon, grid: [col,row], marker?: 'A'|'B'|'C'}]
  }

Grid is 12 columns × 8 rows. Pixel = col * CELL_SIZE, top-left origin.
Renderer is deterministic — same IR → same HTML.
"""

from __future__ import annotations

import copy
import random
import re
from typing import Any

MAP_IR_VERSION = 2


# ── Grid & canvas ──────────────────────────────────────────────────────────
GRID_COLS = 12
GRID_ROWS = 8
CELL_SIZE = 60
MAP_W = GRID_COLS * CELL_SIZE   # 720
MAP_H = GRID_ROWS * CELL_SIZE   # 480
SINGLE_MAP_W = 880              # site_selection single view gets a wider canvas
SINGLE_MAP_H = 540

# Icon whitelist for `landmarks[].icon`. Kept intentionally small —
# emoji is now used for *landmark* embellishment only (bus stops, fountains,
# trees, monuments). The main visual mass is buildings + roads.
MAP_ICON_WHITELIST: set[str] = {
    '🏠', '🏘️', '🏢', '🏬', '🏭', '🏥', '🏫', '🏛️', '⛪', '🏤', '🏨', '🏪',
    '🏟️', '🎡', '🎢', '🎪', '🏰', '🗼',
    '🌲', '🌳', '🌴', '🌾', '🌸', '⛰️',
    '⛲', '🌉', '⚓', '🛳️',
    '🚂', '🚉', '🚌', '✈️', '🚗', '🅿️', '🚏',
    '🚧', '🏗️', '⛺', '🔆', '📍',
}


# ── Style catalogues ───────────────────────────────────────────────────────
# Visual language matches real IELTS Task 1 reference maps:
# - Monochrome line-art on white canvas
# - SVG pattern fills (hatch/dots/wave) instead of pastel colors
# - White building boxes with bold sans-serif labels INSIDE
# - Roads as parallel-line stripes (outer black, inner white channel)
# - Stacked vertical layout for before/after

# SVG <defs> with named patterns. Embedded once per <svg>; each <svg> has its
# own ID scope so the same patterns work in both mapA and mapB simultaneously.
SVG_PATTERN_DEFS = (
    '<defs>'
    '<pattern id="p-hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">'
    '<line x1="0" y1="0" x2="0" y2="7" stroke="#374151" stroke-width="0.7"/>'
    '</pattern>'
    '<pattern id="p-hatch-d" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">'
    '<line x1="0" y1="0" x2="0" y2="6" stroke="#1f2937" stroke-width="1.2"/>'
    '</pattern>'
    '<pattern id="p-cross" patternUnits="userSpaceOnUse" width="9" height="9">'
    '<line x1="0" y1="0" x2="9" y2="0" stroke="#4b5563" stroke-width="0.6"/>'
    '<line x1="0" y1="0" x2="0" y2="9" stroke="#4b5563" stroke-width="0.6"/>'
    '</pattern>'
    '<pattern id="p-dots" patternUnits="userSpaceOnUse" width="9" height="9">'
    '<circle cx="4.5" cy="4.5" r="1.0" fill="#4b5563"/>'
    '</pattern>'
    '<pattern id="p-dots-s" patternUnits="userSpaceOnUse" width="12" height="12">'
    '<circle cx="6" cy="6" r="0.8" fill="#6b7280"/>'
    '</pattern>'
    '<pattern id="p-forest" patternUnits="userSpaceOnUse" width="14" height="14">'
    '<circle cx="7" cy="7" r="2.6" fill="none" stroke="#15803d" stroke-width="0.7"/>'
    '<circle cx="7" cy="7" r="0.6" fill="#15803d"/>'
    '</pattern>'
    '<pattern id="p-wave" patternUnits="userSpaceOnUse" width="16" height="6">'
    '<path d="M0,3 Q4,0 8,3 T16,3" stroke="#0284c7" stroke-width="0.7" fill="none"/>'
    '</pattern>'
    '<pattern id="p-grass" patternUnits="userSpaceOnUse" width="10" height="10">'
    '<line x1="5" y1="2" x2="5" y2="8" stroke="#16a34a" stroke-width="0.7"/>'
    '<line x1="2" y1="5" x2="8" y2="5" stroke="#16a34a" stroke-width="0.4"/>'
    '</pattern>'
    '</defs>'
)

# Region kinds → pattern URL + outline + label color + (very pale) tint
REGION_STYLES: dict[str, dict[str, str]] = {
    'park':              {'fill': 'url(#p-grass)',   'stroke': '#15803d', 'label': '#14532d', 'tint': '#f0fdf4'},
    'forest':            {'fill': 'url(#p-forest)',  'stroke': '#15803d', 'label': '#14532d', 'tint': '#ecfdf5'},
    'farmland':          {'fill': 'url(#p-hatch)',   'stroke': '#a16207', 'label': '#713f12', 'tint': '#fefce8'},
    'water':             {'fill': 'url(#p-wave)',    'stroke': '#0284c7', 'label': '#0c4a6e', 'tint': '#eff6ff'},
    'beach':             {'fill': 'url(#p-dots-s)',  'stroke': '#ca8a04', 'label': '#78350f', 'tint': '#fef9c3'},
    'residential_area':  {'fill': 'url(#p-cross)',   'stroke': '#1f2937', 'label': '#1e293b', 'tint': '#fafafa'},
    'commercial_area':   {'fill': 'url(#p-dots)',    'stroke': '#1f2937', 'label': '#1e293b', 'tint': '#fafafa'},
    'industrial_area':   {'fill': 'url(#p-hatch-d)', 'stroke': '#1f2937', 'label': '#1e293b', 'tint': '#fafafa'},
    'wasteland':         {'fill': 'url(#p-dots-s)',  'stroke': '#6b7280', 'label': '#374151', 'tint': '#fafafa'},
    'plaza':             {'fill': '#fafafa',         'stroke': '#6b7280', 'label': '#1e293b', 'tint': '#fafafa'},
}

# Building kinds: all monochrome (white box + black border + black label).
# `bgPattern` is a CSS background gradient for kinds that conventionally show
# hatching in real IELTS maps (factories, housing blocks).
# `borderStyle` differentiates: heritage = double, transport = solid dark fill.
BUILDING_STYLES: dict[str, dict[str, Any]] = {
    'civic':       {'borderWidth': 1.8, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': False},
    'residential': {'borderWidth': 1.6, 'borderStyle': 'solid', 'bgPattern': 'crosshatch', 'darkFill': False},
    'commercial':  {'borderWidth': 1.6, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': False},
    'educational': {'borderWidth': 1.8, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': False},
    'industrial':  {'borderWidth': 1.6, 'borderStyle': 'solid', 'bgPattern': 'diagonal',   'darkFill': False},
    'leisure':     {'borderWidth': 1.8, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': False},
    'heritage':    {'borderWidth': 2.6, 'borderStyle': 'double','bgPattern': None,         'darkFill': False},
    'transport':   {'borderWidth': 2.0, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': True},
    'medical':     {'borderWidth': 1.8, 'borderStyle': 'solid', 'bgPattern': None,         'darkFill': False},
}

# CSS background-image gradients for hatched building fills.
BUILDING_BG_PATTERN_CSS: dict[str, str] = {
    'diagonal':  'repeating-linear-gradient(45deg, transparent 0 4.5px, #4b5563 4.5px 5.2px), #ffffff',
    'crosshatch': (
        'repeating-linear-gradient(45deg, transparent 0 5.5px, #6b7280 5.5px 6.0px),'
        'repeating-linear-gradient(-45deg, transparent 0 5.5px, #6b7280 5.5px 6.0px),'
        '#ffffff'
    ),
}

# Road kinds → outer stroke + inner stroke (white channel) + dash.
# Inner width is computed as (outer - 4) at render time so the two visible
# parallel lines are ~2px each with the white channel between.
ROAD_STYLES: dict[str, dict[str, Any]] = {
    'main_road':  {'outer': '#1a1a1a', 'inner': '#ffffff', 'width': 11, 'dash': None},
    'motorway':   {'outer': '#1a1a1a', 'inner': '#ffffff', 'width': 16, 'dash': '14 10'},
    'side_road':  {'outer': '#1a1a1a', 'inner': '#ffffff', 'width': 8,  'dash': None},
    'path':       {'outer': '#374151', 'inner': None,      'width': 2.4,'dash': '5 4'},
    'river':      {'outer': '#7dd3fc', 'inner': None,      'width': 18, 'dash': None},
    'stream':     {'outer': '#7dd3fc', 'inner': None,      'width': 10, 'dash': None},
    'coastline':  {'outer': '#0284c7', 'inner': None,      'width': 5,  'dash': None},
    'railway':    {'outer': '#1a1a1a', 'inner': '#ffffff', 'width': 9,  'dash': '5 5'},
    'corridor':   {'outer': '#4b5563', 'inner': '#ffffff', 'width': 10, 'dash': None},
    'bridge':     {'outer': '#1a1a1a', 'inner': '#fbbf24', 'width': 12, 'dash': None},
}

# Site marker colors (A/B/C candidate sites) — kept colored for accessibility.
SITE_MARKER_COLORS: dict[str, str] = {
    'A': '#dc2626',
    'B': '#0ea5e9',
    'C': '#16a34a',
}

# Canvas colors — clean white architectural-plan look
COLOR_BG = '#ffffff'
COLOR_GRID = '#e5e7eb'
COLOR_FRAME = '#1a1a1a'
COLOR_OUTDOOR_BORDER = '#1a1a1a'
COLOR_INDOOR_BORDER = '#1a1a1a'
COLOR_LABEL = '#0f172a'
COLOR_TITLE = '#0f172a'


# ── Story seeds & composition hints ────────────────────────────────────────

STORY_SEEDS_GEOGRAPHICAL: list[str] = [
    'Industrial decline → green regeneration (factories replaced by parks/cycle paths)',
    'Coastal urbanization (a fishing village gains hotels and a marina)',
    'Heritage conservation (old district preserved while modern edges fill in)',
    'Climate adaptation (flood defenses added; low-lying houses relocated)',
    'Transport-led growth (new station spawns a commercial cluster around it)',
    'Suburb maturation (farmland subdivided into housing + schools + shops)',
    'University expansion (campus grows over former allotments and a hospital wing)',
    'River cleanup (industrial wharves → riverside promenade + cafés)',
    'Tourism boom (sleepy village becomes resort with hotels and marina)',
    'Pedestrianization (a market street is closed to cars and gains plazas)',
    'Airport upgrade (a small airfield becomes a regional terminal)',
    'Hospital relocation (old infirmary demolished, new medical campus elsewhere)',
    'Greenway corridor (railway right-of-way converted to linear park)',
    'Cultural quarter (warehouses repurposed into galleries and theatres)',
    'Suburban densification (single houses replaced by apartment blocks)',
    'Stadium build (open land becomes sports arena with car parks)',
    'Tram line introduction (street network reorganized around a new tram)',
    'Wetland restoration (drained marsh re-flooded; nature reserve created)',
    'Conference centre development (mixed-use district built around it)',
    'Town hall expansion (civic square enlarged; council buildings rebuilt)',
    'Beach erosion response (seawall built; coastal road rerouted inland)',
    'Tech-park emergence (greenfield becomes corporate offices and R&D)',
    'Religious district renovation (old chapels restored, new community hall)',
    'Outdoor market modernized (open stalls become enclosed market hall)',
    'School consolidation (three small schools merge into one large campus)',
    'New bridge connection (formerly separate districts joined across river)',
    'Mining-town transition (mine closure leads to housing + heritage museum)',
    'Eco-village conversion (oil depot site becomes solar farm + housing)',
    'Highway bypass (town centre relieved of through-traffic, gains pedestrian zone)',
    'Hospital decentralization (one big hospital splits into community clinics)',
    'Logistics hub (former rail yard becomes distribution centre + warehousing)',
    'Riverside flood basin (lowland farms converted to storm-water park)',
]

STORY_SEEDS_SITE_SELECTION: list[str] = [
    'Three candidate plots for a new hospital near a main road and residential cluster',
    'Choosing among 3 sites for a community library next to schools and a park',
    'Selecting a location for a wind farm: shoreline / hilltop / inland plain',
    'Three possible sites for a sports complex relative to public transport',
    'Picking where to place a new primary school given housing density',
    'Site options for a recycling plant balancing traffic and noise impact',
    'Three candidate sites for a tourist information centre near the station',
    'Locating a new fire station to serve three residential clusters',
    'Choosing a site for a hotel: lakeside / town centre / hilltop',
    'Where to put a new bus interchange among three town districts',
    'Three options for a youth centre balancing access and quiet',
    'Picking a location for a museum near the historic quarter',
    'Three candidate plots for a supermarket with parking and bus access',
    'Choosing a site for a music venue: park / industrial / town centre',
    'Three options for a swimming pool near schools and residential blocks',
    'Picking a site for a cinema multiplex among three commercial districts',
    'Three candidate plots for a farmers\' market near the village green',
    'Locating a new university campus: central / suburban / out-of-town',
    'Three sites for a children\'s playground balancing safety and shade',
    'Selecting a wind-shelter ferry terminal among three coastal points',
    'Three plots for a botanical garden near rivers and existing parks',
    'Choosing where to place an EV charging hub: motorway / mall / depot',
]

COMPOSITION_HINTS_BY_SCENARIO: dict[str, tuple[str, ...]] = {
    'geographical_change': ('cross_road', 'river_bisected', 'coastal', 'linear_strip', 'campus_quad'),
    'site_selection':      ('site_plan', 'cross_road', 'river_bisected', 'campus_quad'),
}

COMPOSITION_HINTS = tuple(sorted({h for hints in COMPOSITION_HINTS_BY_SCENARIO.values() for h in hints}))


def pick_story_seed(scenario_type: str) -> str:
    pool = STORY_SEEDS_GEOGRAPHICAL if scenario_type == 'geographical_change' else STORY_SEEDS_SITE_SELECTION
    return random.choice(pool)


def pick_composition_hint(scenario_type: str) -> str:
    pool = COMPOSITION_HINTS_BY_SCENARIO.get(scenario_type) or COMPOSITION_HINTS
    return random.choice(pool)


# ── Validation ─────────────────────────────────────────────────────────────

ALLOWED_CHANGE_TYPES = {'added', 'removed', 'replaced', 'modified'}

_SITE_RE = re.compile(r'site[_\s-]*[abc]\b', re.IGNORECASE)


def _check_grid(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    col, row = value
    return (
        isinstance(col, int) and 0 <= col < GRID_COLS
        and isinstance(row, int) and 0 <= row < GRID_ROWS
    )


def _check_footprint(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    col, row, w, h = value
    if not all(isinstance(v, int) for v in (col, row, w, h)):
        return False
    return (
        0 <= col < GRID_COLS and 0 <= row < GRID_ROWS
        and 1 <= w <= GRID_COLS and 1 <= h <= GRID_ROWS
        and col + w <= GRID_COLS and row + h <= GRID_ROWS
    )


def _check_polyline(points: Any, min_pts: int) -> bool:
    if not isinstance(points, list) or len(points) < min_pts:
        return False
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return False
        c, r = pt
        if not isinstance(c, int) or not isinstance(r, int):
            return False
        if not (0 <= c <= GRID_COLS and 0 <= r <= GRID_ROWS):
            return False
    return True


def _entity_quadrant(grid: tuple[int, int]) -> int:
    col, row = grid
    if col < GRID_COLS / 2 and row < GRID_ROWS / 2:
        return 1
    if col >= GRID_COLS / 2 and row < GRID_ROWS / 2:
        return 2
    if col < GRID_COLS / 2 and row >= GRID_ROWS / 2:
        return 3
    return 4


def _block_quadrants(block: dict) -> set[int]:
    qs: set[int] = set()
    for b in (block.get('buildings') or []):
        if not isinstance(b, dict):
            continue
        fp = b.get('footprint')
        if _check_footprint(fp):
            cx = fp[0] + fp[2] / 2
            cy = fp[1] + fp[3] / 2
            qs.add(_entity_quadrant((int(cx), int(cy))))
    for lm in (block.get('landmarks') or []):
        if not isinstance(lm, dict):
            continue
        grid = lm.get('grid')
        if _check_grid(grid):
            qs.add(_entity_quadrant((int(grid[0]), int(grid[1]))))
    # Regions also count toward coverage — a labelled park/forest filling a
    # quadrant is visually as much "in" that quadrant as a building is.
    for rg in (block.get('regions') or []):
        if not isinstance(rg, dict):
            continue
        poly = rg.get('polygon')
        if not isinstance(poly, list) or not poly:
            continue
        try:
            cx = sum(float(p[0]) for p in poly) / len(poly)
            cy = sum(float(p[1]) for p in poly) / len(poly)
        except (TypeError, ValueError):
            continue
        qs.add(_entity_quadrant((int(cx), int(cy))))
    return qs


def _block_feature_count(block: dict) -> int:
    return (
        len(block.get('buildings') or [])
        + len(block.get('landmarks') or [])
        + len(block.get('regions') or [])
    )


def _norm_road_points(pts: Any) -> list[tuple[int, int]] | None:
    if not isinstance(pts, list):
        return None
    out: list[tuple[int, int]] = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            out.append((int(p[0]), int(p[1])))
        except (TypeError, ValueError):
            return None
    return out


def _footprint_contains(fp: Any, col: int, row: int) -> bool:
    if not _check_footprint(fp):
        return False
    fc, fr, fw, fh = fp
    return fc <= col < fc + fw and fr <= row < fr + fh


def _point_to_segment_distance(px: float, py: float,
                                ax: float, ay: float,
                                bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _point_in_polygon(px: float, py: float, polygon: list, eps: float = 1e-9) -> bool:
    """Strict interior test. Edge/vertex points return False — a road
    running along a region boundary is considered ALONGSIDE, not THROUGH."""
    if not polygon or len(polygon) < 3:
        return False
    n = len(polygon)
    # Pre-pass: reject points that lie on any edge (boundary, not interior).
    for i in range(n):
        try:
            ax, ay = float(polygon[i][0]), float(polygon[i][1])
            bx, by = float(polygon[(i + 1) % n][0]), float(polygon[(i + 1) % n][1])
        except (TypeError, IndexError):
            return False
        # Cross product zero → collinear with segment line.
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        if abs(cross) < eps:
            if (min(ax, bx) - eps <= px <= max(ax, bx) + eps
                    and min(ay, by) - eps <= py <= max(ay, by) + eps):
                return False  # on edge ⇒ not strictly interior
    # Ray casting for strict-interior points.
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if (yi > py) != (yj > py):
            denom = yj - yi
            if abs(denom) > 1e-9:
                x_intersect = (xj - xi) * (py - yi) / denom + xi
                if px < x_intersect:
                    inside = not inside
        j = i
    return inside


def _distance_to_building_rect(px: float, py: float, fp: Any) -> float:
    """Shortest distance (grid units) from a point to a building's footprint rect.
    Returns 0 if the point is inside the rect."""
    if not _check_footprint(fp):
        return float('inf')
    fc, fr, fw, fh = fp
    dx = max(fc - px, 0.0, px - (fc + fw))
    dy = max(fr - py, 0.0, py - (fr + fh))
    return (dx * dx + dy * dy) ** 0.5


def _min_distance_to_any_building(px: float, py: float, buildings: list) -> float:
    if not buildings:
        return float('inf')
    return min(
        (_distance_to_building_rect(px, py, b.get('footprint'))
         for b in buildings if isinstance(b, dict)),
        default=float('inf'),
    )


def _pick_clear_road_label_position(road_pts: list, buildings: list,
                                    cell_w: float, cell_h: float) -> tuple[float, float]:
    """Pick the road segment midpoint with the greatest clearance from any building.
    Falls back to the polyline midpoint."""
    candidates: list[tuple[float, float, float]] = []
    for i in range(1, len(road_pts)):
        try:
            x1, y1 = float(road_pts[i - 1][0]), float(road_pts[i - 1][1])
            x2, y2 = float(road_pts[i][0]), float(road_pts[i][1])
        except (TypeError, IndexError):
            continue
        # Try midpoint AND quarter/three-quarter points to get extra options.
        for t in (0.5, 0.3, 0.7, 0.2, 0.8):
            mx = x1 + (x2 - x1) * t
            my = y1 + (y2 - y1) * t
            clearance = _min_distance_to_any_building(mx, my, buildings)
            candidates.append((clearance, mx, my))
    if candidates:
        clearance, mx, my = max(candidates, key=lambda c: c[0])
        if clearance >= 0.4:
            return mx * cell_w, my * cell_h
    # Fallback to traditional midpoint
    cx, cy = _polyline_midpoint(road_pts, cell_w, cell_h)
    return cx, cy


def _pick_clear_region_label_position(polygon: list, buildings: list,
                                      cell_w: float, cell_h: float) -> tuple[float, float] | None:
    """Find a polygon-interior point that's outside every building footprint.
    Falls back to centroid (even if it's covered)."""
    if not polygon:
        return None
    # Polygon centroid first (cheap, often works).
    cx_g = sum(float(p[0]) for p in polygon) / len(polygon)
    cy_g = sum(float(p[1]) for p in polygon) / len(polygon)
    if _point_in_polygon(cx_g, cy_g, polygon):
        if _min_distance_to_any_building(cx_g, cy_g, buildings) >= 0.4:
            return cx_g * cell_w, cy_g * cell_h
    # Grid sweep inside the polygon's bounding box.
    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    best: tuple[float, float, float] | None = None
    step = 0.5
    x = x_min + step
    while x < x_max:
        y = y_min + step
        while y < y_max:
            if _point_in_polygon(x, y, polygon):
                clearance = _min_distance_to_any_building(x, y, buildings)
                if best is None or clearance > best[0]:
                    best = (clearance, x, y)
            y += step
        x += step
    if best and best[0] >= 0.4:
        return best[1] * cell_w, best[2] * cell_h
    # Last resort: centroid (may overlap a building, but we tried)
    return cx_g * cell_w, cy_g * cell_h


def _road_crosses_region(road_pts: list, polygon: list) -> bool:
    """True if any road point or segment-midpoint lies strictly inside the polygon."""
    if not road_pts or len(road_pts) < 2 or not polygon or len(polygon) < 3:
        return False
    # Check each road vertex
    for p in road_pts:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, IndexError):
            continue
        if _point_in_polygon(x, y, polygon):
            return True
    # Check segment midpoints (catches roads that span the polygon)
    for i in range(1, len(road_pts)):
        try:
            x1, y1 = float(road_pts[i - 1][0]), float(road_pts[i - 1][1])
            x2, y2 = float(road_pts[i][0]), float(road_pts[i][1])
        except (TypeError, IndexError):
            continue
        for t in (0.25, 0.5, 0.75):
            mx = x1 + (x2 - x1) * t
            my = y1 + (y2 - y1) * t
            if _point_in_polygon(mx, my, polygon):
                return True
    return False


def _validate_map_block(block: Any, label: str, require_site_markers: bool) -> list[str]:
    errors: list[str] = []
    if not isinstance(block, dict):
        return [f'{label} must be an object']

    roads = block.get('roads') or []
    buildings = block.get('buildings') or []
    landmarks = block.get('landmarks') or []
    regions = block.get('regions') or []

    if not isinstance(roads, list) or len(roads) < 1:
        errors.append(f'{label}.roads must contain ≥1 item')
    if not isinstance(buildings, list):
        errors.append(f'{label}.buildings must be an array')
    if not isinstance(landmarks, list):
        errors.append(f'{label}.landmarks must be an array')
    if not isinstance(regions, list):
        errors.append(f'{label}.regions must be an array')

    if isinstance(roads, list):
        for i, r in enumerate(roads):
            if not isinstance(r, dict):
                errors.append(f'{label}.roads[{i}] must be an object')
                continue
            if not isinstance(r.get('id'), str) or not r['id']:
                errors.append(f'{label}.roads[{i}].id must be a non-empty string')
            if not isinstance(r.get('name'), str):
                errors.append(f'{label}.roads[{i}].name must be a string')
            if r.get('kind') not in ROAD_STYLES:
                errors.append(
                    f"{label}.roads[{i}].kind '{r.get('kind')}' must be one of "
                    f'{sorted(ROAD_STYLES.keys())}'
                )
            if not _check_polyline(r.get('points'), min_pts=2):
                errors.append(
                    f'{label}.roads[{i}].points must be ≥2 grid points '
                    f'with col∈[0,{GRID_COLS}] row∈[0,{GRID_ROWS}]'
                )

    if isinstance(buildings, list):
        seen_b_ids: set[str] = set()
        for i, b in enumerate(buildings):
            if not isinstance(b, dict):
                errors.append(f'{label}.buildings[{i}] must be an object')
                continue
            bid = b.get('id')
            if not isinstance(bid, str) or not bid:
                errors.append(f'{label}.buildings[{i}].id must be a non-empty string')
            elif bid in seen_b_ids:
                errors.append(f'{label}.buildings duplicate id "{bid}"')
            else:
                seen_b_ids.add(bid)
            if not isinstance(b.get('name'), str):
                errors.append(f'{label}.buildings[{i}].name must be a string')
            if b.get('kind') not in BUILDING_STYLES:
                errors.append(
                    f"{label}.buildings[{i}].kind '{b.get('kind')}' must be one of "
                    f'{sorted(BUILDING_STYLES.keys())}'
                )
            if not _check_footprint(b.get('footprint')):
                errors.append(
                    f'{label}.buildings[{i}].footprint must be [col,row,w,h] '
                    f'integers with col+w≤{GRID_COLS}, row+h≤{GRID_ROWS}'
                )

    if isinstance(landmarks, list):
        seen_lm_ids: set[str] = set()
        for i, lm in enumerate(landmarks):
            if not isinstance(lm, dict):
                errors.append(f'{label}.landmarks[{i}] must be an object')
                continue
            lid = lm.get('id')
            if not isinstance(lid, str) or not lid:
                errors.append(f'{label}.landmarks[{i}].id must be a non-empty string')
            elif lid in seen_lm_ids:
                errors.append(f'{label}.landmarks duplicate id "{lid}"')
            else:
                seen_lm_ids.add(lid)
            if not isinstance(lm.get('label'), str):
                errors.append(f'{label}.landmarks[{i}].label must be a string')
            if lm.get('icon') not in MAP_ICON_WHITELIST:
                errors.append(
                    f"{label}.landmarks[{i}].icon '{lm.get('icon')}' not in whitelist"
                )
            if not _check_grid(lm.get('grid')):
                errors.append(
                    f'{label}.landmarks[{i}].grid must be [col,row] '
                    f'with col∈[0,{GRID_COLS}) row∈[0,{GRID_ROWS})'
                )
            marker = lm.get('marker')
            if marker is not None and marker not in ('A', 'B', 'C'):
                errors.append(f'{label}.landmarks[{i}].marker must be "A"/"B"/"C" or omitted')

    if isinstance(regions, list):
        for i, rg in enumerate(regions):
            if not isinstance(rg, dict):
                errors.append(f'{label}.regions[{i}] must be an object')
                continue
            if not isinstance(rg.get('id'), str):
                errors.append(f'{label}.regions[{i}].id must be a string')
            if not isinstance(rg.get('name'), str):
                errors.append(f'{label}.regions[{i}].name must be a string')
            if rg.get('kind') not in REGION_STYLES:
                errors.append(
                    f"{label}.regions[{i}].kind '{rg.get('kind')}' must be one of "
                    f'{sorted(REGION_STYLES.keys())}'
                )
            if not _check_polyline(rg.get('polygon'), min_pts=3):
                errors.append(
                    f'{label}.regions[{i}].polygon must be ≥3 grid points'
                )

    # Roads must not cross through region interiors. Regions should be
    # bounded by roads or sit between them, not split by them.
    for ri, rg in enumerate(regions or []):
        if not isinstance(rg, dict):
            continue
        poly = rg.get('polygon')
        if not isinstance(poly, list) or len(poly) < 3:
            continue
        for road in roads or []:
            if not isinstance(road, dict):
                continue
            pts = road.get('points')
            if not isinstance(pts, list) or len(pts) < 2:
                continue
            if _road_crosses_region(pts, poly):
                errors.append(
                    f"{label}: road '{road.get('id')}' passes through region "
                    f"'{rg.get('id')}'; roads must run ALONGSIDE regions, "
                    f'not through them — split the region or move the road'
                )
                break

    feature_count = _block_feature_count(block)
    if feature_count < 3:
        errors.append(f'{label} too sparse: {feature_count} features total, need ≥3')

    qs = _block_quadrants(block)
    required = 3 if feature_count >= 5 else 2
    if qs and len(qs) < required:
        errors.append(
            f'{label} clusters into only {len(qs)} quadrants '
            f'(have {feature_count} features, need ≥{required}); spread them out'
        )

    if require_site_markers:
        markers = sorted({
            lm.get('marker') for lm in (landmarks or [])
            if isinstance(lm, dict) and lm.get('marker') in ('A', 'B', 'C')
        })
        if markers != ['A', 'B', 'C']:
            errors.append(
                f'{label} must contain exactly three landmarks with markers A, B, C '
                f'(found {markers})'
            )

        # Candidate sites must be visually distinct.
        sites: list[tuple[str, int, int]] = []
        for lm in landmarks or []:
            if isinstance(lm, dict) and lm.get('marker') in ('A', 'B', 'C'):
                grid = lm.get('grid')
                if _check_grid(grid):
                    sites.append((lm.get('marker'), int(grid[0]), int(grid[1])))
        for i in range(len(sites)):
            for j in range(i + 1, len(sites)):
                dist = abs(sites[i][1] - sites[j][1]) + abs(sites[i][2] - sites[j][2])
                if dist < 3:
                    errors.append(
                        f'{label}: candidate sites {sites[i][0]} and {sites[j][0]} '
                        f'(at [{sites[i][1]},{sites[i][2]}] / [{sites[j][1]},{sites[j][2]}]) '
                        f'are too close (Manhattan distance {dist}, need ≥3)'
                    )

        # Candidate sites must be on empty land — NOT inside any building footprint.
        for letter, col, row in sites:
            for b in buildings or []:
                if not isinstance(b, dict):
                    continue
                if _footprint_contains(b.get('footprint'), col, row):
                    errors.append(
                        f'{label}: candidate Site {letter} at [{col},{row}] '
                        f'sits inside building "{b.get("id")}"; candidate sites must be on empty land'
                    )
                    break

        # Candidate sites must be NEXT TO a road, not ON it.
        for letter, col, row in sites:
            for r in roads or []:
                if not isinstance(r, dict):
                    continue
                norm = _norm_road_points(r.get('points'))
                if not norm or len(norm) < 2:
                    continue
                hit = False
                for i in range(len(norm) - 1):
                    ax, ay = norm[i]
                    bx, by = norm[i + 1]
                    if _point_to_segment_distance(col, row, ax, ay, bx, by) < 0.5:
                        hit = True
                        break
                if hit:
                    errors.append(
                        f'{label}: candidate Site {letter} at [{col},{row}] '
                        f'sits on road "{r.get("id")}"; place it adjacent to the road, not on it'
                    )
                    break

    return errors


def validate_map_ir(ir: Any) -> tuple[bool, list[str]]:
    """Validate a v2 IR. Returns (ok, errors)."""
    errors: list[str] = []

    if not isinstance(ir, dict):
        return False, ['IR must be a JSON object']

    if ir.get('irVersion') != MAP_IR_VERSION:
        errors.append(f"irVersion must be {MAP_IR_VERSION} (got {ir.get('irVersion')!r})")

    if ir.get('scenarioType') not in {'geographical_change', 'site_selection'}:
        errors.append("scenarioType must be 'geographical_change' or 'site_selection'")

    if ir.get('viewModel') not in {'before_after', 'single'}:
        errors.append("viewModel must be 'before_after' or 'single'")

    if ir.get('environment') not in {'indoor', 'outdoor'}:
        errors.append("environment must be 'indoor' or 'outdoor'")

    if not isinstance(ir.get('locationName'), str) or not ir['locationName'].strip():
        errors.append('locationName must be a non-empty string')

    if not isinstance(ir.get('prompt'), str) or len(ir['prompt']) < 20:
        errors.append('prompt must be a string of at least 20 chars')

    if not isinstance(ir.get('layoutSummary'), str) or len(ir['layoutSummary']) < 20:
        errors.append('layoutSummary must be a string of at least 20 chars')

    composition = ir.get('compositionHint')
    if composition is not None and composition not in COMPOSITION_HINTS:
        errors.append(f'compositionHint must be one of {sorted(COMPOSITION_HINTS)} or omitted')

    view_model = ir.get('viewModel')
    scenario = ir.get('scenarioType')

    # site_selection naturally pairs with single; geographical_change with before_after.
    if scenario == 'site_selection' and view_model != 'single':
        errors.append("site_selection should use viewModel='single' (one shared map with A/B/C)")
    if scenario == 'geographical_change' and view_model != 'before_after':
        errors.append("geographical_change should use viewModel='before_after' (two maps)")

    if view_model == 'before_after':
        title = ir.get('title')
        if not isinstance(title, dict) or not isinstance(title.get('before'), str) \
                or not isinstance(title.get('after'), str):
            errors.append("title must be an object {before, after} for before_after")

        errors.extend(_validate_map_block(ir.get('mapA'), 'mapA', require_site_markers=False))
        errors.extend(_validate_map_block(ir.get('mapB'), 'mapB', require_site_markers=False))

        # Anchor road parity — the comparison's whole point is that the
        # underlying terrain stays put. Any road id shared between maps
        # MUST have identical coordinates; and at least ONE road must be
        # shared to ground the spatial story.
        map_a = ir.get('mapA') if isinstance(ir.get('mapA'), dict) else {}
        map_b = ir.get('mapB') if isinstance(ir.get('mapB'), dict) else {}
        roads_a = {
            r.get('id'): _norm_road_points(r.get('points'))
            for r in (map_a.get('roads') or [])
            if isinstance(r, dict) and isinstance(r.get('id'), str)
        }
        roads_b = {
            r.get('id'): _norm_road_points(r.get('points'))
            for r in (map_b.get('roads') or [])
            if isinstance(r, dict) and isinstance(r.get('id'), str)
        }
        shared_ids = set(roads_a) & set(roads_b)
        if not shared_ids:
            errors.append(
                'mapA and mapB must share at least 1 road id with identical points '
                '(anchor that preserves spatial reference between before and after)'
            )
        for rid in sorted(shared_ids):
            if roads_a[rid] != roads_b[rid] or roads_a[rid] is None:
                errors.append(
                    f"shared road '{rid}' must have identical points in mapA and mapB "
                    f'(got {roads_a[rid]} vs {roads_b[rid]})'
                )

        changes = ir.get('changes')
        if not isinstance(changes, list):
            errors.append('changes must be an array')
        else:
            if not (3 <= len(changes) <= 7):
                errors.append(f'changes must contain 3–7 items (got {len(changes)})')
            for k, ch in enumerate(changes):
                if not isinstance(ch, dict):
                    errors.append(f'changes[{k}] must be an object')
                    continue
                if ch.get('type') not in ALLOWED_CHANGE_TYPES:
                    errors.append(
                        f'changes[{k}].type must be one of {sorted(ALLOWED_CHANGE_TYPES)}'
                    )

    elif view_model == 'single':
        if not isinstance(ir.get('title'), str) or not ir['title'].strip():
            errors.append("title must be a non-empty string for single view")
        errors.extend(_validate_map_block(
            ir.get('map'), 'map',
            require_site_markers=(scenario == 'site_selection'),
        ))

    return (not errors), errors


# ── Rendering ──────────────────────────────────────────────────────────────


def _esc(s: Any) -> str:
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def _grid_to_px(pt: tuple[int, int]) -> tuple[float, float]:
    return pt[0] * CELL_SIZE, pt[1] * CELL_SIZE


def _polyline_path(points: list, cell_w: float, cell_h: float) -> str:
    parts = []
    for i, pt in enumerate(points):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            continue
        x = pt[0] * cell_w
        y = pt[1] * cell_h
        parts.append(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}')
    return ' '.join(parts)


def _polygon_points(points: list, cell_w: float, cell_h: float) -> str:
    return ' '.join(f'{pt[0] * cell_w:.1f},{pt[1] * cell_h:.1f}'
                    for pt in points if isinstance(pt, (list, tuple)) and len(pt) == 2)


def _polyline_midpoint(points: list, cell_w: float, cell_h: float) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    total = 0.0
    segs: list[tuple[float, float, float, float, float]] = []
    for i in range(1, len(points)):
        x1 = points[i - 1][0] * cell_w
        y1 = points[i - 1][1] * cell_h
        x2 = points[i][0] * cell_w
        y2 = points[i][1] * cell_h
        d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        segs.append((x1, y1, x2, y2, d))
        total += d
    if total == 0.0:
        return points[0][0] * cell_w, points[0][1] * cell_h
    target = total / 2
    walked = 0.0
    for x1, y1, x2, y2, d in segs:
        if walked + d >= target and d > 0:
            t = (target - walked) / d
            return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        walked += d
    x1, y1, x2, y2, _ = segs[-1]
    return x2, y2


def _render_region_svg(rg: dict, cell_w: float, cell_h: float) -> str:
    style = REGION_STYLES.get(rg.get('kind', ''), REGION_STYLES['plaza'])
    pts = _polygon_points(rg.get('polygon') or [], cell_w, cell_h)
    if not pts:
        return ''
    # Two-layer fill: pale tint underneath + pattern overlay for visibility on white.
    tint_layer = ''
    if style.get('tint') and style['tint'] != style['fill']:
        tint_layer = (
            f'<polygon points="{pts}" fill="{style["tint"]}" stroke="none" opacity="0.7"/>'
        )
    pattern_layer = (
        f'<polygon points="{pts}" fill="{style["fill"]}" stroke="{style["stroke"]}" '
        f'stroke-width="1.4" stroke-linejoin="round"/>'
    )
    return tint_layer + pattern_layer


def _render_region_label(rg: dict, cell_w: float, cell_h: float,
                          buildings: list | None = None) -> str:
    pts = rg.get('polygon') or []
    if not pts:
        return ''
    name = rg.get('name') or ''
    if not name.strip():
        return ''
    pos = _pick_clear_region_label_position(pts, buildings or [], cell_w, cell_h)
    if pos is None:
        return ''
    cx, cy = pos
    style = REGION_STYLES.get(rg.get('kind', ''), REGION_STYLES['plaza'])
    return (
        f'<div style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;'
        f'transform:translate(-50%,-50%);font-family:Helvetica,Arial,sans-serif;'
        f'font-weight:600;font-size:13px;letter-spacing:0.3px;'
        f'color:{style["label"]};background:rgba(255,255,255,0.92);'
        f'padding:1px 7px;border-radius:3px;pointer-events:none;'
        f'box-shadow:0 0 0 1px rgba(255,255,255,0.6);">'
        f'{_esc(name)}</div>'
    )


def _render_road_svg(road: dict, cell_w: float, cell_h: float) -> str:
    style = ROAD_STYLES.get(road.get('kind', ''), ROAD_STYLES['side_road'])
    path = _polyline_path(road.get('points') or [], cell_w, cell_h)
    if not path:
        return ''
    width = float(style['width'])
    inner_w = max(1.6, width - 4)
    outer_dash = ''
    if style.get('dash') and not style.get('inner'):
        outer_dash = f' stroke-dasharray="{style["dash"]}"'
    outer = (
        f'<path d="{path}" fill="none" stroke="{style["outer"]}" '
        f'stroke-width="{width:.1f}" stroke-linecap="butt" '
        f'stroke-linejoin="round"{outer_dash}/>'
    )
    inner = ''
    if style.get('inner'):
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style.get('dash') else ''
        inner = (
            f'<path d="{path}" fill="none" stroke="{style["inner"]}" '
            f'stroke-width="{inner_w:.1f}" stroke-linecap="butt" '
            f'stroke-linejoin="round"{dash_attr}/>'
        )
    return outer + inner


def _render_road_label(road: dict, cell_w: float, cell_h: float,
                        buildings: list | None = None) -> str:
    name = road.get('name') or ''
    if not name.strip():
        return ''
    pts = road.get('points') or []
    if not pts:
        return ''
    cx, cy = _pick_clear_road_label_position(pts, buildings or [], cell_w, cell_h)
    return (
        f'<div style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;'
        f'transform:translate(-50%,-50%);background:#ffffff;'
        f'border:1px solid #1f2937;color:#0f172a;'
        f'padding:1px 8px;font-size:12px;font-weight:700;'
        f'font-family:Helvetica,Arial,sans-serif;'
        f'letter-spacing:0.3px;white-space:nowrap;'
        f'pointer-events:none;">{_esc(name)}</div>'
    )


def _render_building(b: dict, cell_w: float, cell_h: float) -> str:
    fp = b.get('footprint')
    if not _check_footprint(fp):
        return ''
    kind = b.get('kind', 'civic')
    style = BUILDING_STYLES.get(kind, BUILDING_STYLES['civic'])
    col, row, w, h = fp
    x = col * cell_w
    y = row * cell_h
    bw = w * cell_w
    bh = h * cell_h
    name = b.get('name') or b.get('id', '')
    font_size = 13 if (w >= 3 or h >= 3) else (12 if (w >= 2 or h >= 2) else 11)

    if style.get('darkFill'):
        bg_css = '#1f2937'
        label_color = '#ffffff'
    else:
        pattern_key = style.get('bgPattern')
        bg_css = BUILDING_BG_PATTERN_CSS.get(pattern_key, '#ffffff')
        label_color = COLOR_LABEL

    border_style = style.get('borderStyle', 'solid')
    border_w = style.get('borderWidth', 1.8)
    border_css = f'{border_w}px {border_style} {COLOR_FRAME}'

    # When using a CSS hatch pattern, put the label in a white-ish pill so it stays readable.
    label_wrap_open = ''
    label_wrap_close = ''
    if style.get('bgPattern') and not style.get('darkFill'):
        label_wrap_open = (
            '<span style="background:rgba(255,255,255,0.92);'
            'padding:1px 6px;border-radius:2px;">'
        )
        label_wrap_close = '</span>'

    return (
        f'<div style="position:absolute;left:{x:.0f}px;top:{y:.0f}px;'
        f'width:{bw:.0f}px;height:{bh:.0f}px;'
        f'background:{bg_css};border:{border_css};box-sizing:border-box;'
        f'display:flex;align-items:center;justify-content:center;text-align:center;'
        f'padding:3px;font-family:Helvetica,Arial,sans-serif;color:{label_color};'
        f'font-size:{font_size}px;font-weight:700;line-height:1.15;'
        f'pointer-events:none;overflow:hidden;">'
        f'{label_wrap_open}{_esc(name)}{label_wrap_close}'
        f'</div>'
    )


def _render_landmark(lm: dict, cell_w: float, cell_h: float) -> str:
    grid = lm.get('grid')
    if not _check_grid(grid):
        return ''
    col, row = int(grid[0]), int(grid[1])
    cx = col * cell_w + cell_w / 2
    cy = row * cell_h + cell_h / 2
    marker = lm.get('marker')
    label = lm.get('label') or lm.get('id', '')

    if marker in ('A', 'B', 'C'):
        color = SITE_MARKER_COLORS[marker]
        return (
            f'<div style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;'
            f'transform:translate(-50%,-50%);display:flex;flex-direction:column;'
            f'align-items:center;gap:3px;font-family:Helvetica,Arial,sans-serif;'
            f'pointer-events:none;">'
            f'<div style="width:34px;height:34px;border-radius:50%;background:{color};'
            f'color:#ffffff;font-weight:800;font-size:17px;display:flex;'
            f'align-items:center;justify-content:center;'
            f'box-shadow:0 0 0 2.5px #ffffff, 0 1px 3px rgba(0,0,0,0.35);">'
            f'{marker}</div>'
            f'<div style="background:#ffffff;border:1.4px solid {color};color:#0f172a;'
            f'padding:1px 7px;font-size:11px;font-weight:700;'
            f'white-space:nowrap;">{_esc(label)}</div>'
            f'</div>'
        )

    icon = lm.get('icon', '📍')
    return (
        f'<div style="position:absolute;left:{cx:.0f}px;top:{cy:.0f}px;'
        f'transform:translate(-50%,-50%);display:flex;flex-direction:column;'
        f'align-items:center;gap:2px;font-family:Helvetica,Arial,sans-serif;'
        f'pointer-events:none;">'
        f'<span style="font-size:22px;line-height:1;">{_esc(icon)}</span>'
        f'<span style="background:#ffffff;border:1px solid #1f2937;'
        f'color:#0f172a;padding:1px 6px;font-size:10px;font-weight:600;'
        f'white-space:nowrap;">{_esc(label)}</span>'
        f'</div>'
    )


def _render_corner_compass() -> str:
    """Small IELTS-style compass sitting in the map's top-right corner."""
    return (
        '<svg width="52" height="52" viewBox="0 0 52 52" '
        'style="position:absolute;top:8px;right:8px;'
        'background:#ffffff;border:1.2px solid #1f2937;'
        'font-family:Helvetica,Arial,sans-serif;pointer-events:none;">'
        '<line x1="26" y1="8" x2="26" y2="44" stroke="#1f2937" stroke-width="1.2"/>'
        '<line x1="8" y1="26" x2="44" y2="26" stroke="#1f2937" stroke-width="1.2"/>'
        '<polygon points="26,5 22,12 30,12" fill="#1f2937"/>'
        '<text x="26" y="51" text-anchor="middle" font-size="8" font-weight="700" fill="#1f2937">S</text>'
        '<text x="3" y="29" font-size="8" font-weight="700" fill="#1f2937">W</text>'
        '<text x="46" y="29" font-size="8" font-weight="700" fill="#1f2937">E</text>'
        '<text x="26" y="20" text-anchor="middle" font-size="8" font-weight="700" fill="#1f2937">N</text>'
        '</svg>'
    )


def _render_map_block(
    block: dict,
    title_text: str,
    environment: str,
    width: int = MAP_W,
    height: int = MAP_H,
) -> str:
    cell_w = width / GRID_COLS
    cell_h = height / GRID_ROWS
    border_color = COLOR_INDOOR_BORDER if environment == 'indoor' else COLOR_OUTDOOR_BORDER

    regions = block.get('regions') or []
    roads = block.get('roads') or []
    buildings = block.get('buildings') or []
    landmarks = block.get('landmarks') or []

    region_svg = ''.join(_render_region_svg(r, cell_w, cell_h)
                         for r in regions if isinstance(r, dict))
    road_svg = ''.join(_render_road_svg(r, cell_w, cell_h)
                       for r in roads if isinstance(r, dict))
    # Region/road labels need building footprints to avoid landing on top of names.
    region_labels = ''.join(_render_region_label(r, cell_w, cell_h, buildings)
                            for r in regions if isinstance(r, dict))
    road_labels = ''.join(_render_road_label(r, cell_w, cell_h, buildings)
                          for r in roads if isinstance(r, dict))
    building_html = ''.join(_render_building(b, cell_w, cell_h)
                            for b in buildings if isinstance(b, dict))
    landmark_html = ''.join(_render_landmark(lm, cell_w, cell_h)
                            for lm in landmarks if isinstance(lm, dict))

    title_html = ''
    if title_text:
        title_html = (
            f'<div style="font-size:16px;font-weight:700;color:{COLOR_TITLE};'
            f'font-family:Helvetica,Arial,sans-serif;letter-spacing:0.2px;'
            f'margin-bottom:6px;text-align:center;">'
            f'{_esc(title_text)}</div>'
        )

    corner_compass = _render_corner_compass()

    return (
        '<div style="display:flex;flex-direction:column;align-items:center;">'
        f'{title_html}'
        '<div style="position:relative;'
        f'width:{width}px;height:{height}px;'
        f'background:{COLOR_BG};'
        f'border:2.4px solid {border_color};'
        'overflow:hidden;">'
        f'<svg width="{width}" height="{height}" '
        'style="position:absolute;inset:0;pointer-events:none;">'
        f'{SVG_PATTERN_DEFS}{region_svg}{road_svg}'
        '</svg>'
        f'{region_labels}{building_html}{road_labels}{landmark_html}{corner_compass}'
        '</div>'
        '</div>'
    )


def _render_compass() -> str:
    # Standalone (legacy) compass kept for any caller that asks; the in-frame
    # corner compass is preferred and used inside _render_map_block.
    return _render_corner_compass()


def _collect_legend_pairs(*blocks: dict) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        for lm in (blk.get('landmarks') or []):
            if not isinstance(lm, dict) or lm.get('marker') in ('A', 'B', 'C'):
                continue
            icon = lm.get('icon')
            label = lm.get('label') or lm.get('id', '')
            key = f'{icon}|{label}'
            if icon and key not in seen and icon in MAP_ICON_WHITELIST:
                seen.add(key)
                out.append((icon, label))
    return out


def _render_legend(*blocks: dict) -> str:
    items = _collect_legend_pairs(*blocks)
    if not items:
        return ''
    pairs = ''.join(
        f'<div style="display:flex;align-items:center;gap:8px;'
        f'font-family:Helvetica,Arial,sans-serif;font-size:12px;color:{COLOR_LABEL};">'
        f'<span style="font-size:18px;">{_esc(icon)}</span><span>{_esc(label)}</span></div>'
        for icon, label in items
    )
    return (
        '<div style="display:grid;grid-template-columns:repeat(2,auto);'
        'gap:6px 22px;padding:8px 14px;background:#ffffff;'
        f'border:1.4px solid {COLOR_FRAME};">'
        f'{pairs}'
        '</div>'
    )


def render_map_ir(ir: dict, version: int = MAP_IR_VERSION) -> str:
    """Render a validated v2 IR to a self-contained HTML string.

    Output has no <script>, no inline event handlers, no external resources.
    Renderer is deterministic — same IR always yields the same HTML.
    """
    environment = ir.get('environment', 'outdoor')
    view_model = ir.get('viewModel', 'before_after')

    # Outer container styling — clean white with subtle frame, matches paper feel.
    outer_open = (
        '<div class="ielts-map-pair" style="display:flex;flex-direction:column;'
        'align-items:center;gap:14px;padding:18px;background:#ffffff;'
        'font-family:Helvetica,Arial,sans-serif;">'
    )
    outer_close = '</div>'

    if view_model == 'single':
        block = ir.get('map') or {}
        title_text = ir.get('title') if isinstance(ir.get('title'), str) else (
            ir.get('locationName') or 'Map'
        )
        body = _render_map_block(block, title_text, environment, SINGLE_MAP_W, SINGLE_MAP_H)
        legend = _render_legend(block)
        return (
            f'{outer_open}{body}'
            f'{legend}'
            f'{outer_close}'
        )

    # before_after — vertical stack to match real IELTS (NOW above, AFTER below).
    title = ir.get('title') or {}
    before = title.get('before') or 'Before'
    after = title.get('after') or 'After'
    location = (ir.get('locationName') or '').strip()
    # Match "Norbiton industrial area now" / "Planned future development" pattern.
    before_title = f'{location} — {before}' if location and before not in location else (before or 'Before')
    after_title = f'{location} — {after}' if location and after not in location else (after or 'After')
    map_a = ir.get('mapA') or {}
    map_b = ir.get('mapB') or {}
    top = _render_map_block(map_a, before_title, environment)
    bottom = _render_map_block(map_b, after_title, environment)
    legend = _render_legend(map_a, map_b)
    return (
        f'{outer_open}{top}{bottom}{legend}{outer_close}'
    )


# ── Fallback IRs (v2) ──────────────────────────────────────────────────────
# 6 pre-authored IRs covering the main scenarios. All pass validate_map_ir.

FALLBACK_IRS: list[dict] = [
    {
        'irVersion': 2,
        'scenarioType': 'geographical_change',
        'viewModel': 'before_after',
        'environment': 'outdoor',
        'locationName': 'A small coastal town',
        'title': {'before': '1990', 'after': '2020'},
        'prompt': (
            'The maps below show the changes that took place in a small coastal town between 1990 and 2020. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'The coastline runs along the south of both maps and a main road crosses east-west. '
            'In 1990 the west was forest and the harbour held a fishing pier; by 2020 housing replaced the forest '
            'and a resort hotel took the pier, with a new coastal park added to the east.'
        ),
        'compositionHint': 'coastal',
        'mapA': {
            'regions': [
                {'id': 'forest_a', 'name': 'Forest', 'kind': 'forest',
                 'polygon': [[0, 0], [4, 0], [4, 3], [0, 3]]},
                {'id': 'sea_a', 'name': 'Sea', 'kind': 'water',
                 'polygon': [[0, 7], [12, 7], [12, 8], [0, 8]]},
            ],
            'roads': [
                {'id': 'main_road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'coastline', 'name': 'Coastline', 'kind': 'coastline',
                 'points': [[0, 7], [12, 7]]},
            ],
            'buildings': [
                {'id': 'village_a', 'name': 'Village', 'kind': 'residential',
                 'footprint': [5, 1, 3, 2]},
                {'id': 'harbour_a', 'name': 'Harbour', 'kind': 'transport',
                 'footprint': [7, 5, 3, 2]},
            ],
            'landmarks': [
                {'id': 'pier_a', 'label': 'Fishing pier', 'icon': '⚓', 'grid': [3, 6]},
            ],
        },
        'mapB': {
            'regions': [
                {'id': 'park_b', 'name': 'Coastal Park', 'kind': 'park',
                 'polygon': [[9, 4], [12, 4], [12, 7], [9, 7]]},
                {'id': 'sea_b', 'name': 'Sea', 'kind': 'water',
                 'polygon': [[0, 7], [12, 7], [12, 8], [0, 8]]},
            ],
            'roads': [
                {'id': 'main_road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'coastline', 'name': 'Coastline', 'kind': 'coastline',
                 'points': [[0, 7], [12, 7]]},
            ],
            'buildings': [
                {'id': 'housing_b', 'name': 'Housing', 'kind': 'residential',
                 'footprint': [0, 0, 4, 3]},
                {'id': 'village_b', 'name': 'Village (expanded)', 'kind': 'residential',
                 'footprint': [5, 1, 3, 2]},
                {'id': 'resort_b', 'name': 'Resort Hotel', 'kind': 'leisure',
                 'footprint': [2, 5, 3, 2]},
                {'id': 'harbour_b', 'name': 'Harbour', 'kind': 'transport',
                 'footprint': [7, 5, 3, 2]},
            ],
            'landmarks': [],
        },
        'changes': [
            {'type': 'replaced', 'from': 'forest_a', 'to': 'housing_b'},
            {'type': 'replaced', 'from': 'pier_a', 'to': 'resort_b'},
            {'type': 'modified', 'id': 'village', 'note': 'expanded'},
            {'type': 'added', 'to': 'park_b'},
        ],
    },
    {
        'irVersion': 2,
        'scenarioType': 'geographical_change',
        'viewModel': 'before_after',
        'environment': 'outdoor',
        'locationName': 'A riverside industrial district',
        'title': {'before': '1985', 'after': '2025'},
        'prompt': (
            'The maps below show a riverside industrial district in 1985 and 2025. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'A river flows east-west through the district; a bridge crosses it. '
            'The north bank shifted from factories to offices and a riverside promenade, '
            'while the south bank gained housing and a school.'
        ),
        'compositionHint': 'river_bisected',
        'mapA': {
            'regions': [
                {'id': 'allot_a', 'name': 'Allotments', 'kind': 'farmland',
                 'polygon': [[1, 5], [5, 5], [5, 7], [1, 7]]},
            ],
            'roads': [
                {'id': 'river', 'name': 'River', 'kind': 'river',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'bridge', 'name': 'Bridge', 'kind': 'bridge',
                 'points': [[6, 3], [6, 5]]},
            ],
            'buildings': [
                {'id': 'fac_n1_a', 'name': 'Factory', 'kind': 'industrial',
                 'footprint': [0, 0, 3, 3]},
                {'id': 'fac_n2_a', 'name': 'Factory', 'kind': 'industrial',
                 'footprint': [8, 0, 4, 3]},
                {'id': 'wharf_a', 'name': 'Cargo Wharf', 'kind': 'industrial',
                 'footprint': [3, 2, 4, 2]},
                {'id': 'lane_a', 'name': "Workers' Lane", 'kind': 'residential',
                 'footprint': [7, 5, 5, 2]},
            ],
            'landmarks': [],
        },
        'mapB': {
            'regions': [
                {'id': 'prom_b', 'name': 'Promenade', 'kind': 'park',
                 'polygon': [[7, 0], [12, 0], [12, 3], [7, 3]]},
            ],
            'roads': [
                {'id': 'river', 'name': 'River', 'kind': 'river',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'bridge', 'name': 'Bridge', 'kind': 'bridge',
                 'points': [[6, 3], [6, 5]]},
            ],
            'buildings': [
                {'id': 'office_b', 'name': 'Office Tower', 'kind': 'commercial',
                 'footprint': [0, 0, 3, 3]},
                {'id': 'cafes_b', 'name': 'Cafés', 'kind': 'commercial',
                 'footprint': [3, 2, 4, 2]},
                {'id': 'school_b', 'name': 'School', 'kind': 'educational',
                 'footprint': [1, 5, 4, 2]},
                {'id': 'housing_b', 'name': 'Housing', 'kind': 'residential',
                 'footprint': [7, 5, 5, 2]},
            ],
            'landmarks': [],
        },
        'changes': [
            {'type': 'replaced', 'from': 'fac_n1_a', 'to': 'office_b'},
            {'type': 'replaced', 'from': 'fac_n2_a', 'to': 'prom_b'},
            {'type': 'replaced', 'from': 'wharf_a', 'to': 'cafes_b'},
            {'type': 'replaced', 'from': 'allot_a', 'to': 'school_b'},
            {'type': 'replaced', 'from': 'lane_a', 'to': 'housing_b'},
        ],
    },
    {
        'irVersion': 2,
        'scenarioType': 'geographical_change',
        'viewModel': 'before_after',
        'environment': 'outdoor',
        'locationName': 'A village near a forest',
        'title': {'before': '2000', 'after': '2025'},
        'prompt': (
            'The maps below show a small village near a forest in 2000 and 2025. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'A north-south main road and an east-west stream anchor both maps. '
            'In 2000 forest sat on both sides of the road and farmland filled the southwest; '
            'by 2025 the western forest has been cleared for a school, the eastern forest for a clinic, '
            'and the farmland is now a railway station.'
        ),
        'compositionHint': 'cross_road',
        'mapA': {
            'regions': [
                {'id': 'forest_w', 'name': 'Forest', 'kind': 'forest',
                 'polygon': [[0, 0], [5, 0], [5, 2], [0, 2]]},
                {'id': 'forest_e', 'name': 'Forest', 'kind': 'forest',
                 'polygon': [[7, 0], [12, 0], [12, 2], [7, 2]]},
                {'id': 'farm_a', 'name': 'Farmland', 'kind': 'farmland',
                 'polygon': [[0, 5], [5, 5], [5, 8], [0, 8]]},
            ],
            'roads': [
                {'id': 'road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[6, 0], [6, 8]]},
                {'id': 'stream', 'name': 'Stream', 'kind': 'stream',
                 'points': [[0, 4], [12, 4]]},
            ],
            'buildings': [
                {'id': 'church', 'name': 'Church', 'kind': 'heritage',
                 'footprint': [7, 2, 2, 2]},
                {'id': 'cottage', 'name': 'Cottages', 'kind': 'residential',
                 'footprint': [8, 5, 4, 2]},
            ],
            'landmarks': [],
        },
        'mapB': {
            'roads': [
                {'id': 'road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[6, 0], [6, 8]]},
                {'id': 'stream', 'name': 'Stream', 'kind': 'stream',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'rail', 'name': 'Railway', 'kind': 'railway',
                 'points': [[0, 6], [5, 6]]},
            ],
            'buildings': [
                {'id': 'school_b', 'name': 'School', 'kind': 'educational',
                 'footprint': [0, 0, 5, 2]},
                {'id': 'clinic_b', 'name': 'Clinic', 'kind': 'medical',
                 'footprint': [7, 0, 5, 2]},
                {'id': 'church', 'name': 'Church', 'kind': 'heritage',
                 'footprint': [7, 2, 2, 2]},
                {'id': 'station_b', 'name': 'Station', 'kind': 'transport',
                 'footprint': [0, 5, 4, 2]},
                {'id': 'cottage', 'name': 'Cottages', 'kind': 'residential',
                 'footprint': [8, 5, 4, 2]},
            ],
            'landmarks': [],
        },
        'changes': [
            {'type': 'replaced', 'from': 'forest_w', 'to': 'school_b'},
            {'type': 'replaced', 'from': 'forest_e', 'to': 'clinic_b'},
            {'type': 'replaced', 'from': 'farm_a', 'to': 'station_b'},
            {'type': 'modified', 'id': 'church', 'note': 'preserved'},
        ],
    },
    {
        'irVersion': 2,
        'scenarioType': 'site_selection',
        'viewModel': 'single',
        'environment': 'outdoor',
        'locationName': 'A suburb seeking a new hospital site',
        'title': 'Proposed Hospital Sites — Suburban Area',
        'prompt': (
            'The map below shows three proposed sites for a new hospital in a suburban area. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'The main road runs east-west across the middle; a railway crosses the north. '
            'Site A sits west of the housing estate; Site B is further east near the park; '
            'Site C is north of the railway near open land.'
        ),
        'compositionHint': 'site_plan',
        'map': {
            'regions': [
                {'id': 'park', 'name': 'Park', 'kind': 'park',
                 'polygon': [[2, 0], [5, 0], [5, 2], [2, 2]]},
                {'id': 'open_land', 'name': 'Open Land', 'kind': 'wasteland',
                 'polygon': [[8, 0], [12, 0], [12, 2], [8, 2]]},
            ],
            'roads': [
                {'id': 'main_road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[0, 4], [12, 4]]},
                {'id': 'railway', 'name': 'Railway', 'kind': 'railway',
                 'points': [[0, 2], [12, 2]]},
                {'id': 'side', 'name': 'Side Road', 'kind': 'side_road',
                 'points': [[6, 2], [6, 8]]},
            ],
            'buildings': [
                {'id': 'school', 'name': 'School', 'kind': 'educational',
                 'footprint': [0, 5, 3, 2]},
                {'id': 'housing', 'name': 'Housing Estate', 'kind': 'residential',
                 'footprint': [8, 5, 4, 3]},
            ],
            'landmarks': [
                {'id': 'site_a', 'label': 'Site A', 'icon': '🔆', 'grid': [3, 5], 'marker': 'A'},
                {'id': 'site_b', 'label': 'Site B', 'icon': '🔆', 'grid': [7, 6], 'marker': 'B'},
                {'id': 'site_c', 'label': 'Site C', 'icon': '🔆', 'grid': [10, 1], 'marker': 'C'},
                {'id': 'bus', 'label': 'Bus Stop', 'icon': '🚏', 'grid': [5, 4]},
            ],
        },
    },
    {
        'irVersion': 2,
        'scenarioType': 'site_selection',
        'viewModel': 'single',
        'environment': 'outdoor',
        'locationName': 'Three candidate sites for a community library',
        'title': 'Proposed Library Sites — Riverside District',
        'prompt': (
            'The map below shows three proposed sites for a new community library. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'A river runs north-south through the centre and the main road crosses east-west. '
            'Site A lies far east near the school; Site B is west between the shopping street and a housing cluster; '
            'Site C sits south next to the riverside park, which lies east of the river.'
        ),
        'compositionHint': 'river_bisected',
        'map': {
            'regions': [
                {'id': 'park', 'name': 'Riverside Park', 'kind': 'park',
                 'polygon': [[7, 4], [10, 4], [10, 7], [7, 7]]},
            ],
            'roads': [
                {'id': 'river', 'name': 'River', 'kind': 'river',
                 'points': [[6, 0], [6, 8]]},
                {'id': 'main_road', 'name': 'Main Road', 'kind': 'main_road',
                 'points': [[0, 3], [12, 3]]},
            ],
            'buildings': [
                {'id': 'school', 'name': 'School', 'kind': 'educational',
                 'footprint': [8, 0, 4, 2]},
                {'id': 'shops', 'name': 'Shopping Street', 'kind': 'commercial',
                 'footprint': [0, 0, 4, 2]},
                {'id': 'housing', 'name': 'Housing', 'kind': 'residential',
                 'footprint': [2, 5, 3, 3]},
            ],
            'landmarks': [
                {'id': 'site_a', 'label': 'Site A', 'icon': '🔆', 'grid': [11, 5], 'marker': 'A'},
                {'id': 'site_b', 'label': 'Site B', 'icon': '🔆', 'grid': [2, 4], 'marker': 'B'},
                {'id': 'site_c', 'label': 'Site C', 'icon': '🔆', 'grid': [8, 7], 'marker': 'C'},
                {'id': 'bus', 'label': 'Bus Stop', 'icon': '🚏', 'grid': [5, 3]},
            ],
        },
    },
    {
        'irVersion': 2,
        'scenarioType': 'site_selection',
        'viewModel': 'single',
        'environment': 'outdoor',
        'locationName': 'Three candidate sites for a sports complex',
        'title': 'Proposed Sports Complex Sites',
        'prompt': (
            'The map below shows three possible sites for a new sports complex. '
            'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'
        ),
        'layoutSummary': (
            'A motorway forms the northern boundary and a bus route runs north-south down the middle. '
            'Site A lies northwest near the motorway; Site B is east of the bus station; '
            'Site C sits south near a housing estate.'
        ),
        'compositionHint': 'site_plan',
        'map': {
            'regions': [
                {'id': 'park', 'name': 'Park', 'kind': 'park',
                 'polygon': [[9, 5], [12, 5], [12, 8], [9, 8]]},
            ],
            'roads': [
                {'id': 'motorway', 'name': 'Motorway', 'kind': 'motorway',
                 'points': [[0, 1], [12, 1]]},
                {'id': 'bus_axis', 'name': 'Bus Route', 'kind': 'main_road',
                 'points': [[6, 1], [6, 8]]},
            ],
            'buildings': [
                {'id': 'bus_stn', 'name': 'Bus Station', 'kind': 'transport',
                 'footprint': [5, 3, 3, 2]},
                {'id': 'housing', 'name': 'Housing Estate', 'kind': 'residential',
                 'footprint': [0, 5, 4, 3]},
            ],
            'landmarks': [
                {'id': 'site_a', 'label': 'Site A', 'icon': '🔆', 'grid': [2, 2], 'marker': 'A'},
                {'id': 'site_b', 'label': 'Site B', 'icon': '🔆', 'grid': [9, 3], 'marker': 'B'},
                {'id': 'site_c', 'label': 'Site C', 'icon': '🔆', 'grid': [5, 7], 'marker': 'C'},
            ],
        },
    },
]


def pick_fallback_ir(scenario_type: str, environment: str, location_name: str) -> dict:
    """Pick best-fit fallback. Prefer exact scenario+env match;
    else scenario match; else first. Returns a deep copy."""
    candidates = [ir for ir in FALLBACK_IRS if ir['scenarioType'] == scenario_type]
    if not candidates:
        return copy.deepcopy(FALLBACK_IRS[0])
    exact = [ir for ir in candidates if ir.get('environment') == environment]
    chosen = random.choice(exact) if exact else random.choice(candidates)
    out = copy.deepcopy(chosen)
    if location_name and isinstance(location_name, str):
        out['locationName'] = location_name
    return out


# ── Title helper ───────────────────────────────────────────────────────────


def build_map_title(ir: dict) -> str:
    """Friendly title for AIQuestion.title."""
    scenario_label = {
        'geographical_change': 'Before & After',
        'site_selection': 'Site Selection',
    }
    label = scenario_label.get(ir.get('scenarioType', ''), 'Map')
    location = (ir.get('locationName') or '').strip()
    if location:
        return f'地图 · {location[:60]} · {label}'
    return f'地图 · {label}'
