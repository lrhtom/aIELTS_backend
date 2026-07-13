import os
import uuid
import subprocess
import json
import re
import random
import hashlib
import html
import base64
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.core.ai_client import AIClient, refund_at
from api.core.rate_limit import check_rate_limit
from api.models import AIQuestion
from api.practice.ai_question_views import create_ai_question
from api.practice.map_renderer import (
    MAP_IR_VERSION,
    MAP_ICON_WHITELIST,
    build_map_title,
    pick_composition_hint,
    pick_fallback_ir,
    pick_story_seed,
    render_map_ir,
    validate_map_ir,
)


def _save_chart_question(
    user,
    chart_type: str,
    prompt_text: str,
    payload: dict,
    title_override: str | None = None,
    custom_title: str | None = None,
    custom_description: str | None = None,
) -> dict:
    """Persist a chart-generation payload to AIQuestion and inject aiQuestionId.

    For map questions the caller passes `title_override` derived from the IR
    so the AIBank list shows e.g. "地图 · A coastal town · Before & After"
    instead of the prompt's first line (which is generic across all maps).

    custom_title 非空时优先使用，覆盖 title_override 和 AI 生成的默认 title。
    custom_description 非空时写入 content.description。
    """
    try:
        title = (title_override or (prompt_text or 'Task 1').strip().splitlines()[0])[:200] or 'Task 1 图表'
        content = {k: v for k, v in payload.items() if k != 'atConsumed'} | {'writingKind': 'chart', 'chartType': chart_type}
        if custom_description:
            content['description'] = custom_description
        ai_question = create_ai_question(
            user=user,
            skill=AIQuestion.SKILL_WRITING,
            subtype=f'chart:{chart_type}',
            title=title,
            content=content,
            custom_title=custom_title,
        )
        payload['aiQuestionId'] = ai_question.id
    except Exception as save_err:
        print(f'[Chart] ⚠️ AIQuestion 入库失败: {save_err}', flush=True)
        payload['aiQuestionId'] = None
    return payload
from api.skills.writing.chart import (
    skill_writing_chart_map,
    skill_writing_chart_flowchart,
    skill_writing_chart_standard,
)

CHART_SUBJECT_AREAS = [
    "internet usage and social media trends",
    "employment rates across industries",
    "energy consumption and renewable sources",
    "education enrolment and graduation rates",
    "transport usage in urban areas",
    "household spending and consumer prices",
    "tourism arrivals and revenue",
    "population growth and demographic change",
    "healthcare expenditure and life expectancy",
    "crime rates and types of offences",
    "water usage and access to clean water",
    "carbon emissions by country or sector",
    "trade exports and imports between countries",
    "average wages across professions or genders",
    "smartphone and technology adoption",
    "agricultural land use and food production",
    "university subject enrolment trends",
    "housing prices in different cities",
    "obesity and dietary habits",
    "waste production and recycling rates",
]

MAP_SCENARIO_TYPES = ('geographical_change', 'site_selection')
# Real IELTS map questions are predominantly before/after comparison.
# Site-selection appears but is much rarer — bias the sampler accordingly.
MAP_SCENARIO_WEIGHTS = {'geographical_change': 80, 'site_selection': 20}
MAP_ENV_TYPES = ('indoor', 'outdoor')

MAP_LOCATION_CANDIDATES = [
    'A university campus',
    'A public library',
    'A local museum',
    'An art gallery',
    'A city park',
    'A leisure centre',
    'A sports club',
    'A community centre',
    'A coastal town',
    'A rural village',
    'An industrial estate',
    'A shopping mall',
    'A supermarket layout',
    'A local hospital',
    'An international airport',
    'A train station',
    'A bus terminal',
    'A city centre',
    'A residential area',
    'A tourist resort',
    'A hotel complex',
    'A holiday campsite',
    'A golf course',
    'A botanical garden',
    'A local zoo',
    'An exhibition centre',
    'A conference hall',
    'A theatre building',
    'A cinema complex',
    'A science park',
    'Student accommodation',
    'A factory layout',
    'A business park',
    'An office building',
    'A ferry port',
    'A sea harbour',
    'A road network',
    'A town square',
    'A nature reserve',
    'An archaeological site',
    'A tropical island',
    'A beach resort',
    'A secondary school',
    'A primary school',
    'A college campus',
    'A healthcare centre',
    'A fitness centre',
    'A swimming pool complex',
    'A public playground',
    'A town library',
    'A historical museum',
    'A modern art gallery',
    'A regional park',
    'A local sports centre',
    'A youth centre',
    'A mountain village',
    'A fishing village',
    'A commercial area',
    'A retail park',
    'A department store',
    'A private clinic',
    'A domestic airport',
    'A railway station',
    'A central bus station',
    'A downtown area',
    'A housing estate',
    'A winter resort',
    'A luxury hotel',
    'A summer camp',
    'A public golf club',
    'A city botanical garden',
    'A wildlife park',
    'A trade fair centre',
    'A civic centre',
    'A concert hall',
    'A movie theatre',
    'A technology park',
    'A university dormitory',
    'A manufacturing plant',
    'A corporate headquarters',
    'A cruise terminal',
    'A marina',
    'A highway intersection',
    'A market square',
    'A national park',
    'A historical site',
    'A deserted island',
    'A seaside resort',
    'A high school',
    'An elementary school',
    'A vocational college',
    'A medical clinic',
    'A local gym',
    'A community swimming pool',
    "A children's playground",
    'A central library',
    'A science museum',
    'A cultural centre',
    'A suburban area',
    'A riverside town',
]

MAP_INDOOR_KEYWORDS = (
    'campus', 'library', 'museum', 'gallery', 'centre', 'center', 'club', 'mall',
    'supermarket', 'hospital', 'station', 'terminal', 'hall', 'theatre', 'cinema',
    'office', 'building', 'dormitory', 'factory', 'plant', 'headquarters', 'clinic',
    'pool', 'playground', 'department store', 'accommodation', 'layout'
)

MAP_OUTDOOR_KEYWORDS = (
    'town', 'village', 'park', 'resort', 'campsite', 'golf', 'garden', 'zoo',
    'harbour', 'harbor', 'port', 'road', 'square', 'reserve', 'site', 'island',
    'beach', 'suburban', 'riverside', 'coastal', 'mountain', 'fishing', 'estate',
    'intersection', 'marina', 'downtown', 'area'
)

MAP_VIEWBOX_WIDTH = 1000.0
MAP_VIEWBOX_HEIGHT = 620.0

MAP_ICON_DEFINITIONS = [
    {'key': 'school', 'file': '01_school.png'},
    {'key': 'hospital', 'file': '02_hospital.png'},
    {'key': 'apartment', 'file': '03_apartment.png'},
    {'key': 'airport_terminal', 'file': '04_airport_terminal.png'},
    {'key': 'museum', 'file': '05_museum.png'},
    {'key': 'classical_building', 'file': '06_classical_building.png'},
    {'key': 'temple', 'file': '07_temple.png'},
    {'key': 'classroom', 'file': '08_classroom.png'},
    {'key': 'art_studio', 'file': '09_art_studio.png'},
    {'key': 'living_room', 'file': '10_living_room.png'},
    {'key': 'bedroom', 'file': '11_bedroom.png'},
    {'key': 'kitchen', 'file': '12_kitchen.png'},
    {'key': 'bathroom', 'file': '13_bathroom.png'},
    {'key': 'office', 'file': '14_office.png'},
    {'key': 'tree', 'file': '15_tree.png'},
    {'key': 'hedge', 'file': '16_hedge.png'},
    {'key': 'tulip', 'file': '17_tulip.png'},
    {'key': 'flower', 'file': '18_flower.png'},
    {'key': 'grass', 'file': '19_grass.png'},
    {'key': 'cactus', 'file': '20_cactus.png'},
    {'key': 'palm', 'file': '21_palm.png'},
    {'key': 'bus_stop', 'file': '22_bus_stop.png'},
    {'key': 'park_bench', 'file': '23_park_bench.png'},
    {'key': 'lamp_post', 'file': '24_lamp_post.png'},
    {'key': 'toilet', 'file': '25_toilet.png'},
    {'key': 'library', 'file': '26_library.png'},
    {'key': 'gym', 'file': '27_gym.png'},
    {'key': 'train_station', 'file': '28_train_station.png'},
]

