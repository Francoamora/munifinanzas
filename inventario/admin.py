from django.contrib import admin
from .models import CategoriaInsumo, Insumo, MovimientoStock, Prestamo

@admin.register(CategoriaInsumo)
class CategoriaInsumoAdmin(admin.ModelAdmin):
    list_display = ('nombre',)

@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'stock_actual', 'unidad', 'es_herramienta', 'alerta_stock')
    list_filter = ('categoria', 'es_herramienta')
    search_fields = ('nombre',)
    list_editable = ('stock_actual',)
    
    def alerta_stock(self, obj):
        return "⚠️ BAJO" if obj.stock_actual <= obj.stock_minimo else "✅ OK"

@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    # Actualizado a los campos nuevos
    list_display = ('fecha', 'tipo', 'insumo', 'cantidad', 'referencia', 'usuario')
    list_filter = ('tipo', 'fecha')
    date_hierarchy = 'fecha'

@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ('insumo', 'responsable', 'fecha_salida', 'estado', 'fecha_devolucion')
    list_filter = ('estado', 'fecha_salida')
    search_fields = ('insumo__nombre', 'responsable__apellido')