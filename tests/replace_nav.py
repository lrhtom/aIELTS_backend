import os
import re

frontend_dir = r'e:/code/web/work/aIELTS/frontend/src/pages'

nav_regex = re.compile(r'<nav className="navbar">.*?</nav>', re.DOTALL)

for filename in os.listdir(frontend_dir):
    if filename.endswith('.tsx') and filename != 'App.tsx':
        filepath = os.path.join(frontend_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if '<nav className="navbar">' in content:
            print(f'Replacing in {filename}')
            # Replace nav with AppNavbar
            new_content = nav_regex.sub('<AppNavbar />', content)
            
            # Add import statement if not exists
            if 'import AppNavbar' not in new_content:
                # Insert after the last import
                new_content = 'import AppNavbar from \'../components/AppNavbar\';\n' + new_content
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
