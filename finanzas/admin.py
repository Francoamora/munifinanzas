from django.contrib import admin

from . import models


@admin.register(models.Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)
    list_editable = ("activo",)
    ordering = ("nombre",)
    list_per_page = 25


@admin.register(models.Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "activa")
    list_filter = ("tipo", "activa")
    search_fields = ("nombre", "numero_cuenta")
    list_editable = ("activa",)
    ordering = ("nombre",)
    list_per_page = 25


@admin.register(models.Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "tipo",
        "grupo",
        "es_ayuda_social",
        "es_personal",
        "es_servicio",
        "es_combustible",
    )
    list_filter = (
        "tipo",
        "grupo",
        "es_ayuda_social",
        "es_personal",
        "es_servicio",
        "es_combustible",
    )
    search_fields = ("nombre",)
    list_editable = (
        "es_ayuda_social",
        "es_personal",
        "es_servicio",
        "es_combustible",
    )
    ordering = ("nombre",)
    list_per_page = 50


@admin.register(models.Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cuit", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "cuit", "telefono")
    list_editable = ("activo",)
    ordering = ("nombre",)
    list_per_page = 50


class MovimientoInline(admin.TabularInline):
    """
    Inline solo de lectura para ver los movimientos
    asociados a un beneficiario desde el admin.
    """
    model = models.Movimiento
    fields = ("fecha_operacion", "tipo", "categoria", "area", "monto", "estado")
    readonly_fields = ("fecha_operacion", "tipo", "categoria", "area", "monto", "estado")
    extra = 0
    can_delete = False
    show_change_link = True
    ordering = ("-fecha_operacion", "-id")


class AtencionInline(admin.TabularInline):
    """
    Inline de solo lectura para ver las atenciones sociales
    registradas para una persona desde el admin.
    """
    model = models.Atencion
    fields = (
        "fecha_atencion",
        "motivo_principal",
        "canal",
        "estado",
        "prioridad",
        "requiere_seguimiento",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True
    ordering = ("-fecha_atencion", "-id")


@admin.register(models.Beneficiario)
class BeneficiarioAdmin(admin.ModelAdmin):
    list_display = (
        "apellido",
        "nombre",
        "dni",
        "barrio",
        "paga_servicios",
        "tipo_vinculo",
        "sector_laboral",
        "activo",
    )
    list_filter = (
        "activo",
        "barrio",
        "paga_servicios",
        "tipo_vinculo",
        "sector_laboral",
    )
    search_fields = (
        "apellido",
        "nombre",
        "dni",
        "barrio",
        "direccion",
        "telefono",
    )
    list_editable = ("activo", "paga_servicios", "tipo_vinculo")
    ordering = ("apellido", "nombre")
    list_per_page = 50
    inlines = [MovimientoInline, AtencionInline]


@admin.register(models.Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ("patente", "descripcion", "area", "activo")
    list_filter = ("activo", "area")
    search_fields = ("patente", "descripcion")
    list_editable = ("activo",)
    ordering = ("patente",)
    list_per_page = 50


@admin.register(models.ProgramaAyuda)
class ProgramaAyudaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "descripcion")
    list_editable = ("activo",)
    ordering = ("nombre",)
    list_per_page = 50


@admin.register(models.Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_operacion",
        "tipo",
        "monto",
        "categoria",
        "area",
        "proveedor",
        "beneficiario",
        "tipo_pago_persona",
        "estado",
    )
    list_filter = (
        "tipo",
        "estado",
        "tipo_pago_persona",
        "categoria",
        "area",
        "fecha_operacion",
    )
    search_fields = (
        "descripcion",
        "observaciones",
        "proveedor__nombre",
        "proveedor__cuit",
        "beneficiario__nombre",
        "beneficiario__apellido",
        "beneficiario__dni",
        "programa_ayuda_texto",
    )
    date_hierarchy = "fecha_operacion"
    ordering = ("-fecha_operacion", "-id")
    list_per_page = 50

    # Incluimos todas las FKs que querés autocompletar
    autocomplete_fields = (
        "categoria",
        "area",
        "proveedor",
        "beneficiario",
        "programa_ayuda",
        "vehiculo",
        "cuenta_origen",
        "cuenta_destino",
        "orden_pago",
        "oc",  # FK a OrdenCompra
    )

    readonly_fields = (
        "fecha_carga",
        "actualizado_en",
        "creado_por",
        "actualizado_por",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "categoria",
            "area",
            "proveedor",
            "beneficiario",
            "programa_ayuda",
            "vehiculo",
            "cuenta_origen",
            "cuenta_destino",
            "creado_por",
            "actualizado_por",
        )

    def save_model(self, request, obj, form, change):
        """
        En el admin también queremos que se complete la trazabilidad
        de quién creó/actualizó el movimiento.
        """
        if not obj.creado_por:
            obj.creado_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.AdjuntoMovimiento)
class AdjuntoMovimientoAdmin(admin.ModelAdmin):
    list_display = ("movimiento", "archivo", "subido_por", "fecha_subida")
    list_filter = ("fecha_subida",)
    search_fields = ("movimiento__descripcion", "descripcion")
    date_hierarchy = "fecha_subida"
    list_per_page = 50


@admin.register(models.Atencion)
class AtencionAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_atencion",
        "persona_resumen_admin",
        "motivo_principal",
        "canal",
        "estado",
        "prioridad",
        "requiere_seguimiento",
        "area",
    )
    list_filter = (
        "estado",
        "prioridad",
        "canal",
        "motivo_principal",
        "area",
        "fecha_atencion",
    )
    search_fields = (
        "persona_nombre",
        "persona_dni",
        "persona_barrio",
        "descripcion",
        "resultado",
        "origen_interno",
        "persona__apellido",
        "persona__nombre",
        "persona__dni",
    )
    autocomplete_fields = ("persona", "area", "tarea_seguimiento")
    date_hierarchy = "fecha_atencion"
    ordering = ("-fecha_atencion", "-id")
    list_per_page = 50

    readonly_fields = (
        "fecha_creacion",
        "actualizado_en",
        "creado_por",
        "actualizado_por",
    )

    def persona_resumen_admin(self, obj):
        return obj.persona_resumen

    persona_resumen_admin.short_description = "Persona"

    def save_model(self, request, obj, form, change):
        if not obj.creado_por:
            obj.creado_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)


