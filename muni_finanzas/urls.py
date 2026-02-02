# ============================================
# ARCHIVO: muni_finanzas/urls.py
# ============================================
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login del sistema
    path(
        "ingresar/",
        LoginView.as_view(
            template_name="finanzas/login.html",
            redirect_authenticated_user=True,  # 👈 si ya está logueado, lo manda al HOME
        ),
        name="login",
    ),

    # Logout (usa LOGOUT_REDIRECT_URL = "login" de settings.py si está definido)
    path(
        "salir/",
        LogoutView.as_view(),
        name="logout",
    ),

    # Rutas de agenda (DEBE IR ANTES de finanzas para respetar namespaces)
    path("agenda/", include("agenda.urls", namespace="agenda")),

    # Rutas principales de la aplicación de finanzas
    path("", include("finanzas.urls", namespace="finanzas")),

    # Inventario
    path('inventario/', include('inventario.urls')),
]

# Archivos de media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
