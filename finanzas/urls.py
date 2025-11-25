# finanzas/urls.py
from django.urls import path, include

from .views import (
    HomeView,
    DashboardView,

    # Movimientos
    MovimientoListView,
    MovimientoCreateView,
    MovimientoUpdateView,
    MovimientoDetailView,
    MovimientoCambiarEstadoView,

    # Personas / Censo
    PersonaListView,
    PersonaDetailView,
    PersonaCreateView,
    PersonaUpdateView,

    # Balances
    BalanceResumenView,

    # API
    persona_buscar_por_dni,

    # Órdenes de pago
    OrdenPagoListView,
    OrdenPagoCreateView,
    OrdenPagoUpdateView,
    OrdenPagoDetailView,
    OrdenPagoCambiarEstadoView,
    OrdenPagoGenerarMovimientoView,
)

app_name = "finanzas"

urlpatterns = [
    # =========================
    # Home / Panel inicial simple
    # =========================
    path("", HomeView.as_view(), name="home"),

    # =========================
    # Tablero avanzado de finanzas
    # =========================
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # =========================
    # Movimientos
    # =========================
    path("movimientos/", MovimientoListView.as_view(), name="movimiento_list"),
    path("movimientos/nuevo/", MovimientoCreateView.as_view(), name="movimiento_create"),
    path("movimientos/<int:pk>/editar/", MovimientoUpdateView.as_view(), name="movimiento_update"),
    path("movimientos/<int:pk>/", MovimientoDetailView.as_view(), name="movimiento_detail"),
    path(
        "movimientos/<int:pk>/cambiar-estado/<str:accion>/",
        MovimientoCambiarEstadoView.as_view(),
        name="movimiento_cambiar_estado",
    ),

    # =========================
    # Órdenes de pago (módulo propio)
    # =========================
    path("ordenes-pago/", OrdenPagoListView.as_view(), name="orden_pago_list"),
    path("ordenes-pago/nueva/", OrdenPagoCreateView.as_view(), name="orden_pago_create"),
    path("ordenes-pago/<int:pk>/", OrdenPagoDetailView.as_view(), name="orden_pago_detail"),
    path("ordenes-pago/<int:pk>/editar/", OrdenPagoUpdateView.as_view(), name="orden_pago_update"),
    path(
        "ordenes-pago/<int:pk>/cambiar-estado/<str:accion>/",
        OrdenPagoCambiarEstadoView.as_view(),
        name="orden_pago_cambiar_estado",
    ),
    path(
        "ordenes-pago/<int:pk>/generar-movimiento/",
        OrdenPagoGenerarMovimientoView.as_view(),
        name="orden_pago_generar_movimiento",
    ),

    # =========================
    # Personas / Censo
    # =========================
    path("personas/", PersonaListView.as_view(), name="persona_list"),
    path("personas/nueva/", PersonaCreateView.as_view(), name="persona_create"),
    path("personas/<int:pk>/", PersonaDetailView.as_view(), name="persona_detail"),
    path("personas/<int:pk>/editar/", PersonaUpdateView.as_view(), name="persona_update"),

    # =========================
    # Balances
    # =========================
    path("balances/", BalanceResumenView.as_view(), name="balance_resumen"),

    # =========================
    # API
    # =========================
    path(
        "api/personas/buscar-por-dni/",
        persona_buscar_por_dni,
        name="persona_buscar_dni",
    ),


]