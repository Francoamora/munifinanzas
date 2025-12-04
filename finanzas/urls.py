# finanzas/urls.py 
from django.urls import path

# Vistas principales y de finanzas
from .views import (
    HomeView,
    DashboardView,

    # Movimientos
    MovimientoListView,
    MovimientoCreateView,
    MovimientoUpdateView,
    MovimientoDetailView,
    MovimientoCambiarEstadoView,
    MovimientoOrdenPagoView,  # legacy: orden de pago ligada a movimiento

    # Personas / Censo
    PersonaListView,
    PersonaDetailView,
    PersonaCreateView,
    PersonaUpdateView,

    # Balances
    BalanceResumenView,

    # APIs personas / vehículos (personas y autocomplete)
    persona_buscar_por_dni,
    persona_autocomplete,
    vehiculo_autocomplete,

    # Órdenes de pago
    OrdenPagoListView,
    OrdenPagoCreateView,
    OrdenPagoUpdateView,
    OrdenPagoDetailView,
    OrdenPagoCambiarEstadoView,
    OrdenPagoGenerarMovimientoView,

    # Generar movimiento desde OT (sigue en views.py)
    OrdenTrabajoGenerarMovimientoIngresoView,

    # Flota: consumo detallado por vehículo
    ConsumoCombustibleView,
)

# Órdenes de compra + APIs proveedor/vehículos
from .views_oc import (
    OCListView,
    OCCreateView,
    OCUpdateView,
    OCDetailView,
    OCCambiarEstadoView,
    OCGenerarMovimientoView,
    proveedor_por_cuit,
    proveedor_suggest,
    vehiculo_por_patente,
)

# Flota / vehículos / viajes / dashboard de combustible
from .views_flota import (
    VehiculoListView,
    VehiculoCreateView,
    VehiculoUpdateView,
    VehiculoDetailView,
    ViajeVehiculoListView,
    ViajeVehiculoCreateView,
    ViajeVehiculoUpdateView,
    ViajeVehiculoDetailView,
    FlotaCombustibleResumenView,
)

# Órdenes de trabajo + API personas (OT)
from .views_ot import (
    OrdenTrabajoListView,
    OrdenTrabajoCreateView,
    OrdenTrabajoUpdateView,
    OrdenTrabajoDetailView,
    persona_suggest,
)

