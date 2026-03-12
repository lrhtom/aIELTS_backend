import os
import uuid
import subprocess
import json
import re
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.ai_client import AIClient


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
        chart_type = request.data.get('type', 'line')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        if chart_type == 'flowchart':
            chart_instructions = """
   - The user requested a FLOWCHART (Process Diagram).
   - You MUST NOT use matplotlib or python.
   - You MUST generate valid `mermaid.js` flowchart code.
   - Ensure the flowchart has clearly labeled nodes and directional arrows.
   - Example snippet:
     flowchart TD
       A[Start] --> B(Process 1)
       B --> C{Decision}
       C -- Yes --> D[End 1]"""
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
       - Keep node labels simple and parser-safe (avoid unescaped quotes/brackets).
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

        system_prompt = f'''You are an IELTS Task 1 examiner.
You need to provide a new chart practice question.
The requested chart type is: {chart_type}.

You MUST return a JSON with EXACTLY these two fields:
1. "prompt": The IELTS Task 1 question description (e.g., "The graph below shows the population of three cities...", or "The diagram below shows the process of...").
    2. "code": {code_requirement}

    Additional chart constraints:
    {chart_instructions}
'''
        
        # Call the AI
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the chart prompt and code (or mermaid syntax) for the requested chart type."}
        ]
        
        try:
            # AIClient parses JSON automatically if expect_json=True
            response_data, at_cost = client.generate(messages, expect_json=True, user_id=user.id)
            prompt_text = response_data.get('prompt', '')
            python_code = response_data.get('code', '')
            if not python_code:
                raise ValueError("No code generated")
        except Exception as e:
            return Response({'error': f'Failed to parse AI response: {e}.'}, status=500)

        # If Flowchart, BYPASS the Python Matplotlib Sandbox
        if chart_type == 'flowchart':
            clean_code = _strip_code_fences(python_code)
            # AI occasionally returns matplotlib despite instructions; enforce Mermaid fallback.
            if _looks_like_python(clean_code) or not _is_valid_mermaid_flowchart(clean_code):
                clean_code = _build_fallback_flowchart(prompt_text)

            return Response({
                'imageUrl': None,
                'mermaidCode': clean_code,
                'prompt': prompt_text,
                'pythonCode': clean_code, # keep naming for eval compatibility
                'atConsumed': at_cost
            })

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
                return Response({'error': f'Matplotlib execution failed: {result.stderr}'}, status=500)
        except subprocess.TimeoutExpired:
            return Response({'error': 'Matplotlib execution timed out.'}, status=500)
            
        # Read the generated image into base64
        import base64
        try:
            with open(img_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                img_url = f"data:image/png;base64,{encoded_string}"
        except OSError as oe:
            return Response({'error': f'Failed to read generated chart: {oe}'}, status=500)
            
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
        prompt_text = request.data.get('prompt', '')
        python_code = request.data.get('pythonCode', '')
        user_answer = request.data.get('userAnswer', '')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)
        system_prompt = '''You are an expert IELTS examiner evaluator.
Evaluate the user's Task 1 Writing based on the provided Prompt and the Reference Data Code which represents the exact figures or process steps to describe.
Return a JSON with EXACTLY this structure:
{
  "scores": {
    "ta": <0-9 float for Task Achievement>,
    "cc": <0-9 float for Coherence & Cohesion>,
    "lr": <0-9 float for Lexical Resource>,
    "gra": <0-9 float for Grammatical Range & Accuracy>
  },
  "overall": <0-9 float for overall band score>,
  "feedback": "Detailed feedback..."
}'''
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