MAP_ICON_FILE_BY_KEY = {item['key']: item['file'] for item in MAP_ICON_DEFINITIONS}

MAP_FALLBACK_PLACEMENTS_SITE = [
    {'iconKey': 'school', 'x': 90, 'y': 80, 'w': 86, 'h': 86, 'rotation': 0, 'label': 'Primary School'},
    {'iconKey': 'hospital', 'x': 420, 'y': 80, 'w': 84, 'h': 84, 'rotation': 0, 'label': 'City Hospital'},
    {'iconKey': 'library', 'x': 730, 'y': 86, 'w': 88, 'h': 88, 'rotation': 0, 'label': 'Public Library'},
    {'iconKey': 'park_bench', 'x': 190, 'y': 250, 'w': 82, 'h': 72, 'rotation': 0, 'label': 'Central Park'},
    {'iconKey': 'bus_stop', 'x': 60, 'y': 410, 'w': 92, 'h': 76, 'rotation': 0, 'label': 'Bus Stop'},
    {'iconKey': 'train_station', 'x': 790, 'y': 406, 'w': 96, 'h': 86, 'rotation': 0, 'label': 'Railway Station'},
    {'iconKey': 'gym', 'x': 586, 'y': 410, 'w': 90, 'h': 82, 'rotation': 0, 'label': 'Fitness Centre'},
    {'iconKey': 'tree', 'x': 326, 'y': 414, 'w': 82, 'h': 86, 'rotation': 0, 'label': 'Woodland Area'},
]

MAP_FALLBACK_PLACEMENTS_CHANGE = [
    {'iconKey': 'school', 'x': 100, 'y': 120, 'w': 82, 'h': 82, 'rotation': 0, 'label': 'School (Before)'},
    {'iconKey': 'apartment', 'x': 180, 'y': 360, 'w': 86, 'h': 84, 'rotation': 0, 'label': 'Old Apartments'},
    {'iconKey': 'bus_stop', 'x': 90, 'y': 452, 'w': 84, 'h': 70, 'rotation': 0, 'label': 'Old Bus Stop'},
    {'iconKey': 'tree', 'x': 322, 'y': 456, 'w': 78, 'h': 82, 'rotation': 0, 'label': 'Green Strip'},
    {'iconKey': 'hospital', 'x': 700, 'y': 126, 'w': 86, 'h': 86, 'rotation': 0, 'label': 'New Hospital'},
    {'iconKey': 'library', 'x': 552, 'y': 236, 'w': 86, 'h': 86, 'rotation': 0, 'label': 'New Library'},
    {'iconKey': 'museum', 'x': 760, 'y': 272, 'w': 84, 'h': 82, 'rotation': 0, 'label': 'Museum'},
    {'iconKey': 'train_station', 'x': 842, 'y': 420, 'w': 90, 'h': 82, 'rotation': 0, 'label': 'New Station'},
    {'iconKey': 'gym', 'x': 602, 'y': 420, 'w': 84, 'h': 78, 'rotation': 0, 'label': 'Fitness Centre'},
    {'iconKey': 'park_bench', 'x': 700, 'y': 506, 'w': 84, 'h': 68, 'rotation': 0, 'label': 'Riverside Park'},
]

MAP_MIN_ICON_COUNT = 8

MAP_ICON_GROUPS = {
    'school': 'major_building',
    'hospital': 'major_building',
    'apartment': 'major_building',
    'airport_terminal': 'transport_hub',
    'museum': 'major_building',
    'classical_building': 'major_building',
    'temple': 'major_building',
    'classroom': 'indoor_facility',
    'art_studio': 'indoor_facility',
    'living_room': 'indoor_facility',
    'bedroom': 'indoor_facility',
    'kitchen': 'indoor_facility',
    'bathroom': 'indoor_facility',
    'office': 'indoor_facility',
    'tree': 'nature',
    'hedge': 'nature',
    'tulip': 'nature',
    'flower': 'nature',
    'grass': 'nature',
    'cactus': 'nature',
    'palm': 'nature',
    'bus_stop': 'street_furniture',
    'park_bench': 'street_furniture',
    'lamp_post': 'street_furniture',
    'toilet': 'indoor_facility',
    'library': 'major_building',
    'gym': 'indoor_facility',
    'train_station': 'transport_hub',
}

# (min_w_ratio, max_w_ratio, min_h_ratio, max_h_ratio)
MAP_ICON_SIZE_PROFILES = {
    'major_building': (0.052, 0.132, 0.052, 0.145),
    'transport_hub': (0.058, 0.145, 0.052, 0.14),
    'indoor_facility': (0.046, 0.118, 0.04, 0.115),
    'nature': (0.036, 0.096, 0.04, 0.108),
    'street_furniture': (0.032, 0.088, 0.032, 0.086),
}

MAP_ICON_ROTATION_LIMITS = {
    'major_building': (-6.0, 6.0),
    'transport_hub': (-8.0, 8.0),
    'indoor_facility': (-10.0, 10.0),
    'nature': (-12.0, 12.0),
    'street_furniture': (-14.0, 14.0),
}

