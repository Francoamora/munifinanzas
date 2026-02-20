from django.urls import path
from . import views
from . import views_autocomplete

# =========================================================
# IMPORTACIONES MODULARES (Protección contra errores)
# =========================================================
try: from . import views_flota; has_flota = True
except ImportError: has_flota = False

try: from . import views_oc; has_oc = True
except ImportError: has_oc = False

try: from . import views_ot; has_ot = True
except ImportError: has_ot = False

try: from . import views_atenciones; has_atenciones = True
except ImportError: has_atenciones = False

# Intento importar views_personas por si tenés la lógica separada ahí
try: from . import views_personas; has_personas = True
except ImportError: has_personas = False

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
    path('movimiento/<int:pk>/recibo/', views.ReciboIngresoPrintView.as_view(), name='recibo_print'), # Alias corto
    path('movimientos/<int:pk>/recibo/', views.ReciboIngresoPrintView.as_view(), name='movimiento_recibo_print'), # Alias largo

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
    path('api/proveedores/crear-express/', views.proveedor_create_express, name='proveedor_create_express'),

    # =========================
    # APIS GLOBALES (AJAX)
    # =========================
    path("api/personas/autocomplete/", views_autocomplete.persona_autocomplete, name="persona_autocomplete"),
    path("api/personas/quick-create/", views_autocomplete.persona_quick_create, name="persona_quick_create"),
    path("api/personas/buscar-por-dni/", views.persona_buscar_por_dni, name="persona_buscar_dni"),
    path("api/categorias/por-tipo/", views.categorias_por_tipo, name="categorias_por_tipo"),
]

# =========================
# MÓDULO: SOCIAL (PERSONAS)
# =========================
# Usamos views_personas si existe (lo nuevo), sino views (lo viejo)
persona_views = views_personas if has_personas else views

urlpatterns += [
    path("personas/", persona_views.PersonaListView.as_view(), name="persona_list"),
    path("personas/nueva/", persona_views.PersonaCreateView.as_view(), name="persona_create"),
    path("personas/<int:pk>/", persona_views.PersonaDetailView.as_view(), name="persona_detail"),
    path("personas/<int:pk>/editar/", persona_views.PersonaUpdateView.as_view(), name="persona_update"),
    
    # Documentos
    path('personas/<int:pk>/documentos/nuevo/', persona_views.BeneficiarioUploadView.as_view(), name='persona_documento_create'),
    # Verificamos si existe la vista de doc sensible en el módulo seleccionado
    path('persona/<int:pk>/upload-sensible/', 
         getattr(persona_views, 'DocumentoSensibleUploadView', views.BeneficiarioUploadView).as_view(), 
         name='persona_doc_sensible_create'),
]

# =========================
# MÓDULO: ÓRDENES DE COMPRA (OC)
# =========================
if has_oc:
    urlpatterns += [
        # CRUD Principal
        path("ordenes-compra/", views_oc.OCListView.as_view(), name="oc_list"),
        path("ordenes-compra/nueva/", views_oc.OCCreateView.as_view(), name="oc_create"),
        path("ordenes-compra/<int:pk>/", views_oc.OCDetailView.as_view(), name="oc_detail"),
        path("ordenes-compra/<int:pk>/editar/", views_oc.OCUpdateView.as_view(), name="oc_update"),
        # Agregar junto a las otras de OC
        path("ordenes-compra/autorizar-masivo/", views_oc.OCAutorizarMasivoView.as_view(), name="oc_autorizar_masivo"),
        
        # Acciones de Estado (Apuntando a views_oc que es donde está la lógica nueva)
        path("ordenes-compra/<int:pk>/cambiar-estado/<str:accion>/", views_oc.OCCambiarEstadoView.as_view(), name="oc_cambiar_estado"),
        path("ordenes-compra/<int:pk>/pagar/", views_oc.OCGenerarMovimientoView.as_view(), name="oc_pagar"),
        path("ordenes-compra/<int:pk>/generar-movimiento/", views_oc.OCGenerarMovimientoView.as_view(), name="oc_generar_movimiento"), # Alias
        
        # APIs JSON (AJAX) - ¡CRÍTICAS PARA EL FORMULARIO!
        path("api/oc/proveedor-por-cuit/", views_oc.proveedor_por_cuit, name="oc_proveedor_por_cuit"),
        path("api/oc/proveedores-suggest/", views_oc.proveedor_suggest, name="oc_proveedores_suggest"),
        path("api/oc/beneficiario-quick-create/", views_oc.api_beneficiario_create, name="api_beneficiario_create"), # <--- LA QUE FALTABA
        path("api/oc/pendientes/", views_oc.ocs_pendientes_por_proveedor, name="oc_pendientes_proveedor"),
        
        # Helper vehículo
        path("api/vehiculos/buscar-por-patente/", views_oc.vehiculo_por_patente, name="vehiculo_por_patente"),
    ]

# =========================
# MÓDULO: FLOTA Y LOGÍSTICA
# =========================
if has_flota:
    urlpatterns += [
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
        
        # APIs Flota
        path("vehiculos/autocomplete/", views_flota.vehiculo_autocomplete, name="vehiculo_autocomplete"),
        path("api/vehiculos/<int:pk>/detalle/", views_flota.api_vehiculo_detalle, name="api_vehiculo_detalle"),
    ]

# =========================
# MÓDULO: ATENCIONES SOCIALES
# =========================
if has_atenciones:
    urlpatterns += [
        path("atenciones/", views_atenciones.AtencionListView.as_view(), name="atencion_list"),
        path("atenciones/nueva/", views_atenciones.AtencionCreateView.as_view(), name="atencion_create"),
        path("atenciones/<int:pk>/editar/", views_atenciones.AtencionUpdateView.as_view(), name="atencion_update"),
        path("personas/<int:pk>/atenciones/", views_atenciones.AtencionBeneficiarioListView.as_view(), name="atencion_beneficiario_list"),
    ]

# =========================
# MÓDULO: ÓRDENES DE TRABAJO (OT)
# =========================
if has_ot:
    urlpatterns += [
        path("ordenes-trabajo/", views_ot.OrdenTrabajoListView.as_view(), name="orden_trabajo_list"),
        path("ordenes-trabajo/nueva/", views_ot.OrdenTrabajoCreateView.as_view(), name="orden_trabajo_create"),
        path("ordenes-trabajo/<int:pk>/", views_ot.OrdenTrabajoDetailView.as_view(), name="orden_trabajo_detail"),
        path("ordenes-trabajo/<int:pk>/editar/", views_ot.OrdenTrabajoUpdateView.as_view(), name="orden_trabajo_update"),
        path("ordenes-trabajo/<int:pk>/generar-movimiento/", views_ot.OrdenTrabajoGenerarMovimientoIngresoView.as_view(), name="orden_trabajo_generar_movimiento"),
    ]