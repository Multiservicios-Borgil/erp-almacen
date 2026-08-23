import re
import os

path = 'app/main.py'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Caso con contexto complejo
    content = re.sub(r'templates\.TemplateResponse\(([\"\'].*?[\"\']),\s*(\{.*?request.*?\})\)', 
                     r'templates.TemplateResponse(request=request, name=\1, context=\2)', content)
    
    # 2. Caso con solo request
    content = re.sub(r'templates\.TemplateResponse\(([\"\'].*?[\"\']),\s*\{\s*[\"\']request[\"\']:\s*request\s*\}\)', 
                     r'templates.TemplateResponse(request=request, name=\1)', content)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Corrección de TemplateResponse completada.")