SCRIPT_TAG_RE = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', re.IGNORECASE | re.DOTALL)
EVENT_HANDLER_RE = re.compile(r'\son[a-zA-Z]+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)
JS_PROTOCOL_RE = re.compile(r'javascript\s*:', re.IGNORECASE)
VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _build_map_icon_assets() -> dict[str, str]:
    media_prefix = settings.MEDIA_URL.rstrip('/')
    return {
        item['key']: f"{media_prefix}/map_icons/items/{item['file']}"
        for item in MAP_ICON_DEFINITIONS
    }


def _build_map_icon_data_urls(icon_keys: set[str]) -> dict[str, str]:
    if not icon_keys:
        return {}

    result: dict[str, str] = {}
    for key in sorted(icon_keys):
        filename = MAP_ICON_FILE_BY_KEY.get(key)
        if not filename:
            continue
        file_path = os.path.join(settings.MEDIA_ROOT, 'map_icons', 'items', filename)
        if not os.path.isfile(file_path):
            continue

        try:
            with open(file_path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('ascii')
            result[key] = f'data:image/png;base64,{encoded}'
        except OSError:
            continue

    return result


def _infer_scene_environment(scene_name: str) -> str:
    text = (scene_name or '').lower()
    indoor_hits = sum(1 for token in MAP_INDOOR_KEYWORDS if token in text)
    outdoor_hits = sum(1 for token in MAP_OUTDOOR_KEYWORDS if token in text)
    if indoor_hits > outdoor_hits:
        return 'indoor'
    if outdoor_hits > indoor_hits:
        return 'outdoor'
    return random.choice(MAP_ENV_TYPES)


def _candidate_scenes_for_env(environment_type: str) -> list[str]:
    env = (environment_type or '').strip().lower()
    if env not in MAP_ENV_TYPES:
        return MAP_LOCATION_CANDIDATES[:]
    result = [scene for scene in MAP_LOCATION_CANDIDATES if _infer_scene_environment(scene) == env]
    return result if result else MAP_LOCATION_CANDIDATES[:]


def _scene_catalog_prompt_text(max_items: int = 80) -> str:
    candidates = MAP_LOCATION_CANDIDATES[:max_items]
    return '\n'.join(f"- {item}" for item in candidates)


def _pick_map_generation_profile() -> dict[str, str]:
    weights = [MAP_SCENARIO_WEIGHTS.get(s, 1) for s in MAP_SCENARIO_TYPES]
    question_type = random.choices(MAP_SCENARIO_TYPES, weights=weights, k=1)[0]
    environment_type = random.choice(MAP_ENV_TYPES)
    scene_pool = _candidate_scenes_for_env(environment_type)
    scene_name = random.choice(scene_pool) if scene_pool else random.choice(MAP_LOCATION_CANDIDATES)
    return {
        'questionType': question_type,
        'environmentType': environment_type,
        'sceneName': scene_name,
    }


# ── Raster (FLUX.2-pro) map generation ────────────────────────────────────
# The user's text-model of choice writes both the IELTS prompt (English) and
# a compact image-prompt for FLUX.2-pro. FLUX then renders a photorealistic
# / illustrative IELTS-style map. PNG bytes are saved under
#   <MEDIA_ROOT>/maps/<user_id>/<uuid>.png
# and the relative path is stored on AIQuestion.content_json['mapImagePath']
# so it can be unlinked on delete (see ai_question_views.ai_question_detail).

_RASTER_MAP_SYSTEM = """You are an IELTS Task 1 map-question setter.
Output ONLY a JSON object with exactly these keys:
{
  "prompt": "<the IELTS question prompt, English, one paragraph, 40-70 words>",
  "titleOverride": "<short display title, ≤80 chars>",
  "imagePrompt": "<English image-generation prompt for FLUX.2-pro, 60-140 words>"
}
Rules:
- The question MUST be a Task 1 map task with EITHER a before/after comparison OR a site-selection layout.
- prompt: standard IELTS phrasing, e.g. "The two maps below show ..." or "The map illustrates ...".
- titleOverride: like "地图 · A coastal town · Before & After" or "地图 · University campus · Site plan".
- imagePrompt: instruct a diffusion image model to render an IELTS Task 1 style map illustration.
    * MUST specify: top-down map view; clean flat vector illustration; labelled buildings; roads with white centre-line; north arrow; scale bar if useful; two side-by-side panels labelled 'Before' / 'After' for change scenarios, or one panel with candidate sites A/B/C for site-selection scenarios.
    * Keep style: minimal palette (light neutral background, sage/soft-blue accents), thin black outlines, bold sans-serif labels.
    * Absolutely no photorealistic satellite imagery, no aerial photography, no ornate 3D — this is a schematic classroom map.
    * Include real place names / building names from `prompt`.
"""


def _generate_raster_map(client, user) -> dict:
    """Runs text model → FLUX.2-pro pipeline. Returns AIQuestion content payload."""
    import os as _os
    import uuid as _uuid
    from django.conf import settings as _settings

    profile = _pick_map_generation_profile()
    user_hint = (
        f"scene: {profile['sceneName']}, environment: {profile['environmentType']}, "
        f"question type: {profile['questionType']}. "
        "Now emit the JSON."
    )
    messages = [
        {"role": "system", "content": _RASTER_MAP_SYSTEM},
        {"role": "user", "content": user_hint},
    ]
    prompt_payload, text_at_cost = client.generate(
        messages,
        expect_json=True,
        user_id=user.id,
        singleflight_scope='writing_map_raster_prompt',
    )
    if not isinstance(prompt_payload, dict):
        raise ValueError('文本模型返回结构异常')
    ielts_prompt = str(prompt_payload.get('prompt') or '').strip()
    image_prompt = str(prompt_payload.get('imagePrompt') or '').strip()
    title_override = str(prompt_payload.get('titleOverride') or '').strip() or None
    if not ielts_prompt or not image_prompt:
        raise ValueError('文本模型未返回完整的 prompt / imagePrompt')

    # FLUX.2-pro — always this model for raster mode (no user choice).
    from api.core.ai_client import AIClient as _AIClient
    image_client = _AIClient()
    png_bytes, image_at_cost = image_client.generate_image(
        prompt=image_prompt,
        size='1024x1024',
        user_id=user.id,
    )

    # Save under MEDIA_ROOT/maps/<user_id>/<uuid>.png
    rel_dir = _os.path.join('maps', str(user.id))
    abs_dir = _os.path.join(_settings.MEDIA_ROOT, rel_dir)
    _os.makedirs(abs_dir, exist_ok=True)
    file_id = _uuid.uuid4().hex
    rel_path = _os.path.join(rel_dir, f'{file_id}.png').replace('\\', '/')
    abs_path = _os.path.join(_settings.MEDIA_ROOT, rel_path)
    with open(abs_path, 'wb') as f:
        f.write(png_bytes)

    media_url = getattr(_settings, 'MEDIA_URL', '/media/')
    image_url = (media_url.rstrip('/') + '/' + rel_path).replace('//', '/')
    if not image_url.startswith('/'):
        image_url = '/' + image_url

    at_total = int(text_at_cost or 0) + int(image_at_cost or 0)
    return {
        'imageUrl': image_url,
        'mapImagePath': rel_path,          # relative to MEDIA_ROOT, used for delete-cleanup
        'mapImageMode': 'raster',
        'mapImageModel': 'FLUX.2-pro',
        'mermaidCode': None,
        'htmlContent': None,
        'prompt': ielts_prompt,
        'imagePrompt': image_prompt,
        'pythonCode': None,
        'atConsumed': at_total,
        'titleOverride': title_override,
    }


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _icon_size_bounds(icon_key: str, view_w: float, view_h: float) -> tuple[float, float, float, float]:
    group = MAP_ICON_GROUPS.get(icon_key, 'indoor_facility')
    w_min_r, w_max_r, h_min_r, h_max_r = MAP_ICON_SIZE_PROFILES.get(group, MAP_ICON_SIZE_PROFILES['indoor_facility'])
    min_w = _clamp(view_w * w_min_r, 24.0, max(24.0, view_w * 0.28))
    max_w = _clamp(view_w * w_max_r, min_w + 2.0, max(min_w + 2.0, view_w * 0.34))
    min_h = _clamp(view_h * h_min_r, 24.0, max(24.0, view_h * 0.28))
    max_h = _clamp(view_h * h_max_r, min_h + 2.0, max(min_h + 2.0, view_h * 0.34))
    return min_w, max_w, min_h, max_h


def _icon_rotation_bounds(icon_key: str) -> tuple[float, float]:
    group = MAP_ICON_GROUPS.get(icon_key, 'indoor_facility')
    return MAP_ICON_ROTATION_LIMITS.get(group, (-10.0, 10.0))


def _stable_sign(seed: str) -> float:
    marker = hashlib.sha1(seed.encode('utf-8')).hexdigest()
    return -1.0 if int(marker[-1], 16) % 2 else 1.0


def _rect_intersection_area(a: dict, b: dict) -> float:
    ax1, ay1 = a['x'], a['y']
    ax2, ay2 = ax1 + a['w'], ay1 + a['h']
    bx1, by1 = b['x'], b['y']
    bx2, by2 = bx1 + b['w'], by1 + b['h']
    overlap_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    overlap_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    return overlap_w * overlap_h


def _overlap_ratio(a: dict, b: dict) -> float:
    inter = _rect_intersection_area(a, b)
    if inter <= 0.0:
        return 0.0
    min_area = max(1.0, min(a['w'] * a['h'], b['w'] * b['h']))
    return inter / min_area


def _quadrant_coverage(placements: list[dict], view_w: float, view_h: float) -> set[int]:
    covered: set[int] = set()
    cx_mid = view_w / 2.0
    cy_mid = view_h / 2.0
    for item in placements:
        cx = item['x'] + item['w'] / 2.0
        cy = item['y'] + item['h'] / 2.0
        if cx < cx_mid and cy < cy_mid:
            covered.add(1)
        elif cx >= cx_mid and cy < cy_mid:
            covered.add(2)
        elif cx < cx_mid and cy >= cy_mid:
            covered.add(3)
        else:
            covered.add(4)
    return covered


def _count_overlap_conflicts(placements: list[dict], threshold: float) -> tuple[int, float]:
    conflicts = 0
    max_ratio = 0.0
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            ratio = _overlap_ratio(placements[i], placements[j])
            max_ratio = max(max_ratio, ratio)
            if ratio > threshold:
                conflicts += 1
    return conflicts, max_ratio


def _clamp_placement_in_bounds(item: dict, view_w: float, view_h: float) -> None:
    item['x'] = _clamp(item['x'], 0.0, max(0.0, view_w - item['w']))
    item['y'] = _clamp(item['y'], 0.0, max(0.0, view_h - item['h']))


def _nudge_pair_apart(a: dict, b: dict, view_w: float, view_h: float) -> None:
    acx = a['x'] + a['w'] / 2.0
    acy = a['y'] + a['h'] / 2.0
    bcx = b['x'] + b['w'] / 2.0
    bcy = b['y'] + b['h'] / 2.0

    dx = acx - bcx
    dy = acy - bcy
    if abs(dx) + abs(dy) < 0.001:
        dx = _stable_sign(f"{a['iconKey']}|{b['iconKey']}")
        dy = _stable_sign(f"{b['iconKey']}|{a['iconKey']}")

    dist = max(0.001, (dx * dx + dy * dy) ** 0.5)
    ux = dx / dist
    uy = dy / dist
    push = max(6.0, min(a['w'], a['h'], b['w'], b['h']) * 0.16)

    a['x'] += ux * push * 0.5
    a['y'] += uy * push * 0.5
    b['x'] -= ux * push * 0.5
    b['y'] -= uy * push * 0.5

    _clamp_placement_in_bounds(a, view_w, view_h)
    _clamp_placement_in_bounds(b, view_w, view_h)


def _placement_penalty(candidate: dict, others: list[dict], view_w: float, view_h: float) -> float:
    overlap_penalty = 0.0
    for other in others:
        overlap_penalty += (_overlap_ratio(candidate, other) ** 2) * 20.0

    edge_margin_x = view_w * 0.025
    edge_margin_y = view_h * 0.025
    edge_penalty = 0.0
    if candidate['x'] < edge_margin_x or (candidate['x'] + candidate['w']) > (view_w - edge_margin_x):
        edge_penalty += 1.0
    if candidate['y'] < edge_margin_y or (candidate['y'] + candidate['h']) > (view_h - edge_margin_y):
        edge_penalty += 1.0

    return overlap_penalty + edge_penalty


def _improve_map_icon_placements(placements: list[dict], view_w: float, view_h: float) -> list[dict]:
    improved = [dict(item) for item in placements]
    if len(improved) < 2:
        return improved

    for item in improved:
        _clamp_placement_in_bounds(item, view_w, view_h)

    # Phase 1: iterative separation for pairwise overlaps.
    for _ in range(6):
        moved = False
        for i in range(len(improved)):
            for j in range(i + 1, len(improved)):
                if _overlap_ratio(improved[i], improved[j]) > 0.18:
                    _nudge_pair_apart(improved[i], improved[j], view_w, view_h)
                    moved = True
        if not moved:
            break

    # Phase 2: coverage balancing (avoid all icons clustered in one side).
    covered = _quadrant_coverage(improved, view_w, view_h)
    if len(covered) < 3 and len(improved) >= 4:
        anchors = {
            1: (0.18, 0.2),
            2: (0.72, 0.2),
            3: (0.2, 0.7),
            4: (0.72, 0.72),
        }
        movable_indices = sorted(range(len(improved)), key=lambda idx: improved[idx]['w'] * improved[idx]['h'])
        used: set[int] = set()
        for quadrant in [1, 2, 3, 4]:
            if quadrant in covered:
                continue
            anchor = anchors[quadrant]
            for idx in movable_indices:
                if idx in used:
                    continue
                item = improved[idx]
                item['x'] = anchor[0] * view_w - item['w'] / 2.0
                item['y'] = anchor[1] * view_h - item['h'] / 2.0
                _clamp_placement_in_bounds(item, view_w, view_h)
                used.add(idx)
                break

    # Phase 3: local search for severely overlapping nodes.
    offsets = [
        (0.0, 0.0),
        (0.14, 0.0), (-0.14, 0.0), (0.0, 0.14), (0.0, -0.14),
        (0.12, 0.12), (-0.12, 0.12), (0.12, -0.12), (-0.12, -0.12),
        (0.22, 0.0), (-0.22, 0.0), (0.0, 0.22), (0.0, -0.22),
    ]
    for idx, item in enumerate(improved):
        peers = [p for p_i, p in enumerate(improved) if p_i != idx]
        current_penalty = _placement_penalty(item, peers, view_w, view_h)
        if current_penalty < 2.5:
            continue

        best_x = item['x']
        best_y = item['y']
        best_penalty = current_penalty
        base_x = item['x']
        base_y = item['y']
        for ox, oy in offsets:
            candidate = dict(item)
            candidate['x'] = base_x + ox * view_w
            candidate['y'] = base_y + oy * view_h
            _clamp_placement_in_bounds(candidate, view_w, view_h)
            score = _placement_penalty(candidate, peers, view_w, view_h)
            if score < best_penalty:
                best_penalty = score
                best_x = candidate['x']
                best_y = candidate['y']

        item['x'] = best_x
        item['y'] = best_y

    return improved


def _evaluate_map_placement_quality(placements: list[dict], view_w: float, view_h: float) -> dict:
    conflicts, max_overlap = _count_overlap_conflicts(placements, threshold=0.18)
    severe_conflicts, _ = _count_overlap_conflicts(placements, threshold=0.32)
    quadrant_coverage = len(_quadrant_coverage(placements, view_w, view_h))

    edge_margin_x = view_w * 0.018
    edge_margin_y = view_h * 0.018
    edge_touch_count = 0
    icon_counts: dict[str, int] = {}
    for item in placements:
        icon_counts[item['iconKey']] = icon_counts.get(item['iconKey'], 0) + 1
        if (
            item['x'] < edge_margin_x or
            item['y'] < edge_margin_y or
            (item['x'] + item['w']) > (view_w - edge_margin_x) or
            (item['y'] + item['h']) > (view_h - edge_margin_y)
        ):
            edge_touch_count += 1

    repeated_icon_penalty = sum(max(0, count - 2) for count in icon_counts.values())

    score = 100.0
    score -= conflicts * 8.0
    score -= severe_conflicts * 18.0
    score -= max(0, 3 - quadrant_coverage) * 14.0
    score -= edge_touch_count * 2.2
    score -= repeated_icon_penalty * 3.0
    score = round(_clamp(score, 0.0, 100.0), 2)

    return {
        'score': score,
        'count': len(placements),
        'overlapConflicts': conflicts,
        'severeConflicts': severe_conflicts,
        'maxOverlapRatio': round(max_overlap, 4),
        'quadrantCoverage': quadrant_coverage,
        'edgeTouchCount': edge_touch_count,
        'fallbackApplied': False,
    }


def _sanitize_svg(svg_text: str) -> str:
    cleaned = (svg_text or '').strip()
    if not cleaned:
        return ''
    cleaned = SCRIPT_TAG_RE.sub('', cleaned)
    cleaned = EVENT_HANDLER_RE.sub('', cleaned)
    cleaned = JS_PROTOCOL_RE.sub('', cleaned)
    if '<svg' not in cleaned.lower():
        cleaned = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(MAP_VIEWBOX_WIDTH)} {int(MAP_VIEWBOX_HEIGHT)}">'
            + cleaned +
            '</svg>'
        )
    return cleaned


