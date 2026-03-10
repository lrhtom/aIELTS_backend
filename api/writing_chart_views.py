import os
import uuid
import subprocess
import json
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.ai_client import AIClient

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
   - You MUST use `matplotlib.patches` (e.g., FancyBboxPatch, Circle, Arrow, FancyArrowPatch) and `plt.text` to draw the diagram.
   - The flowchart should illustrate a process (e.g., manufacturing process, natural cycle).
   - IMPORTANT: Turn off axes using `plt.axis('off')`.
   - Arrange the nodes logically (top-to-bottom or left-to-right).
   - Draw connectings arrows between the nodes.
   - Example snippet:
     import matplotlib.patches as patches
     fig, ax = plt.subplots(figsize=(10, 6))
     ax.axis('off')
     # Add patches and text
     ..."""
        else:
            chart_instructions = """
   - The code must generate its own random but plausible data arrays inline for the chart.
   - Use ONLY standard chart functions (plot, bar, pie, etc.) for data visualization."""

        system_prompt = f'''You are an IELTS Task 1 examiner.
You need to provide a new chart practice question.
The requested chart type is: {chart_type}.

You MUST return a JSON with EXACTLY these two fields:
1. "prompt": The IELTS Task 1 question description (e.g., "The graph below shows the population of three cities...", or "The diagram below shows the process of...").
2. "code": Python code using Matplotlib that generates the chart. {chart_instructions}
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
     plt.close()
'''
        
        # Call the AI
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the chart prompt and python matplotlib code."}
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
Evaluate the user's Task 1 Writing based on the provided Prompt and the Python data code which represents the exact figures.
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
        user_msg = f"Prompt:\n{prompt_text}\n\nData (Python):\n{python_code}\n\nUser Answer:\n{user_answer}"
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
