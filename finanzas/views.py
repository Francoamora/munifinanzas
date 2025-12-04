from datetime import datetime
from decimal import Decimal
import json

from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count, Q, F
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import (
    ListView,
    CreateView,
    DetailView,
    UpdateView,
    TemplateView,
)
from django.forms import inlineformset_factory
from django.core.serializers.json import DjangoJSONEncoder
from django.apps import apps

from .forms import (
    MovimientoForm,
    BeneficiarioForm,
    OrdenPagoForm,
    OrdenPagoLineaFormSet,
    # Órdenes de trabajo
    OrdenTrabajoForm,
    OrdenTrabajoMaterialFormSet,
    AdjuntoOrdenTrabajoForm,
)
from .models import (
    Movimiento,
    Categoria,
    Area,
    Cuenta,
    Proveedor,
    Beneficiario,
    Vehiculo,
    OrdenPago,
    # Órdenes de trabajo
    OrdenTrabajo,
    OrdenTrabajoMaterial,
    AdjuntoOrdenTrabajo,
    # Flota / viajes
    ViajeVehiculo,
)


# ===== AGENDA (nuevo módulo) =====


def _get_tarea_model():
    """
    Devuelve el modelo Tarea de la app agenda de forma segura,
    evitando imports circulares. Si no existe o la app no está
    lista (por ejemplo durante migraciones), devuelve None.
    """
    try:
        return apps.get_model("agenda", "Tarea")
    except Exception:
        return None


# ===== FORMSETS ADJUNTOS OT =====

AdjuntoOrdenTrabajoFormSet = inlineformset_factory(
    OrdenTrabajo,
    AdjuntoOrdenTrabajo,
    form=AdjuntoOrdenTrabajoForm,
    extra=1,
    can_delete=True,
)


# ========= ROLES Y PERMISOS =========


def _user_in_groups(user, group_names):
    """Helper: verifica si el usuario pertenece a alguno de los grupos indicados."""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name__in=group_names).exists()


def es_admin_sistema(user):
    """
    ADMIN_SISTEMA:
      - superusuario de Django
      - o usuario en grupo "ADMIN_SISTEMA"
    """
    if not user.is_authenticated:
        return False
    return user.is_superuser or _user_in_groups(user, ["ADMIN_SISTEMA"])


def es_staff_finanzas(user):
    """
    STAFF_FINANZAS:
      - ADMIN_SISTEMA
      - o grupo "STAFF_FINANZAS"
      - fallback de compatibilidad:
        usuario is_staff sin otros roles específicos (operadores/consulta)
    """
    if not user.is_authenticated:
        return False

    if es_admin_sistema(user):
        return True

    if _user_in_groups(user, ["STAFF_FINANZAS"]):
        return True

    # Compatibilidad: si hoy ya usás is_staff y todavía no creaste grupos,
    # tratamos a esos usuarios como staff financiero mientras no tengan
    # asignado un rol más acotado.
    if user.is_staff and not _user_in_groups(
        user,
        ["OPERADOR_FINANZAS", "OPERADOR_SOCIAL", "CONSULTA_POLITICA"],
    ):
        return True

    return False


def es_operador_finanzas(user):
    """
    OPERADOR_FINANZAS:
      - grupo "OPERADOR_FINANZAS"
      - o cualquier STAFF_FINANZAS / ADMIN_SISTEMA (>= operador)
    """
    if not user.is_authenticated:
        return False
    if es_staff_finanzas(user):
        return True
    return _user_in_groups(user, ["OPERADOR_FINANZAS"])


def es_operador_social(user):
    """
    OPERADOR_SOCIAL:
      - grupo "OPERADOR_SOCIAL"
      - o cualquier STAFF_FINANZAS
    """
    if not user.is_authenticated:
        return False
    if es_staff_finanzas(user):
        return True
    return _user_in_groups(user, ["OPERADOR_SOCIAL"])


def es_consulta_politica(user):
    """
    CONSULTA_POLITICA:
      - grupo "CONSULTA_POLITICA"
    """
    if not user.is_authenticated:
        return False
    return _user_in_groups(user, ["CONSULTA_POLITICA"])


def _roles_ctx(user):
    """
    Helper centralizado para inyectar al contexto los flags de rol.
    Así no repetimos lo mismo en todas las vistas.
    """
    return {
        "rol_staff_finanzas": es_staff_finanzas(user),
        "rol_operador_finanzas": es_operador_finanzas(user),
        "rol_operador_social": es_operador_social(user),
        "rol_consulta_politica": es_consulta_politica(user),
    }


# ========= HELPERS =========


def _parse_date_or_none(value: str):
    """
    Convierte 'YYYY-MM-DD' -> date.
    Si viene vacío o inválido, devuelve None.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _resolver_proveedor_y_beneficiario(form, movimiento):
    """
    Reutiliza la lógica de alta/edición para vincular proveedor y beneficiario
    a partir de los campos de formulario (CUIT / DNI + datos básicos).
    No guarda el movimiento; solo ajusta sus FKs.
    """
    cleaned = form.cleaned_data

    # ===== PROVEEDOR por CUIT =====
    cuit = (cleaned.get("proveedor_cuit") or "").strip()
    nombre_proveedor = (cleaned.get("proveedor_nombre") or "").strip()

    if cuit or nombre_proveedor:
        proveedor = None
        if cuit:
            proveedor, created = Proveedor.objects.get_or_create(
                cuit=cuit,
                defaults={"nombre": nombre_proveedor or ""},
            )
            if not created and nombre_proveedor and not proveedor.nombre:
                proveedor.nombre = nombre_proveedor
                proveedor.save()
        else:
            proveedor, _ = Proveedor.objects.get_or_create(
                nombre=nombre_proveedor or "Proveedor sin nombre"
            )
        movimiento.proveedor = proveedor

    # ===== BENEFICIARIO / PERSONA por DNI =====
    dni = (cleaned.get("beneficiario_dni") or "").strip()
    nombre_beneficiario = (cleaned.get("beneficiario_nombre") or "").strip()
    benef_direccion = (cleaned.get("beneficiario_direccion") or "").strip()
    benef_barrio = (cleaned.get("beneficiario_barrio") or "").strip()

    beneficiario = None
    if dni or nombre_beneficiario:
        if dni:
            apellido = ""
            nombre = ""
            if nombre_beneficiario:
                partes = nombre_beneficiario.strip().split(" ", 1)
                if len(partes) == 2:
                    apellido, nombre = partes[0], partes[1]
                else:
                    nombre = nombre_beneficiario

            beneficiario, created = Beneficiario.objects.get_or_create(
                dni=dni,
                defaults={
                    "nombre": nombre or nombre_beneficiario or "",
                    "apellido": apellido or "",
                    "direccion": benef_direccion or "",
                    "barrio": benef_barrio or "",
                },
            )

            if not created:
                updated = False
                if benef_direccion and not beneficiario.direccion:
                    beneficiario.direccion = benef_direccion
                    updated = True
                if benef_barrio and not beneficiario.barrio:
                    beneficiario.barrio = benef_barrio
                    updated = True
                if updated:
                    beneficiario.save()
        else:
            beneficiario, _ = Beneficiario.objects.get_or_create(
                nombre=nombre_beneficiario or "Sin nombre",
                apellido="",
            )
            if benef_direccion and not beneficiario.direccion:
                beneficiario.direccion = benef_direccion
            if benef_barrio and not beneficiario.barrio:
                beneficiario.barrio = benef_barrio
            beneficiario.save()

        movimiento.beneficiario = beneficiario


def _flota_metrics_mes(hoy, primer_dia_mes):
    """
    Métricas de flota para el mes actual.

    Devuelve (viajes_mes, total_km_mes).

    - Intenta usar el modelo ViajeVehiculo si existe.
    - No rompe si el modelo cambia o aún no está migrado.
    """
    viajes_mes = 0
    total_km_mes = 0

    try:
        # import local para evitar problemas en migraciones
        from .models import ViajeVehiculo as ViajeModel
    except Exception:
        return 0, 0

    viajes_qs = ViajeModel.objects.all()

    # Intentamos detectar campo de fecha (prioridad: fecha_salida, luego otros nombres legacy)
    if hasattr(ViajeModel, "fecha_salida"):
        viajes_qs = viajes_qs.filter(
            fecha_salida__gte=primer_dia_mes,
            fecha_salida__lte=hoy,
        )
    elif hasattr(ViajeModel, "fecha"):
        viajes_qs = viajes_qs.filter(fecha__gte=primer_dia_mes, fecha__lte=hoy)
    elif hasattr(ViajeModel, "fecha_viaje"):
        viajes_qs = viajes_qs.filter(
            fecha_viaje__gte=primer_dia_mes,
            fecha_viaje__lte=hoy,
        )

    viajes_mes = viajes_qs.count()

    # Kilómetros recorridos
    try:
        if hasattr(ViajeModel, "km_recorridos"):
            total_km_mes = sum(
                (getattr(v, "km_recorridos", 0) or 0) for v in viajes_qs
            )
        else:
            total_km = Decimal("0.00")
            for v in viajes_qs:
                ini = getattr(v, "odometro_inicial", None)
                fin = getattr(v, "odometro_final", None)
                if ini is not None and fin is not None:
                    diff = fin - ini
                    if diff > 0:
                        total_km += diff
            total_km_mes = total_km
    except Exception:
        total_km_mes = 0

    return viajes_mes, total_km_mes


# ========= MIXINS DE ACCESO =========


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Acceso restringido a STAFF_FINANZAS / ADMIN_SISTEMA."""

    def test_func(self):
        return es_staff_finanzas(self.request.user)


class OperadorFinanzasRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Vistas que pueden usar STAFF_FINANZAS y OPERADOR_FINANZAS."""

    def test_func(self):
        return es_operador_finanzas(self.request.user)


class PersonaCensoAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Vistas del censo de personas:
    - STAFF_FINANZAS / ADMIN_SISTEMA
    - OPERADOR_FINANZAS
    - OPERADOR_SOCIAL
    - CONSULTA_POLITICA
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_operador_social(user)
            or es_consulta_politica(user)
        )


class PersonaCensoEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Edición del censo de personas:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    - OPERADOR_SOCIAL
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_operador_social(user)
        )


class DashboardAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Acceso a Dashboard y Balances:
    - STAFF_FINANZAS / ADMIN_SISTEMA
    - CONSULTA_POLITICA (solo lectura)
    """

    def test_func(self):
        user = self.request.user
        return es_staff_finanzas(user) or es_consulta_politica(user)


class MovimientosAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Listado / detalle de movimientos:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    - CONSULTA_POLITICA (solo lectura)
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_consulta_politica(user)
        )


class OrdenPagoAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Listado / detalle de Órdenes de pago:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    - CONSULTA_POLITICA (solo lectura)
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_consulta_politica(user)
        )


class OrdenPagoEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Alta / edición de Órdenes de pago:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    """

    def test_func(self):
        user = self.request.user
        return es_staff_finanzas(user) or es_operador_finanzas(user)


class FlotaAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Flota / Vehículos / Viajes:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    - OPERADOR_SOCIAL (por si usan viajes para traslados sociales)
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_operador_social(user)
        )


class FlotaEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Edición Flota / Viajes:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    """

    def test_func(self):
        user = self.request.user
        return es_staff_finanzas(user) or es_operador_finanzas(user)


class OrdenTrabajoAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Órdenes de trabajo:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    - CONSULTA_POLITICA (solo lectura)
    """

    def test_func(self):
        user = self.request.user
        return (
            es_staff_finanzas(user)
            or es_operador_finanzas(user)
            or es_consulta_politica(user)
        )


class OrdenTrabajoEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Alta / edición de órdenes de trabajo:
    - STAFF_FINANZAS
    - OPERADOR_FINANZAS
    """

    def test_func(self):
        user = self.request.user
        return es_staff_finanzas(user) or es_operador_finanzas(user)


# ========= HOME / TABLERO PRINCIPAL =========


class HomeView(LoginRequiredMixin, TemplateView):
    """Tablero de inicio para cualquier usuario autenticado."""

    template_name = "finanzas/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)

        movimientos_mes = Movimiento.objects.filter(
            estado=Movimiento.ESTADO_APROBADO,
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )

        total_ingresos_mes = (
            movimientos_mes.filter(tipo=Movimiento.TIPO_INGRESO)
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )
        total_gastos_mes = (
            movimientos_mes.filter(tipo=Movimiento.TIPO_GASTO)
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )
        saldo_mes = total_ingresos_mes - total_gastos_mes

        ayudas_mes = (
            movimientos_mes.filter(
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_ayuda_social=True,
            )
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )

        personal_mes = (
            movimientos_mes.filter(
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_personal=True,
            )
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )

        servicios_mes = (
            movimientos_mes.filter(
                tipo=Movimiento.TIPO_INGRESO,
                categoria__es_servicio=True,
            )
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )

        # Combustible del mes (gasto en categorías marcadas como combustible)
        combustible_mes = (
            movimientos_mes.filter(
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_combustible=True,
            )
            .aggregate(total=Sum("monto"))["total"]
            or 0
        )

        # Métricas de flota (viajes / km) usando helper robusto
        try:
            viajes_mes, total_km_mes = _flota_metrics_mes(hoy, primer_dia_mes)
        except Exception:
            viajes_mes, total_km_mes = 0, 0

        ultimos_movimientos = (
            Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO)
            .select_related("categoria", "area")
            .order_by("-fecha_operacion", "-id")[:5]
        )

        # Órdenes de pago pendientes (no pagadas ni anuladas)
        ordenes_pendientes_qs = OrdenPago.objects.exclude(
            estado__in=[OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA]
        )
        cantidad_ordenes_pendientes = ordenes_pendientes_qs.count()
        monto_ordenes_pendientes = Decimal("0.00")
        for op in ordenes_pendientes_qs:
            monto_ordenes_pendientes += op.total_monto

        # ===== Agenda: pendientes del usuario (badge en home/header) =====
        user = self.request.user
        tareas_pendientes_usuario = 0
        TareaModel = _get_tarea_model()
        if TareaModel is not None:
            tareas_pendientes_usuario = TareaModel.objects.filter(
                responsable=user,
                estado__in=[
                    TareaModel.ESTADO_PENDIENTE,
                    TareaModel.ESTADO_EN_PROCESO,
                ],
            ).count()

        ctx.update(
            {
                "hoy": hoy,
                "primer_dia_mes": primer_dia_mes,
                "total_ingresos_mes": total_ingresos_mes,
                "total_gastos_mes": total_gastos_mes,
                "saldo_mes": saldo_mes,
                "ayudas_mes": ayudas_mes,
                "personal_mes": personal_mes,
                "servicios_mes": servicios_mes,
                "combustible_mes": combustible_mes,
                "viajes_mes": viajes_mes,
                "total_km_mes": total_km_mes,
                "ultimos_movimientos": ultimos_movimientos,
                "cantidad_ordenes_pendientes": cantidad_ordenes_pendientes,
                "total_ordenes_pendientes": monto_ordenes_pendientes,
                "tareas_pendientes_usuario": tareas_pendientes_usuario,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


# ======= MOVIMIENTOS =======


class MovimientoListView(MovimientosAccessMixin, ListView):
    model = Movimiento
    template_name = "finanzas/movimiento_list.html"
    context_object_name = "movimientos"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("categoria", "area", "proveedor", "beneficiario")
        )
        user = self.request.user

        tipo = (self.request.GET.get("tipo") or "").strip()
        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        q = (self.request.GET.get("q") or "").strip()

        estado = (self.request.GET.get("estado") or Movimiento.ESTADO_APROBADO).strip()

        if es_consulta_politica(user):
            estado = Movimiento.ESTADO_APROBADO

        if tipo in [
            Movimiento.TIPO_INGRESO,
            Movimiento.TIPO_GASTO,
            Movimiento.TIPO_TRANSFERENCIA,
        ]:
            qs = qs.filter(tipo=tipo)

        if fecha_desde:
            qs = qs.filter(fecha_operacion__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_operacion__lte=fecha_hasta)

        if q:
            qs = qs.filter(
                Q(descripcion__icontains=q)
                | Q(categoria__nombre__icontains=q)
                | Q(beneficiario__nombre__icontains=q)
                | Q(beneficiario__apellido__icontains=q)
                | Q(proveedor__nombre__icontains=q)
                | Q(programa_ayuda_texto__icontains=q)
            )

        if estado != "TODOS" and estado in [
            Movimiento.ESTADO_BORRADOR,
            Movimiento.ESTADO_APROBADO,
            Movimiento.ESTADO_RECHAZADO,
        ]:
            qs = qs.filter(estado=estado)

        return qs.order_by("-fecha_operacion", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        estado = (self.request.GET.get("estado") or Movimiento.ESTADO_APROBADO).strip()
        if es_consulta_politica(user):
            estado = Movimiento.ESTADO_APROBADO

        q = (self.request.GET.get("q") or "").strip()

        hay_filtros = bool(
            self.request.GET.get("tipo")
            or self.request.GET.get("desde")
            or self.request.GET.get("hasta")
            or q
            or estado
            in [Movimiento.ESTADO_BORRADOR, Movimiento.ESTADO_RECHAZADO, "TODOS"]
        )

        totales = self.object_list.aggregate(
            total_ingresos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO)),
            total_gastos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO)),
        )
        total_ingresos = totales["total_ingresos"] or 0
        total_gastos = totales["total_gastos"] or 0

        ctx.update(
            {
                "hoy": timezone.now().date(),
                "tipos": Movimiento.TIPO_CHOICES,
                "estado_actual": estado,
                "q": q,
                "hay_filtros": hay_filtros,
                "total_ingresos_filtro": total_ingresos,
                "total_gastos_filtro": total_gastos,
                "saldo_filtro": total_ingresos - total_gastos,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class MovimientoCreateView(OperadorFinanzasRequiredMixin, CreateView):
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"
    success_url = reverse_lazy("finanzas:movimiento_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = {str(c.id): c.tipo for c in Categoria.objects.all()}
        ctx["categoria_tipos_json"] = json.dumps(data, cls=DjangoJSONEncoder)
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def get_success_url(self):
        # Evitamos depender de self.object para no disparar el bug de NoneType.__dict__
        return str(self.success_url)

    @transaction.atomic
    def form_valid(self, form):
        movimiento = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(movimiento, "creado_por") and not movimiento.creado_por:
                movimiento.creado_por = user
            if hasattr(movimiento, "actualizado_por"):
                movimiento.actualizado_por = user

        accion = (self.request.POST.get("accion") or "borrador").strip()

        if es_staff_finanzas(user) and accion == "aprobar":
            movimiento.estado = Movimiento.ESTADO_APROBADO
            mensaje = "Movimiento guardado y aprobado correctamente."
        else:
            movimiento.estado = Movimiento.ESTADO_BORRADOR
            if es_staff_finanzas(user):
                mensaje = "Movimiento guardado como borrador."
            else:
                mensaje = (
                    "Movimiento guardado como borrador. Un responsable de finanzas "
                    "debe aprobarlo para que impacte en balances."
                )

        _resolver_proveedor_y_beneficiario(form, movimiento)

        movimiento.save()
        # Dejamos self.object seteado por prolijidad
        self.object = movimiento

        messages.success(self.request, mensaje)
        return redirect(self.get_success_url())


class MovimientoUpdateView(OperadorFinanzasRequiredMixin, UpdateView):
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"
    context_object_name = "movimiento"
    success_url = reverse_lazy("finanzas:movimiento_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = {str(c.id): c.tipo for c in Categoria.objects.all()}
        ctx["categoria_tipos_json"] = json.dumps(data, cls=DjangoJSONEncoder)
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    def get_success_url(self):
        # URL fija, no depende de self.object
        return str(self.success_url)

    @transaction.atomic
    def form_valid(self, form):
        original = self.get_object()
        movimiento = form.save(commit=False)
        user = self.request.user
        es_staff = es_staff_finanzas(user)

        if original.estado != Movimiento.ESTADO_BORRADOR and not es_staff:
            messages.error(
                self.request,
                "Solo el staff financiero puede editar movimientos aprobados o rechazados.",
            )
            return redirect(self.get_success_url())

        if hasattr(movimiento, "creado_por"):
            movimiento.creado_por = getattr(original, "creado_por", None)
        if user.is_authenticated and hasattr(movimiento, "actualizado_por"):
            movimiento.actualizado_por = user

        accion = (self.request.POST.get("accion") or "").strip()

        if original.estado == Movimiento.ESTADO_BORRADOR:
            if es_staff and accion == "aprobar":
                movimiento.estado = Movimiento.ESTADO_APROBADO
                mensaje = "Movimiento guardado y aprobado correctamente."
            else:
                movimiento.estado = Movimiento.ESTADO_BORRADOR
                if es_staff:
                    mensaje = "Movimiento guardado como borrador."
                else:
                    mensaje = (
                        "Movimiento guardado como borrador. Solo el staff financiero "
                        "puede aprobarlo para que impacte en balances."
                    )

            _resolver_proveedor_y_beneficiario(form, movimiento)

        else:
            movimiento.estado = original.estado

            campos_bloqueados = [
                "tipo",
                "fecha_operacion",
                "monto",
                "cuenta_origen_texto",
                "cuenta_destino_texto",
            ]
            for nombre in campos_bloqueados:
                setattr(movimiento, nombre, getattr(original, nombre))

            for nombre_fk in ["cuenta_origen", "cuenta_destino"]:
                if hasattr(original, nombre_fk):
                    setattr(movimiento, nombre_fk, getattr(original, nombre_fk))

            _resolver_proveedor_y_beneficiario(form, movimiento)

            mensaje = (
                "Cambios guardados. Se actualizaron la clasificación contable, "
                "el área y otros datos descriptivos del movimiento."
            )

        movimiento.save()
        self.object = movimiento

        messages.success(self.request, mensaje)
        return redirect(self.get_success_url())


# ========= DETALLE DE MOVIMIENTO =========


class MovimientoDetailView(MovimientosAccessMixin, DetailView):
    model = Movimiento
    template_name = "finanzas/movimiento_detail.html"
    context_object_name = "movimiento"

    def get_queryset(self):
        return (
            Movimiento.objects.select_related(
                "categoria",
                "area",
                "cuenta_origen",
                "cuenta_destino",
                "proveedor",
                "beneficiario",
                "vehiculo",
                "programa_ayuda",
                "creado_por",
                "actualizado_por",
            )
            .prefetch_related("adjuntos")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = self.object
        user = self.request.user
        ctx.update(
            {
                "es_ingreso": m.tipo == Movimiento.TIPO_INGRESO,
                "es_gasto": m.tipo == Movimiento.TIPO_GASTO,
                "es_transferencia": m.tipo == Movimiento.TIPO_TRANSFERENCIA,
                # Flags robustos: si no existen en el modelo, no rompen
                "es_pago_servicio": getattr(m, "es_pago_servicio", False),
                "es_ayuda_social": getattr(m, "es_ayuda_social", False),
                "es_gasto_personal": getattr(m, "es_gasto_personal", False),
                "es_combustible": getattr(m, "es_combustible", False),
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class MovimientoCambiarEstadoView(StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk, accion):
        movimiento = get_object_or_404(Movimiento, pk=pk)

        estado_anterior = movimiento.estado

        if accion == "aprobar":
            nuevo_estado = Movimiento.ESTADO_APROBADO
            mensaje_ok = (
                "Movimiento aprobado correctamente. Desde este momento impacta "
                "en balances y resúmenes."
            )
        elif accion == "rechazar":
            nuevo_estado = Movimiento.ESTADO_RECHAZADO
            mensaje_ok = (
                "Movimiento marcado como RECHAZADO. No impacta en balances ni resúmenes."
            )
        elif accion == "borrador":
            nuevo_estado = Movimiento.ESTADO_BORRADOR
            mensaje_ok = (
                "Movimiento devuelto a BORRADOR. Podés revisarlo antes de aprobarlo."
            )
        else:
            messages.error(request, "Acción de estado no reconocida.")
            return redirect("finanzas:movimiento_detail", pk=movimiento.pk)

        if estado_anterior == nuevo_estado:
            messages.info(request, "El movimiento ya estaba en ese estado.")
            return redirect("finanzas:movimiento_detail", pk=movimiento.pk)

        movimiento.estado = nuevo_estado
        if request.user.is_authenticated and hasattr(movimiento, "actualizado_por"):
            movimiento.actualizado_por = request.user
        movimiento.save()

        messages.success(request, mensaje_ok)
        return redirect("finanzas:movimiento_detail", pk=movimiento.pk)


# ========= ORDEN DE PAGO / FACTURA (LEGACY) =========


class MovimientoOrdenPagoView(StaffRequiredMixin, DetailView):
    model = Movimiento
    template_name = "finanzas/orden_pago.html"
    context_object_name = "movimiento"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        movimiento = self.object

        if movimiento.estado != Movimiento.ESTADO_APROBADO:
            messages.error(
                request,
                "Solo se puede emitir orden de pago para movimientos en estado APROBADO.",
            )
            return redirect("finanzas:movimiento_detail", pk=movimiento.pk)

        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        movimiento = self.object

        if movimiento.estado != Movimiento.ESTADO_APROBADO:
            messages.error(
                request,
                "Solo se pueden cargar datos de orden de pago para movimientos APROBADOS.",
            )
            return redirect("finanzas:movimiento_detail", pk=movimiento.pk)

        condicion = (request.POST.get("condicion_pago") or "").strip()
        medio = (request.POST.get("medio_pago") or "").strip()
        orden_fecha_raw = (request.POST.get("orden_pago_fecha") or "").strip()
        orden_obs = (request.POST.get("orden_pago_observaciones") or "").strip()

        factura_tipo = (request.POST.get("factura_tipo") or "").strip()
        factura_numero = (request.POST.get("factura_numero") or "").strip()
        factura_fecha_raw = (request.POST.get("factura_fecha") or "").strip()

        # Campos legacy: solo los tocamos si existen en el modelo
        if hasattr(movimiento, "condicion_pago"):
            movimiento.condicion_pago = condicion
        if hasattr(movimiento, "medio_pago"):
            movimiento.medio_pago = medio
        if hasattr(movimiento, "orden_pago_observaciones"):
            movimiento.orden_pago_observaciones = orden_obs
        if hasattr(movimiento, "factura_tipo"):
            movimiento.factura_tipo = factura_tipo
        if hasattr(movimiento, "factura_numero"):
            movimiento.factura_numero = factura_numero

        orden_fecha = _parse_date_or_none(orden_fecha_raw)
        if orden_fecha_raw and not orden_fecha:
            messages.warning(
                request,
                "La fecha de la orden de pago no tiene un formato válido (aaaa-mm-dd).",
            )
        if hasattr(movimiento, "orden_pago_fecha"):
            movimiento.orden_pago_fecha = orden_fecha

        factura_fecha = _parse_date_or_none(factura_fecha_raw)
        if factura_fecha_raw and not factura_fecha:
            messages.warning(
                request,
                "La fecha de la factura no tiene un formato válido (aaaa-mm-dd).",
            )
        if hasattr(movimiento, "factura_fecha"):
            movimiento.factura_fecha = factura_fecha

        if request.user.is_authenticated and hasattr(movimiento, "actualizado_por"):
            movimiento.actualizado_por = request.user

        movimiento.save()
        messages.success(
            request,
            "Datos de orden de pago y factura actualizados correctamente.",
        )
        return redirect("finanzas:movimiento_orden_pago", pk=movimiento.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = self.object
        user = self.request.user

        cargado_por = (
            m.creado_por.get_full_name() if getattr(m, "creado_por", None) else ""
        )
        autorizado_por = (
            m.actualizado_por.get_full_name()
            if getattr(m, "actualizado_por", None)
            else ""
        )

        ctx.update(
            {
                "cargado_por": cargado_por
                or (m.creado_por.username if getattr(m, "creado_por", None) else ""),
                "autorizado_por": autorizado_por
                or (
                    m.actualizado_por.username
                    if getattr(m, "actualizado_por", None)
                    else ""
                ),
                "CONDICION_PAGO_CHOICES": getattr(
                    Movimiento, "CONDICION_PAGO_CHOICES", []
                ),
                "MEDIO_PAGO_CHOICES": getattr(Movimiento, "MEDIO_PAGO_CHOICES", []),
                "FACTURA_TIPO_CHOICES": getattr(
                    Movimiento, "FACTURA_TIPO_CHOICES", []
                ),
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


# ======= ÓRDENES DE PAGO =======


class OrdenPagoListView(OrdenPagoAccessMixin, ListView):
    model = OrdenPago
    template_name = "finanzas/orden_pago_list.html"
    context_object_name = "ordenes"
    paginate_by = 25

    def get_queryset(self):
        qs = OrdenPago.objects.select_related("proveedor", "area")
        estado = (self.request.GET.get("estado") or "PENDIENTES").strip()
        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        q = (self.request.GET.get("q") or "").strip()

        if estado == "PENDIENTES":
            qs = qs.exclude(
                estado__in=[OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA]
            )
        elif estado == "TODAS":
            pass
        elif estado in [
            OrdenPago.ESTADO_BORRADOR,
            OrdenPago.ESTADO_AUTORIZADA,
            OrdenPago.ESTADO_FACTURADA,
            OrdenPago.ESTADO_PAGADA,
            OrdenPago.ESTADO_ANULADA,
        ]:
            qs = qs.filter(estado=estado)

        if fecha_desde:
            qs = qs.filter(fecha_orden__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_orden__lte=fecha_hasta)

        if q:
            qs = qs.filter(
                Q(numero__icontains=q)
                | Q(proveedor_nombre__icontains=q)
                | Q(proveedor_cuit__icontains=q)
                | Q(observaciones__icontains=q)
            )

        return qs.order_by("-fecha_orden", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        estado = (self.request.GET.get("estado") or "PENDIENTES").strip()
        q = (self.request.GET.get("q") or "").strip()
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)

        hay_filtros = bool(
            self.request.GET.get("desde")
            or self.request.GET.get("hasta")
            or q
            or estado not in ["PENDIENTES"]
        )

        # Monto total del listado actual
        total_monto_listado = Decimal("0.00")
        for op in self.object_list:
            total_monto_listado += op.total_monto

        # Resumen global: borradores, autorizadas y pagadas este mes
        borradores_qs = OrdenPago.objects.filter(estado=OrdenPago.ESTADO_BORRADOR)
        autorizadas_qs = OrdenPago.objects.filter(estado=OrdenPago.ESTADO_AUTORIZADA)
        pagadas_mes_qs = OrdenPago.objects.filter(
            estado=OrdenPago.ESTADO_PAGADA,
            fecha_orden__gte=primer_dia_mes,
            fecha_orden__lte=hoy,
        )

        resumen_borradores_cantidad = borradores_qs.count()
        resumen_autorizadas_cantidad = autorizadas_qs.count()
        resumen_pagadas_mes_cantidad = pagadas_mes_qs.count()

        resumen_borradores_monto = (
            borradores_qs.aggregate(total=Sum("lineas__monto"))["total"]
            or Decimal("0.00")
        )
        resumen_autorizadas_monto = (
            autorizadas_qs.aggregate(total=Sum("lineas__monto"))["total"]
            or Decimal("0.00")
        )
        resumen_pagadas_mes_monto = (
            pagadas_mes_qs.aggregate(total=Sum("lineas__monto"))["total"]
            or Decimal("0.00")
        )

        ctx.update(
            {
                "hoy": hoy,
                "estado_actual": estado,
                "q": q,
                "hay_filtros": hay_filtros,
                "total_monto_listado": total_monto_listado,
                "ESTADO_CHOICES": OrdenPago.ESTADO_CHOICES,
                "resumen_borradores_cantidad": resumen_borradores_cantidad,
                "resumen_borradores_monto": resumen_borradores_monto,
                "resumen_autorizadas_cantidad": resumen_autorizadas_cantidad,
                "resumen_autorizadas_monto": resumen_autorizadas_monto,
                "resumen_pagadas_mes_cantidad": resumen_pagadas_mes_cantidad,
                "resumen_pagadas_mes_monto": resumen_pagadas_mes_monto,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class OrdenPagoCreateView(OrdenPagoEditMixin, CreateView):
    model = OrdenPago
    form_class = OrdenPagoForm
    template_name = "finanzas/orden_pago_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if "fecha_orden" not in initial:
            initial["fecha_orden"] = timezone.now().date()
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(self.request.POST)
        else:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet()
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["lineas_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        orden = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(orden, "creado_por") and not orden.creado_por:
                orden.creado_por = user
            if hasattr(orden, "actualizado_por"):
                orden.actualizado_por = user

        accion = (self.request.POST.get("accion") or "borrador").strip()
        if es_staff_finanzas(user) and accion == "autorizar":
            orden.estado = OrdenPago.ESTADO_AUTORIZADA
            mensaje = "Orden de pago creada y autorizada correctamente."
        else:
            orden.estado = OrdenPago.ESTADO_BORRADOR
            mensaje = "Orden de pago creada como borrador."

        if not orden.fecha_orden:
            orden.fecha_orden = timezone.now().date()

        orden.save()
        formset.instance = orden
        formset.save()

        messages.success(self.request, mensaje)
        return redirect("finanzas:orden_pago_detail", pk=orden.pk)


class OrdenPagoUpdateView(OrdenPagoEditMixin, UpdateView):
    model = OrdenPago
    form_class = OrdenPagoForm
    template_name = "finanzas/orden_pago_form.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(
                self.request.POST, instance=self.object
            )
        else:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(instance=self.object)

        ctx.update(_roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["lineas_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        orden_original = self.get_object()
        orden = form.save(commit=False)
        user = self.request.user
        es_staff = es_staff_finanzas(user)

        # Operadores solo pueden editar borradores
        if not es_staff and orden_original.estado != OrdenPago.ESTADO_BORRADOR:
            messages.error(
                self.request,
                "Solo el staff financiero puede editar órdenes que ya fueron autorizadas, facturadas o pagadas.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden_original.pk)

        orden.estado = orden_original.estado
        if user.is_authenticated:
            if hasattr(orden, "creado_por") and not orden.creado_por:
                orden.creado_por = orden_original.creado_por or user
            if hasattr(orden, "actualizado_por"):
                orden.actualizado_por = user

        orden.save()
        formset.instance = orden
        formset.save()

        messages.success(self.request, "Orden de pago actualizada correctamente.")
        return redirect("finanzas:orden_pago_detail", pk=orden.pk)


class OrdenPagoDetailView(OrdenPagoAccessMixin, DetailView):
    model = OrdenPago
    template_name = "finanzas/orden_pago_detail.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        orden = self.object
        lineas = orden.lineas.select_related("categoria", "area")
        total = orden.total_monto
        movimientos = (
            orden.movimientos.select_related("categoria", "area")
            .order_by("-fecha_operacion", "-id")
        )

        total_movimientos = (
            movimientos.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
        )
        tiene_movimientos = movimientos.exists()

        user = self.request.user
        puede_generar_movimiento = (
            es_staff_finanzas(user)
            and orden.estado == OrdenPago.ESTADO_PAGADA
            and not tiene_movimientos
        )

        ctx.update(
            {
                "lineas": lineas,
                "total_monto": total,
                "movimientos": movimientos,
                "total_movimientos": total_movimientos,
                "tiene_movimientos": tiene_movimientos,
                "puede_generar_movimiento": puede_generar_movimiento,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class OrdenPagoCambiarEstadoView(StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk, accion):
        orden = get_object_or_404(OrdenPago, pk=pk)
        estado_anterior = orden.estado

        if accion == "borrador":
            nuevo_estado = OrdenPago.ESTADO_BORRADOR
            mensaje_ok = "La orden volvió a estado BORRADOR."
        elif accion == "autorizar":
            nuevo_estado = OrdenPago.ESTADO_AUTORIZADA
            mensaje_ok = "Orden de pago autorizada correctamente."
        elif accion == "facturar":
            nuevo_estado = OrdenPago.ESTADO_FACTURADA
            mensaje_ok = "Orden marcada como FACTURADA."
        elif accion == "pagar":
            nuevo_estado = OrdenPago.ESTADO_PAGADA
            mensaje_ok = "Orden marcada como PAGADA."
        elif accion == "anular":
            nuevo_estado = OrdenPago.ESTADO_ANULADA
            mensaje_ok = (
                "Orden ANULADA. No debería generar pagos ni movimientos nuevos."
            )
        else:
            messages.error(
                request, "Acción de estado no reconocida para la orden de pago."
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        if estado_anterior == nuevo_estado:
            messages.info(request, "La orden ya estaba en ese estado.")
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        orden.estado = nuevo_estado
        if request.user.is_authenticated and hasattr(orden, "actualizado_por"):
            orden.actualizado_por = request.user
        orden.save()

        # ===== HOOKS AGENDA (si la app existe) =====
        TareaModel = _get_tarea_model()
        if TareaModel is not None:
            # 1) Al autorizar: crear tarea de pago/vencimiento
            if nuevo_estado == OrdenPago.ESTADO_AUTORIZADA:
                titulo = f"Pagar OP #{orden.numero or orden.id}"
                if orden.proveedor_nombre or orden.proveedor:
                    titulo += f" – {orden.proveedor_nombre or orden.proveedor.nombre}"

                existe = TareaModel.objects.filter(
                    orden_pago=orden,
                    tipo=getattr(TareaModel, "TIPO_PAGO_VENCIMIENTO", None),
                    estado__in=[
                        TareaModel.ESTADO_PENDIENTE,
                        TareaModel.ESTADO_EN_PROCESO,
                    ],
                ).exists()

                if not existe:
                    tarea = TareaModel(
                        titulo=titulo,
                        descripcion=(
                            "Tarea creada automáticamente al autorizar la Orden de pago."
                        ),
                        tipo=getattr(TareaModel, "TIPO_PAGO_VENCIMIENTO", None),
                        origen=getattr(TareaModel, "ORIGEN_SISTEMA", None),
                        prioridad=getattr(TareaModel, "PRIORIDAD_ALTA", None),
                        estado=TareaModel.ESTADO_PENDIENTE,
                        fecha_vencimiento=orden.fecha_orden,
                        responsable=request.user,
                        ambito=getattr(TareaModel, "AMBITO_FINANZAS", None),
                        orden_pago=orden,
                        proveedor=orden.proveedor if orden.proveedor else None,
                        creado_por=request.user,
                        actualizado_por=request.user,
                    )
                    tarea.save()

            # 2) Al pagar: cerrar tareas ligadas a esa OP
            if nuevo_estado == OrdenPago.ESTADO_PAGADA:
                tareas = TareaModel.objects.filter(
                    orden_pago=orden,
                    estado__in=[
                        TareaModel.ESTADO_PENDIENTE,
                        TareaModel.ESTADO_EN_PROCESO,
                    ],
                )
                for t in tareas:
                    if hasattr(t, "marcar_completada"):
                        t.marcar_completada(user=request.user)
                    else:
                        t.estado = TareaModel.ESTADO_COMPLETADA
                        t.save()

        messages.success(request, mensaje_ok)
        return redirect("finanzas:orden_pago_detail", pk=orden.pk)


class OrdenPagoGenerarMovimientoView(StaffRequiredMixin, View):
    """
    Genera un Movimiento de GASTO a partir de una Orden de pago PAGADA.
    - Usa el total de la orden.
    - Usa categoría única de las líneas (si hay más de una, no genera).
    - Usa área de la orden o, si no, área única de las líneas.
    - Proveedor / CUIT se copian desde la orden.
    """

    @transaction.atomic
    def post(self, request, pk):
        orden = get_object_or_404(OrdenPago, pk=pk)

        if orden.estado != OrdenPago.ESTADO_PAGADA:
            messages.error(
                request,
                "Solo se puede generar el movimiento cuando la orden está en estado PAGADA.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        if orden.movimientos.exists():
            messages.warning(
                request,
                "Esta orden ya tiene movimientos vinculados. No se generó otro para evitar duplicados.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        lineas = list(orden.lineas.select_related("categoria", "area"))

        if not lineas:
            messages.error(
                request,
                "La orden no tiene líneas de detalle. Agregá al menos una línea con monto antes de generar el movimiento.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        categorias_ids = {l.categoria_id for l in lineas if l.categoria_id is not None}
        if not categorias_ids:
            messages.error(
                request,
                "Las líneas de la orden no tienen categoría asignada. Completalas antes de generar el movimiento.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        if len(categorias_ids) > 1:
            messages.error(
                request,
                (
                    "La orden tiene líneas con distintas categorías. "
                    "Por ahora solo se puede generar el movimiento automático cuando todas las líneas "
                    "comparten la misma categoría (para no mezclar rubros contables). "
                    "Podés cargar el movimiento manualmente desde el módulo de Movimientos."
                ),
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        categoria = lineas[0].categoria

        # Área: priorizamos el área general de la orden; si no, un área única de las líneas
        area = orden.area
        if area is None:
            areas_ids = {l.area_id for l in lineas if l.area_id is not None}
            if len(areas_ids) == 1:
                area = lineas[0].area

        total_orden = orden.total_monto or Decimal("0.00")
        if total_orden <= 0:
            messages.error(
                request,
                "El total de la orden es cero o negativo. Revisá los montos de las líneas antes de generar el movimiento.",
            )
            return redirect("finanzas:orden_pago_detail", pk=orden.pk)

        # Datos de proveedor
        proveedor = orden.proveedor
        proveedor_nombre = orden.proveedor_nombre or (
            proveedor.nombre if proveedor else ""
        )
        proveedor_cuit = orden.proveedor_cuit or (proveedor.cuit if proveedor else "")

        descripcion = f"Orden de pago {orden.numero or orden.id}"
        if proveedor_nombre:
            descripcion += f" – {proveedor_nombre}"

        # Creamos el movimiento con los campos seguros (existen sí o sí)
        movimiento = Movimiento(
            tipo=Movimiento.TIPO_GASTO,
            fecha_operacion=timezone.now().date(),
            monto=total_orden,
            categoria=categoria,
            area=area,
            descripcion=descripcion,
            observaciones=(
                f"Movimiento generado automáticamente desde la Orden de pago "
                f"{orden.numero or orden.id}."
            ),
            estado=Movimiento.ESTADO_APROBADO,
        )

        # Campos opcionales del modelo Movimiento
        if hasattr(movimiento, "tipo_pago_persona"):
            movimiento.tipo_pago_persona = getattr(
                Movimiento,
                "PAGO_PERSONA_NINGUNO",
                movimiento.tipo_pago_persona,
            )

        if hasattr(movimiento, "proveedor"):
            movimiento.proveedor = proveedor

        if hasattr(movimiento, "proveedor_nombre"):
            movimiento.proveedor_nombre = proveedor_nombre or ""

        if hasattr(movimiento, "proveedor_cuit"):
            movimiento.proveedor_cuit = proveedor_cuit or ""

        if hasattr(movimiento, "orden_pago"):
            movimiento.orden_pago = orden

        if request.user.is_authenticated:
            if hasattr(movimiento, "creado_por") and not movimiento.creado_por:
                movimiento.creado_por = request.user
            if hasattr(movimiento, "actualizado_por"):
                movimiento.actualizado_por = request.user

        movimiento.save()

        messages.success(
            request,
            "Movimiento de gasto generado y aprobado correctamente a partir de la orden de pago.",
        )
        return redirect("finanzas:movimiento_detail", pk=movimiento.pk)


# ======= PERSONAS / CENSO =======


class PersonaListView(PersonaCensoAccessMixin, ListView):
    model = Beneficiario
    template_name = "finanzas/persona_list.html"
    context_object_name = "personas"
    paginate_by = 25

    def get_queryset(self):
        qs = Beneficiario.objects.filter(activo=True).select_related("sector_laboral")
        q = (self.request.GET.get("q") or "").strip()
        flag = (self.request.GET.get("flag") or "").strip()

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(apellido__icontains=q)
                | Q(dni__icontains=q)
                | Q(barrio__icontains=q)
                | Q(direccion__icontains=q)
            )

        # Filtros rápidos por indicadores
        if flag == "beneficio":
            qs = qs.filter(percibe_beneficio=True)
        elif flag == "servicios":
            qs = qs.filter(paga_servicios=True)
        elif flag == "laboral":
            qs = qs.exclude(tipo_vinculo=Beneficiario.TIPO_VINCULO_NINGUNO)
        elif flag == "sin_indicadores":
            qs = qs.filter(
                percibe_beneficio=False,
                paga_servicios=False,
                tipo_vinculo=Beneficiario.TIPO_VINCULO_NINGUNO,
            )

        # IMPORTANTÍSIMO: censo y balances solo con APROBADOS
        qs = qs.annotate(
            total_ayudas=Sum(
                "movimientos__monto",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_GASTO,
                    movimientos__categoria__es_ayuda_social=True,
                ),
            ),
            cantidad_ayudas=Count(
                "movimientos",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_GASTO,
                    movimientos__categoria__es_ayuda_social=True,
                ),
                distinct=True,
            ),
            total_servicios=Sum(
                "movimientos__monto",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_INGRESO,
                    movimientos__categoria__es_servicio=True,
                ),
            ),
            cantidad_servicios=Count(
                "movimientos",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_INGRESO,
                    movimientos__categoria__es_servicio=True,
                ),
                distinct=True,
            ),
            total_personal=Sum(
                "movimientos__monto",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_GASTO,
                    movimientos__categoria__es_personal=True,
                ),
            ),
            cantidad_personal=Count(
                "movimientos",
                filter=Q(
                    movimientos__estado=Movimiento.ESTADO_APROBADO,
                    movimientos__tipo=Movimiento.TIPO_GASTO,
                    movimientos__categoria__es_personal=True,
                ),
                distinct=True,
            ),
        )

        return qs.order_by("apellido", "nombre")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["flag"] = (self.request.GET.get("flag") or "").strip()
        ctx.update(_roles_ctx(user))
        return ctx


class PersonaDetailView(PersonaCensoAccessMixin, DetailView):
    """
    Ficha de persona (Beneficiario) con:
      - Ayudas / sueldos / servicios.
      - Historial de viajes donde figura como beneficiario (flota).
    """

    model = Beneficiario
    template_name = "finanzas/persona_detail.html"
    context_object_name = "persona"

    def _get_viajes_queryset(self, persona):
        """
        Viajes donde la persona figura como beneficiaria.
        Reutiliza el mismo orden que el listado general de viajes.
        """
        qs = (
            ViajeVehiculo.objects.select_related("vehiculo", "area", "chofer")
            .prefetch_related("beneficiarios")
            .filter(beneficiarios=persona)
        )

        # Permitimos filtros opcionales por fecha en la URL (?viajes_desde= & viajes_hasta=)
        fecha_desde = _parse_date_or_none(
            self.request.GET.get("viajes_desde") or self.request.GET.get("desde")
        )
        fecha_hasta = _parse_date_or_none(
            self.request.GET.get("viajes_hasta") or self.request.GET.get("hasta")
        )

        if fecha_desde:
            qs = qs.filter(fecha_salida__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_salida__lte=fecha_hasta)

        qs = qs.order_by("-fecha_salida", "-hora_salida", "-id")
        return qs, fecha_desde, fecha_hasta

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        persona = self.object

        # ===== Ayudas / sueldos / servicios =====
        ayudas = (
            persona.movimientos.select_related("categoria", "area")
            .filter(
                estado=Movimiento.ESTADO_APROBADO,
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_ayuda_social=True,
            )
            .order_by("-fecha_operacion", "-id")
        )
        total_ayudas = ayudas.aggregate(total=Sum("monto"))["total"] or 0

        sueldos_changas = (
            persona.movimientos.select_related("categoria", "area")
            .filter(
                estado=Movimiento.ESTADO_APROBADO,
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_personal=True,
            )
            .order_by("-fecha_operacion", "-id")
        )
        total_sueldos_changas = (
            sueldos_changas.aggregate(total=Sum("monto"))["total"] or 0
        )
        cantidad_sueldos_changas = sueldos_changas.count()

        pagos_servicios = (
            persona.movimientos.select_related("categoria")
            .filter(
                estado=Movimiento.ESTADO_APROBADO,
                tipo=Movimiento.TIPO_INGRESO,
                categoria__es_servicio=True,
            )
            .order_by("-fecha_operacion", "-id")
        )
        total_servicios_persona = (
            pagos_servicios.aggregate(total=Sum("monto"))["total"] or 0
        )
        cantidad_servicios_persona = pagos_servicios.count()

        # ===== Historial de viajes (Flota) =====
        viajes_qs, fecha_desde, fecha_hasta = self._get_viajes_queryset(persona)
        total_viajes_persona = viajes_qs.count()

        total_km_persona = Decimal("0.00")
        total_viajes_con_km_persona = 0
        viajes_persona = []

        for viaje in viajes_qs:
            km = getattr(viaje, "km_recorridos", None)
            if (
                km is None
                and viaje.odometro_inicial is not None
                and viaje.odometro_final is not None
            ):
                km = viaje.odometro_final - viaje.odometro_inicial

            if km:
                try:
                    km_val = Decimal(km)
                except Exception:
                    km_val = Decimal(str(km))
                if km_val > 0:
                    total_km_persona += km_val
                    total_viajes_con_km_persona += 1

            # Para la ficha mostramos solo los últimos 20 viajes
            if len(viajes_persona) < 20:
                viajes_persona.append(viaje)

        user = self.request.user
        ctx.update(
            {
                # Movimientos
                "ayudas": ayudas,
                "total_ayudas": total_ayudas,
                "sueldos_changas": sueldos_changas,
                "total_sueldos_changas": total_sueldos_changas,
                "cantidad_sueldos_changas": cantidad_sueldos_changas,
                "pagos_servicios": pagos_servicios,
                "total_servicios_persona": total_servicios_persona,
                "cantidad_servicios_persona": cantidad_servicios_persona,
                # Viajes
                "viajes_persona": viajes_persona,
                "total_viajes_persona": total_viajes_persona,
                "total_km_persona": total_km_persona,
                "total_viajes_con_km_persona": total_viajes_con_km_persona,
                "viajes_fecha_desde": fecha_desde,
                "viajes_fecha_hasta": fecha_hasta,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class PersonaCreateView(PersonaCensoEditMixin, CreateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    success_url = reverse_lazy("finanzas:persona_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class PersonaUpdateView(PersonaCensoEditMixin, UpdateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    context_object_name = "persona"
    success_url = reverse_lazy("finanzas:persona_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class PersonaViajesListView(PersonaCensoAccessMixin, ListView):
    """
    Listado paginado de viajes para una persona (historial completo).
    Opcional: usar en URL /personas/<pk>/viajes/.
    """

    template_name = "finanzas/persona_viajes_list.html"
    context_object_name = "viajes"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        self.persona = get_object_or_404(Beneficiario, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            ViajeVehiculo.objects.select_related("vehiculo", "area", "chofer")
            .prefetch_related("beneficiarios")
            .filter(beneficiarios=self.persona)
        )

        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        q = (self.request.GET.get("q") or "").strip()
        estado = (self.request.GET.get("estado") or "").strip()

        if fecha_desde:
            qs = qs.filter(fecha_salida__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_salida__lte=fecha_hasta)

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

        return qs.order_by("-fecha_salida", "-hora_salida", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        viajes = self.object_list

        total_km = Decimal("0.00")
        viajes_con_km = 0
        for v in viajes:
            km = getattr(v, "km_recorridos", None)
            if (
                km is None
                and v.odometro_inicial is not None
                and v.odometro_final is not None
            ):
                km = v.odometro_final - v.odometro_inicial
            if km:
                try:
                    km_val = Decimal(km)
                except Exception:
                    km_val = Decimal(str(km))
                if km_val > 0:
                    total_km += km_val
                    viajes_con_km += 1

        ctx.update(
            {
                "persona": self.persona,
                "q": (self.request.GET.get("q") or "").strip(),
                "fecha_desde": _parse_date_or_none(self.request.GET.get("desde")),
                "fecha_hasta": _parse_date_or_none(self.request.GET.get("hasta")),
                "estado_actual": (self.request.GET.get("estado") or "TODOS").strip(),
                "total_viajes_persona": viajes.count(),
                "total_km_persona": total_km,
                "total_viajes_con_km_persona": viajes_con_km,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


# ======= BALANCES =======


class BalanceResumenView(DashboardAccessMixin, TemplateView):
    template_name = "finanzas/balance_resumen.html"

    def get_context_data(self, **kwargs):
        # ===== COPIA BASE con mejoras de combustible =====
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)

        movimientos = Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO)
        movimientos_mes = movimientos.filter(
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )

        totales_globales = movimientos.aggregate(
            total_ingresos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO)),
            total_gastos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO)),
            cantidad_movimientos=Count("id"),
        )
        total_ingresos = totales_globales["total_ingresos"] or 0
        total_gastos = totales_globales["total_gastos"] or 0

        totales_mes = movimientos_mes.aggregate(
            total_ingresos_mes=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO)),
            total_gastos_mes=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO)),
            cantidad_movimientos_mes=Count("id"),
        )
        total_ingresos_mes = totales_mes["total_ingresos_mes"] or 0
        total_gastos_mes = totales_mes["total_gastos_mes"] or 0

        ayudas_qs = movimientos.filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_ayuda_social=True,
        )
        ayudas_mes_qs = ayudas_qs.filter(
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )
        total_ayudas = ayudas_qs.aggregate(total=Sum("monto"))["total"] or 0
        total_ayudas_mes = ayudas_mes_qs.aggregate(total=Sum("monto"))["total"] or 0

        porcentaje_ayudas_sobre_gastos = (
            (total_ayudas / total_gastos) * 100 if total_gastos else 0
        )

        personal_qs = movimientos.filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_personal=True,
        )
        personal_mes_qs = personal_qs.filter(
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )
        total_personal = personal_qs.aggregate(total=Sum("monto"))["total"] or 0
        total_personal_mes = (
            personal_mes_qs.aggregate(total=Sum("monto"))["total"] or 0
        )
        porcentaje_personal_sobre_gastos = (
            (total_personal / total_gastos) * 100 if total_gastos else 0
        )

        servicios_qs = movimientos.filter(
            tipo=Movimiento.TIPO_INGRESO,
            categoria__es_servicio=True,
        )
        servicios_mes_qs = servicios_qs.filter(
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )
        total_servicios = servicios_qs.aggregate(total=Sum("monto"))["total"] or 0
        total_servicios_mes = (
            servicios_mes_qs.aggregate(total=Sum("monto"))["total"] or 0
        )
        porcentaje_servicios_sobre_ingresos = (
            (total_servicios / total_ingresos) * 100 if total_ingresos else 0
        )

        # Combustible (global y mes)
        combustible_qs = movimientos.filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_combustible=True,
        )
        combustible_mes_qs = combustible_qs.filter(
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )
        combustible_total = combustible_qs.aggregate(total=Sum("monto"))["total"] or 0
        combustible_mes = combustible_mes_qs.aggregate(total=Sum("monto"))["total"] or 0

        top_categorias = (
            movimientos.filter(tipo=Movimiento.TIPO_GASTO)
            .values("categoria__nombre")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        top_areas = (
            movimientos.filter(tipo=Movimiento.TIPO_GASTO, area__isnull=False)
            .values("area__nombre")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        top_programas = (
            ayudas_qs.exclude(programa_ayuda_texto__isnull=True)
            .exclude(programa_ayuda_texto__exact="")
            .values("programa_ayuda_texto")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        top_barrios = (
            ayudas_qs.exclude(beneficiario__barrio__isnull=True)
            .exclude(beneficiario__barrio__exact="")
            .values(barrio=F("beneficiario__barrio"))
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        top_beneficiarios = (
            ayudas_qs.filter(beneficiario__isnull=False)
            .values(
                "beneficiario__dni",
                apellido=F("beneficiario__apellido"),
                nombre=F("beneficiario__nombre"),
            )
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        top_contribuyentes_servicios = (
            servicios_qs.filter(beneficiario__isnull=False)
            .values(
                "beneficiario__dni",
                apellido=F("beneficiario__apellido"),
                nombre=F("beneficiario__nombre"),
            )
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:8]
        )

        ultimos_movimientos = (
            movimientos.select_related("categoria", "area")
            .order_by("-fecha_operacion", "-id")[:10]
        )

        ctx.update(
            {
                "hoy": hoy,
                "primer_dia_mes": primer_dia_mes,
                "total_ingresos": total_ingresos,
                "total_gastos": total_gastos,
                "saldo": total_ingresos - total_gastos,
                "cantidad_movimientos": totales_globales["cantidad_movimientos"] or 0,
                "total_ingresos_mes": total_ingresos_mes,
                "total_gastos_mes": total_gastos_mes,
                "saldo_mes": total_ingresos_mes - total_gastos_mes,
                "cantidad_movimientos_mes": totales_mes["cantidad_movimientos_mes"]
                or 0,
                "total_ayudas": total_ayudas,
                "total_ayudas_mes": total_ayudas_mes,
                "porcentaje_ayudas_sobre_gastos": porcentaje_ayudas_sobre_gastos,
                "total_personal": total_personal,
                "total_personal_mes": total_personal_mes,
                "porcentaje_personal_sobre_gastos": porcentaje_personal_sobre_gastos,
                "total_servicios": total_servicios,
                "total_servicios_mes": total_servicios_mes,
                "porcentaje_servicios_sobre_ingresos": porcentaje_servicios_sobre_ingresos,
                "combustible_total": combustible_total,
                "combustible_mes": combustible_mes,
                "top_categorias": top_categorias,
                "top_areas": top_areas,
                "top_programas": top_programas,
                "top_barrios": top_barrios,
                "top_beneficiarios": top_beneficiarios,
                "top_contribuyentes_servicios": top_contribuyentes_servicios,
                "ultimos_movimientos": ultimos_movimientos,
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class DashboardView(BalanceResumenView):
    template_name = "finanzas/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # ============================
        # 1) Estados de movimientos
        # ============================
        estado_counts = Movimiento.objects.values("estado").annotate(
            cantidad=Count("id")
        )
        mapa = {row["estado"]: row["cantidad"] for row in estado_counts}

        ctx["total_borradores"] = mapa.get(Movimiento.ESTADO_BORRADOR, 0)
        ctx["total_aprobados"] = mapa.get(Movimiento.ESTADO_APROBADO, 0)
        ctx["total_rechazados"] = mapa.get(Movimiento.ESTADO_RECHAZADO, 0)

        ctx["borradores_recientes"] = (
            Movimiento.objects.filter(estado=Movimiento.ESTADO_BORRADOR)
            .select_related("categoria", "area")
            .order_by("-fecha_operacion", "-id")[:10]
        )

        ctx["rechazados_recientes"] = (
            Movimiento.objects.filter(estado=Movimiento.ESTADO_RECHAZADO)
            .select_related("categoria", "area")
            .order_by("-fecha_operacion", "-id")[:5]
        )

        # ============================
        # 2) Flota: viajes + km mes actual
        # ============================
        hoy = ctx.get("hoy") or timezone.now().date()
        primer_dia_mes = ctx.get("primer_dia_mes") or hoy.replace(day=1)
        try:
            viajes_mes, total_km_mes = _flota_metrics_mes(hoy, primer_dia_mes)
        except Exception:
            viajes_mes, total_km_mes = 0, 0

        ctx["viajes_mes"] = viajes_mes
        ctx["total_km_mes"] = total_km_mes

        # ============================
        # 3) Órdenes de pago pendientes (panel OP/Compras)
        # ============================
        ordenes_pendientes_qs = OrdenPago.objects.exclude(
            estado__in=[OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA]
        )
        cantidad_ordenes_pendientes = ordenes_pendientes_qs.count()

        monto_ordenes_pendientes = Decimal("0.00")
        for op in ordenes_pendientes_qs:
            monto_ordenes_pendientes += op.total_monto

        ctx["cantidad_ordenes_pendientes"] = cantidad_ordenes_pendientes
        ctx["total_ordenes_pendientes"] = monto_ordenes_pendientes

        # ============================
        # 4) Órdenes de compra (si el modelo existe)
        # ============================
        oc_pendientes_cantidad = 0
        oc_pendientes_monto = Decimal("0.00")

        try:
            from .models import OrdenCompra as OCModel
        except Exception:
            OCModel = None

        if OCModel is not None:
            oc_qs = OCModel.objects.all()

            estados_cerrados = []
            if hasattr(OCModel, "ESTADO_CERRADA"):
                estados_cerrados.append(OCModel.ESTADO_CERRADA)
            if hasattr(OCModel, "ESTADO_ANULADA"):
                estados_cerrados.append(OCModel.ESTADO_ANULADA)

            if estados_cerrados:
                oc_qs = oc_qs.exclude(estado__in=estados_cerrados)

            oc_pendientes_cantidad = oc_qs.count()
            oc_pendientes_monto = (
                oc_qs.aggregate(total=Sum("lineas__monto"))["total"]
                or Decimal("0.00")
            )

        ctx["oc_pendientes_cantidad"] = oc_pendientes_cantidad
        ctx["oc_pendientes_monto"] = oc_pendientes_monto

        # ============================
        # 5) Agenda / tareas pendientes
        # ============================
        tareas_pendientes_usuario = 0
        tareas_pendientes_totales = 0
        TareaModel = _get_tarea_model()
        if TareaModel is not None:
            tareas_pendientes_usuario = TareaModel.objects.filter(
                responsable=user,
                estado__in=[
                    TareaModel.ESTADO_PENDIENTE,
                    TareaModel.ESTADO_EN_PROCESO,
                ],
            ).count()
            tareas_pendientes_totales = TareaModel.objects.filter(
                estado__in=[
                    TareaModel.ESTADO_PENDIENTE,
                    TareaModel.ESTADO_EN_PROCESO,
                ],
            ).count()

        ctx["tareas_pendientes_usuario"] = tareas_pendientes_usuario
        ctx["tareas_pendientes_totales"] = tareas_pendientes_totales

        # ============================
        # 6) Órdenes de trabajo (OT)
        # ============================
        ot_total = OrdenTrabajo.objects.count()
        estado_finalizada = getattr(OrdenTrabajo, "ESTADO_FINALIZADA", None)
        estado_anulada = getattr(OrdenTrabajo, "ESTADO_ANULADA", None)

        ot_finalizadas = 0
        ot_anuladas = 0

        if estado_finalizada:
            ot_finalizadas = OrdenTrabajo.objects.filter(
                estado=estado_finalizada
            ).count()
        if estado_anulada:
            ot_anuladas = OrdenTrabajo.objects.filter(estado=estado_anulada).count()

        ot_abiertas = ot_total - ot_finalizadas - ot_anuladas

        ot_mes_qs = OrdenTrabajo.objects.all()
        if hasattr(OrdenTrabajo, "fecha_ot"):
            ot_mes_qs = ot_mes_qs.filter(
                fecha_ot__gte=primer_dia_mes,
                fecha_ot__lte=hoy,
            )

        ot_importe_estimado_mes = (
            ot_mes_qs.aggregate(total=Sum("importe_estimado"))["total"]
            or Decimal("0.00")
        )
        ot_importe_final_mes = (
            ot_mes_qs.aggregate(total=Sum("importe_final"))["total"]
            or Decimal("0.00")
        )

        ctx["ot_total"] = ot_total
        ctx["ot_abiertas"] = ot_abiertas
        ctx["ot_finalizadas"] = ot_finalizadas
        ctx["ot_anuladas"] = ot_anuladas
        ctx["ot_importe_estimado_mes"] = ot_importe_estimado_mes
        ctx["ot_importe_final_mes"] = ot_importe_final_mes

        ctx.update(_roles_ctx(user))
        return ctx


# ======= FLOTA: CONSUMO DE COMBUSTIBLE (resumen pro) =======


class ConsumoCombustibleView(FlotaAccessMixin, TemplateView):
    """
    Vista de consumo de combustible por vehículo.

    Usa el template `finanzas/flota_combustible_resumen.html` y expone:

      - vehiculos: queryset de vehículos activos
      - vehiculo_actual: id (string) del vehículo filtrado o ""
      - fecha_desde / fecha_hasta: rango de fechas
      - resumen_vehiculos: lista de dicts con:
            vehiculo, total_combustible, total_km,
            costo_por_km, total_viajes, viajes_con_km
      - total_combustible, total_km, total_viajes, viajes_con_km
      - costo_promedio_km: costo global por km
      - top_destino: dict {destino, cantidad, porcentaje} o None
      - top_choferes: lista de dicts {nombre, cantidad, porcentaje}
      - top_beneficiarios: lista de dicts {dni, nombre, cantidad}
    """

    template_name = "finanzas/flota_combustible_resumen.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.now().date()

        fecha_desde = _parse_date_or_none(self.request.GET.get("desde")) or hoy.replace(
            day=1
        )
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta")) or hoy

        vehiculo_actual = (self.request.GET.get("vehiculo") or "").strip()

        # Vehículos activos
        vehiculos = Vehiculo.objects.filter(activo=True).order_by(
            "descripcion", "patente"
        )
        vehiculos_filtrados = vehiculos
        if vehiculo_actual:
            vehiculos_filtrados = vehiculos_filtrados.filter(pk=vehiculo_actual)

        resumen_vehiculos = []

        total_combustible = Decimal("0.00")
        total_km = Decimal("0.00")
        total_viajes = 0
        viajes_con_km_global = 0

        # Intentamos importar ViajeVehiculo de forma segura
        try:
            from .models import ViajeVehiculo as ViajeModel
        except Exception:
            ViajeModel = None

        # ---- RESUMEN POR VEHÍCULO ----
        for v in vehiculos_filtrados:
            # Movimientos de combustible del vehículo en el período
            cargas_qs = v.cargas_combustible.filter(
                estado=Movimiento.ESTADO_APROBADO,
                tipo=Movimiento.TIPO_GASTO,
                categoria__es_combustible=True,
                fecha_operacion__gte=fecha_desde,
                fecha_operacion__lte=fecha_hasta,
            )

            monto_combustible = (
                cargas_qs.aggregate(total=Sum("monto"))["total"]
                or Decimal("0.00")
            )

            km = Decimal("0.00")
            viajes_count = 0
            viajes_con_km = 0

            if ViajeModel is not None:
                viajes_qs_v = v.viajes_vehiculo.all()

                # Campo de fecha robusto
                if hasattr(ViajeModel, "fecha_salida"):
                    viajes_qs_v = viajes_qs_v.filter(
                        fecha_salida__gte=fecha_desde,
                        fecha_salida__lte=fecha_hasta,
                    )
                elif hasattr(ViajeModel, "fecha"):
                    viajes_qs_v = viajes_qs_v.filter(
                        fecha__gte=fecha_desde,
                        fecha__lte=fecha_hasta,
                    )
                elif hasattr(ViajeModel, "fecha_viaje"):
                    viajes_qs_v = viajes_qs_v.filter(
                        fecha_viaje__gte=fecha_desde,
                        fecha_viaje__lte=fecha_hasta,
                    )

                viajes_count = viajes_qs_v.count()

                # Km recorridos por odómetro
                for viaje in viajes_qs_v:
                    ini = getattr(viaje, "odometro_inicial", None)
                    fin = getattr(viaje, "odometro_final", None)
                    if ini is not None and fin is not None:
                        diff = fin - ini
                        if diff > 0:
                            km += diff
                            viajes_con_km += 1

            costo_por_km = monto_combustible / km if km > 0 else None

            total_combustible += monto_combustible
            total_km += km
            total_viajes += viajes_count
            viajes_con_km_global += viajes_con_km

            resumen_vehiculos.append(
                {
                    "vehiculo": v,
                    "total_combustible": monto_combustible,
                    "total_km": km,
                    "costo_por_km": costo_por_km,
                    "total_viajes": viajes_count,
                    "viajes_con_km": viajes_con_km,
                }
            )

        costo_promedio_km = total_combustible / total_km if total_km > 0 else None

        # ---- INSIGHTS RÁPIDOS ----
        top_destino = None
        top_choferes = []
        top_beneficiarios = []

        if ViajeModel is not None:
            viajes_periodo = ViajeModel.objects.all()

            # Filtro por fecha (campo robusto)
            if hasattr(ViajeModel, "fecha_salida"):
                viajes_periodo = viajes_periodo.filter(
                    fecha_salida__gte=fecha_desde,
                    fecha_salida__lte=fecha_hasta,
                )
            elif hasattr(ViajeModel, "fecha"):
                viajes_periodo = viajes_periodo.filter(
                    fecha__gte=fecha_desde,
                    fecha__lte=fecha_hasta,
                )
            elif hasattr(ViajeModel, "fecha_viaje"):
                viajes_periodo = viajes_periodo.filter(
                    fecha_viaje__gte=fecha_desde,
                    fecha_viaje__lte=fecha_hasta,
                )

            # Filtro por vehículo (opcional)
            if vehiculo_actual:
                viajes_periodo = viajes_periodo.filter(vehiculo_id=vehiculo_actual)

            total_viajes_periodo = viajes_periodo.count()

            if total_viajes_periodo > 0:
                # Destino más frecuente
                destinos_qs = (
                    viajes_periodo.exclude(destino__isnull=True)
                    .exclude(destino__exact="")
                    .values("destino")
                    .annotate(cantidad=Count("id"))
                    .order_by("-cantidad")
                )
                if destinos_qs:
                    d0 = destinos_qs[0]
                    top_destino = {
                        "destino": d0["destino"],
                        "cantidad": d0["cantidad"],
                        "porcentaje": (d0["cantidad"] / total_viajes_periodo) * 100,
                    }

                # Choferes con más viajes
                if hasattr(ViajeModel, "chofer_nombre"):
                    choferes_qs = (
                        viajes_periodo.exclude(chofer_nombre__isnull=True)
                        .exclude(chofer_nombre__exact="")
                        .values("chofer_nombre")
                        .annotate(cantidad=Count("id"))
                        .order_by("-cantidad")[:3]
                    )
                    for c in choferes_qs:
                        top_choferes.append(
                            {
                                "nombre": c["chofer_nombre"],
                                "cantidad": c["cantidad"],
                                "porcentaje": (c["cantidad"] / total_viajes_periodo)
                                * 100,
                            }
                        )
                else:
                    choferes_qs = (
                        viajes_periodo.filter(chofer__isnull=False)
                        .values(
                            "chofer__dni",
                            "chofer__apellido",
                            "chofer__nombre",
                        )
                        .annotate(cantidad=Count("id"))
                        .order_by("-cantidad")[:3]
                    )
                    for c in choferes_qs:
                        nombre = f"{c['chofer__apellido']} {c['chofer__nombre']}".strip()
                        top_choferes.append(
                            {
                                "nombre": nombre or c["chofer__dni"],
                                "cantidad": c["cantidad"],
                                "porcentaje": (c["cantidad"] / total_viajes_periodo)
                                * 100,
                            }
                        )

                # Beneficiarios más trasladados
                beneficiarios_qs = (
                    viajes_periodo.filter(beneficiarios__isnull=False)
                    .values(
                        "beneficiarios__dni",
                        "beneficiarios__apellido",
                        "beneficiarios__nombre",
                    )
                    # cantidad de viajes distintos donde aparece cada beneficiario
                    .annotate(cantidad=Count("id", distinct=True))
                    .order_by("-cantidad")[:3]
                )
                for b in beneficiarios_qs:
                    nombre_benef = (
                        f"{b['beneficiarios__apellido']} {b['beneficiarios__nombre']}"
                    ).strip()
                    top_beneficiarios.append(
                        {
                            "dni": b["beneficiarios__dni"],
                            "nombre": nombre_benef or b["beneficiarios__dni"],
                            "cantidad": b["cantidad"],
                        }
                    )

        ctx.update(
            {
                "vehiculos": vehiculos,
                "vehiculo_actual": vehiculo_actual,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "resumen_vehiculos": resumen_vehiculos,
                "total_combustible": total_combustible,
                "total_km": total_km,
                "total_viajes": total_viajes,
                "viajes_con_km": viajes_con_km_global,
                "costo_promedio_km": costo_promedio_km,
                "top_destino": top_destino,
                "top_choferes": top_choferes,
                "top_beneficiarios": top_beneficiarios,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


# ======= API: búsqueda rápida por DNI / autocomplete =======


@login_required
@require_GET
def persona_buscar_por_dni(request):
    """
    Devuelve datos básicos de persona por DNI (para autocompletar en el formulario).
    Respuesta JSON:
      {found: true/false, nombre, direccion, barrio}
    Solo accesible si está logueado.
    """
    dni = (request.GET.get("dni") or "").strip()
    if not dni:
        return JsonResponse({"found": False})

    try:
        persona = Beneficiario.objects.get(dni=dni, activo=True)
    except Beneficiario.DoesNotExist:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "nombre": f"{persona.apellido} {persona.nombre}".strip(),
            "direccion": persona.direccion or "",
            "barrio": persona.barrio or "",
        }
    )


@login_required
@require_GET
def persona_autocomplete(request):
    """
    Autocomplete por apellido/nombre/dni para Beneficiario (censo de personas).
    Devuelve hasta 20 resultados.
    """
    q = (request.GET.get("q") or "").strip()
    results = []

    if len(q) >= 2:
        queryset = Beneficiario.objects.filter(activo=True)

        # Permitimos buscar por partes (ej: "pérez juan")
        for term in q.split():
            queryset = queryset.filter(
                Q(apellido__icontains=term)
                | Q(nombre__icontains=term)
                | Q(dni__icontains=term)
            )

        queryset = queryset.order_by("apellido", "nombre")[:20]

        for b in queryset:
            results.append(
                {
                    "id": b.id,
                    "dni": b.dni or "",
                    "apellido": b.apellido or "",
                    "nombre": b.nombre or "",
                    "direccion": getattr(b, "direccion", "") or "",
                    "barrio": getattr(b, "barrio", "") or "",
                }
            )

    return JsonResponse({"results": results})


@login_required
@require_GET
def vehiculo_autocomplete(request):
    """
    Autocomplete de vehículos para el bloque de combustible / flota.
    Busca por descripción o patente.
    """
    q = (request.GET.get("q") or "").strip()
    results = []

    if len(q) >= 2:
        queryset = Vehiculo.objects.filter(activo=True)

        for term in q.split():
            queryset = queryset.filter(
                Q(descripcion__icontains=term) | Q(patente__icontains=term)
            )

        queryset = queryset.order_by("descripcion", "patente")[:20]

        for v in queryset:
            results.append(
                {
                    "id": v.id,
                    # Etiqueta amigable: patente + descripción (propiedad del modelo)
                    "label": getattr(v, "etiqueta_busqueda", str(v)),
                    "descripcion": getattr(v, "descripcion", "") or "",
                    "patente": getattr(v, "patente", "") or "",
                    # Por compatibilidad con JS viejo que pudiera leer 'interno'
                    "interno": getattr(v, "interno", "")
                    if hasattr(v, "interno")
                    else "",
                }
            )

    return JsonResponse({"results": results})


# =====================================================
#   ÓRDENES DE TRABAJO (OT PRO)
# =====================================================


class OrdenTrabajoListView(OrdenTrabajoAccessMixin, ListView):
    model = OrdenTrabajo
    template_name = "finanzas/orden_trabajo_list.html"
    context_object_name = "ordenes_trabajo"
    paginate_by = 25

    def get_queryset(self):
        qs = OrdenTrabajo.objects.select_related(
            "area",
            "vehiculo",
            "solicitante",
            "responsable",
        )
        estado = (self.request.GET.get("estado") or "TODAS").strip()
        fecha_desde = _parse_date_or_none(self.request.GET.get("desde"))
        fecha_hasta = _parse_date_or_none(self.request.GET.get("hasta"))
        q = (self.request.GET.get("q") or "").strip()
        area_id = (self.request.GET.get("area") or "").strip()

        if estado and estado != "TODAS":
            qs = qs.filter(estado=estado)

        if area_id:
            qs = qs.filter(area_id=area_id)

        if fecha_desde:
            qs = qs.filter(fecha_ot__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_ot__lte=fecha_hasta)

        if q:
            qs = qs.filter(
                Q(numero__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(trabajos_realizados__icontains=q)
                | Q(solicitante__apellido__icontains=q)
                | Q(solicitante__nombre__icontains=q)
                | Q(solicitante_texto__icontains=q)
            )

        return qs.order_by("-fecha_ot", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ordenes = self.object_list

        total_estimado = Decimal("0.00")
        total_final = Decimal("0.00")
        for ot in ordenes:
            if ot.importe_estimado:
                total_estimado += ot.importe_estimado
            if ot.importe_final:
                total_final += ot.importe_final

        ctx.update(
            {
                "q": (self.request.GET.get("q") or "").strip(),
                "estado_actual": (self.request.GET.get("estado") or "TODAS").strip(),
                "area_actual": (self.request.GET.get("area") or "").strip(),
                "total_estimado_listado": total_estimado,
                "total_final_listado": total_final,
                "areas": Area.objects.filter(activo=True).order_by("nombre"),
            }
        )
        ctx.update(_roles_ctx(self.request.user))
        return ctx


class OrdenTrabajoCreateView(OrdenTrabajoEditMixin, CreateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/orden_trabajo_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if "fecha_ot" not in initial:
            initial["fecha_ot"] = timezone.now().date()
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["materiales_formset"] = OrdenTrabajoMaterialFormSet(self.request.POST)
            ctx["adjuntos_formset"] = AdjuntoOrdenTrabajoFormSet(
                self.request.POST, self.request.FILES
            )
        else:
            ctx["materiales_formset"] = OrdenTrabajoMaterialFormSet()
            ctx["adjuntos_formset"] = AdjuntoOrdenTrabajoFormSet()
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        materiales_fs = context["materiales_formset"]
        adjuntos_fs = context["adjuntos_formset"]

        if not materiales_fs.is_valid() or not adjuntos_fs.is_valid():
            return self.form_invalid(form)

        ot = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(ot, "creado_por") and not ot.creado_por:
                ot.creado_por = user
            if hasattr(ot, "actualizado_por"):
                ot.actualizado_por = user

        ot.save()
        form.save_m2m()

        materiales_fs.instance = ot
        materiales_fs.save()

        adjuntos_fs.instance = ot
        adjuntos_fs.save()

        messages.success(self.request, "Orden de trabajo creada correctamente.")
        return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)


class OrdenTrabajoUpdateView(OrdenTrabajoEditMixin, UpdateView):
    model = OrdenTrabajo
    form_class = OrdenTrabajoForm
    template_name = "finanzas/orden_trabajo_form.html"
    context_object_name = "orden_trabajo"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["materiales_formset"] = OrdenTrabajoMaterialFormSet(
                self.request.POST, instance=self.object
            )
            ctx["adjuntos_formset"] = AdjuntoOrdenTrabajoFormSet(
                self.request.POST, self.request.FILES, instance=self.object
            )
        else:
            ctx["materiales_formset"] = OrdenTrabajoMaterialFormSet(
                instance=self.object
            )
            ctx["adjuntos_formset"] = AdjuntoOrdenTrabajoFormSet(
                instance=self.object
            )
        ctx.update(_roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        materiales_fs = context["materiales_formset"]
        adjuntos_fs = context["adjuntos_formset"]

        if not materiales_fs.is_valid() or not adjuntos_fs.is_valid():
            return self.form_invalid(form)

        ot_original = self.get_object()
        ot = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if hasattr(ot, "creado_por") and not ot.creado_por:
                ot.creado_por = getattr(ot_original, "creado_por", user)
            if hasattr(ot, "actualizado_por"):
                ot.actualizado_por = user

        ot.save()
        form.save_m2m()

        materiales_fs.instance = ot
        materiales_fs.save()

        adjuntos_fs.instance = ot
        adjuntos_fs.save()

        messages.success(self.request, "Orden de trabajo actualizada correctamente.")
        return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)


class OrdenTrabajoDetailView(OrdenTrabajoAccessMixin, DetailView):
    model = OrdenTrabajo
    template_name = "finanzas/orden_trabajo_detail.html"
    context_object_name = "orden_trabajo"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ot = self.object

        materiales = ot.materiales.all().order_by("id")
        adjuntos = ot.adjuntos.all().order_by("id")

        total_materiales = Decimal("0.00")
        for m in materiales:
            if m.costo_total:
                total_materiales += m.costo_total

        user = self.request.user
        puede_generar_movimiento = (
            es_staff_finanzas(user)
            and getattr(ot, "movimiento_ingreso", None) is None
            and ot.categoria_ingreso is not None
        )

        ctx.update(
            {
                "materiales": materiales,
                "adjuntos": adjuntos,
                "total_materiales": total_materiales,
                "puede_generar_movimiento": puede_generar_movimiento,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class OrdenTrabajoGenerarMovimientoIngresoView(StaffRequiredMixin, View):
    """
    Genera un Movimiento de INGRESO a partir de una Orden de Trabajo.
    - Usa importe_final si existe, si no importe_estimado.
    - Usa categoría_ingreso configurada en la OT.
    - Vincula el movimiento a la OT (si el modelo tiene ese FK).
    """

    @transaction.atomic
    def post(self, request, pk):
        ot = get_object_or_404(OrdenTrabajo, pk=pk)

        if getattr(ot, "movimiento_ingreso", None) is not None:
            messages.warning(
                request,
                "Esta orden de trabajo ya tiene un movimiento de ingreso vinculado.",
            )
            return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)

        if ot.categoria_ingreso is None:
            messages.error(
                request,
                "La orden de trabajo no tiene configurada la categoría contable de ingreso. Completala antes de generar el movimiento.",
            )
            return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)

        # Si el modelo define un estado 'FINALIZADA', lo usamos como requisito
        estado_finalizada = getattr(OrdenTrabajo, "ESTADO_FINALIZADA", None)
        if estado_finalizada and ot.estado != estado_finalizada:
            messages.error(
                request,
                "Solo se puede generar el movimiento de ingreso cuando la OT está marcada como FINALIZADA.",
            )
            return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)

        monto = ot.importe_final or ot.importe_estimado or Decimal("0.00")
        if monto <= 0:
            messages.error(
                request,
                "El importe de la OT es cero o negativo. Cargá un importe estimado o final antes de generar el movimiento.",
            )
            return redirect("finanzas:orden_trabajo_detail", pk=ot.pk)

        beneficiario = ot.solicitante
        beneficiario_nombre = ""
        beneficiario_dni = ""
        if beneficiario:
            beneficiario_nombre = (
                f"{beneficiario.apellido} {beneficiario.nombre}".strip()
            )
            beneficiario_dni = beneficiario.dni or ""

        descripcion = f"Trabajo {ot.numero or ot.id}"
        if ot.descripcion:
            descripcion += f" – {ot.descripcion[:80]}"

        # Creamos el movimiento con lo básico y seguro
        movimiento = Movimiento(
            tipo=Movimiento.TIPO_INGRESO,
            fecha_operacion=timezone.now().date(),
            monto=monto,
            categoria=ot.categoria_ingreso,
            area=ot.area,
            descripcion=descripcion,
            observaciones=(
                f"Movimiento generado automáticamente desde la Orden de trabajo "
                f"{ot.numero or ot.id}."
            ),
            estado=Movimiento.ESTADO_APROBADO,
        )

        if hasattr(movimiento, "tipo_pago_persona"):
            movimiento.tipo_pago_persona = getattr(
                Movimiento,
                "PAGO_PERSONA_NINGUNO",
                movimiento.tipo_pago_persona,
            )

        # Beneficiario y datos asociados (si existen en el modelo)
        if beneficiario and hasattr(movimiento, "beneficiario"):
            movimiento.beneficiario = beneficiario
            if hasattr(movimiento, "beneficiario_dni"):
                movimiento.beneficiario_dni = beneficiario_dni
            if hasattr(movimiento, "beneficiario_nombre"):
                movimiento.beneficiario_nombre = beneficiario_nombre

        # Vehículo y texto (si existen en el modelo)
        if ot.vehiculo and hasattr(movimiento, "vehiculo"):
            movimiento.vehiculo = ot.vehiculo
            if hasattr(movimiento, "vehiculo_texto"):
                movimiento.vehiculo_texto = str(ot.vehiculo)

        if request.user.is_authenticated:
            if hasattr(movimiento, "creado_por") and not movimiento.creado_por:
                movimiento.creado_por = request.user
            if hasattr(movimiento, "actualizado_por"):
                movimiento.actualizado_por = request.user

        # Si el modelo de Movimiento tiene FK a OrdenTrabajo, lo usamos
        if hasattr(movimiento, "orden_trabajo"):
            movimiento.orden_trabajo = ot

        movimiento.save()

        # Vincular desde la OT si tiene campo movimiento_ingreso
        if hasattr(ot, "movimiento_ingreso"):
            ot.movimiento_ingreso = movimiento
            ot.save()

        messages.success(
            request,
            "Movimiento de ingreso generado y aprobado correctamente a partir de la orden de trabajo.",
        )
        return redirect("finanzas:movimiento_detail", pk=movimiento.pk)