def _extract_svg_viewport(svg_text: str) -> tuple[float, float]:
    match = VIEWBOX_RE.search(svg_text or '')
    if not match:
        return MAP_VIEWBOX_WIDTH, MAP_VIEWBOX_HEIGHT
    parts = re.split(r'\s+', match.group(1).strip())
    if len(parts) != 4:
        return MAP_VIEWBOX_WIDTH, MAP_VIEWBOX_HEIGHT
    width = _safe_float(parts[2], MAP_VIEWBOX_WIDTH)
    height = _safe_float(parts[3], MAP_VIEWBOX_HEIGHT)
    if width <= 10 or height <= 10:
        return MAP_VIEWBOX_WIDTH, MAP_VIEWBOX_HEIGHT
    return width, height


def _evaluate_map_svg_structure(svg_text: str, question_type: str) -> dict:
    text = (svg_text or '')
    lower = text.lower()

    rect_count = len(re.findall(r'<\s*rect\b', lower))
    line_count = len(re.findall(r'<\s*line\b', lower))
    polyline_count = len(re.findall(r'<\s*polyline\b', lower))
    path_count = len(re.findall(r'<\s*path\b', lower))
    text_node_count = len(re.findall(r'<\s*text\b', lower))

    road_terms = len(re.findall(r'road|street|avenue|lane|corridor|path|route|highway|drive|boulevard|junction|intersection', lower))
    area_terms = len(re.findall(r'district|zone|area|park|residential|commercial|industrial|medical|education|leisure|civic|wing|hall|sector|site', lower))
    candidate_terms = len(re.findall(r'candidate\s*site|site\s*[abc]', lower))
    before_after_terms = len(re.findall(r'before|after|previous|current|existing|redevelop', lower))

    road_shape_count = line_count + polyline_count + path_count

    score = 100.0
    if rect_count < 4:
        score -= (4 - rect_count) * 8.0
    if road_shape_count < 3:
        score -= (3 - road_shape_count) * 12.0
    if road_terms < 2:
        score -= (2 - road_terms) * 10.0
    if area_terms < 3:
        score -= (3 - area_terms) * 8.0
    if text_node_count < 8:
        score -= (8 - text_node_count) * 4.0

    q_type = (question_type or '').strip().lower()
    if q_type == 'site_selection' and candidate_terms < 2:
        score -= (2 - candidate_terms) * 16.0
    if q_type == 'geographical_change' and before_after_terms < 2:
        score -= (2 - before_after_terms) * 14.0

    score = round(_clamp(score, 0.0, 100.0), 2)
    return {
        'score': score,
        'rectCount': rect_count,
        'roadShapeCount': road_shape_count,
        'roadTerms': road_terms,
        'areaTerms': area_terms,
        'textNodeCount': text_node_count,
        'candidateTerms': candidate_terms,
        'beforeAfterTerms': before_after_terms,
    }


