import os
import sys

from api.ai_client import AIClient
import json

def test():
    client = AIClient()
    chart_type = 'flowchart'
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
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Generate the chart prompt and python matplotlib code."}
    ]
    print("Calling AI for Flowchart...")
    try:
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.first()
        response_data, _ = client.generate(messages, expect_json=True, user_id=user.id if user else None)
        print("Prompt:", response_data.get('prompt'))
        print("Code exists:", bool(response_data.get('code')))
        
        # let's try to run the code
        import tempfile
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_path = os.path.join(tmpdir, 'test.py')
            img_path = os.path.join(tmpdir, 'test.png')
            with open(py_path, 'w', encoding='utf-8') as f:
                f.write(response_data.get('code'))
                
            print("Running subprocess...")
            result = subprocess.run(['python', py_path, img_path], capture_output=True, text=True, timeout=12)
            if result.returncode != 0:
                print("Execution failed!")
                print("Stderr:", result.stderr)
            else:
                print("Execution succeeded! Image base64 sample length:", os.path.getsize(img_path))
                
    except Exception as e:
        import traceback
        print("Error calling AI or parsing JSON:", e)
        traceback.print_exc()

if __name__ == '__main__':
    test()
