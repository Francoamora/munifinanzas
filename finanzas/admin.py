from django.contrib import admin
from unfold.admin import ModelAdmin  # <--- EL MOTOR VISUAL DE UNFOLD

# Importamos todos tus modelos
from .models import (
    Area, Cuenta, Categoria, Proveedor, Beneficiario,
    Movimiento, OrdenPago, OrdenCompra, HojaRuta, Traslado, 
    Vehiculo, Atencion, ProgramaAyuda
)

@admin.register(Area)
class AreaAdmin(ModelAdmin):
    list_display = ("nombre", "activo")
    search_fields = ("nombre",)

@admin.register(Cuenta)
class CuentaAdmin(ModelAdmin):
    list_display = ("nombre", "tipo", "activa")
    list_filter = ("tipo", "activa")

@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ("nombre", "tipo", "grupo")
    list_filter = ("tipo", "grupo")
    search_fields = ("nombre",)
    list_filter_submit = True 

@admin.register(Proveedor)
class ProveedorAdmin(ModelAdmin):
    list_display = ("nombre", "cuit", "activo")
    search_fields = ("nombre", "cuit", "rubro")
    list_filter = ("activo",)

@admin.register(Beneficiario)
class BeneficiarioAdmin(ModelAdmin):
    list_display = ("apellido", "nombre", "dni", "barrio", "activo")
    search_fields = ("apellido", "nombre", "dni")
    list_filter = ("activo", "barrio")
    list_filter_submit = True

@admin.register(Movimiento)
class MovimientoAdmin(ModelAdmin):
    list_display = ("fecha_operacion", "tipo", "monto", "categoria", "estado")
    list_filter = ("tipo", "estado", "fecha_operacion", "categoria")
    search_fields = ("descripcion", "monto", "proveedor__nombre", "beneficiario__apellido")
    readonly_fields = ("fecha_carga", "creado_por", "actualizado_por")
    list_filter_submit = True
    date_hierarchy = "fecha_operacion"

@admin.register(OrdenPago)
class OrdenPagoAdmin(ModelAdmin):
    list_display = ("numero", "fecha_orden", "proveedor", "estado", "total_monto")
    list_filter = ("estado", "fecha_orden")
    search_fields = ("numero", "proveedor__nombre", "proveedor__cuit")
    list_filter_submit = True

@admin.register(OrdenCompra)
class OrdenCompraAdmin(ModelAdmin):
    list_display = ("numero", "fecha_oc", "proveedor", "estado")
    list_filter = ("estado", "fecha_oc")
    search_fields = ("numero", "proveedor__nombre")
    list_filter_submit = True

@admin.register(Vehiculo)
class VehiculoAdmin(ModelAdmin):
    # Agregamos 'marca' y 'tipo' que ahora existen en el modelo
    list_display = ("patente", "descripcion", "marca", "activo", "kilometraje_referencia")
    list_filter = ("activo", "tipo")
    search_fields = ("patente", "descripcion", "marca")

@admin.register(HojaRuta)
class HojaRutaAdmin(ModelAdmin):
    # Usamos km_recorridos que ahora es un campo real
    list_display = ("fecha", "vehiculo", "chofer_nombre", "estado", "km_recorridos")
    list_filter = ("estado", "fecha", "vehiculo")
    search_fields = ("vehiculo__patente", "chofer_nombre")
    date_hierarchy = "fecha"

@admin.register(Traslado)
class TrasladoAdmin(ModelAdmin):
    list_display = ("hoja_ruta", "origen", "destino", "motivo")
    search_fields = ("destino", "pasajeros__apellido", "origen")

@admin.register(Atencion)
class AtencionAdmin(ModelAdmin):
    list_display = ("fecha_atencion", "persona", "motivo_principal", "estado")
    list_filter = ("estado", "motivo_principal", "fecha_atencion")
    search_fields = ("persona__apellido", "descripcion")
    readonly_fields = ("fecha_creacion", "creado_por", "actualizado_por")
    list_filter_submit = True

@admin.register(ProgramaAyuda)
class ProgramaAyudaAdmin(ModelAdmin):
    # CORREGIDO: Quitamos 'monto_default' para evitar el error
    list_display = ("nombre",) 
    search_fields = ("nombre",)