def _normalize_map_icon_placements(raw_placements, allowed_keys: set[str], view_w: float, view_h: float) -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(raw_placements, list):
        return normalized

    for item in raw_placements:
        if not isinstance(item, dict):
            continue
        icon_key = str(item.get('iconKey', '')).strip()
        if icon_key not in allowed_keys:
            continue

        min_w, max_w, min_h, max_h = _icon_size_bounds(icon_key, view_w, view_h)
        rot_low, rot_high = _icon_rotation_bounds(icon_key)

        w = _clamp(_safe_float(item.get('w'), 82.0), min_w, max_w)
        h = _clamp(_safe_float(item.get('h'), 82.0), min_h, max_h)
        x = _clamp(_safe_float(item.get('x'), 0.0), 0.0, max(0.0, view_w - w))
        y = _clamp(_safe_float(item.get('y'), 0.0), 0.0, max(0.0, view_h - h))
        rotation = _clamp(_safe_float(item.get('rotation'), 0.0), rot_low, rot_high)

        label = str(item.get('label', '') or '').strip()
        label = re.sub(r'\s+', ' ', label)[:64]

        normalized.append({
            'iconKey': icon_key,
            'x': round(x, 2),
            'y': round(y, 2),
            'w': round(w, 2),
            'h': round(h, 2),
            'rotation': round(rotation, 2),
            'label': label,
        })
        if len(normalized) >= 24:
            break

    return normalized


def _scaled_fallback_placements(view_w: float, view_h: float, question_type: str = 'site_selection') -> list[dict]:
    sx = view_w / MAP_VIEWBOX_WIDTH
    sy = view_h / MAP_VIEWBOX_HEIGHT
    scaled: list[dict] = []
    q_type = (question_type or '').strip().lower()
    template = MAP_FALLBACK_PLACEMENTS_CHANGE if q_type == 'geographical_change' else MAP_FALLBACK_PLACEMENTS_SITE
    for item in template:
        scaled.append({
            'iconKey': item['iconKey'],
            'x': round(float(item['x']) * sx, 2),
            'y': round(float(item['y']) * sy, 2),
            'w': round(float(item['w']) * sx, 2),
            'h': round(float(item['h']) * sy, 2),
            'rotation': item.get('rotation', 0),
            'label': item.get('label', ''),
        })
    return scaled


