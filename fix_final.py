import re
import os

path = 'app/main.py'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Patrón para capturar TemplateResponse multilínea o simple
    # Capturamos el nombre de la plantilla y el diccionario de contexto
    # Usamos DOTALL para que el punto (.) coincida con saltos de línea
    pattern = r'templates\.TemplateResponse\(\s*([\"\'].*?[\"\']),\s*(\{\s*[\"\']request[\"\']:\s*request,?\s*(.*?)\})\s*\)'
    
    def fix_match(m):
        name = m.group(1)
        extra_context = m.group(3).strip()
        if extra_context:
            # Si hay más cosas en el contexto, las ponemos en context=
            if extra_context.startswith(','): extra_context = extra_context[1:].strip()
            return f'templates.TemplateResponse(request=request, name={name}, context={{{extra_context}}})'
        else:
            # Si solo estaba el request, usamos el formato simple
            return f'templates.TemplateResponse(request=request, name={name})'

    new_content = re.sub(pattern, fix_match, content, flags=re.DOTALL)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Corrección técnica de TemplateResponse completada con éxito.")
