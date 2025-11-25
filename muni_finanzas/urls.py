# ============================================
# ARCHIVO 1: muni_finanzas/urls.py
# ============================================
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login / logout del sistema interno
    path(
        "ingresar/",
        LoginView.as_view(
            template_name="finanzas/login.html",
        ),
        name="login",
    ),
    path(
        "salir/",
        LogoutView.as_view(next_page="login"),
        name="logout",
    ),

    # Rutas de agenda (DEBE IR ANTES de finanzas)
    path("agenda/", include("agenda.urls", namespace="agenda")),

    # Rutas principales de la aplicación de finanzas
    path("", include("finanzas.urls", namespace="finanzas")),
]

# Archivos de media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)