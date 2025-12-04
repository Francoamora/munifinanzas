from decimal import Decimal
from collections import Counter

from django.contrib import messages
from django.db.models import (
    Q,
    Sum,
    F,
    DecimalField,
    ExpressionWrapper,
    Count,
)
from django.utils import timezone
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DetailView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.shortcuts import redirect

from .models import Vehiculo, ViajeVehiculo, Movimiento, Area
from .forms import (
    VehiculoForm,
    ViajeVehiculoForm,
    ViajeVehiculoTramoFormSet,
)
from .mixins import BaseRolMixin, SoloFinanzasMixin
from . import permisos
from .views import (
    _roles_ctx,
    _parse_date_or_none,
)


# ============================================
#   HELPERS COMPARTIDOS PARA FECHAS DE VIAJES
# ============================================


def _viaje_fecha_field() -> str:
    """
    Devuelve el nombre del campo de fecha a usar en ViajeVehiculo.
    Prioridad:
      1) fecha_salida
      2) fecha
      3) fecha_viaje
    """
    if hasattr(ViajeVehiculo, "fecha_salida"):
        return "fecha_salida"
    if hasattr(ViajeVehiculo, "fecha"):
        return "fecha"
    if hasattr(ViajeVehiculo, "fecha_viaje"):
        return "fecha_viaje"
    # Fallback: asumimos fecha_salida para no romper filtros
    return "fecha_salida"


def _viaje_aplicar_filtro_fecha(qs, fecha_desde, fecha_hasta):
    """
    Aplica filtro de rango de fechas al queryset de ViajeVehiculo,
    usando el campo detectado por _viaje_fecha_field().
    """
    field_name = _viaje_fecha_field()
    if fecha_desde:
        qs = qs.filter(**{f"{field_name}__gte": fecha_desde})
    if fecha_hasta:
        qs = qs.filter(**{f"{field_name}__lte": fecha_hasta})
    return qs


def _viaje_order_by_reciente(qs):
    """
    Ordena los viajes del más reciente al más antiguo,
    intentando usar campo de fecha + hora si existe.
    """
    field_name = _viaje_fecha_field()
    order_fields = []

    # Campo de fecha
    if hasattr(ViajeVehiculo, field_name):
        order_fields.append(f"-{field_name}")

    # Campo de hora (si existe)
    if hasattr(ViajeVehiculo, "hora_salida"):
        order_fields.append("-hora_salida")

    # Siempre caemos en -id como último criterio
    order_fields.append("-id")

    return qs.order_by(*order_fields)


# ============================================
#   MIXINS DE FLOTA (ROLES)
# ============================================


class FlotaAccessMixin(BaseRolMixin):
    """
    Acceso de lectura a flota (vehículos y viajes).

    Habilita:
      - Roles de finanzas (permisos.es_finanzas)
      - CONSULTA_POLITICA (permisos.es_consulta_politica)
      - OPERADOR_SOCIAL (para ver y gestionar viajes sin ver balances generales).
    """

    permission_denied_message = "No tenés permisos para acceder a la sección de flota."

    def test_func(self):
        user = self.request.user
        return (
            permisos.es_finanzas(user)
            or permisos.es_operador_social(user)
            or permisos.es_consulta_politica(user)
        )


class FlotaEditMixin(BaseRolMixin):
    """
    Edición/carga de flota (vehículos, viajes).

    Habilita:
      - Roles de finanzas (permisos.es_finanzas)
      - OPERADOR_SOCIAL (para registrar y editar viajes).
    """

    permission_denied_message = (
        "No tenés permisos para registrar o editar vehículos y viajes."
    )

    def test_func(self):
        user = self.request.user
        return (
            permisos.es_finanzas(user)
            or permisos.es_operador_social(user)
        )


# ============================================
#   VEHÍCULOS
# ============================================


