import os
import sys
import django

sys.path.append(r'e:\code\web\work\aIELTS\backend')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
django.setup()

from api.ai_client import AIClient
import json

def test():
    client = AIClient()
    chart_type = 'line'
    system_prompt = f'''You are an IELTS Task 1 examiner.
    ... [same prompt here] ...
'''
    # We will just redefine the test script prompt directly for simplicity
    system_prompt = f'''You are an IELTS Task 1 examiner.
You need to provide a new chart practice question.
The requested chart type is: {chart_type}.

You MUST return a JSON with EXACTLY these two fields:
1. "prompt": The IELTS Task 1 question description (e.g., "The graph below shows the population of three cities...").
2. "code": Python code using Matplotlib that generates the chart.
   - The code must generate its own random but plausible data arrays inline for the chart.
   - The code MUST save the chart to the image path passed as `sys.argv[1]`.
   - Do NOT use `plt.show()`.
   - Use ONLY `matplotlib`, `numpy`, or standard libraries. NO dangerous OS imports.
   - It is extremely important that the image is sized correctly (e.g., `plt.figure(figsize=(8, 5))`) and looks professional.
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
    print("Calling AI...")
    try:
        response_data, _ = client.generate(messages, expect_json=True)
        print("Prompt:", response_data.get('prompt'))
        print("Code exists:", bool(response_data.get('code')))
        data = response_data
    except Exception as e:
        print("Error calling AI or parsing JSON:", e)
        return
        
        # let's try to run the code
        import tempfile
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_path = os.path.join(tmpdir, 'test.py')
            img_path = os.path.join(tmpdir, 'test.png')
            with open(py_path, 'w', encoding='utf-8') as f:
                f.write(data.get('code'))
                
            print("Running subprocess...")
            result = subprocess.run(['python', py_path, img_path], capture_output=True, text=True, timeout=12)
            if result.returncode != 0:
                print("Execution failed!")
                print("Stderr:", result.stderr)
            else:
                print("Execution succeeded! Image size:", os.path.getsize(img_path))
                
    except Exception as e:
        print("Parse error:", e)

if __name__ == '__main__':
    test()
