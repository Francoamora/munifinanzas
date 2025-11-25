from django.contrib import admin
from .models import Tarea


@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "titulo",
        "tipo",
        "prioridad",
        "estado",
        "ambito",
        "fecha_vencimiento",
        "responsable",
        "origen",
    )
    list_filter = ("estado", "tipo", "prioridad", "ambito", "origen")
    search_fields = ("titulo", "descripcion")
    autocomplete_fields = ("orden_pago", "movimiento", "persona", "proveedor", "responsable")
    ordering = ("fecha_vencimiento", "-prioridad", "-id")