# =========================
# ÓRDENES DE PAGO
# =========================
@admin.register(models.OrdenPago)
class OrdenPagoAdmin(admin.ModelAdmin):
    """
    Admin simple y seguro para Orden de Pago:
    - Necesario para usar autocomplete_fields desde otros módulos.
    """
    list_display = ("numero", "fecha_orden", "proveedor_nombre", "area")
    list_filter = ("area", "fecha_orden")
    search_fields = ("numero", "proveedor_nombre", "proveedor__nombre", "proveedor_cuit")
    date_hierarchy = "fecha_orden"
    ordering = ("-fecha_orden", "-id")
    list_per_page = 50


# =========================
# ÓRDENES DE COMPRA (FIX ERROR admin.E039)
# =========================
@admin.register(models.OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    """
    Admin para OrdenCompra:
    - Requerido para que MovimientoAdmin.autocomplete_fields pueda apuntar a 'oc'.
    - Definimos search_fields para que el autocomplete funcione.
    """
    list_display = ("serie", "numero", "fecha_oc", "proveedor_nombre", "estado", "area")
    list_filter = ("estado", "rubro_principal", "area", "fecha_oc")
    search_fields = (
        "numero",
        "proveedor_nombre",
        "proveedor_cuit",
        "proveedor__nombre",
        "proveedor__cuit",
    )
    date_hierarchy = "fecha_oc"
    ordering = ("-fecha_oc", "-id")
    list_per_page = 50


# Personalización básica del admin
admin.site.site_header = "Comuna de Tacuarendí - Administración"
admin.site.site_title = "Comuna de Tacuarendí"
admin.site.index_title = "Panel de gestión"
