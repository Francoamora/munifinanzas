# finanzas/views_autocomplete.py
import json
import re

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .models import Beneficiario


_DNI_RE = re.compile(r"\D+")


def _dni_solo_digitos(v: str) -> str:
    return _DNI_RE.sub("", (v or "").strip())


@login_required
@require_GET
def persona_autocomplete(request):
    """
    Select2 AJAX endpoint (fuente única).
    URL: /finanzas/personas/autocomplete/
    Params: q o term
    Respuesta: { "results": [ {id, text, nombre, apellido, dni, documento} ] }
    """
    term = (request.GET.get("q") or request.GET.get("term") or "").strip()

    # ✅ mínimo 2 chars para no matar DB
    if len(term) < 2:
        return JsonResponse({"results": []})

    dni_digits = _dni_solo_digitos(term)

    qs = Beneficiario.objects.all()

    # ✅ por defecto solo activos (UX)
    # (si necesitás incluir inactivos, avisame y lo abrimos con flag GET include_inactivos=1)
    qs = qs.filter(activo=True)

    q_obj = Q(apellido__icontains=term) | Q(nombre__icontains=term)
    if dni_digits:
        q_obj = q_obj | Q(dni__icontains=dni_digits)

    personas = qs.filter(q_obj).order_by("apellido", "nombre")[:20]

    results = []
    for p in personas:
        dni = (p.dni or "").strip()
        label = f"{p.apellido}, {p.nombre}"
        if dni:
            label = f"{label} ({dni})"

        results.append({
            "id": p.id,
            "text": label,
            "nombre": (p.nombre or "").strip(),
            "apellido": (p.apellido or "").strip(),
            "dni": dni,
            "documento": dni,
        })

    return JsonResponse({"results": results})


@login_required
@require_POST
@transaction.atomic
def persona_quick_create(request):
    """
    Quick create para modales: crea o reactiva Beneficiario.
    Acepta form-encoded o JSON.
    Respuesta compatible:
      { ok: True, id: X, text: "...", result: {...} }
    """
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
    else:
        payload = request.POST

    dni = _dni_solo_digitos(payload.get("dni") or payload.get("documento") or "")
    apellido = (payload.get("apellido") or "").strip()
    nombre = (payload.get("nombre") or "").strip()
    direccion = (payload.get("direccion") or "").strip()
    barrio = (payload.get("barrio") or "").strip()
    telefono = (payload.get("telefono") or "").strip()

    if not dni:
        return JsonResponse({"ok": False, "error": "DNI/CUIL es obligatorio."}, status=400)

    if len(dni) not in (7, 8, 9, 11):
        return JsonResponse({"ok": False, "error": "DNI/CUIL inválido (cantidad de dígitos)."}, status=400)

    if not apellido or not nombre:
        return JsonResponse({"ok": False, "error": "Nombre y Apellido son obligatorios."}, status=400)

    obj, created = Beneficiario.objects.get_or_create(
        dni=dni,
        defaults={
            "apellido": apellido,
            "nombre": nombre,
            "direccion": direccion,
            "barrio": barrio,
            "telefono": telefono,
            "activo": True,
        }
    )

    # si existía pero estaba inactivo, lo reactivamos
    if not obj.activo:
        obj.activo = True

    # si existía pero faltaban datos, completamos sin pisar si ya hay valor
    changed = False
    for field, value in (
        ("apellido", apellido),
        ("nombre", nombre),
        ("direccion", direccion),
        ("barrio", barrio),
        ("telefono", telefono),
    ):
        if value and not (getattr(obj, field) or "").strip():
            setattr(obj, field, value)
            changed = True

    if created or changed or not obj.activo:
        obj.save()

    dni_show = (obj.dni or "").strip()
    label = f"{obj.apellido}, {obj.nombre}"
    if dni_show:
        label = f"{label} ({dni_show})"

    result = {
        "id": obj.id,
        "text": label,
        "nombre": (obj.nombre or "").strip(),
        "apellido": (obj.apellido or "").strip(),
        "dni": dni_show,
        "documento": dni_show,
    }

    return JsonResponse({"ok": True, "id": obj.id, "text": label, "result": result})
