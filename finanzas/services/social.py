from django.db.models import Q, Count, QuerySet
from finanzas.models import Atencion, Beneficiario

class SocialService:
    """
    Servicio para centralizar la lógica de negocio del área Social.
    Aquí van los filtros, estadísticas y reglas de validación complejas.
    """

    @staticmethod
    def filtrar_atenciones(params: dict) -> QuerySet:
        """
        Recibe los parámetros GET (request.GET) y devuelve el QuerySet filtrado.
        Limpia la vista de toda esta lógica condicional.
        """
        qs = Atencion.objects.select_related("persona", "area", "tarea_seguimiento")

        # 1. Búsqueda de texto (Buscador general)
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(persona__apellido__icontains=q)
                | Q(persona__nombre__icontains=q)
                | Q(persona__dni__icontains=q)
                | Q(persona_nombre__icontains=q)
                | Q(persona_dni__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(resultado__icontains=q)
            )

        # 2. Filtros específicos
        if persona_id := params.get("persona"):
            qs = qs.filter(persona_id=persona_id)

        if area_id := params.get("area"):
            qs = qs.filter(area_id=area_id)

        if estado := params.get("estado"):
            qs = qs.filter(estado=estado)

        if prioridad := params.get("prioridad"):
            qs = qs.filter(prioridad=prioridad)

        if canal := params.get("canal"):
            qs = qs.filter(canal=canal)

        if motivo := params.get("motivo"):
            qs = qs.filter(motivo_principal=motivo)

        # Filtro booleano inteligente
        seguimiento = params.get("seguimiento")
        if seguimiento in ("1", "true", "True", "on"):
            qs = qs.filter(requiere_seguimiento=True)

        return qs.order_by("-fecha_atencion", "-id")

    @staticmethod
    def obtener_resumen_estadistico(queryset: QuerySet) -> dict:
        """
        Calcula los contadores para el dashboard social basándose en un queryset ya filtrado.
        """
        return {
            "total": queryset.count(),
            "con_seguimiento": queryset.filter(requiere_seguimiento=True).count(),
            "por_estado": list(queryset.values("estado").annotate(cantidad=Count("id")).order_by("estado")),
            "por_motivo": list(queryset.values("motivo_principal").annotate(cantidad=Count("id")).order_by("motivo_principal")),
            "por_area": list(queryset.values("area__nombre").annotate(cantidad=Count("id")).order_by("area__nombre")),
        }

    @staticmethod
    def crear_atencion(data: dict, usuario) -> Atencion:
        """
        Crea una atención asegurando que los campos de auditoría se llenen.
        (Opcional, si querés sacar la lógica del form.save)
        """
        atencion = Atencion(**data)
        atencion.creado_por = usuario
        atencion.actualizado_por = usuario
        atencion.save()
        return atencion