def _fallback_map_svg(
    question_type: str = 'site_selection',
    environment_type: str = 'outdoor',
    scene_name: str = 'A city centre',
) -> str:
    q_type = (question_type or '').strip().lower()
    env = (environment_type or '').strip().lower()
    if q_type not in MAP_SCENARIO_TYPES:
        q_type = 'site_selection'
    if env not in MAP_ENV_TYPES:
        env = 'outdoor'

    safe_scene = html.escape(scene_name or 'A city centre')

    if q_type == 'geographical_change':
        if env == 'indoor':
            before_1, before_2, before_3 = 'Old Study Wing', 'Old Service Wing', 'Old Transit Hall'
            after_1, after_2, after_3 = 'New Learning Hub', 'New Service Core', 'Renovated Access Hall'
            road_main, road_cross = 'Main Corridor', 'Cross Corridor'
        else:
            before_1, before_2, before_3 = 'Old Residential Zone', 'Old Commercial Block', 'Open Yard'
            after_1, after_2, after_3 = 'New Civic Zone', 'Medical District', 'Riverside Park'
            road_main, road_cross = 'Old Main Road', 'New Ring Road'

        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 620">'
            '<rect width="1000" height="620" fill="#f8fafc"/>'
            f'<text x="500" y="36" text-anchor="middle" font-size="24" fill="#0f172a" font-family="Arial, sans-serif">{safe_scene}: Before and After Redevelopment</text>'
            '<rect x="40" y="70" width="430" height="510" rx="14" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.6"/>'
            '<rect x="530" y="70" width="430" height="510" rx="14" fill="#eef2ff" stroke="#94a3b8" stroke-width="1.6"/>'
            '<line x1="500" y1="64" x2="500" y2="584" stroke="#64748b" stroke-width="2" stroke-dasharray="8 7"/>'
            '<text x="255" y="96" text-anchor="middle" font-size="20" fill="#334155" font-family="Arial, sans-serif">Before</text>'
            '<text x="745" y="96" text-anchor="middle" font-size="20" fill="#334155" font-family="Arial, sans-serif">After</text>'
            '<rect x="70" y="130" width="170" height="130" rx="10" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.2"/>'
            '<rect x="260" y="130" width="180" height="130" rx="10" fill="#e5e7eb" stroke="#94a3b8" stroke-width="1.2"/>'
            '<rect x="80" y="390" width="230" height="150" rx="10" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.2"/>'
            f'<text x="155" y="194" text-anchor="middle" font-size="16" fill="#334155" font-family="Arial, sans-serif">{html.escape(before_1)}</text>'
            f'<text x="350" y="194" text-anchor="middle" font-size="16" fill="#334155" font-family="Arial, sans-serif">{html.escape(before_2)}</text>'
            f'<text x="195" y="468" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(before_3)}</text>'
            '<rect x="560" y="130" width="170" height="130" rx="10" fill="#dbeafe" stroke="#60a5fa" stroke-width="1.2"/>'
            '<rect x="750" y="130" width="180" height="130" rx="10" fill="#d1fae5" stroke="#34d399" stroke-width="1.2"/>'
            '<rect x="570" y="390" width="340" height="150" rx="10" fill="#dcfce7" stroke="#4ade80" stroke-width="1.2"/>'
            f'<text x="645" y="194" text-anchor="middle" font-size="16" fill="#334155" font-family="Arial, sans-serif">{html.escape(after_1)}</text>'
            f'<text x="840" y="194" text-anchor="middle" font-size="16" fill="#334155" font-family="Arial, sans-serif">{html.escape(after_2)}</text>'
            f'<text x="740" y="468" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(after_3)}</text>'
            '<line x1="58" y1="326" x2="460" y2="326" stroke="#94a3b8" stroke-width="14" stroke-linecap="round"/>'
            '<line x1="540" y1="326" x2="942" y2="326" stroke="#64748b" stroke-width="18" stroke-linecap="round"/>'
            '<line x1="255" y1="102" x2="255" y2="564" stroke="#94a3b8" stroke-width="10" stroke-linecap="round"/>'
            '<line x1="725" y1="102" x2="725" y2="564" stroke="#64748b" stroke-width="10" stroke-linecap="round"/>'
            f'<text x="255" y="312" text-anchor="middle" font-size="14" fill="#475569" font-family="Arial, sans-serif">{html.escape(road_main)}</text>'
            f'<text x="725" y="312" text-anchor="middle" font-size="14" fill="#334155" font-family="Arial, sans-serif">{html.escape(road_cross)}</text>'
            '</svg>'
        )

    if env == 'indoor':
        zone_1, zone_2, zone_3, zone_4 = 'Entrance Hall', 'Service Zone', 'Study Zone', 'Quiet Wing'
        road_1, road_2, road_3 = 'Main Corridor', 'North-South Corridor', 'East Link'
    else:
        zone_1, zone_2, zone_3, zone_4 = 'Residential Area', 'Commercial Area', 'Civic District', 'Green Park'
        road_1, road_2, road_3 = 'Central Avenue', 'North-South Road', 'Riverside Drive'

    compass = ''
    if env == 'outdoor':
        compass = (
            '<text x="86" y="52" font-size="18" fill="#0f172a" font-family="Arial, sans-serif">N</text>'
            '<line x1="92" y1="56" x2="92" y2="84" stroke="#0f172a" stroke-width="3"/>'
            '<polygon points="92,40 86,56 98,56" fill="#0f172a"/>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 620">'
        '<rect width="1000" height="620" fill="#f8fafc"/>'
        f'<text x="500" y="36" text-anchor="middle" font-size="24" fill="#0f172a" font-family="Arial, sans-serif">{safe_scene}: Site Selection</text>'
        '<rect x="52" y="74" width="896" height="500" rx="16" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5"/>'
        '<rect x="78" y="112" width="320" height="180" rx="12" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.1"/>'
        '<rect x="620" y="112" width="286" height="180" rx="12" fill="#dbeafe" stroke="#60a5fa" stroke-width="1.1"/>'
        '<rect x="86" y="384" width="268" height="168" rx="12" fill="#e5e7eb" stroke="#94a3b8" stroke-width="1.1"/>'
        '<rect x="536" y="378" width="370" height="176" rx="12" fill="#dcfce7" stroke="#4ade80" stroke-width="1.1"/>'
        f'<text x="238" y="198" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(zone_1)}</text>'
        f'<text x="762" y="198" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(zone_2)}</text>'
        f'<text x="220" y="472" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(zone_3)}</text>'
        f'<text x="720" y="470" text-anchor="middle" font-size="18" fill="#334155" font-family="Arial, sans-serif">{html.escape(zone_4)}</text>'
        '<line x1="60" y1="330" x2="940" y2="330" stroke="#64748b" stroke-width="16" stroke-linecap="round"/>'
        '<line x1="470" y1="96" x2="470" y2="560" stroke="#64748b" stroke-width="12" stroke-linecap="round"/>'
        '<line x1="130" y1="560" x2="470" y2="440" stroke="#94a3b8" stroke-width="8" stroke-linecap="round"/>'
        f'<text x="500" y="318" text-anchor="middle" font-size="15" fill="#1f2937" font-family="Arial, sans-serif">{html.escape(road_1)}</text>'
        f'<text x="486" y="98" text-anchor="start" font-size="14" fill="#1f2937" font-family="Arial, sans-serif">{html.escape(road_2)}</text>'
        f'<text x="260" y="532" text-anchor="middle" font-size="13" fill="#475569" font-family="Arial, sans-serif">{html.escape(road_3)}</text>'
        '<circle cx="340" cy="318" r="20" fill="#f97316" opacity="0.88"/>'
        '<circle cx="520" cy="276" r="20" fill="#0ea5e9" opacity="0.88"/>'
        '<circle cx="710" cy="350" r="20" fill="#10b981" opacity="0.88"/>'
        '<text x="340" y="323" text-anchor="middle" font-size="16" fill="#ffffff" font-family="Arial, sans-serif" font-weight="700">A</text>'
        '<text x="520" y="281" text-anchor="middle" font-size="16" fill="#ffffff" font-family="Arial, sans-serif" font-weight="700">B</text>'
        '<text x="710" y="355" text-anchor="middle" font-size="16" fill="#ffffff" font-family="Arial, sans-serif" font-weight="700">C</text>'
        '<text x="340" y="350" text-anchor="middle" font-size="13" fill="#334155" font-family="Arial, sans-serif">Candidate Site A</text>'
        '<text x="520" y="308" text-anchor="middle" font-size="13" fill="#334155" font-family="Arial, sans-serif">Candidate Site B</text>'
        '<text x="710" y="382" text-anchor="middle" font-size="13" fill="#334155" font-family="Arial, sans-serif">Candidate Site C</text>'
        f'{compass}'
        '</svg>'
    )


def _generate_map_ir(
    client: AIClient,
    user,
    subject_area: str,
    map_profile: dict[str, str],
    max_retries: int = 1,
) -> tuple[dict, float, bool]:
    """Ask GPT-5.4 (or any provider) for a Map IR; validate; retry once with
    error feedback; if still invalid, fall back to a pre-authored IR.

    Returns (ir, total_at_cost, used_fallback).
    """
    scenario = (map_profile.get('questionType') or 'site_selection').strip().lower()
    environment = (map_profile.get('environmentType') or 'outdoor').strip().lower()
    scene_name = map_profile.get('sceneName') or 'A city centre'

    if scenario not in MAP_SCENARIO_TYPES:
        scenario = 'site_selection'
    if environment not in MAP_ENV_TYPES:
        environment = 'outdoor'

    scenario_desc = 'geographical-change map (before vs after)' if scenario == 'geographical_change' else 'site-selection map (candidate locations)'
    environment_desc = 'indoor floor-plan style' if environment == 'indoor' else 'outdoor town/area style'
    story_seed = pick_story_seed(scenario)
    composition_hint = pick_composition_hint(scenario)
    icon_whitelist = sorted(MAP_ICON_WHITELIST)
    # site_selection → single big map with A/B/C markers
    # geographical_change → before/after twin maps
    view_model = 'single' if scenario == 'site_selection' else 'before_after'

    system_prompt = skill_writing_chart_map(
        scenario=scenario, environment=environment, scene_name=scene_name,
        scenario_desc=scenario_desc, environment_desc=environment_desc,
        subject_area=subject_area,
        view_model=view_model,
        story_seed=story_seed,
        composition_hint=composition_hint,
        icon_whitelist=icon_whitelist,
    )

    total_at = 0.0
    last_errors: list[str] = []
    last_ir: dict | None = None

    for attempt in range(max_retries + 1):
        messages: list[dict] = [
            {'role': 'system', 'content': system_prompt},
        ]
        if attempt == 0 or not last_errors:
            messages.append({'role': 'user', 'content': 'Generate a complete map IR now.'})
        else:
            err_lines = '\n'.join(f'- {e}' for e in last_errors[:8])
            messages.append({
                'role': 'user',
                'content': (
                    'Your previous IR failed validation with the following issues:\n'
                    f'{err_lines}\n'
                    'Emit a corrected IR (JSON only) that fixes ALL of the above.'
                ),
            })

        try:
            ir, at_cost = client.generate(
                messages,
                expect_json=True,
                user_id=user.id,
                # Only the first attempt deduplicates via singleflight;
                # retries should always reach the model.
                singleflight_scope='writing_chart_generate' if attempt == 0 else None,
            )
            total_at += float(at_cost or 0)
        except Exception as e:
            print(f'[Map IR] attempt {attempt} call failed: {e}', flush=True)
            break

        if not isinstance(ir, dict):
            last_errors = ['AI did not return a JSON object']
            last_ir = None
            continue

        ok, errors = validate_map_ir(ir)
        if ok:
            return ir, total_at, False

        last_errors = errors
        last_ir = ir
        print(f'[Map IR] attempt {attempt} validation failed: {errors[:3]}', flush=True)

    # All AI attempts exhausted → fallback IR (no extra AT cost)
    fallback_ir = pick_fallback_ir(scenario, environment, scene_name)
    print(f'[Map IR] using fallback IR for scenario={scenario} env={environment}', flush=True)
    return fallback_ir, total_at, True


# Kept for any external callers; thin wrapper around the new IR pipeline.
# Returns raw IR dict + cost; HTML rendering happens at the view layer.
def _build_map_prompt_payload(
    client: AIClient,
    user,
    subject_area: str,
    map_profile: dict[str, str],
) -> tuple[dict, float]:
    ir, at_cost, _ = _generate_map_ir(client, user, subject_area, map_profile)
    return ir, at_cost


def _strip_code_fences(text: str) -> str:
    cleaned = (text or '').strip()
    if cleaned.startswith('```'):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        cleaned = '\n'.join(lines).strip()
    return cleaned


def _looks_like_python(code: str) -> bool:
    lower = code.lower()
    markers = [
        'import matplotlib',
        'def ',
        'plt.',
        'ax.',
        'if __name__ == "__main__":',
        'if __name__ == \"__main__\":',
        'sys.argv',
    ]
    return any(m in lower for m in markers)


def _is_valid_mermaid_flowchart(code: str) -> bool:
    stripped = (code or '').lstrip().lower()
    return stripped.startswith('flowchart ') or stripped.startswith('graph ')


def _build_fallback_flowchart(prompt_text: str) -> str:
    # Keep fallback deterministic and parser-safe.
    title = (prompt_text or 'Process Diagram').strip()
    title = re.sub(r'[^a-zA-Z0-9\s\-:,\.\(\)]', '', title)[:90] or 'Process Diagram'
    return (
        'flowchart TD\n'
        f'  T["{title}"]\n'
        '  A["Step 1: Start"] --> B["Step 2: Main Process"]\n'
        '  B --> C["Step 3: Quality Check"]\n'
        '  C --> D["Step 4: Output"]\n'
        '  D --> E["Step 5: End"]\n'
    )


def _build_singleflight_scope(scope_prefix: str, payload) -> str:
    try:
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_text = str(payload)
    digest = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:16]
    return f"{scope_prefix}:{digest}"


# ── 真题题干骨架 (剑桥 4-21 二十年不变的五件套, 见 雅思资料/蒸馏/writing_skill.md) ──
_TASK1_SCAFFOLD_HEAD = 'You should spend about 20 minutes on this task.'
_TASK1_SCAFFOLD_TAIL = (
    'Summarise the information by selecting and reporting the main features, '
    'and make comparisons where relevant.\n\nWrite at least 150 words.'
)


def _wrap_task1_prompt(core: str) -> str:
    """把 AI 生成的核心描述句包进真题固定骨架; 先剥掉 AI 可能自带的骨架句避免重复."""
    text = (core or '').strip()
    text = re.sub(r'(?i)you should spend about 20 minutes on this task\.?', '', text)
    text = re.sub(
        r'(?i)summari[sz]e the information by selecting and reporting the main features'
        r'(,? and make comparisons where relevant)?\.?',
        '', text)
    text = re.sub(r'(?i)write at least 150 words\.?', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        return core or ''
    return f'{_TASK1_SCAFFOLD_HEAD}\n\n{text}\n\n{_TASK1_SCAFFOLD_TAIL}'


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_chart(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'chart_generate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        chart_type = request.data.get('type', 'line')
        custom_title = (request.data.get('customName') or request.data.get('customTitle') or '').strip() or None
        custom_description = (request.data.get('customDescription') or request.data.get('description') or '').strip() or None
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        if chart_type == 'flowchart':
            # 真题体裁 (剑桥 4-21 蒸馏): 流程图是描述性的工艺/自然/生物流程,
            # 线性或环形, 6-9 步; 绝无判断菱形和 Yes/No 条件边 —— 描述条件逻辑
            # 不是雅思考核的语言技能。见 雅思资料/蒸馏/writing_skill.md。
            chart_instructions = """
   - The user requested an IELTS Task 1 PROCESS DIAGRAM (flow-chart).
   - You MUST NOT use matplotlib or python.
   - You MUST generate valid `mermaid.js` flowchart code.
   - AUTHENTIC IELTS GENRE (hard constraints):
       * Depict a real-world manufacturing, natural, biological or recycling PROCESS
         (e.g. how fabric is made from bamboo, the life cycle of a salmon, brick
         production, how rainwater is reused, chocolate production).
       * The process is DESCRIPTIVE — it always happens the same way. There must be
         NO decisions, NO conditions, NO Yes/No edges, NO diamond nodes. Real IELTS
         process diagrams never contain conditional logic.
       * Structure: a LINEAR chain (Stage 1 → ... → Stage N), or a natural CYCLE
         (the last stage loops back to the first, e.g. the water cycle). One simple
         fork or merge for a by-product/input is allowed (e.g. waste returned for
         recycling), but never a decision.
       * 6-9 stages total. Each stage label is a short noun phrase or gerund
         ("Harvesting", "Soaking in solution", "Spinning into yarn").
   - Node shapes: A["label"] rectangles for stages; optionally S(["Raw material"]) and
     E(["Finished product"]) pills for start/end. Do NOT use diamond {} nodes or circles.
   - Direction: flowchart LR for manufacturing chains, flowchart TD for tall processes;
     cycles loop back with a plain edge (no label).
   - CRITICAL SYNTAX RULES (violations cause parse errors):
       * Every node label MUST be in double quotes: A["Label text here"]
       * Never use unquoted labels containing spaces or : ( ) { }
       * Plain edges only: A --> B  (edge labels are not needed in this genre)
   - Example A (linear manufacturing):
     flowchart LR
       S(["Raw bamboo"]) --> A["Harvesting"]
       A --> B["Crushing into pulp"]
       B --> C["Soaking in solution"]
       C --> D["Spinning into yarn"]
       D --> E["Weaving"]
       E --> F(["Finished fabric"])
   - Example B (natural cycle):
     flowchart TD
       A["Evaporation from oceans"] --> B["Condensation into clouds"]
       B --> C["Precipitation"]
       C --> D["Runoff into rivers"]
       D --> E["Collection in oceans"]
       E --> A"""
        elif chart_type == 'map':
            chart_instructions = """
     - MAP mode is handled by the dedicated SVG + icon placement branch below.
     - This instruction block is intentionally unused for map generation."""
        elif chart_type == 'mixed':
            chart_instructions = """
   - The code MUST generate a MIXED chart (e.g., a combination of two different chart types like a bar chart and a line graph, or two side-by-side subplots such as a pie chart and a bar chart) using matplotlib.
   - The two charts should display related but different datasets about the same topic.
   - The code must generate its own random but plausible data arrays inline for the charts.
   - Use ONLY standard chart functions for data visualization."""
        elif chart_type == 'table':
            # 真题高频原生题型: 数据表格 (常为多表组合, 如 C20 NYC 人口 3 表)。
            # 用 matplotlib ax.table 渲染成图片, 复用现有 image 管线。
            chart_instructions = """
   - The user requested a TABLE (authentic high-frequency IELTS Task 1 stimulus).
   - Render ONE OR TWO clean data tables as an image using matplotlib's `ax.table` with axes hidden (`ax.axis('off')`).
   - Structure like real Cambridge tables: 4-7 data rows x 3-5 columns, comparing categories
     across 2-3 time points OR across 3-6 countries/groups (e.g. "proportion of households
     in poverty by family type", "city population 1800/1900/2000").
   - Include a clear title (plt.title or fig.suptitle), column headers, and a units note
     (%, thousands, millions) either in headers or a caption.
   - Numbers must be plausible and internally consistent (a total row should roughly equal
     the sum of its parts); mix magnitudes like real data (79,216 vs 8,009,185).
   - Style: white background, header row shaded light grey (use cellColours or set_facecolor),
     readable font (table.set_fontsize(11); table.scale(1, 1.6)), thin cell edges.
   - If TWO tables, use two stacked subplots sharing one topic (like Cambridge multi-table sets)."""
        else:
            chart_instructions = """
   - The code must generate its own random but plausible data arrays inline for the chart.
   - Use ONLY standard chart functions (plot, bar, pie, etc.) for data visualization."""

        if chart_type == 'flowchart':
            code_requirement = '''Mermaid.js flowchart code ONLY.
       - Start with `flowchart TD` or `flowchart LR`.
       - Do NOT return Python, matplotlib, pseudocode, or markdown explanation.
       - Descriptive linear or cyclical process only — NO decision diamonds, NO Yes/No edges (authentic IELTS genre).
       - Node labels must be parser-safe: wrap multi-word labels in double quotes inside brackets, e.g. A["Raw Material Input"].
       - Plain edges only: A --> B.
       - Return pure Mermaid text in the `code` field.'''
        else:
            code_requirement = '''Python code using Matplotlib.
       - The code MUST save the chart to the image path passed as `sys.argv[1]`.
       - Do NOT use `plt.show()`.
       - Use ONLY `matplotlib`, `numpy`, or standard libraries. NO dangerous OS imports.
       - It is crutial that the image is sized correctly and looks professional.
       - Example file structure:
         import sys
         import matplotlib.pyplot as plt
         import numpy as np
         ...
         plt.savefig(sys.argv[1])
         plt.close()'''

        # 鈹€鈹€ FLOWCHART: plain-text mode avoids JSON-escaping issues with Mermaid { } " 鈹€鈹€
        if chart_type == 'flowchart':
            from api.skills.custom_prompt import custom_prompt_block
            fc_system = skill_writing_chart_flowchart(chart_instructions) + custom_prompt_block(request.data.get('customPrompt'))
            fc_messages = [
                {"role": "system", "content": fc_system},
                {"role": "user", "content": "Generate an IELTS Task 1 process diagram practice question now."},
            ]
            try:
                raw_text, at_cost = client.generate(
                    fc_messages,
                    expect_json=False,
                    user_id=user.id,
                    singleflight_scope='writing_chart_generate',
                )
            except Exception as e:
                return Response({'error': f'AI generation failed: {e}'}, status=500)

            # Parse the delimiter-separated response
            prompt_text = ''
            mermaid_code = ''
            prompt_match = re.search(r'IELTS_PROMPT:\s*(.+?)(?=MERMAID_CODE:)', raw_text, re.DOTALL | re.IGNORECASE)
            code_match   = re.search(r'MERMAID_CODE:\s*(.+)',                    raw_text, re.DOTALL | re.IGNORECASE)
            if prompt_match:
                prompt_text  = prompt_match.group(1).strip()
            if code_match:
                mermaid_code = _strip_code_fences(code_match.group(1).strip())

            # Fallback: scan the raw text for any flowchart block
            if not _is_valid_mermaid_flowchart(mermaid_code):
                fc_find = re.search(r'(flowchart\s+(?:TD|LR|TB|BT|RL)\b.+)', raw_text, re.DOTALL | re.IGNORECASE)
                mermaid_code = fc_find.group(1).strip() if fc_find else _build_fallback_flowchart(prompt_text)

            if _looks_like_python(mermaid_code):
                mermaid_code = _build_fallback_flowchart(prompt_text)

            if not prompt_text:
                prompt_text = 'The diagram below shows the process illustrated in the flowchart.'
            prompt_text = _wrap_task1_prompt(prompt_text)

            fc_payload = {
                'imageUrl':    None,
                'mermaidCode': mermaid_code,
                'prompt':      prompt_text,
                'pythonCode':  mermaid_code,
                'atConsumed':  at_cost,
            }
            return Response(_save_chart_question(user, chart_type, prompt_text, fc_payload, custom_title=custom_title, custom_description=custom_description))

        # ── MAP: always FLUX.2-pro raster (SVG/IR pipeline retired 2026-07). ──
        # The `image_mode` request param is ignored; every map generation now
        # goes through text-model → FLUX.2-pro PNG.
        if chart_type == 'map':
            try:
                payload = _generate_raster_map(client, user)
                payload['prompt'] = _wrap_task1_prompt(payload.get('prompt') or '')
                return Response(_save_chart_question(
                    user, chart_type, payload['prompt'], payload,
                    title_override=payload.get('titleOverride'),
                    custom_title=custom_title,
                    custom_description=custom_description,
                ))
            except Exception as e:
                import traceback
                print(f'[Map Raster] [ERR] {traceback.format_exc()}', flush=True)
                return Response({'error': f'AI 地图生成失败: {e}'}, status=500)

        # 鈹€鈹€ OTHER CHART TYPES: JSON mode + Matplotlib sandbox ┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢┢
        subject_area = random.choice(CHART_SUBJECT_AREAS)
        from api.skills.custom_prompt import custom_prompt_block
        system_prompt = skill_writing_chart_standard(
            chart_type, subject_area, code_requirement, chart_instructions
        ) + custom_prompt_block(request.data.get('customPrompt'))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the chart prompt and code for the requested chart type."}
        ]

        try:
            response_data, at_cost = client.generate(
                messages,
                expect_json=True,
                user_id=user.id,
                singleflight_scope='writing_chart_generate',
            )
            prompt_text = _wrap_task1_prompt(response_data.get('prompt', ''))
            python_code = response_data.get('code', '')
            if not python_code:
                raise ValueError("No code generated")
        except Exception as e:
            return Response({'error': f'Failed to parse AI response: {e}.'}, status=500)

        # --- SANDBOX EXECUTION FOR REGULAR CHARTS/MAPS ---
        # Save and run python code
        # We save media files in the static media directory
        charts_dir = os.path.join(settings.MEDIA_ROOT, 'charts')
        os.makedirs(charts_dir, exist_ok=True)
        
        file_id = str(uuid.uuid4())
        py_path = os.path.join(charts_dir, f'{file_id}.py')
        img_path = os.path.join(charts_dir, f'{file_id}.png')
        
        with open(py_path, 'w', encoding='utf-8') as f:
            f.write(python_code)
            
        # Execute the sandbox script
        try:
            result = subprocess.run(['python', py_path, img_path], capture_output=True, text=True, timeout=12)
            if result.returncode != 0:
                refund_at(user.id, at_cost)
                return Response({'error': '抱歉，AI 图表代码执行失败，已退还 AT 币。请稍后重试。', 'atRefunded': at_cost}, status=500)
        except subprocess.TimeoutExpired:
            refund_at(user.id, at_cost)
            return Response({'error': '抱歉，AI 图表生成超时，已退还 AT 币。请稍后重试。', 'atRefunded': at_cost}, status=500)

        # Read the generated image into base64
        import base64
        try:
            with open(img_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                img_url = f"data:image/png;base64,{encoded_string}"
        except OSError as oe:
            refund_at(user.id, at_cost)
            return Response({'error': f'抱歉，图表读取失败，已退还 AT 币。({oe})', 'atRefunded': at_cost}, status=500)
            
        # Delete temporary files to save server storage
        try:
            os.remove(py_path)
            os.remove(img_path)
        except OSError:
            pass # ignore cleanup errors
        
        std_payload = {
            'imageUrl': img_url,
            'mermaidCode': None,
            'prompt': prompt_text,
            'pythonCode': python_code,
            'atConsumed': at_cost,
        }
        return Response(_save_chart_question(user, chart_type, prompt_text, std_payload, custom_title=custom_title, custom_description=custom_description))
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)

