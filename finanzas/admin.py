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
    inlines = [MovimientoInline]


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

    autocomplete_fields = (
        "categoria",
        "area",
        "proveedor",
        "beneficiario",
        "programa_ayuda",
        "vehiculo",
        "cuenta_origen",
        "cuenta_destino",
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


# =========================
# ÓRDENES DE PAGO (fix autocomplete Agenda)
# =========================
@admin.register(models.OrdenPago)
class OrdenPagoAdmin(admin.ModelAdmin):
    """
    Admin simple y seguro para no romper nada:
    - Se registra el modelo para que Agenda pueda usar autocomplete_fields.
    - Search mínimo para que el autocomplete funcione.
    """
    search_fields = ("numero",)
    ordering = ("-id",)
    list_per_page = 50


# Personalización básica del admin
admin.site.site_header = "Comuna de Tacuarendí - Administración"
admin.site.site_title = "Comuna de Tacuarendí"
admin.site.index_title = "Panel de gestión"