# Atenciones sociales (módulo social, sin montos)
from .views_atenciones import (
    AtencionListView,
    AtencionCreateView,
    AtencionBeneficiarioListView,
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
    path(
        "movimientos/<int:pk>/orden-pago/",
        MovimientoOrdenPagoView.as_view(),
        name="movimiento_orden_pago",
    ),

    # =========================
    # Órdenes de pago
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
    # Órdenes de compra (OC)
    # =========================
    path("ordenes-compra/", OCListView.as_view(), name="oc_list"),
    path("ordenes-compra/nueva/", OCCreateView.as_view(), name="oc_create"),
    path("ordenes-compra/<int:pk>/", OCDetailView.as_view(), name="oc_detail"),
    path("ordenes-compra/<int:pk>/editar/", OCUpdateView.as_view(), name="oc_update"),
    path(
        "ordenes-compra/<int:pk>/cambiar-estado/<str:accion>/",
        OCCambiarEstadoView.as_view(),
        name="oc_cambiar_estado",
    ),
    path(
        "ordenes-compra/<int:pk>/generar-movimiento/",
        OCGenerarMovimientoView.as_view(),
        name="oc_generar_movimiento",
    ),

    # =========================
    # Órdenes de trabajo (OT)
    # =========================
    path(
        "ordenes-trabajo/",
        OrdenTrabajoListView.as_view(),
        name="orden_trabajo_list",
    ),
    path(
        "ordenes-trabajo/nueva/",
        OrdenTrabajoCreateView.as_view(),
        name="orden_trabajo_create",
    ),
    path(
        "ordenes-trabajo/<int:pk>/",
        OrdenTrabajoDetailView.as_view(),
        name="orden_trabajo_detail",
    ),
    path(
        "ordenes-trabajo/<int:pk>/editar/",
        OrdenTrabajoUpdateView.as_view(),
        name="orden_trabajo_update",
    ),
    path(
        "ordenes-trabajo/<int:pk>/generar-movimiento/",
        OrdenTrabajoGenerarMovimientoIngresoView.as_view(),
        name="orden_trabajo_generar_movimiento",
    ),

    # =========================
    # Flota / Vehículos / Viajes / Combustible
    # =========================
    # Home de Flota / Dashboard general
    path(
        "flota/",
        FlotaCombustibleResumenView.as_view(),
        name="flota_home",
    ),

    # Listado y ABM de vehículos
    path("flota/vehiculos/", VehiculoListView.as_view(), name="vehiculo_list"),
    path("flota/vehiculos/nuevo/", VehiculoCreateView.as_view(), name="vehiculo_create"),
    path("flota/vehiculos/<int:pk>/", VehiculoDetailView.as_view(), name="vehiculo_detail"),
    path("flota/vehiculos/<int:pk>/editar/", VehiculoUpdateView.as_view(), name="vehiculo_update"),

    # Viajes de vehículos (odómetro)
    path("flota/viajes/", ViajeVehiculoListView.as_view(), name="viaje_vehiculo_list"),
    path("flota/viajes/nuevo/", ViajeVehiculoCreateView.as_view(), name="viaje_vehiculo_create"),
    path("flota/viajes/<int:pk>/", ViajeVehiculoDetailView.as_view(), name="viaje_vehiculo_detail"),
    path("flota/viajes/<int:pk>/editar/", ViajeVehiculoUpdateView.as_view(), name="viaje_vehiculo_update"),

    # Vista detallada de consumo por vehículo
    path(
        "flota/consumo/",
        ConsumoCombustibleView.as_view(),
        name="flota_combustible_resumen",
    ),

    # =========================
    # Personas / Censo
    # =========================
    path("personas/", PersonaListView.as_view(), name="persona_list"),
    path("personas/nueva/", PersonaCreateView.as_view(), name="persona_create"),
    path("personas/<int:pk>/", PersonaDetailView.as_view(), name="persona_detail"),
    path("personas/<int:pk>/editar/", PersonaUpdateView.as_view(), name="persona_update"),

    # =========================
    # Atenciones sociales (módulo social, sin montos)
    # =========================
    path(
        "atenciones/",
        AtencionListView.as_view(),
        name="atencion_list",
    ),
    path(
        "atenciones/nueva/",
        AtencionCreateView.as_view(),
        name="atencion_create",
    ),
    path(
        "personas/<int:pk>/atenciones/",
        AtencionBeneficiarioListView.as_view(),
        name="atencion_beneficiario_list",
    ),

    # =========================
    # Balances
    # =========================
    path("balances/", BalanceResumenView.as_view(), name="balance_resumen"),

    # =========================
    # APIs Personas / Proveedores / Vehículos
    # =========================
    path(
        "api/personas/buscar-por-dni/",
        persona_buscar_por_dni,
        name="persona_buscar_dni",
    ),
    path(
        "api/personas/suggest/",
        persona_suggest,
        name="persona_suggest",
    ),
    path(
        "personas/autocomplete/",
        persona_autocomplete,
        name="persona_autocomplete",
    ),
    path(
        "vehiculos/autocomplete/",
        vehiculo_autocomplete,
        name="vehiculo_autocomplete",
    ),
    path(
        "api/oc/proveedor-por-cuit/",
        proveedor_por_cuit,
        name="oc_proveedor_por_cuit",
    ),
    path(
        "api/oc/proveedores-suggest/",
        proveedor_suggest,
        name="oc_proveedores_suggest",
    ),
    path(
        "api/vehiculos/buscar-por-patente/",
        vehiculo_por_patente,
        name="vehiculo_por_patente",
    ),
]
