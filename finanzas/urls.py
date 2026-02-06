from django.urls import path
from . import views
from . import views_autocomplete

# Importaciones Modulares (Optimizadas para evitar errores silenciosos críticos)
# Si falta un módulo, Django avisará en consola en lugar de ocultar la URL.
try: from . import views_flota; has_flota = True
except ImportError: has_flota = False

try: from . import views_oc; has_oc = True
except ImportError: has_oc = False

try: from . import views_ot; has_ot = True
except ImportError: has_ot = False

try: from . import views_atenciones; has_atenciones = True
except ImportError: has_atenciones = False

app_name = "finanzas"

urlpatterns = [
    # =========================
    # CORE: HOME & DASHBOARD
    # =========================
    path("", views.HomeView.as_view(), name="home"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("balances/", views.BalanceResumenView.as_view(), name="balance_resumen"),

    # =========================
    # CAJA Y MOVIMIENTOS
    # =========================
    path("movimientos/", views.MovimientoListView.as_view(), name="movimiento_list"),
    path("movimientos/nuevo/", views.MovimientoCreateView.as_view(), name="movimiento_create"),
    path("movimientos/<int:pk>/", views.MovimientoDetailView.as_view(), name="movimiento_detail"),
    path("movimientos/<int:pk>/editar/", views.MovimientoUpdateView.as_view(), name="movimiento_update"),
    path("movimientos/<int:pk>/cambiar-estado/<str:accion>/", views.MovimientoCambiarEstadoView.as_view(), name="movimiento_cambiar_estado"),
    path("movimientos/<int:pk>/orden-pago/", views.MovimientoOrdenPagoView.as_view(), name="movimiento_orden_pago"),

    path("movimiento/<int:pk>/recibo/", views.ReciboIngresoPrintView.as_view(), name="recibo_print"),

    # =========================
    # TESORERÍA (ÓRDENES DE PAGO - OP)
    # =========================
    path("ordenes-pago/", views.OrdenPagoListView.as_view(), name="orden_pago_list"),
    path("ordenes-pago/nueva/", views.OrdenPagoCreateView.as_view(), name="orden_pago_create"),
    path("ordenes-pago/<int:pk>/", views.OrdenPagoDetailView.as_view(), name="orden_pago_detail"),
    path("ordenes-pago/<int:pk>/editar/", views.OrdenPagoUpdateView.as_view(), name="orden_pago_update"),
    path("ordenes-pago/<int:pk>/cambiar-estado/<str:accion>/", views.OrdenPagoCambiarEstadoView.as_view(), name="orden_pago_cambiar_estado"),
    path("ordenes-pago/<int:pk>/generar-movimiento/", views.OrdenPagoGenerarMovimientoView.as_view(), name="orden_pago_generar_movimiento"),

    # =========================
    # COMPRAS (PROVEEDORES)
    # =========================
    path("proveedores/", views.ProveedorListView.as_view(), name="proveedor_list"),
    path("proveedores/nuevo/", views.ProveedorCreateView.as_view(), name="proveedor_create"),
    path("proveedores/<int:pk>/", views.ProveedorDetailView.as_view(), name="proveedor_detail"),
    path("proveedores/<int:pk>/editar/", views.ProveedorUpdateView.as_view(), name="proveedor_update"),

    # =========================
    # SOCIAL (PERSONAS)
    # =========================
    path("personas/", views.PersonaListView.as_view(), name="persona_list"),
    path("personas/nueva/", views.PersonaCreateView.as_view(), name="persona_create"),
    path("personas/<int:pk>/", views.PersonaDetailView.as_view(), name="persona_detail"),
    path("personas/<int:pk>/editar/", views.PersonaUpdateView.as_view(), name="persona_update"),
    # ✅ RUTA NUEVA PARA SUBIR ARCHIVOS
    path('personas/<int:pk>/documentos/nuevo/', views.BeneficiarioUploadView.as_view(), name='persona_documento_create'),
    path('persona/<int:pk>/upload-sensible/', views.DocumentoSensibleUploadView.as_view(), name='persona_doc_sensible_create'),

    # =========================
    # APIS GLOBALES (AJAX)
    # =========================
    # Personas
    path("api/personas/autocomplete/", views_autocomplete.persona_autocomplete, name="persona_autocomplete"),
    path("api/personas/quick-create/", views_autocomplete.persona_quick_create, name="persona_quick_create"),
    path("api/personas/buscar-por-dni/", views.persona_buscar_por_dni, name="persona_buscar_dni"),
    
    # Categorías
    path("api/categorias/por-tipo/", views.categorias_por_tipo, name="categorias_por_tipo"),
    # Proveedor
    path('api/proveedores/crear-express/', views.proveedor_create_express, name='proveedor_create_express'),
    # Impresion
    path('movimiento/<int:pk>/recibo/', views.ReciboIngresoPrintView.as_view(), name='movimiento_recibo_print'),
]

# === MÓDULO: FLOTA Y LOGÍSTICA ===
if has_flota:
    urlpatterns += [
        # Dashboard
        path("flota/", views_flota.FlotaCombustibleResumenView.as_view(), name="flota_home"),
        path("flota/consumo/", views_flota.FlotaCombustibleResumenView.as_view(), name="consumo_combustible"),
        
        # Hojas de Ruta
        path("flota/hojas/", views_flota.HojaRutaListView.as_view(), name="hoja_ruta_list"),
        path("flota/hojas/nueva/", views_flota.HojaRutaCreateView.as_view(), name="hoja_ruta_create"),
        path("flota/hojas/<int:pk>/", views_flota.HojaRutaDetailView.as_view(), name="hoja_ruta_detail"),
        
        # Vehículos
        path("flota/vehiculos/", views_flota.VehiculoListView.as_view(), name="vehiculo_list"),
        path("flota/vehiculos/nuevo/", views_flota.VehiculoCreateView.as_view(), name="vehiculo_create"),
        path("flota/vehiculos/<int:pk>/", views_flota.VehiculoDetailView.as_view(), name="vehiculo_detail"),
        path("flota/vehiculos/<int:pk>/editar/", views_flota.VehiculoUpdateView.as_view(), name="vehiculo_update"),
        
        # APIs Específicas
        path("vehiculos/autocomplete/", views_flota.vehiculo_autocomplete, name="vehiculo_autocomplete"),
        path("api/vehiculos/<int:pk>/detalle/", views_flota.api_vehiculo_detalle, name="api_vehiculo_detalle"),
    ]

# === MÓDULO: ATENCIONES SOCIALES ===
if has_atenciones:
    urlpatterns += [
        path("atenciones/", views_atenciones.AtencionListView.as_view(), name="atencion_list"),
        path("atenciones/nueva/", views_atenciones.AtencionCreateView.as_view(), name="atencion_create"),
        path("atenciones/<int:pk>/editar/", views_atenciones.AtencionUpdateView.as_view(), name="atencion_update"),
        path("personas/<int:pk>/atenciones/", views_atenciones.AtencionBeneficiarioListView.as_view(), name="atencion_beneficiario_list"),
    ]

# === MÓDULO: ÓRDENES DE COMPRA (OC) ===
if has_oc:
    urlpatterns += [
        path("ordenes-compra/", views_oc.OCListView.as_view(), name="oc_list"),
        path("ordenes-compra/nueva/", views_oc.OCCreateView.as_view(), name="oc_create"),
        path("ordenes-compra/<int:pk>/", views_oc.OCDetailView.as_view(), name="oc_detail"),
        path("ordenes-compra/<int:pk>/editar/", views_oc.OCUpdateView.as_view(), name="oc_update"),
        path("ordenes-compra/<int:pk>/cambiar-estado/<str:accion>/", views_oc.OCCambiarEstadoView.as_view(), name="oc_cambiar_estado"),
        path("ordenes-compra/<int:pk>/generar-movimiento/", views_oc.OCGenerarMovimientoView.as_view(), name="oc_generar_movimiento"),
        
        # APIs OC
        path("api/oc/proveedor-por-cuit/", views_oc.proveedor_por_cuit, name="oc_proveedor_por_cuit"),
        path("api/oc/proveedores-suggest/", views_oc.proveedor_suggest, name="oc_proveedores_suggest"),
        path("api/vehiculos/buscar-por-patente/", views_oc.vehiculo_por_patente, name="vehiculo_por_patente"),

        # ✅ NUEVO: API PARA BUSCAR OCS PENDIENTES (ESTO ES LO QUE FALTA)
        path("api/oc/pendientes/", views_oc.ocs_pendientes_por_proveedor, name="oc_pendientes_proveedor"),
    ]

# === MÓDULO: ÓRDENES DE TRABAJO (OT) ===
if has_ot:
    urlpatterns += [
        path("ordenes-trabajo/", views_ot.OrdenTrabajoListView.as_view(), name="orden_trabajo_list"),
        path("ordenes-trabajo/nueva/", views_ot.OrdenTrabajoCreateView.as_view(), name="orden_trabajo_create"),
        path("ordenes-trabajo/<int:pk>/", views_ot.OrdenTrabajoDetailView.as_view(), name="orden_trabajo_detail"),
        path("ordenes-trabajo/<int:pk>/editar/", views_ot.OrdenTrabajoUpdateView.as_view(), name="orden_trabajo_update"),
        path("ordenes-trabajo/<int:pk>/generar-movimiento/", views_ot.OrdenTrabajoGenerarMovimientoIngresoView.as_view(), name="orden_trabajo_generar_movimiento"),
    ]