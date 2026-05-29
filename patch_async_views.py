import os

def patch_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        print(f"Skipping {filepath} due to UnicodeDecodeError")
        return

    original_content = content
    lines = content.split('\n')
    has_changes = False

    # 1. Patch @api_view async endpoints
    for i in range(len(lines)):
        if lines[i].lstrip().startswith('async def ') or ' async def ' in lines[i]:
            # Look backwards to see if it's decorated with @api_view
            is_api_view = False
            for j in range(i-1, max(-1, i-10), -1):
                if '@adrf_sync' in lines[j] or '@async_to_sync' in lines[j]:
                    is_api_view = False
                    break
                if '@api_view' in lines[j]:
                    is_api_view = True
                    break
                if 'def ' in lines[j] or 'class ' in lines[j]:
                    break
            
            if is_api_view:
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines.insert(i, indent + '@adrf_sync')
                has_changes = True

    # 2. Patch APIView methods
    for i in range(len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith('async def get(self') or stripped.startswith('async def post(self') or stripped.startswith('async def put(self') or stripped.startswith('async def delete(self'):
            # Check if @adrf_sync is above it
            if i > 0 and '@adrf_sync' not in lines[i-1] and '@async_to_sync' not in lines[i-1]:
                indent = lines[i][:len(lines[i]) - len(stripped)]
                lines.insert(i, indent + '@adrf_sync')
                has_changes = True

    if has_changes:
        content = '\n'.join(lines)
        if 'from api.utils import adrf_sync' not in content:
            # Find the best place to insert the import
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i
            
            lines.insert(insert_idx + 1, 'from api.utils import adrf_sync')
            content = '\n'.join(lines)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Patched: {filepath}')

directories = [
    'e:/code/web/work/aIELTS/backend/api/practice',
    'e:/code/web/work/aIELTS/backend/api/extra',
    'e:/code/web/work/aIELTS/backend/api/vocab',
    'e:/code/web/work/aIELTS/backend/api/auth'
]

for dirpath in directories:
    for root, dirs, files in os.walk(dirpath):
        for f in files:
            if f.endswith('.py'):
                patch_file(os.path.join(root, f))
