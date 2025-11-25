from datetime import datetime
from decimal import Decimal

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
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView

from .forms import (
    MovimientoForm,
    BeneficiarioForm,
    OrdenPagoForm,
    OrdenPagoLineaFormSet,
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
)

# ===== AGENDA (nuevo módulo) =====
# Fallback seguro: si Agenda todavía no está lista, no rompe finanzas.
try:
    from agenda.models import Tarea
except Exception:
    Tarea = None


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
        if Tarea is not None:
            tareas_pendientes_usuario = Tarea.objects.filter(
                responsable=user,
                estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO],
            ).count()

        ctx.update(
            {
                "hoy": hoy,
                "total_ingresos_mes": total_ingresos_mes,
                "total_gastos_mes": total_gastos_mes,
                "saldo_mes": saldo_mes,
                "ayudas_mes": ayudas_mes,
                "personal_mes": personal_mes,
                "servicios_mes": servicios_mes,
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
            or estado in [Movimiento.ESTADO_BORRADOR, Movimiento.ESTADO_RECHAZADO, "TODOS"]
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

    def form_valid(self, form):
        movimiento = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if not movimiento.creado_por:
                movimiento.creado_por = user
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
        messages.success(self.request, mensaje)
        return redirect(self.get_success_url())


class MovimientoUpdateView(OperadorFinanzasRequiredMixin, UpdateView):
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"
    context_object_name = "movimiento"
    success_url = reverse_lazy("finanzas:movimiento_list")

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

        movimiento.creado_por = original.creado_por
        if user.is_authenticated:
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
                setattr(movimiento, nombre_fk, getattr(original, nombre_fk))

            _resolver_proveedor_y_beneficiario(form, movimiento)

            mensaje = (
                "Cambios guardados. Se actualizaron la clasificación contable, "
                "el área y otros datos descriptivos del movimiento."
            )

        movimiento.save()
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
            ).prefetch_related("adjuntos")
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
                "es_pago_servicio": m.es_pago_servicio,
                "es_ayuda_social": m.es_ayuda_social,
                "es_gasto_personal": m.es_gasto_personal,
                "es_combustible": m.es_combustible,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class MovimientoCambiarEstadoView(StaffRequiredMixin, View):
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
        if request.user.is_authenticated:
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

        movimiento.condicion_pago = condicion
        movimiento.medio_pago = medio
        movimiento.orden_pago_observaciones = orden_obs
        movimiento.factura_tipo = factura_tipo
        movimiento.factura_numero = factura_numero

        orden_fecha = _parse_date_or_none(orden_fecha_raw)
        if orden_fecha_raw and not orden_fecha:
            messages.warning(
                request,
                "La fecha de la orden de pago no tiene un formato válido (aaaa-mm-dd).",
            )
        movimiento.orden_pago_fecha = orden_fecha

        factura_fecha = _parse_date_or_none(factura_fecha_raw)
        if factura_fecha_raw and not factura_fecha:
            messages.warning(
                request,
                "La fecha de la factura no tiene un formato válido (aaaa-mm-dd).",
            )
        movimiento.factura_fecha = factura_fecha

        if request.user.is_authenticated:
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

        cargado_por = m.creado_por.get_full_name() if m.creado_por else ""
        autorizado_por = m.actualizado_por.get_full_name() if m.actualizado_por else ""

        ctx.update(
            {
                "cargado_por": cargado_por
                or (m.creado_por.username if m.creado_por else ""),
                "autorizado_por": autorizado_por
                or (m.actualizado_por.username if m.actualizado_por else ""),
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

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["lineas_formset"]

        if not formset.is_valid():
            return self.form_invalid(form)

        orden = form.save(commit=False)
        user = self.request.user

        if user.is_authenticated:
            if not orden.creado_por:
                orden.creado_por = user
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
            if not orden.creado_por:
                orden.creado_por = orden_original.creado_por or user
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
        if request.user.is_authenticated:
            orden.actualizado_por = request.user
        orden.save()

        # ===== HOOKS AGENDA (si la app existe) =====
        if Tarea is not None:
            # 1) Al autorizar: crear tarea de pago/vencimiento
            if nuevo_estado == OrdenPago.ESTADO_AUTORIZADA:
                titulo = f"Pagar OP #{orden.numero or orden.id}"
                if orden.proveedor_nombre or orden.proveedor:
                    titulo += f" – {orden.proveedor_nombre or orden.proveedor.nombre}"

                existe = Tarea.objects.filter(
                    orden_pago=orden,
                    tipo=Tarea.TIPO_PAGO_VENCIMIENTO,
                    estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO],
                ).exists()

                if not existe:
                    tarea = Tarea(
                        titulo=titulo,
                        descripcion="Tarea creada automáticamente al autorizar la Orden de pago.",
                        tipo=Tarea.TIPO_PAGO_VENCIMIENTO,
                        origen=Tarea.ORIGEN_SISTEMA,
                        prioridad=Tarea.PRIORIDAD_ALTA,
                        estado=Tarea.ESTADO_PENDIENTE,
                        fecha_vencimiento=orden.fecha_orden,
                        responsable=request.user,
                        ambito=Tarea.AMBITO_FINANZAS,
                        orden_pago=orden,
                        proveedor=orden.proveedor if orden.proveedor else None,
                        creado_por=request.user,
                        actualizado_por=request.user,
                    )
                    tarea.save()

            # 2) Al pagar: cerrar tareas ligadas a esa OP
            if nuevo_estado == OrdenPago.ESTADO_PAGADA:
                tareas = Tarea.objects.filter(
                    orden_pago=orden,
                    estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO],
                )
                for t in tareas:
                    t.marcar_completada(user=request.user)

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

        lineas = list(
            orden.lineas.select_related("categoria", "area")
        )

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
        proveedor_nombre = (
            orden.proveedor_nombre
            or (proveedor.nombre if proveedor else "")
        )
        proveedor_cuit = orden.proveedor_cuit or (proveedor.cuit if proveedor else "")

        descripcion = f"Orden de pago {orden.numero or orden.id}"
        if proveedor_nombre:
            descripcion += f" – {proveedor_nombre}"

        movimiento = Movimiento(
            tipo=Movimiento.TIPO_GASTO,
            fecha_operacion=timezone.now().date(),
            monto=total_orden,
            categoria=categoria,
            area=area,
            proveedor=proveedor,
            proveedor_nombre=proveedor_nombre or "",
            proveedor_cuit=proveedor_cuit or "",
            descripcion=descripcion,
            observaciones=(
                f"Movimiento generado automáticamente desde la Orden de pago "
                f"{orden.numero or orden.id}."
            ),
            tipo_pago_persona=Movimiento.PAGO_PERSONA_NINGUNO,
            orden_pago=orden,
            estado=Movimiento.ESTADO_APROBADO,
        )

        if request.user.is_authenticated:
            movimiento.creado_por = request.user
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
    model = Beneficiario
    template_name = "finanzas/persona_detail.html"
    context_object_name = "persona"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        persona = self.object

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

        user = self.request.user
        ctx.update(
            {
                "ayudas": ayudas,
                "total_ayudas": total_ayudas,
                "sueldos_changas": sueldos_changas,
                "total_sueldos_changas": total_sueldos_changas,
                "cantidad_sueldos_changas": cantidad_sueldos_changas,
                "pagos_servicios": pagos_servicios,
                "total_servicios_persona": total_servicios_persona,
                "cantidad_servicios_persona": cantidad_servicios_persona,
            }
        )
        ctx.update(_roles_ctx(user))
        return ctx


class PersonaCreateView(PersonaCensoEditMixin, CreateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    success_url = reverse_lazy("finanzas:persona_list")


class PersonaUpdateView(PersonaCensoEditMixin, UpdateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    context_object_name = "persona"
    success_url = reverse_lazy("finanzas:persona_list")


# ======= BALANCES =======

class BalanceResumenView(DashboardAccessMixin, TemplateView):
    template_name = "finanzas/balance_resumen.html"

    def get_context_data(self, **kwargs):
        # ===== COPIA EXACTA de tu implementación estable =====
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
                "cantidad_movimientos_mes": totales_mes["cantidad_movimientos_mes"] or 0,
                "total_ayudas": total_ayudas,
                "total_ayudas_mes": total_ayudas_mes,
                "porcentaje_ayudas_sobre_gastos": porcentaje_ayudas_sobre_gastos,
                "total_personal": total_personal,
                "total_personal_mes": total_personal_mes,
                "porcentaje_personal_sobre_gastos": porcentaje_personal_sobre_gastos,
                "total_servicios": total_servicios,
                "total_servicios_mes": total_servicios_mes,
                "porcentaje_servicios_sobre_ingresos": porcentaje_servicios_sobre_ingresos,
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

        return ctx


# ======= API: búsqueda rápida por DNI =======

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
