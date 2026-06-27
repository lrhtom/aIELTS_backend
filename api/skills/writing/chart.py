"""
Writing Chart Skills — 写作 Task 1 图表出题 / 评分 AI 技能
包含：地图(map)、流程图(flowchart)、常规图表(line/bar/pie/mixed)、图表评分
"""


def skill_writing_chart_map(
    scenario: str, environment: str, scene_name: str,
    scenario_desc: str, environment_desc: str,
    subject_area: str,
    view_model: str,
    story_seed: str = '',
    composition_hint: str = '',
    icon_whitelist: list[str] | None = None,
):
    """Task 1 地图出题 — Map IR v2 JSON mode.

    AI emits a structured IR with regions/roads/buildings/landmarks;
    backend deterministically renders to HTML that looks like a real
    IELTS Task 1 map. AI must NOT output HTML/SVG/CSS.

    `view_model` is 'before_after' for geographical_change scenarios
    and 'single' for site_selection scenarios.
    """
    icons = icon_whitelist or [
        '🏠', '🏘️', '🏢', '🏬', '🏭', '🏥', '🏫', '🏛️', '⛪', '🏤', '🏨', '🏪',
        '🏟️', '🎡', '🎢', '🎪', '🏰', '🗼', '🌲', '🌳', '🌴', '🌾', '🌸', '⛰️',
        '⛲', '🌉', '⚓', '🛳️', '🚂', '🚉', '🚌', '✈️', '🚗', '🅿️', '🚏',
        '🚧', '🏗️', '⛺', '🔆', '📍',
    ]
    icon_list = ' '.join(icons)
    story_block = f'\nSTORY SEED (use this as inspiration, do NOT copy verbatim):\n  {story_seed}\n' if story_seed else ''
    comp_block = f'\nCOMPOSITION HINT (shape the layout this way): {composition_hint}\n' if composition_hint else ''

    if view_model == 'single':
        view_section = '''VIEW MODEL: single
- Emit ONE shared map under the top-level `map` field.
- `title` is a single string (e.g. "Proposed Hospital Sites — Suburban Area").
- DO NOT emit mapA / mapB / changes.
- `map.landmarks` MUST contain exactly THREE landmarks with marker fields "A", "B", "C" — these are the three candidate sites.
- Each candidate landmark also needs a normal `label` (e.g. "Site A").
- The three candidate sites must be visually distinct: Manhattan distance ≥3 grid cells between any pair.
- Add reference buildings (school, housing, park, station…) so each candidate site has at least one nearby feature to compare against.
'''
        schema = '''{
  "irVersion": 2,
  "scenarioType": "site_selection",
  "viewModel": "single",
  "environment": "indoor" | "outdoor",
  "locationName": "<short>",
  "title": "<short title string>",
  "prompt": "<IELTS Task 1 prompt sentence>",
  "layoutSummary": "<2-4 line spatial summary>",
  "compositionHint": "site_plan" | "cross_road" | "river_bisected" | ...,
  "map": <MapBlock>
}'''
    else:
        view_section = '''VIEW MODEL: before_after
- This is the DOMINANT IELTS map question type. Comparison is the whole point —
  the candidate's writing must contrast mapA (before) and mapB (after).
- Emit TWO maps: `mapA` (before) and `mapB` (after).
- `title` is an object {"before": "...", "after": "..."} (often years like "1990" / "2020").
- `changes` MUST be 3-7 entries summarising what differs (added / removed / replaced / modified).
- Shared anchor features (river, main road, coastline) MUST appear in BOTH mapA AND mapB
  with the SAME id and SAME points/polygon — this preserves spatial reference.
  At least ONE road id MUST be shared between mapA and mapB.
- Make the changes **visually obvious and well-distributed**: replace large regions,
  swap building kinds (industrial→commercial, farmland→residential), add or remove
  named landmarks. Subtle relabeling alone is NOT enough — the maps must look
  clearly different at a glance.
- Each `changes[]` entry should describe ONE specific, visually verifiable difference.
- DO NOT emit a top-level `map` field.
'''
        schema = '''{
  "irVersion": 2,
  "scenarioType": "geographical_change",
  "viewModel": "before_after",
  "environment": "indoor" | "outdoor",
  "locationName": "<short>",
  "title": {"before": "<e.g. 1990>", "after": "<e.g. 2020>"},
  "prompt": "<IELTS Task 1 prompt sentence>",
  "layoutSummary": "<2-4 line spatial summary>",
  "compositionHint": "river_bisected" | "coastal" | "cross_road" | ...,
  "mapA": <MapBlock>,
  "mapB": <MapBlock>,
  "changes": [
    {"type": "added"|"removed"|"replaced"|"modified",
     "from": "<id>", "to": "<id>", "id": "<id>", "note": "<short>"}
  ]
}'''

    return f'''You are an IELTS Task 1 examiner and spatial planner.
You produce STRUCTURED JSON (Map IR v2) describing a map question. The backend
renders the IR into HTML — you must NOT output HTML, SVG, CSS, or Markdown.

GRID: 12 columns × 8 rows, origin top-left. All coordinates are INTEGER pairs.

TOP-LEVEL SCHEMA:
{schema}

MapBlock = {{
  "regions":   [{{"id": str, "name": str, "kind": str, "polygon": [[col,row], ...]}}],
  "roads":     [{{"id": str, "name": str, "kind": str, "points":  [[col,row], ...]}}],
  "buildings": [{{"id": str, "name": str, "kind": str, "footprint": [col,row,w,h]}}],
  "landmarks": [{{"id": str, "label": str, "icon": str, "grid": [col,row], "marker"?: "A"|"B"|"C"}}]
}}

ALLOWED `kind` VALUES (use ONLY these):
- region.kind:   park, forest, farmland, water, beach, residential_area,
                 commercial_area, industrial_area, wasteland, plaza
- road.kind:     main_road, motorway, side_road, path, river, stream,
                 coastline, railway, corridor, bridge
- building.kind: civic, residential, commercial, educational, industrial,
                 leisure, heritage, transport, medical
- landmark.icon must be exactly one of: {icon_list}

MANDATORY PROFILE FOR THIS REQUEST:
- scenarioType MUST be: {scenario}
- environment MUST be: {environment}
- locationName MUST be: {scene_name}
- Scenario meaning: {scenario_desc}
- Environment style: {environment_desc}
{story_block}{comp_block}
{view_section}

HARD CONSTRAINTS (validator will reject otherwise):
1) All grid coords are integers; col∈[0,12], row∈[0,8] (polygon/road points may touch the edge).
2) Building footprint = [col, row, w, h]; col+w ≤ 12, row+h ≤ 8; w ≥ 1; h ≥ 1.
3) Landmark grid = [col, row] with col∈[0,12), row∈[0,8).
4) Each MapBlock MUST contain ≥1 road; ≥3 total features (regions+buildings+landmarks combined).
5) Spread features across the canvas — at least 2 of the 4 quadrants must be covered
   (3 quadrants if the block has 5+ features). Do NOT cluster everything in one corner.
6) Building footprints SHOULD NOT overlap. Two buildings touching at an edge is fine.
7) Roads of the same kind running parallel must be ≥2 grid cells apart.
8) **Roads MUST NOT pass through the interior of any region polygon.** Regions are
   areas BOUNDED BY roads (or at the map edge), not split by them. If you want a
   forest on both sides of a road, emit TWO region entries (e.g. forest_w, forest_e)
   with the road as the boundary between them.
9) Use realistic English names: "Main Road", "Riverside Park", "Primary School", etc.
   Avoid generic "Building 1" / "Region 2".
10) For before_after, `mapB.roads` MUST include every road id that appears in `mapA.roads`
    at the same coordinates — these are spatial anchors.
11) DO NOT output HTML / SVG / CSS / Markdown / extra commentary. Output JSON only.

QUALITY GOALS:
- Make the spatial story coherent: anchors stay put; the periphery changes.
- Vary building footprints — mix tall (h≥3) and wide (w≥3) and small (1×1) blocks.
- Pick building `kind` semantically: hospital → medical; church → heritage;
  warehouse → industrial; cafés → commercial; school → educational.
- Use regions to convey "ground type" (forest, farmland, park, residential area).
- Use landmarks sparingly — usually 0-3 per map (bus stops, fountains, monuments).
- Keep names short (≤24 chars). English only.

Subject context (optional flavor for the story): {subject_area}
'''


