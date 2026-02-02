from django.template.loader import get_template
from django.http import HttpResponse
from django.conf import settings
import os

# Intentamos importar weasyprint. 
# Si falla (porque se está instalando), no romperá el sistema hasta que lo uses.
try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = None

def render_to_pdf(template_src, context_dict={}):
    """
    Función genérica para renderizar cualquier template HTML como PDF.
    Devuelve un objeto HttpResponse con el PDF.
    """
    if HTML is None:
        return HttpResponse("Error: La librería WeasyPrint no está instalada o configurada.", status=500)

    template = get_template(template_src)
    html_string = template.render(context_dict)
    
    # Base URL para que encuentre las imágenes estáticas (Logo, CSS)
    # Esto es clave para que las imágenes salgan en el PDF
    base_url = request.build_absolute_uri() if 'request' in context_dict else settings.STATIC_URL

    html = HTML(string=html_string, base_url=str(settings.BASE_DIR))
    
    # CSS para forzar tamaño A4 y márgenes
    css_string = """
        @page {
            size: A4;
            margin: 1cm;
            @bottom-right {
                content: "Página " counter(page) " de " counter(pages);
                font-family: sans-serif;
                font-size: 9pt;
            }
        }
    """
    css = CSS(string=css_string)

    result = html.write_pdf(stylesheets=[css])

    response = HttpResponse(result, content_type='application/pdf')
    # Si quieres que se descargue directo, descomenta la línea de abajo:
    # response['Content-Disposition'] = 'attachment; filename="documento.pdf"'
    
    # Si quieres que se abra en el navegador (preview):
    response['Content-Disposition'] = 'inline; filename="documento.pdf"'
    
    return response