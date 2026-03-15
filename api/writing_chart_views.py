import os
import uuid
import subprocess
import json
import re
import random
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.ai_client import AIClient, refund_at
from api.rate_limit import check_rate_limit

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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_chart(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'chart_generate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        chart_type = request.data.get('type', 'line')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        if chart_type == 'flowchart':
            chart_instructions = """
   - The user requested a FLOWCHART (Process Diagram).
   - You MUST NOT use matplotlib or python.
   - You MUST generate valid `mermaid.js` flowchart code.
   - VARIETY IS REQUIRED — randomly pick one of these structural patterns each time:
       A) LINEAR WITH BRANCH: a main chain that splits into 2-3 parallel paths, then reconverges (one-to-many then many-to-one).
       B) LOOP/CYCLE: a decision diamond that loops back to an earlier step when the condition is not met (e.g. quality-check retry, feedback loop, resubmission cycle).
       C) PARALLEL MERGE: two or more independent starting sub-processes that both feed into a shared downstream step.
       D) MIXED: combine a loop AND a branch in the same diagram (most complex, use for longer processes).
   - Use VARIED node shapes for semantic clarity:
       A["label"]    — standard rectangular process step
       A(("label"))  — circle, for key events
       A{"label"}    — diamond, for decisions only
       A(["label"])  — pill/stadium, for start or end
   - For one-to-many branching use: A --> B & C & D
   - For many-to-one merging  use: B & C --> D
   - For a loop-back          use: D -->|No| B
   - Direction: prefer flowchart TD for tall processes, flowchart LR for wide/parallel ones.
   - Aim for 8-14 nodes total; label edges where it adds meaning (Yes/No, Approved/Rejected, etc.).
   - CRITICAL SYNTAX RULES (violations cause parse errors):
       * Every node label MUST be in double quotes: A["Label text here"]
       * Never use unquoted labels containing spaces or : ( ) { }
       * Edge labels use pipe syntax: A -->|Yes| B
       * No spaces around & in parallel syntax: A --> B & C
   - Example A (loop pattern):
     flowchart TD
       S(["Start"]) --> A["Submit Application"]
       A --> B{"Complete?"}
       B -->|No| C["Return for Revision"]
       C --> A
       B -->|Yes| D["Review Panel"]
       D --> E{"Approved?"}
       E -->|No| F["Notify Applicant"]
       F --> A
       E -->|Yes| G["Issue Certificate"]
       G --> Z(["End"])
   - Example B (branch and merge pattern):
     flowchart LR
       S(["Raw Material"]) --> P["Pre-treatment"]
       P --> Q & R & T
       Q["Line A Cutting"] --> M["Assembly"]
       R["Line B Moulding"] --> M
       T["Line C Printing"] --> M
       M --> I{"Quality Check"}
       I -->|Pass| D(["Dispatch"])
       I -->|Fail| X["Rework"] --> M"""
        elif chart_type == 'map':
            chart_instructions = """
   - The user requested a MAP (Geographic/Floor Plan layout).
   - You MUST use `matplotlib.patches` (Rectangle, Circle, Polygon) and `plt.text` to draw a stylized map layout (e.g., a town, an island, or a museum plan).
   - It is highly recommended to generate TWO subplots side-by-side to show changes over time (e.g., '1990' vs 'Now').
   - IMPORTANT: Turn off axes using `ax.axis('off')` for all subplots.
   - Add a simple compass (N, S, E, W) indicator using `plt.text` or arrows.
   - DO NOT use standard statistical plots (bar, line).
   - Example snippet:
     import matplotlib.patches as patches
     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
     ax1.axis('off'); ax2.axis('off')
     ax1.add_patch(patches.Rectangle((0, 0), 10, 10, fill=False))
     ax1.text(5, 5, 'Supermarket')
     ..."""
        else:
            chart_instructions = """
   - The code must generate its own random but plausible data arrays inline for the chart.
   - Use ONLY standard chart functions (plot, bar, pie, etc.) for data visualization."""

        if chart_type == 'flowchart':
            code_requirement = '''Mermaid.js flowchart code ONLY.
       - Start with `flowchart TD` or `flowchart LR`.
       - Do NOT return Python, matplotlib, pseudocode, or markdown explanation.
       - Use the structural variety described in the chart constraints (branch, loop, parallel, or mixed).
       - Node labels must be parser-safe: wrap multi-word labels in double quotes inside brackets, e.g. A["Raw Material Input"].
       - Edge labels use the pipe syntax: A -->|Yes| B  or  A -- label --> B.
       - For parallel edges use: A --> B & C  (no extra spaces around &).
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

        # ── FLOWCHART: plain-text mode avoids JSON-escaping issues with Mermaid { } " ──
        if chart_type == 'flowchart':
            fc_system = (
                "You are an IELTS Task 1 examiner generating a process diagram practice question.\n"
                "Return your response in EXACTLY this two-part format — no other text:\n\n"
                "IELTS_PROMPT: <one sentence IELTS question, e.g. 'The diagram below shows the process of...'>\n"
                "MERMAID_CODE:\n<valid mermaid flowchart code starting with 'flowchart TD' or 'flowchart LR'>\n\n"
                "Flowchart constraints:\n" + chart_instructions.strip()
            )
            fc_messages = [
                {"role": "system", "content": fc_system},
                {"role": "user", "content": "Generate an IELTS Task 1 process diagram practice question now."},
            ]
            try:
                raw_text, at_cost = client.generate(fc_messages, expect_json=False, user_id=user.id)
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
                prompt_text = ('The diagram below shows the process illustrated in the flowchart. '
                               'Summarise the information by selecting and reporting the main features.')

            return Response({
                'imageUrl':    None,
                'mermaidCode': mermaid_code,
                'prompt':      prompt_text,
                'pythonCode':  mermaid_code,
                'atConsumed':  at_cost,
            })

        # ── OTHER CHART TYPES: JSON mode + Matplotlib sandbox ──────────────────────
        subject_area = random.choice(CHART_SUBJECT_AREAS)
        system_prompt = f'''You are an IELTS Task 1 examiner.
You need to provide a new chart practice question.
The requested chart type is: {chart_type}.
The subject area for the data must relate to: {subject_area}.

You MUST return a JSON with EXACTLY these two fields:
1. "prompt": The IELTS Task 1 question description (e.g., "The graph below shows the population of three cities...").
2. "code": {code_requirement}

Additional chart constraints:
{chart_instructions}
'''
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the chart prompt and code for the requested chart type."}
        ]

        try:
            response_data, at_cost = client.generate(messages, expect_json=True, user_id=user.id)
            prompt_text = response_data.get('prompt', '')
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
        
        return Response({
            'imageUrl': img_url,
            'mermaidCode': None,
            'prompt': prompt_text,
            'pythonCode': python_code,
            'atConsumed': at_cost
        })
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_chart(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'chart_evaluate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        prompt_text = request.data.get('prompt', '')
        python_code = request.data.get('pythonCode', '')
        user_answer = request.data.get('userAnswer', '')
        ui_lang = request.data.get('lang', 'en')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        lang_instruction = (
            'Write the "feedback" field in Simplified Chinese (中文).'
            if ui_lang == 'zh'
            else 'Write the "feedback" field in English.'
        )

        system_prompt = f'''You are an expert IELTS examiner evaluator.
Evaluate the user's Task 1 Writing based on the provided Prompt and the Reference Data Code which represents the exact figures or process steps to describe.
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
        user_msg = f"Prompt:\n{prompt_text}\n\nReference Data (Python/Mermaid):\n{python_code}\n\nUser Answer:\n{user_answer}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        
        try:
            response_data, at_cost = client.generate(messages, expect_json=True, user_id=user.id)
            response_data['atConsumed'] = at_cost
            return Response(response_data)
        except Exception as e:
            return Response({'error': f'Failed to evaluate or parse: {e}'}, status=500)
            
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)