def skill_writing_chart_flowchart(chart_instructions: str):
    """Task 1 流程图出题 — 系统指令"""
    return (
        "You are an IELTS Task 1 examiner generating a process diagram practice question.\n"
        "Return your response in EXACTLY this two-part format - no other text:\n\n"
        "IELTS_PROMPT: <one sentence IELTS question, e.g. 'The diagram below shows the process of...'>\n"
        "MERMAID_CODE:\n<valid mermaid flowchart code starting with 'flowchart TD' or 'flowchart LR'>\n\n"
        "Flowchart constraints:\n" + chart_instructions.strip()
    )


def skill_writing_chart_standard(chart_type: str, subject_area: str,
                                  code_requirement: str, chart_instructions: str):
    """Task 1 常规图表出题 — 系统指令"""
    return f'''You are an IELTS Task 1 examiner.
You need to provide a new chart practice question.
The requested chart type is: {chart_type}.
The subject area for the data must relate to: {subject_area}.

You MUST return a JSON with EXACTLY these two fields:
1. "prompt": The IELTS Task 1 question description (e.g., "The graph below shows the population of three cities...").
2. "code": {code_requirement}

Additional chart constraints:
{chart_instructions}
'''


def skill_writing_chart_evaluate(lang_instruction: str):
    """Task 1 图表评分 — 系统指令"""
    return f'''You are an expert IELTS examiner evaluator.
    Evaluate the user's Task 1 Writing based on the provided Prompt and the Reference Data Code (Python / Mermaid / Map JSON) which represents the exact figures, map layout, or process steps to describe.
Return a JSON with EXACTLY this structure:
{{
  "scores": {{
    "ta": <0-9 float for Task Achievement>,
    "cc": <0-9 float for Coherence & Cohesion>,
    "lr": <0-9 float for Lexical Resource>,
    "gra": <0-9 float for Grammatical Range & Accuracy>
  }},
  "overall": <0-9 float for overall band score>,
  "feedback": "Detailed feedback..."
}}
LANGUAGE INSTRUCTION: {lang_instruction}'''