class VehiculoListView(FlotaAccessMixin, ListView):
    """
    Listado de vehículos con filtros y km acumulados.
    Compatible con los filtros antiguos (parámetro ?activos=1/0)
    y nuevos (?estado=activos/inactivos/todos).
    """

    model = Vehiculo
    template_name = "finanzas/vehiculo_list.html"
    context_object_name = "vehiculos"
    paginate_by = 25

    def get_queryset(self):
        # Base: todos los vehículos, con el área resuelta en un solo JOIN
        qs = Vehiculo.objects.select_related("area")

        # Filtros de la tabla
        q = (self.request.GET.get("q") or "").strip()
        area_id = (self.request.GET.get("area") or "").strip()

        # Nuevo filtro por estado + compatibilidad con ?activos=1/0
        estado = (self.request.GET.get("estado") or "").strip()
        activos_param = (self.request.GET.get("activos") or "").strip()

        if activos_param:
            # Compatibilidad con la versión anterior:
            #   activos=1 -> solo activos
            #   activos=0 -> todos
            estado = "activos" if activos_param != "0" else "todos"

        if estado not in ("activos", "inactivos", "todos"):
            estado = "activos"

        if q:
            qs = qs.filter(
                Q(patente__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(area__nombre__icontains=q)
            )

        if area_id:
            qs = qs.filter(area_id=area_id)

        if estado == "activos":
            qs = qs.filter(activo=True)
        elif estado == "inactivos":
            qs = qs.filter(activo=False)
        # "todos" => no filtramos por activo

        # Km acumulados a partir de los viajes (nivel vehículo)
        km_expr = ExpressionWrapper(
            F("viajes_vehiculo__odometro_final")
            - F("viajes_vehiculo__odometro_inicial"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

        qs = qs.annotate(
            km_acumulados_viajes_agg=Sum(
                km_expr,
                filter=Q(
                    viajes_vehiculo__odometro_inicial__isnull=False,
                    viajes_vehiculo__odometro_final__isnull=False,
                ),
            )
        )

        # Activos primero
        return qs.order_by("-activo", "patente", "descripcion")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        estado = (self.request.GET.get("estado") or "").strip()
        activos_param = (self.request.GET.get("activos") or "").strip()
        if activos_param:
            estado = "activos" if activos_param != "0" else "todos"
        if estado not in ("activos", "inactivos", "todos"):
            estado = "activos"

        ctx.update(
            {
                "areas": Area.objects.filter(activo=True).order_by("nombre"),
                "q": (self.request.GET.get("q") or "").strip(),
                "area_actual": (self.request.GET.get("area") or "").strip(),
                "estado_actual": estado,
                # alias de compatibilidad para plantillas antiguas
                "solo_activos": estado == "activos",
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class VehiculoCreateView(FlotaEditMixin, CreateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def form_valid(self, form):
        vehiculo = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(vehiculo, "creado_por") and not getattr(
                vehiculo, "creado_por", None
            ):
                vehiculo.creado_por = user
            if hasattr(vehiculo, "actualizado_por"):
                vehiculo.actualizado_por = user

        vehiculo.save()
        messages.success(self.request, "Vehículo guardado correctamente.")
        return redirect(self.success_url)


class VehiculoUpdateView(FlotaEditMixin, UpdateView):
    model = Vehiculo
    form_class = VehiculoForm
    template_name = "finanzas/vehiculo_form.html"
    success_url = reverse_lazy("finanzas:vehiculo_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def form_valid(self, form):
        vehiculo = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated and hasattr(vehiculo, "actualizado_por"):
            vehiculo.actualizado_por = user

        vehiculo.save()
        messages.success(self.request, "Vehículo actualizado correctamente.")
        return redirect(self.success_url)


class VehiculoDetailView(FlotaAccessMixin, DetailView):
    """
    Ficha del vehículo: datos + uso + consumo.

    - Usa el @property km_recorridos del modelo ViajeVehiculo (no lo pisa con annotate).
    - Calcula totales de km y viajes en Python, coherentes con el dashboard de flota.
    """

    model = Vehiculo
    template_name = "finanzas/vehiculo_detail.html"
    context_object_name = "vehiculo"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vehiculo = self.object

        # Query simple, sin chocar con el @property km_recorridos
        viajes_qs = (
            ViajeVehiculo.objects.filter(vehiculo=vehiculo)
            .select_related("area", "chofer")
            .prefetch_related("beneficiarios")
        )
        viajes_qs = _viaje_order_by_reciente(viajes_qs)
        viajes_lista = list(viajes_qs)

        # Totales a partir del @property km_recorridos
        total_viajes = len(viajes_lista)
        total_km = Decimal("0.00")

        for v in viajes_lista:
            km = getattr(v, "km_recorridos", None)
            if km is None and v.odometro_inicial is not None and v.odometro_final is not None:
                km = v.odometro_final - v.odometro_inicial

            if km:
                try:
                    total_km += Decimal(km)
                except Exception:
                    total_km += Decimal(str(km))

        # Combustible total asociado al vehículo (todos los tiempos, solo GASTOS aprobados)
        mov_qs = Movimiento.objects.filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_combustible=True,
            estado=Movimiento.ESTADO_APROBADO,
            vehiculo=vehiculo,
        )
        total_combustible = mov_qs.aggregate(total=Sum("monto"))["total"] or Decimal(
            "0.00"
        )

        if total_combustible and total_km:
            try:
                costo_por_km = total_combustible / total_km
            except Exception:
                costo_por_km = None
        else:
            costo_por_km = None

        viajes_recientes = viajes_lista[:10]

        ctx.update(
            {
                "total_km_vehiculo": total_km,
                "total_viajes_vehiculo": total_viajes,
                "total_combustible_vehiculo": total_combustible,
                "costo_por_km_vehiculo": costo_por_km,
                "viajes_recientes": viajes_recientes,
                # alias para compatibilidad con la versión anterior
                "total_km_registrados": total_km,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


# ============================================
#   VIAJES DE VEHÍCULOS
# ============================================


class ViajeVehiculoListView(FlotaAccessMixin, ListView):
    model = ViajeVehiculo
    template_name = "finanzas/viaje_vehiculo_list.html"
    context_object_name = "viajes"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            ViajeVehiculo.objects.select_related("vehiculo", "area", "chofer")
            .prefetch_related("beneficiarios")
        )

        vehiculo_id = (self.request.GET.get("vehiculo") or "").strip()
        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        q = (self.request.GET.get("q") or "").strip()
        estado = (self.request.GET.get("estado") or "").strip()

        if vehiculo_id:
            qs = qs.filter(vehiculo_id=vehiculo_id)

        # Filtro de fechas robusto (cubre fecha_salida / fecha / fecha_viaje)
        qs = _viaje_aplicar_filtro_fecha(qs, fecha_desde, fecha_hasta)

        if estado and estado != "TODOS":
            qs = qs.filter(estado=estado)

        if q:
            qs = qs.filter(
                Q(origen__icontains=q)
                | Q(destino__icontains=q)
                | Q(motivo__icontains=q)
                | Q(chofer_nombre__icontains=q)
                | Q(vehiculo__patente__icontains=q)
                | Q(vehiculo__descripcion__icontains=q)
            )

        # Orden reciente consistente con el resto de flota
        qs = _viaje_order_by_reciente(qs)

        # ⚠️ IMPORTANTE:
        # NO anotamos km_recorridos para no chocar con el @property del modelo.
        # El template puede usar viaje.km_recorridos directamente.

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        viajes = self.object_list

        total_km = Decimal("0.00")
        viajes_con_km = 0

        for v in viajes:
            km = getattr(v, "km_recorridos", None)
            if km is None and v.odometro_inicial is not None and v.odometro_final is not None:
                km = v.odometro_final - v.odometro_inicial

            if km:
                try:
                    km_val = Decimal(km)
                except Exception:
                    km_val = Decimal(str(km))
                if km_val > 0:
                    total_km += km_val
                    viajes_con_km += 1

        vehiculo_id = (self.request.GET.get("vehiculo") or "").strip()
        estado = (self.request.GET.get("estado") or "").strip() or "TODOS"

        ctx.update(
            {
                "vehiculos": Vehiculo.objects.filter(activo=True).order_by(
                    "patente", "descripcion"
                ),
                "fecha_desde": _parse_date_or_none(self.request.GET.get("desde")),
                "fecha_hasta": _parse_date_or_none(self.request.GET.get("hasta")),
                "vehiculo_actual": vehiculo_id,
                "estado_actual": estado,
                "q": (self.request.GET.get("q") or "").strip(),
                "total_km_listado": total_km,
                "total_viajes_listado": viajes.count(),
                "total_viajes_con_km_listado": viajes_con_km,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class ViajeVehiculoCreateView(FlotaEditMixin, CreateView):
    model = ViajeVehiculo
    form_class = ViajeVehiculoForm
    template_name = "finanzas/viaje_vehiculo_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if "fecha_salida" not in initial and hasattr(ViajeVehiculo, "fecha_salida"):
            initial["fecha_salida"] = timezone.now().date()
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["tramos_formset"] = ViajeVehiculoTramoFormSet(self.request.POST)
        else:
            ctx["tramos_formset"] = ViajeVehiculoTramoFormSet()
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["tramos_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        viaje = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(viaje, "creado_por") and not getattr(
                viaje, "creado_por", None
            ):
                viaje.creado_por = user
            if hasattr(viaje, "actualizado_por"):
                viaje.actualizado_por = user

        viaje.save()
        form.save_m2m()

        formset.instance = viaje
        formset.save()

        messages.success(self.request, "Viaje registrado correctamente.")
        return redirect("finanzas:viaje_vehiculo_detail", pk=viaje.pk)


class ViajeVehiculoUpdateView(FlotaEditMixin, UpdateView):
    model = ViajeVehiculo
    form_class = ViajeVehiculoForm
    template_name = "finanzas/viaje_vehiculo_form.html"
    context_object_name = "viaje"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["tramos_formset"] = ViajeVehiculoTramoFormSet(
                self.request.POST, instance=self.object
            )
        else:
            ctx["tramos_formset"] = ViajeVehiculoTramoFormSet(instance=self.object)
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["tramos_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        viaje = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated and hasattr(viaje, "actualizado_por"):
            viaje.actualizado_por = user

        viaje.save()
        form.save_m2m()

        formset.instance = viaje
        formset.save()

        messages.success(self.request, "Viaje actualizado correctamente.")
        return redirect("finanzas:viaje_vehiculo_detail", pk=viaje.pk)


class ViajeVehiculoDetailView(FlotaAccessMixin, DetailView):
    """
    Detalle de un viaje de vehículo.
    Muestra el viaje, tramos, cargas de combustible y km recorridos calculados.
    """

    model = ViajeVehiculo
    template_name = "finanzas/viaje_vehiculo_detail.html"
    context_object_name = "viaje"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        viaje = self.object

        km_recorridos = getattr(viaje, "km_recorridos", None)
        if km_recorridos is None and (
            viaje.odometro_inicial is not None and viaje.odometro_final is not None
        ):
            try:
                km_recorridos = Decimal(viaje.odometro_final) - Decimal(
                    viaje.odometro_inicial
                )
            except Exception:
                km_recorridos = None

        tramos = viaje.tramos.order_by("orden", "id")

        # Cargas de combustible vinculadas al viaje (si el related existe)
        cargas = []
        if hasattr(viaje, "cargas_combustible"):
            cargas = viaje.cargas_combustible.select_related("categoria", "area")

        ctx.update(
            {
                "km_recorridos": km_recorridos,
                "km_viaje": km_recorridos,  # alias de compatibilidad
                "tramos": tramos,
                "cargas_combustible": cargas,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


# ============================================
#   RESUMEN DE COMBUSTIBLE POR VEHÍCULO
# ============================================


class FlotaCombustibleResumenView(SoloFinanzasMixin, TemplateView):
    """
    Dashboard de Flota / Consumo de combustible.

    Solo roles de finanzas (no OPERADOR_SOCIAL).

    - Filtra por rango de fechas (desde/hasta) y opcionalmente por vehículo.
    - Calcula km recorridos por vehículo (según odómetro).
    - Agrupa gastos de combustible (Movimientos de combustible aprobados).
    - Expone:
        * viajes_periodo: queryset de viajes del período (opcionalmente filtrado por vehículo)
        * total_viajes_periodo: cantidad de viajes en el período
        * viajes_con_km: cantidad de viajes del período con odómetro cargado
        * resumen_vehiculos: lista de dicts con:
              - vehiculo
              - km_totales
              - cantidad_viajes
              - cantidad_viajes_con_km
              - combustible_monto
              - costo_km (gasto / km, si aplica)
        * totales globales de km y gasto combustible del período
        * insights: destino más frecuente, choferes y beneficiarios top
    """

    template_name = "finanzas/flota_combustible_resumen.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.now().date()

        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        vehiculo_id = (self.request.GET.get("vehiculo") or "").strip()

        # Defaults: mes en curso
        if not fecha_hasta:
            fecha_hasta = hoy
        if not fecha_desde:
            fecha_desde = fecha_hasta.replace(day=1)

        # Base de vehículos activos para la tabla
        vehiculos_base = Vehiculo.objects.filter(activo=True)
        if vehiculo_id:
            vehiculos_base = vehiculos_base.filter(pk=vehiculo_id)

        # -----------------------------
        # VIAJES DEL PERÍODO
        # -----------------------------
        viajes_qs = ViajeVehiculo.objects.select_related("vehiculo", "area")

        viajes_qs = _viaje_aplicar_filtro_fecha(viajes_qs, fecha_desde, fecha_hasta)

        if vehiculo_id:
            viajes_qs = viajes_qs.filter(vehiculo_id=vehiculo_id)

        viajes_qs = _viaje_order_by_reciente(viajes_qs)

        total_viajes_periodo = viajes_qs.count()
        total_km_periodo = Decimal("0.00")
        total_viajes_con_km_periodo = 0

        # Dict maestro por vehículo: se va enriqueciendo con viajes + combustible
        resumen_por_vehiculo: dict[int, dict] = {}

        for viaje in viajes_qs:
            if not viaje.vehiculo_id:
                continue

            data = resumen_por_vehiculo.setdefault(
                viaje.vehiculo_id,
                {
                    "vehiculo": viaje.vehiculo,
                    "km_totales": Decimal("0.00"),
                    "cantidad_viajes": 0,
                    "cantidad_viajes_con_km": 0,
                    "combustible_monto": Decimal("0.00"),
                },
            )

            data["cantidad_viajes"] += 1

            km_viaje = getattr(viaje, "km_recorridos", None)
            if km_viaje is None and (
                viaje.odometro_inicial is not None
                and viaje.odometro_final is not None
            ):
                try:
                    km_viaje = Decimal(viaje.odometro_final) - Decimal(
                        viaje.odometro_inicial
                    )
                except Exception:
                    km_viaje = None

            if km_viaje is not None and km_viaje > 0:
                data["km_totales"] += km_viaje
                data["cantidad_viajes_con_km"] += 1
                total_km_periodo += km_viaje
                total_viajes_con_km_periodo += 1

        # -----------------------------
        # MOVIMIENTOS DE COMBUSTIBLE
        # -----------------------------
        mov_qs = Movimiento.objects.select_related("vehiculo", "categoria").filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_combustible=True,
            estado=Movimiento.ESTADO_APROBADO,
            fecha_operacion__gte=fecha_desde,
            fecha_operacion__lte=fecha_hasta,
        )
        if vehiculo_id:
            mov_qs = mov_qs.filter(vehiculo_id=vehiculo_id)

        total_combustible_monto = Decimal("0.00")

        for mov in mov_qs:
            monto = mov.monto or Decimal("0.00")
            total_combustible_monto += monto

            if not mov.vehiculo_id:
                # Suma al total global, pero no se vincula a un vehículo puntual
                continue

            data = resumen_por_vehiculo.setdefault(
                mov.vehiculo_id,
                {
                    "vehiculo": mov.vehiculo,
                    "km_totales": Decimal("0.00"),
                    "cantidad_viajes": 0,
                    "cantidad_viajes_con_km": 0,
                    "combustible_monto": Decimal("0.00"),
                },
            )
            data["combustible_monto"] += monto

        # -----------------------------
        # INSIGHTS: DESTINO / CHOFER / BENEFICIARIOS
        # -----------------------------
        # Destino más frecuente
        dest_counter = Counter()
        for row in viajes_qs.values("destino"):
            dest = (row["destino"] or "").strip()
            if dest:
                dest_counter[dest] += 1

        top_destino_data = None
        if dest_counter and total_viajes_periodo:
            dest, cant = dest_counter.most_common(1)[0]
            top_destino_data = {
                "destino": dest,
                "cantidad": cant,
                "porcentaje": (cant / total_viajes_periodo) * 100,
            }

        # Choferes con más viajes (censo + texto)
        chofer_counter = Counter()
        for row in viajes_qs.values(
            "chofer_id",
            "chofer__apellido",
            "chofer__nombre",
            "chofer_nombre",
        ):
            if row["chofer_id"]:
                nombre = f"{row['chofer__apellido'] or ''} {row['chofer__nombre'] or ''}".strip()
                if not nombre:
                    nombre = "Chofer sin nombre"
            elif row["chofer_nombre"]:
                nombre = row["chofer_nombre"].strip()
            else:
                nombre = "Sin chofer cargado"

            chofer_counter[nombre] += 1

        top_choferes_data = []
        if chofer_counter and total_viajes_periodo:
            for nombre, cant in chofer_counter.most_common(3):
                top_choferes_data.append(
                    {
                        "nombre": nombre,
                        "cantidad": cant,
                        "porcentaje": (cant / total_viajes_periodo) * 100,
                    }
                )

        # Beneficiarios más trasladados (solo censo, M2M)
        benef_counter = Counter()
        for row in viajes_qs.values(
            "beneficiarios__id",
            "beneficiarios__apellido",
            "beneficiarios__nombre",
        ):
            if not row["beneficiarios__id"]:
                continue
            nombre = f"{row['beneficiarios__apellido'] or ''} {row['beneficiarios__nombre'] or ''}".strip()
            if not nombre:
                nombre = f"ID {row['beneficiarios__id']}"
            benef_counter[nombre] += 1

        top_beneficiarios_data = []
        if benef_counter and total_viajes_periodo:
            for nombre, cant in benef_counter.most_common(3):
                top_beneficiarios_data.append(
                    {
                        "nombre": nombre,
                        "cantidad": cant,
                        "porcentaje": (cant / total_viajes_periodo) * 100,
                    }
                )

        # -----------------------------
        # ARMADO DEL RESUMEN POR VEHÍCULO
        # -----------------------------
        resumen_vehiculos = []
        for vehiculo in vehiculos_base.order_by("patente", "descripcion"):
            data = resumen_por_vehiculo.get(
                vehiculo.id,
                {
                    "vehiculo": vehiculo,
                    "km_totales": Decimal("0.00"),
                    "cantidad_viajes": 0,
                    "cantidad_viajes_con_km": 0,
                    "combustible_monto": Decimal("0.00"),
                },
            )
            km_tot = data["km_totales"]
            gasto = data["combustible_monto"]

            costo_km = None
            if km_tot > 0 and gasto > 0:
                try:
                    costo_km = gasto / km_tot
                except Exception:
                    costo_km = None

            data["costo_km"] = costo_km
            resumen_vehiculos.append(data)

        # Ordenamos por km descendente (y luego por gasto)
        resumen_vehiculos.sort(
            key=lambda e: (
                e["km_totales"],
                e.get("combustible_monto") or Decimal("0.00"),
            ),
            reverse=True,
        )

        # Costo promedio global
        costo_promedio_km = None
        if total_combustible_monto and total_km_periodo:
            try:
                costo_promedio_km = total_combustible_monto / total_km_periodo
            except Exception:
                costo_promedio_km = None

        # ============================
        #   CONTEXTO PARA EL TEMPLATE
        # ============================
        ctx.update(
            {
                "hoy": hoy,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "vehiculo_actual": vehiculo_id,
                "vehiculos": vehiculos_base.order_by("patente", "descripcion"),
                "resumen_vehiculos": resumen_vehiculos,
                # KPIs globales (nombres nuevos y alias para compatibilidad)
                "total_combustible_monto": total_combustible_monto,
                "total_km_periodo": total_km_periodo,
                "total_viajes_periodo": total_viajes_periodo,
                "viajes_con_km": total_viajes_con_km_periodo,
                "costo_promedio_km": costo_promedio_km,
                # aliases estilo versión anterior
                "total_combustible": total_combustible_monto,
                "total_km": total_km_periodo,
                "total_viajes": total_viajes_periodo,
                # Insights
                "top_destino": top_destino_data,
                "top_choferes": top_choferes_data,
                "top_beneficiarios": top_beneficiarios_data,
                # Dataset de viajes por si lo querés usar en el template
                "viajes_periodo": viajes_qs,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx
