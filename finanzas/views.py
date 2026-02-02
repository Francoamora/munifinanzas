import json
from decimal import Decimal
from datetime import datetime, timedelta
from datetime import date

# Django Imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q, Count, F, Avg
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView
from num2words import num2words
from django.contrib.auth.mixins import LoginRequiredMixin

# === MIXINS PROPIOS ===
from .mixins import (
    roles_ctx, StaffRequiredMixin, OperadorFinanzasRequiredMixin,
    MovimientosAccessMixin, DashboardAccessMixin, OrdenPagoAccessMixin,
    OrdenPagoEditMixin, PersonaCensoAccessMixin, PersonaCensoEditMixin,
    es_staff_finanzas
)

# === MODELOS DE OTRAS APPS (Agenda / Operativo) ===
try:
    from agenda.models import Atencion
except ImportError:
    Atencion = None

# === MODELOS LOCALES (Finanzas) ===
from .models import (
    Movimiento, Categoria, Area, Proveedor, Beneficiario,
    OrdenPago, OrdenPagoLinea, OrdenCompra, OrdenCompraLinea, 
    Vehiculo, ProgramaAyuda, HojaRuta, 
    OrdenTrabajo, OrdenTrabajoMaterial
)

# === FORMULARIOS ===
from .forms import (
    MovimientoForm, BeneficiarioForm, OrdenPagoForm, OrdenPagoLineaFormSet,
    OrdenCompraForm, OrdenCompraLineaFormSet,
    OrdenTrabajoForm, OrdenTrabajoMaterialFormSet
)

# === SUBIR DOCUMENTACION BENEFICIARIOS===
from .models import DocumentoBeneficiario
from .forms import DocumentoBeneficiarioForm

# =========================================================
# IMPORTACIONES MODULARES (FLOTA, OC, OT, ATENCIONES)
# =========================================================
try:
    from .views_flota import (
        VehiculoListView, VehiculoCreateView, VehiculoUpdateView, VehiculoDetailView,
        HojaRutaListView, HojaRutaCreateView, HojaRutaDetailView,
        FlotaCombustibleResumenView, vehiculo_autocomplete
    )
except ImportError: pass

try:
    from .views_oc import (
        OCListView, OCCreateView, OCUpdateView, OCDetailView,
        OCCambiarEstadoView, OCGenerarMovimientoView,
        proveedor_por_cuit, proveedor_suggest, vehiculo_por_patente
    )
except ImportError: pass

try:
    from .views_ot import (
        OrdenTrabajoListView, OrdenTrabajoCreateView, OrdenTrabajoUpdateView,
        OrdenTrabajoDetailView, OrdenTrabajoGenerarMovimientoIngresoView,
    )
except ImportError: pass

try:
    from .views_atenciones import (
        AtencionListView, AtencionCreateView, AtencionBeneficiarioListView, AtencionUpdateView
    )
except ImportError: pass


# =========================================================
# 1) UTILIDADES INTERNAS
# =========================================================

def _resolver_proveedor_y_beneficiario(form, movimiento: Movimiento) -> None:
    """Sincroniza FKs con campos de texto (snapshot)."""
    cleaned = form.cleaned_data
    
    # Proveedor
    prov_obj = cleaned.get("proveedor")
    if prov_obj:
        movimiento.proveedor = prov_obj
        movimiento.proveedor_nombre = prov_obj.razon_social # Ajuste: Usamos razon_social
        movimiento.proveedor_cuit = prov_obj.cuit or ""
    
    # Beneficiario
    ben_obj = cleaned.get("beneficiario")
    if ben_obj:
        movimiento.beneficiario = ben_obj
        movimiento.beneficiario_nombre = f"{ben_obj.apellido}, {ben_obj.nombre}".strip()
        movimiento.beneficiario_dni = ben_obj.dni or ""

def _redirect_movimiento_post_save(request, mov: Movimiento, msg: str):
    """Redirección inteligente según estado."""
    messages.success(request, msg)
    if mov.estado == Movimiento.ESTADO_APROBADO:
        return redirect("finanzas:movimiento_detail", pk=mov.pk)
    # Si es borrador, volver a la lista filtrada
    url = reverse("finanzas:movimiento_list")
    return redirect(f"{url}?estado={mov.estado}&highlight={mov.pk}")

def _label_caja_por_tipo(tipo: str) -> str:
    t = (tipo or "").upper()
    if "ING" in t: return "Ingreso"
    if "GAS" in t: return "Gasto"
    return "Movimiento"


# =========================================================
# 2) APIs AJAX (Categorías y Proveedor Express)
# =========================================================

@login_required
def categorias_por_tipo(request):
    """API para llenar el select de categorías dinámicamente."""
    tipo = request.GET.get('tipo')
    if not tipo:
        return JsonResponse({'results': []})
    
    cats = Categoria.objects.filter(tipo=tipo, activa=True).order_by('nombre')
    data = [{
        'id': c.id, 
        'text': c.nombre,
        'es_ayuda_social': c.es_ayuda_social,
        'es_combustible': c.es_combustible
    } for c in cats]
    
    return JsonResponse({'results': data})

@login_required
@require_POST
def proveedor_create_express(request):
    """API para crear proveedores al vuelo desde el formulario de movimientos."""
    try:
        razon_social = request.POST.get('razon_social', '').strip()
        cuit = request.POST.get('cuit', '').strip()
        telefono = request.POST.get('telefono', '').strip()

        if not razon_social:
            return JsonResponse({'status': 'error', 'message': 'La Razón Social es obligatoria.'}, status=400)

        if cuit and Proveedor.objects.filter(cuit=cuit).exists():
            return JsonResponse({'status': 'error', 'message': 'Ya existe un proveedor con ese CUIT.'}, status=400)

        proveedor = Proveedor.objects.create(
            razon_social=razon_social,
            cuit=cuit,
            telefono=telefono,
            creado_por=request.user
        )

        return JsonResponse({
            'status': 'success',
            'id': proveedor.id,
            'text': f"{proveedor.razon_social} ({proveedor.cuit or 'S/C'})",
            'razon_social': proveedor.razon_social,
            'cuit': proveedor.cuit or ''
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# =========================================================
# 2) DASHBOARD (HOME)
# =========================================================

class HomeView(DashboardAccessMixin, TemplateView):
    template_name = "finanzas/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # --- 1. CONFIGURACIÓN DEL TIEMPO (CEREBRO DEL DASHBOARD) ---
        hoy = timezone.now().date()
        inicio_mes_actual = hoy.replace(day=1)
        
        # FECHA CLAVE: INICIO DE GESTIÓN
        inicio_gestion = date(2025, 12, 10) 

        # Detectar qué quiere ver el usuario
        filtro = self.request.GET.get('ver', 'mes') # 'mes' (default) o 'gestion'
        
        if filtro == 'gestion':
            fecha_inicio = inicio_gestion
            titulo_periodo = "Gestión (Desde 10/12/2025)"
        else:
            fecha_inicio = inicio_mes_actual
            titulo_periodo = "Mes en Curso"

        # =================================================
        # 2. PULSO OPERATIVO (SIEMPRE ES "HOY")
        # =================================================
        ctx['viajes_hoy'] = HojaRuta.objects.filter(fecha=hoy).count()
        ctx['atenciones_hoy'] = Atencion.objects.filter(fecha_atencion=hoy).count() if Atencion else 0
        ctx['ocs_hoy'] = OrdenCompra.objects.filter(fecha_oc=hoy).count()

        # =================================================
        # 3. DATOS FINANCIEROS (SENSIBLES AL FILTRO)
        # =================================================
        
        # Base de Movimientos Aprobados en el rango seleccionado
        movs_periodo = Movimiento.objects.filter(
            estado=Movimiento.ESTADO_APROBADO,
            fecha_operacion__gte=fecha_inicio,
            fecha_operacion__lte=hoy,
        )
        
        # Cálculo de Balance
        balance = movs_periodo.aggregate(
            ingresos=Sum("monto", filter=Q(tipo__iexact="INGRESO")),
            gastos=Sum("monto", filter=Q(tipo__iexact="GASTO")),
        )
        ingresos = balance["ingresos"] or 0
        gastos = balance["gastos"] or 0
        
        # KPIs Específicos (Ayudas y Combustible) en el rango seleccionado
        ctx['ayudas_mes_cant'] = movs_periodo.filter(
            tipo__iexact="GASTO", categoria__es_ayuda_social=True
        ).count()
        
        ctx['ayudas_mes_monto'] = movs_periodo.filter(
            tipo__iexact="GASTO", categoria__es_ayuda_social=True
        ).aggregate(t=Sum('monto'))['t'] or 0

        ctx['combustible_mes'] = movs_periodo.filter(
            tipo__iexact="GASTO", categoria__es_combustible=True
        ).aggregate(t=Sum('monto'))['t'] or 0
        
        # Viajes en el periodo
        ctx['viajes_mes'] = HojaRuta.objects.filter(fecha__gte=fecha_inicio, fecha__lte=hoy).count()

        # Últimos Movimientos (Siempre mostramos los últimos reales, sin importar el filtro)
        # CORREGIDO: Usamos relaciones reales (beneficiario, proveedor) en lugar de 'persona'
        ultimos = Movimiento.objects.filter(
            estado=Movimiento.ESTADO_APROBADO
        ).select_related(
            "categoria", "cuenta_destino", "cuenta_origen", "beneficiario", "proveedor"
        ).order_by("-fecha_operacion", "-id")[:7]

        # Contexto final
        ctx.update({
            "hoy": hoy,
            "titulo_periodo": titulo_periodo,
            "filtro_activo": filtro, # Para pintar el botón activo
            "saldo_mes": ingresos - gastos,
            "total_ingresos_mes": ingresos,
            "total_gastos_mes": gastos,
            "cantidad_ordenes_pendientes": OrdenPago.objects.filter(estado="BORRADOR").count(),
            "ultimos_movimientos": ultimos,
        })
        
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx

# Alias para compatibilidad
DashboardView = HomeView


# =========================================================
# 3) BALANCE RESUMEN
# =========================================================

class BalanceResumenView(DashboardAccessMixin, TemplateView):
    template_name = "finanzas/balance_resumen.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 1. CONFIGURACIÓN DE FECHAS
        hoy = timezone.now().date()
        periodo = self.request.GET.get("periodo", "mes")
        fecha_desde_str = self.request.GET.get("fecha_desde")
        fecha_hasta_str = self.request.GET.get("fecha_hasta")

        fecha_desde = hoy.replace(day=1)
        fecha_hasta = hoy
        titulo_periodo = "Mes Actual"

        # Lógica de filtros del Balance
        if periodo == "hoy":
            fecha_desde = hoy
            fecha_hasta = hoy
            titulo_periodo = "Día de Hoy"
        elif periodo == "ayer":
            fecha_desde = hoy - timedelta(days=1)
            fecha_hasta = hoy - timedelta(days=1)
            titulo_periodo = "Ayer"
        elif periodo == "semana":
            fecha_desde = hoy - timedelta(days=hoy.weekday())
            titulo_periodo = "Esta Semana"
        elif periodo == "mes":
            fecha_desde = hoy.replace(day=1)
            titulo_periodo = "Mes Actual"
        elif periodo == "anio":
            fecha_desde = hoy.replace(month=1, day=1)
            titulo_periodo = "Año en Curso"
        elif periodo == "custom" and fecha_desde_str and fecha_hasta_str:
            try:
                fecha_desde = timezone.datetime.strptime(fecha_desde_str, "%Y-%m-%d").date()
                fecha_hasta = timezone.datetime.strptime(fecha_hasta_str, "%Y-%m-%d").date()
                titulo_periodo = f"Del {fecha_desde.strftime('%d/%m')} al {fecha_hasta.strftime('%d/%m')}"
            except ValueError:
                pass

        # 2. QUERYSETS BASE
        qs_historico = Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO)
        qs_periodo = qs_historico.filter(fecha_operacion__range=[fecha_desde, fecha_hasta])

        # 3. KPI FINANCIEROS
        ingresos_periodo = qs_periodo.filter(tipo__iexact="INGRESO").aggregate(s=Sum("monto"))["s"] or 0
        gastos_periodo = qs_periodo.filter(tipo__iexact="GASTO").aggregate(s=Sum("monto"))["s"] or 0
        saldo_periodo = ingresos_periodo - gastos_periodo

        # 4. KPI HISTÓRICOS
        hist_ingresos = qs_historico.filter(tipo__iexact="INGRESO").aggregate(s=Sum("monto"))["s"] or 0
        hist_gastos = qs_historico.filter(tipo__iexact="GASTO").aggregate(s=Sum("monto"))["s"] or 0
        saldo_caja = hist_ingresos - hist_gastos

        # 5. DESGLOSES FINANCIEROS
        top_categorias = (qs_periodo.filter(tipo__iexact="GASTO")
                          .values("categoria__nombre")
                          .annotate(total=Sum("monto"), cantidad=Count("id"))
                          .order_by("-total")[:5])

        top_areas = (qs_periodo.filter(tipo__iexact="GASTO")
                     .values("area__nombre")
                     .annotate(total=Sum("monto"))
                     .order_by("-total")[:5])

        # 6. TERMÓMETRO SOCIAL (LIMPIEZA)
        filtro_exclusiones_laborales = (
            Q(categoria__nombre__icontains="Sueldo") |
            Q(categoria__nombre__icontains="Haber") |
            Q(categoria__nombre__icontains="Personal") |
            Q(categoria__nombre__icontains="Honorario") |
            Q(categoria__nombre__icontains="Jornal") |     
            Q(categoria__nombre__icontains="Changarin") |  
            Q(categoria__nombre__icontains="Changarín") |  
            Q(categoria__nombre__icontains="Prestacion") | 
            Q(categoria__nombre__icontains="Servicio")     
        )

        top_beneficiarios = (qs_periodo
            .filter(tipo__iexact="GASTO", beneficiario__isnull=False)
            .exclude(filtro_exclusiones_laborales) 
            .values("beneficiario__nombre", "beneficiario__apellido", "beneficiario__dni", "beneficiario__direccion")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by("-total")[:5]
        )
        
        top_barrios = (qs_periodo
            .filter(tipo__iexact="GASTO", beneficiario__isnull=False)
            .exclude(filtro_exclusiones_laborales)
            .values("beneficiario__direccion") 
            .annotate(total=Sum("monto"), ayudas=Count("id"))
            .order_by("-total")[:5]
        )

        # 7. EFICIENCIA OPERATIVA
        qs_viajes = HojaRuta.objects.filter(fecha__range=[fecha_desde, fecha_hasta])
        total_viajes = qs_viajes.count()
        
        kms_data = qs_viajes.aggregate(total_km=Sum(F('odometro_fin') - F('odometro_inicio')))
        kms_recorridos = kms_data['total_km'] or 0
        
        gasto_combustible = qs_periodo.filter(
            Q(categoria__nombre__icontains="Combustible") | 
            Q(categoria__nombre__icontains="Nafta") |
            Q(categoria__nombre__icontains="Gasoil")
        ).aggregate(s=Sum("monto"))["s"] or 0
        
        costo_promedio_viaje = gasto_combustible / total_viajes if total_viajes > 0 else 0

        # 8. TRAZABILIDAD
        movs_con_op = qs_periodo.filter(orden_pago__isnull=False).count()
        movs_directos = qs_periodo.filter(orden_pago__isnull=True, tipo__iexact="GASTO").count()

        ctx.update({
            "hoy": hoy,
            "titulo_periodo": titulo_periodo,
            "periodo_seleccionado": periodo,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "ingresos_periodo": ingresos_periodo,
            "gastos_periodo": gastos_periodo,
            "saldo_periodo": saldo_periodo,
            "movimientos_count": qs_periodo.count(),
            "saldo_caja": saldo_caja,
            "top_categorias": top_categorias,
            "top_areas": top_areas,
            "top_beneficiarios": top_beneficiarios,
            "top_barrios": top_barrios,
            "total_viajes": total_viajes,
            "kms_recorridos": kms_recorridos,
            "gasto_combustible": gasto_combustible,
            "costo_promedio_viaje": costo_promedio_viaje,
            "movs_con_op": movs_con_op,
            "movs_directos": movs_directos,
        })
        
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx


# =========================================================
# 3) PROVEEDORES
# =========================================================

class ProveedorListView(StaffRequiredMixin, ListView):
    model = Proveedor
    template_name = "finanzas/proveedor_list.html"
    context_object_name = "proveedores"
    paginate_by = 20

    def get_queryset(self):
        qs = Proveedor.objects.all().order_by("nombre")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(cuit__icontains=q) | Q(rubro__icontains=q))
        return qs

class ProveedorCreateView(StaffRequiredMixin, CreateView):
    model = Proveedor
    fields = ["nombre", "cuit", "telefono", "email", "direccion", "rubro", "cbu", "alias"] 
    template_name = "finanzas/proveedor_form.html"
    success_url = reverse_lazy("finanzas:proveedor_list")

    def form_valid(self, form):
        messages.success(self.request, "Proveedor registrado exitosamente.")
        return super().form_valid(form)

class ProveedorUpdateView(StaffRequiredMixin, UpdateView):
    model = Proveedor
    fields = ["nombre", "cuit", "telefono", "email", "direccion", "rubro", "cbu", "alias"]
    template_name = "finanzas/proveedor_form.html"
    success_url = reverse_lazy("finanzas:proveedor_list")
    
    def form_valid(self, form):
        messages.success(self.request, "Datos actualizados.")
        return super().form_valid(form)

class ProveedorDetailView(StaffRequiredMixin, DetailView):
    model = Proveedor
    template_name = "finanzas/proveedor_detail.html"
    context_object_name = "proveedor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pagos = Movimiento.objects.filter(proveedor=self.object, tipo=Movimiento.TIPO_GASTO, estado=Movimiento.ESTADO_APROBADO).order_by("-fecha_operacion")
        total_pagado = pagos.aggregate(Sum("monto"))["monto__sum"] or 0
        ocs = OrdenCompra.objects.filter(proveedor=self.object).order_by("-fecha_oc")
        
        ctx["ultimos_pagos"] = pagos[:10]
        ctx["ultimas_ocs"] = ocs[:10]
        ctx["total_pagado_historico"] = total_pagado
        return ctx


# =========================================================
# 4) MOVIMIENTOS
# =========================================================

class MovimientoListView(MovimientosAccessMixin, ListView):
    model = Movimiento
    template_name = "finanzas/movimiento_list.html"
    context_object_name = "movimientos"
    paginate_by = 25
    
    # CLAVE: Ordenar por fecha descendente y ID descendente (Lo último cargado aparece primero)
    ordering = ["-fecha_operacion", "-id"]

    def get_queryset(self):
        # 1. Optimización: Traemos todas las relaciones necesarias para la tabla
        qs = super().get_queryset().select_related(
            "categoria", "area", "proveedor", "beneficiario", "vehiculo", "orden_pago",
            "cuenta_origen", "cuenta_destino"
        )
        
        # 2. Obtener Parámetros de Filtro
        q = (self.request.GET.get("q") or "").strip()
        tipo = self.request.GET.get("tipo")
        estado = self.request.GET.get("estado")
        categoria_id = self.request.GET.get("categoria")
        fecha_desde = self.request.GET.get("fecha_desde")
        fecha_hasta = self.request.GET.get("fecha_hasta")
        
        # 3. Aplicar Filtros Lógicos
        
        # Estado (Por defecto solo APROBADO, salvo que se pida otro explícitamente)
        if estado == "BORRADOR":
            qs = qs.filter(estado=Movimiento.ESTADO_BORRADOR)
        elif estado == "TODOS":
            pass # No filtramos estado
        else:
            qs = qs.filter(estado=Movimiento.ESTADO_APROBADO) # Default: Caja Real

        # Tipo (Ingreso / Gasto)
        if tipo:
            qs = qs.filter(tipo__iexact=tipo)

        # Categoría
        if categoria_id:
            qs = qs.filter(categoria_id=categoria_id)

        # Rango de Fechas
        if fecha_desde and fecha_hasta:
            qs = qs.filter(fecha_operacion__range=[fecha_desde, fecha_hasta])
        elif fecha_desde:
            qs = qs.filter(fecha_operacion__gte=fecha_desde)
        elif fecha_hasta:
            qs = qs.filter(fecha_operacion__lte=fecha_hasta)
        
        # Búsqueda Global (Texto)
        if q:
            qs = qs.filter(
                Q(descripcion__icontains=q) | 
                Q(monto__icontains=q) |
                Q(categoria__nombre__icontains=q) | 
                Q(beneficiario__nombre__icontains=q) | 
                Q(beneficiario__apellido__icontains=q) |
                Q(proveedor__nombre__icontains=q) |
                Q(vehiculo__patente__icontains=q)
            )
            
        return qs.order_by("-fecha_operacion", "-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Datos para poblar los selects del filtro
        ctx["categorias"] = Categoria.objects.all().order_by("nombre")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["estado_actual"] = self.request.GET.get("estado", "APROBADO")
        
        # Detectar si hay filtros activos (para UX: mostrar botón limpiar)
        filtros = [
            self.request.GET.get("q"), self.request.GET.get("tipo"),
            self.request.GET.get("categoria"), self.request.GET.get("fecha_desde"),
            self.request.GET.get("fecha_hasta"), self.request.GET.get("estado")
        ]
        ctx["hay_filtros"] = any(f for f in filtros if f and f != "APROBADO")

        # CINTA DE RESUMEN (Calculada sobre el total filtrado, no solo la página)
        resumen = self.object_list.aggregate(
            ing=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO)), 
            gas=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO))
        )
        
        ing = resumen["ing"] or 0
        gas = resumen["gas"] or 0
        
        ctx.update({
            "total_ingresos_filtro": ing,
            "total_gastos_filtro": gas,
            "saldo_filtro": ing - gas
        })
        return ctx

class MovimientoCreateView(OperadorFinanzasRequiredMixin, CreateView):
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"

    @transaction.atomic
    def form_valid(self, form):
        mov = form.save(commit=False)
        mov.creado_por = self.request.user
        accion = (self.request.POST.get("accion") or "").strip().lower()
        
        # Lógica de aprobación automática para Staff
        if accion == "aprobar" and es_staff_finanzas(self.request.user):
            mov.estado = Movimiento.ESTADO_APROBADO
            msg = "Movimiento aprobado e impactado en caja."
        else:
            mov.estado = Movimiento.ESTADO_BORRADOR
            msg = "Guardado como borrador (Pendiente de revisión)."
        
        # Helper para vincular la entidad correcta (Definido en tu archivo utils o al final)
        if hasattr(self, '_resolver_proveedor_y_beneficiario'):
             self._resolver_proveedor_y_beneficiario(form, mov)
        elif '_resolver_proveedor_y_beneficiario' in globals():
             _resolver_proveedor_y_beneficiario(form, mov)
        
        # Defaults de seguridad
        if not mov.tipo_pago_persona: 
            mov.tipo_pago_persona = "NINGUNO"
        
        mov.save() # Aquí se dispara la lógica del modelo que actualiza saldos
        
        # Redirección
        if '_redirect_movimiento_post_save' in globals():
            return _redirect_movimiento_post_save(self.request, mov, msg)
        return redirect('finanzas:movimiento_list')

class MovimientoUpdateView(OperadorFinanzasRequiredMixin, UpdateView):
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Seguridad: Bloquear edición de movimientos cerrados para no-staff
        if self.object.estado == Movimiento.ESTADO_APROBADO and not es_staff_finanzas(request.user):
            messages.error(request, "Este movimiento ya está cerrado. Solo un administrador puede editarlo.")
            return redirect("finanzas:movimiento_detail", pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        mov = form.save(commit=False)
        mov.actualizado_por = self.request.user
        accion = (self.request.POST.get("accion") or "").strip().lower()
        
        if accion == "aprobar" and es_staff_finanzas(self.request.user):
            mov.estado = Movimiento.ESTADO_APROBADO
            msg = "Movimiento aprobado exitosamente."
        elif accion == "borrador":
            mov.estado = Movimiento.ESTADO_BORRADOR
            msg = "Guardado como borrador."
        else:
            msg = "Movimiento actualizado."
            
        if '_resolver_proveedor_y_beneficiario' in globals():
             _resolver_proveedor_y_beneficiario(form, mov)

        mov.save()
        
        if '_redirect_movimiento_post_save' in globals():
            return _redirect_movimiento_post_save(self.request, mov, msg)
        return redirect('finanzas:movimiento_list')

class MovimientoDetailView(MovimientosAccessMixin, DetailView):
    model = Movimiento
    template_name = "finanzas/movimiento_detail.html"
    context_object_name = "movimiento"

class MovimientoCambiarEstadoView(StaffRequiredMixin, View):
    def post(self, request, pk, accion):
        mov = get_object_or_404(Movimiento, pk=pk)
        
        if accion == "aprobar": 
            mov.estado = Movimiento.ESTADO_APROBADO
        elif accion == "rechazar": 
            mov.estado = Movimiento.ESTADO_RECHAZADO
        elif accion == "borrador": 
            mov.estado = Movimiento.ESTADO_BORRADOR
            
        mov.save()
        messages.success(request, f"Estado actualizado a: {mov.get_estado_display()}")
        return redirect("finanzas:movimiento_detail", pk=pk)

class MovimientoOrdenPagoView(StaffRequiredMixin, DetailView):
    model = Movimiento
    template_name = "finanzas/orden_pago.html"
    context_object_name = "movimiento"
    
    def post(self, request, *args, **kwargs):
        mov = self.get_object()
        mov.factura_numero = request.POST.get("factura_numero")
        mov.save()
        messages.success(request, "Datos de comprobante actualizados.")
        return redirect("finanzas:movimiento_orden_pago", pk=mov.pk)


# =========================================================
# 5) ORDENES DE PAGO
# =========================================================

class OrdenPagoListView(OrdenPagoAccessMixin, ListView):
    model = OrdenPago
    template_name = "finanzas/orden_pago_list.html"
    context_object_name = "ordenes"
    paginate_by = 25

    def get_queryset(self):
        # Optimización: Traemos proveedor y área para evitar N+1 queries
        qs = super().get_queryset().select_related("proveedor", "area")
        
        # Filtros
        estado = self.request.GET.get("estado")
        q = (self.request.GET.get("q") or "").strip()

        # Por defecto ocultamos las pagadas/anuladas para limpiar la vista, salvo que se pida explícitamente
        if estado == "TODAS":
            pass # No filtramos nada
        elif estado:
            qs = qs.filter(estado=estado)
        else:
            qs = qs.exclude(estado__in=[OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA])

        # Buscador inteligente
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) |
                Q(proveedor_nombre__icontains=q) |
                Q(proveedor__nombre__icontains=q) |
                Q(proveedor_cuit__icontains=q) |
                Q(observaciones__icontains=q) |
                Q(factura_numero__icontains=q)
            )
            
        return qs.order_by("-fecha_orden", "-id")

class OrdenPagoCreateView(OrdenPagoEditMixin, CreateView):
    model = OrdenPago
    form_class = OrdenPagoForm
    template_name = "finanzas/orden_pago_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(self.request.POST)
        else:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet()
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["lineas_formset"]
        
        if form.is_valid() and formset.is_valid():
            op = form.save(commit=False)
            op.creado_por = self.request.user
            
            # Snapshot de datos del proveedor (Congelamos datos fiscales al momento de la orden)
            if op.proveedor: 
                op.proveedor_nombre = op.proveedor.nombre
                op.proveedor_cuit = op.proveedor.cuit or ""
            
            # Determinamos estado inicial
            accion = self.request.POST.get("accion")
            if accion == "autorizar" and es_staff_finanzas(self.request.user):
                op.estado = OrdenPago.ESTADO_AUTORIZADA
            else:
                op.estado = OrdenPago.ESTADO_BORRADOR
                
            op.save()
            
            # Guardamos las líneas manuales
            formset.instance = op
            formset.save()
            
            # === LOGICA PRO: AUTO-GENERACIÓN DE LÍNEA ===
            # Si el usuario puso el monto total pero no cargó el detalle en la tabla,
            # generamos una línea automática para que el total contable coincida.
            if op.lineas.count() == 0 and op.factura_monto and op.factura_monto > 0:
                OrdenPagoLinea.objects.create(
                    orden=op,
                    area=op.area,
                    # Intentamos buscar una categoría genérica o dejamos null
                    categoria=Categoria.objects.filter(nombre__icontains="General").first(),
                    descripcion=f"Pago Factura {op.factura_numero or 'S/N'} (Generado Automáticamente)",
                    monto=op.factura_monto
                )
            # ============================================

            messages.success(self.request, f"Orden de Pago #{op.id} registrada correctamente.")
            return redirect("finanzas:orden_pago_detail", pk=op.pk)
            
        return self.render_to_response(self.get_context_data(form=form))

class OrdenPagoUpdateView(OrdenPagoEditMixin, UpdateView):
    model = OrdenPago
    form_class = OrdenPagoForm
    template_name = "finanzas/orden_pago_form.html"
    context_object_name = "orden"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        # Protección: No editar si ya está pagada o anulada (salvo superuser)
        if obj.estado in [OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA] and not request.user.is_superuser:
            messages.warning(request, "No se puede editar una OP Pagada o Anulada.")
            return redirect("finanzas:orden_pago_detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(self.request.POST, instance=self.object)
        else:
            ctx["lineas_formset"] = OrdenPagoLineaFormSet(instance=self.object)
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["lineas_formset"]
        
        if form.is_valid() and formset.is_valid():
            op = form.save(commit=False)
            
            # Actualizamos snapshot si cambió el proveedor
            if op.proveedor:
                op.proveedor_nombre = op.proveedor.nombre
                op.proveedor_cuit = op.proveedor.cuit or ""
            
            op.save()
            formset.save()
            
            # === LOGICA PRO: AUTO-GENERACIÓN EN EDICIÓN ===
            # Misma lógica: si borraron todas las líneas pero dejaron el monto
            if op.lineas.count() == 0 and op.factura_monto and op.factura_monto > 0:
                OrdenPagoLinea.objects.create(
                    orden=op,
                    area=op.area,
                    categoria=Categoria.objects.filter(nombre__icontains="General").first(),
                    descripcion=f"Pago Factura {op.factura_numero or 'S/N'} (Automático)",
                    monto=op.factura_monto
                )

            messages.success(self.request, "Orden de Pago actualizada.")
            return redirect("finanzas:orden_pago_detail", pk=op.pk)
            
        return self.render_to_response(self.get_context_data(form=form))

class OrdenPagoDetailView(OrdenPagoAccessMixin, DetailView):
    model = OrdenPago
    template_name = "finanzas/orden_pago_detail.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Pasamos los movimientos vinculados para el historial
        ctx["movimientos"] = Movimiento.objects.filter(orden_pago=self.object)
        ctx["total_movimientos"] = ctx["movimientos"].aggregate(Sum("monto"))["monto__sum"] or 0
        
        # Validaciones para botones
        ctx["tiene_movimientos"] = ctx["movimientos"].exists()
        ctx["puede_generar_movimiento"] = (
            self.object.estado == OrdenPago.ESTADO_AUTORIZADA 
            and not ctx["tiene_movimientos"]
        )
        return ctx

class OrdenPagoCambiarEstadoView(StaffRequiredMixin, View):
    def post(self, request, pk, accion):
        op = get_object_or_404(OrdenPago, pk=pk)
        
        if accion == "autorizar":
            # Validar que tenga monto > 0
            if op.total_monto <= 0 and (not op.factura_monto or op.factura_monto <= 0):
                messages.error(request, "No se puede autorizar una orden con monto $0.")
                return redirect("finanzas:orden_pago_detail", pk=pk)
            op.estado = OrdenPago.ESTADO_AUTORIZADA
            
        elif accion == "pagar":
            op.estado = OrdenPago.ESTADO_PAGADA
            
        elif accion == "anular":
            # Si tiene movimientos, advertir (idealmente bloquear, pero permitimos flexibilidad)
            if Movimiento.objects.filter(orden_pago=op).exists():
                messages.warning(request, "Atención: Esta orden tiene movimientos contables asociados.")
            op.estado = OrdenPago.ESTADO_ANULADA
            
        elif accion == "borrador":
            op.estado = OrdenPago.ESTADO_BORRADOR
            
        op.save()
        messages.success(request, f"Estado actualizado a: {op.get_estado_display()}")
        return redirect("finanzas:orden_pago_detail", pk=pk)

class OrdenPagoGenerarMovimientoView(StaffRequiredMixin, View):
    """
    Genera el EGRESO real en la caja (Movimiento) y marca la OP como PAGADA.
    """
    @transaction.atomic
    def post(self, request, pk):
        op = get_object_or_404(OrdenPago, pk=pk)
        
        # 1. Validaciones
        if op.estado != OrdenPago.ESTADO_AUTORIZADA and op.estado != OrdenPago.ESTADO_PAGADA:
            messages.error(request, "La orden debe estar AUTORIZADA para generar el pago.")
            return redirect("finanzas:orden_pago_detail", pk=pk)
            
        if Movimiento.objects.filter(orden_pago=op).exists():
            messages.warning(request, "Ya existe un movimiento de caja para esta orden.")
            return redirect("finanzas:orden_pago_detail", pk=pk)

        # 2. Determinar Monto
        monto_real = op.total_monto
        if monto_real <= 0:
            messages.error(request, "El monto total de la orden es $0. Verifique las líneas.")
            return redirect("finanzas:orden_pago_detail", pk=pk)

        # 3. Determinar Categoría (Tomamos la de la primera línea o una genérica)
        primera_linea = op.lineas.first()
        categoria_ref = primera_linea.categoria if primera_linea else None

        # 4. Crear Movimiento (Egreso de Caja)
        mov = Movimiento.objects.create(
            tipo=Movimiento.TIPO_GASTO,
            monto=monto_real,
            fecha_operacion=timezone.now().date(),
            descripcion=f"Pago OP #{op.numero} - {op.proveedor_nombre}",
            orden_pago=op,
            proveedor=op.proveedor,
            proveedor_nombre=op.proveedor_nombre,
            proveedor_cuit=op.proveedor_cuit,
            area=op.area,
            categoria=categoria_ref,
            estado=Movimiento.ESTADO_APROBADO, # Impacta directo en saldo
            creado_por=request.user
        )
        
        # 5. Actualizar estado OP
        op.estado = OrdenPago.ESTADO_PAGADA
        op.save()
        
        messages.success(request, f"Pago de ${monto_real} registrado exitosamente. OP cerrada.")
        return redirect("finanzas:movimiento_detail", pk=mov.pk)


# =========================================================
# 6) PERSONAS (SOCIAL)
# =========================================================

# Asegurate de tener esto importado arriba en tu archivo:
# from .mixins import puede_ver_historial_economico, PersonaCensoAccessMixin, PersonaCensoEditMixin, OperadorFinanzasRequiredMixin

class PersonaListView(PersonaCensoAccessMixin, ListView):
    model = Beneficiario
    template_name = "finanzas/persona_list.html"
    context_object_name = "personas"
    paginate_by = 25

    def get_queryset(self):
        # Ordenamos alfabéticamente por defecto
        qs = Beneficiario.objects.all().order_by("apellido", "nombre")
        
        # 1. Búsqueda por Texto (Nombre, Apellido, DNI)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | 
                Q(apellido__icontains=q) | 
                Q(dni__icontains=q)
            )

        # 2. Filtro de Estado (Activo / Inactivo / Todos)
        estado = self.request.GET.get("estado", "activos")
        if estado == "activos":
            qs = qs.filter(activo=True)
        elif estado == "inactivos":
            qs = qs.filter(activo=False)
        
        # 3. Filtros Avanzados (INTELIGENTES)
        
        # ¿Trabaja en la Comuna?
        vinculo = self.request.GET.get("vinculo")
        if vinculo == "si":
            qs = qs.exclude(tipo_vinculo="NINGUNO")
        
        # ¿Tiene Beneficio Social?
        beneficio = self.request.GET.get("beneficio")
        if beneficio == "si":
            qs = qs.filter(percibe_beneficio=True)
            
        # ¿Paga Servicios?
        servicios = self.request.GET.get("servicios")
        if servicios == "si":
            qs = qs.filter(
                Q(paga_servicios=True) | 
                Q(movimientos__tipo='INGRESO')
            ).distinct()

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # --- KPI CARDS ---
        activos_qs = Beneficiario.objects.filter(activo=True)
        
        ctx["count_total"] = Beneficiario.objects.count()
        ctx["count_activos"] = activos_qs.count()
        ctx["count_inactivos"] = Beneficiario.objects.filter(activo=False).count()
        ctx["count_empleados"] = activos_qs.exclude(tipo_vinculo="NINGUNO").count()
        ctx["count_beneficios"] = activos_qs.filter(percibe_beneficio=True).count()
        ctx["count_pagadores"] = activos_qs.filter(paga_servicios=True).count()
        
        # Estado de filtros
        ctx["estado_actual"] = self.request.GET.get("estado", "activos")
        ctx["q_actual"] = self.request.GET.get("q", "")
        ctx["f_vinculo"] = self.request.GET.get("vinculo", "")
        ctx["f_beneficio"] = self.request.GET.get("beneficio", "")
        ctx["f_servicios"] = self.request.GET.get("servicios", "")
        ctx["highlight_id"] = self.request.GET.get("highlight")

        # --- PERMISOS DE VISIBILIDAD (DINERO) ---
        # Usamos la lógica centralizada del mixin
        ctx["perms_ver_dinero"] = puede_ver_historial_economico(self.request.user)
        
        return ctx

class PersonaCreateView(PersonaCensoEditMixin, CreateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    
    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.activo = True
        self.object.save()
        form.save_m2m()
        
        messages.success(self.request, f"Persona '{self.object}' registrada correctamente.")
        base_url = reverse("finanzas:persona_list")
        return redirect(f"{base_url}?q={self.object.dni}&highlight={self.object.id}")

class PersonaUpdateView(PersonaCensoEditMixin, UpdateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    
    def get_success_url(self):
        return reverse("finanzas:persona_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Datos de la persona actualizados exitosamente.")
        return super().form_valid(form)

class PersonaDetailView(PersonaCensoAccessMixin, DetailView):
    model = Beneficiario
    template_name = "finanzas/persona_detail.html"
    context_object_name = "persona"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 1. Chequeo de permisos usando tu función de mixins.py
        ver_dinero = puede_ver_historial_economico(self.request.user)
        ctx['perms_ver_dinero'] = ver_dinero
        
        # 2. Carga Condicional de Datos Sensibles
        if ver_dinero:
            # Solo si tiene permiso, consultamos la base de datos de pagos
            pagos = Movimiento.objects.filter(
                beneficiario=self.object,
                tipo='INGRESO'
            ).order_by('-fecha_operacion')
            
            ctx['pagos_servicios'] = pagos
            ctx['total_pagado_historico'] = pagos.aggregate(total=Sum('monto'))['total'] or 0
        else:
            # Si no tiene permiso (ej: Operador Social), mandamos vacío para seguridad
            ctx['pagos_servicios'] = []
            ctx['total_pagado_historico'] = 0
        
        return ctx

class BeneficiarioUploadView(PersonaCensoEditMixin, CreateView):
    # CAMBIO IMPORTANTE: Usamos PersonaCensoEditMixin para que Social pueda subir DNI
    model = DocumentoBeneficiario
    form_class = DocumentoBeneficiarioForm
    template_name = "finanzas/persona_detail.html"

    def form_valid(self, form):
        beneficiario_id = self.kwargs['pk']
        beneficiario = get_object_or_404(Beneficiario, pk=beneficiario_id)
        
        documento = form.save(commit=False)
        documento.beneficiario = beneficiario
        documento.subido_por = self.request.user
        documento.save()
        
        messages.success(self.request, "Documento digitalizado y archivado correctamente.")
        return redirect('finanzas:persona_detail', pk=beneficiario_id)

    def form_invalid(self, form):
        beneficiario_id = self.kwargs['pk']
        messages.error(self.request, "Error al subir. Verificá el archivo.")
        return redirect('finanzas:persona_detail', pk=beneficiario_id)
# =========================================================
# 7) APIS AJAX (CRÍTICAS PARA EL FORMULARIO)
# =========================================================

@login_required
@require_GET
def persona_buscar_por_dni(request):
    """API para autocompletar DNI en formulario."""
    dni = (request.GET.get("dni") or "").strip()
    if not dni: return JsonResponse({"found": False})
    
    try:
        p = Beneficiario.objects.get(dni=dni, activo=True)
        return JsonResponse({
            "found": True, 
            "id": p.id, 
            "nombre": f"{p.apellido}, {p.nombre}",
            "text": f"{p.apellido}, {p.nombre} ({p.dni or 'S/D'})"
        })
    except Beneficiario.DoesNotExist:
        return JsonResponse({"found": False})

@login_required
@require_GET
def persona_autocomplete(request):
    """Select2 para personas."""
    q = (request.GET.get("term") or request.GET.get("q") or "").strip()
    if len(q) < 2: return JsonResponse({"results": []})
    
    qs = Beneficiario.objects.filter(activo=True).filter(
        Q(apellido__icontains=q) | 
        Q(nombre__icontains=q) | 
        Q(dni__icontains=q)
    )[:20]
    
    return JsonResponse({
        "results": [
            {"id": p.id, "text": f"{p.apellido}, {p.nombre} ({p.dni or 'S/D'})"} 
            for p in qs
        ]
    })

@login_required
@require_GET
def categorias_por_tipo(request):
    """
    API JSON para el selector dinámico de categorías en Movimientos.
    Devuelve flags para activar tabs de ayuda/combustible.
    """
    tipo_raw = (request.GET.get("tipo") or "").strip().upper()
    if not tipo_raw: return JsonResponse({"results": []})

    # Mapeo robusto de tipos
    if "ING" in tipo_raw: modo = "INGRESO"
    elif "GAS" in tipo_raw: modo = "GASTO"
    elif "TRANS" in tipo_raw: modo = "TRANSFERENCIA"
    else: return JsonResponse({"results": []}) # Tipo desconocido

    # Filtrar query
    qs = Categoria.objects.all() # Asumimos todas activas, si tenés campo 'activo', agregalo.
    
    cat_ing = getattr(Categoria, "TIPO_INGRESO", "INGRESO")
    cat_gas = getattr(Categoria, "TIPO_GASTO", "GASTO")
    cat_amb = getattr(Categoria, "TIPO_AMBOS", "AMBOS")

    if modo == "INGRESO":
        qs = qs.filter(tipo__in=[cat_ing, cat_amb])
    elif modo == "GASTO":
        qs = qs.filter(tipo__in=[cat_gas, cat_amb])
    
    # Ordenar y serializar
    qs = qs.order_by("grupo", "nombre")
    results = []
    
    for cat in qs:
        # Obtener label de grupo si existe método
        grupo = cat.get_grupo_display() if hasattr(cat, "get_grupo_display") else (getattr(cat, "grupo", "") or "General")
        
        results.append({
            "id": cat.id,
            "text": cat.nombre,
            "grupo": grupo,
            # Flags booleanos para el JS
            "es_ayuda_social": getattr(cat, "es_ayuda_social", False),
            "es_combustible": getattr(cat, "es_combustible", False),
        })

    return JsonResponse({"results": results})

@login_required
@require_POST
def proveedor_create_express(request):
    """API para crear proveedores al vuelo desde el formulario de movimientos."""
    try:
        razon_social = request.POST.get('razon_social', '').strip()
        cuit = request.POST.get('cuit', '').strip()
        telefono = request.POST.get('telefono', '').strip()

        if not razon_social:
            return JsonResponse({'status': 'error', 'message': 'La Razón Social es obligatoria.'}, status=400)

        # Verificar duplicados por CUIT si se ingresó uno
        if cuit and Proveedor.objects.filter(cuit=cuit).exists():
            return JsonResponse({'status': 'error', 'message': 'Ya existe un proveedor con ese CUIT.'}, status=400)

        proveedor = Proveedor.objects.create(
            razon_social=razon_social,
            cuit=cuit,
            telefono=telefono,
            creado_por=request.user
        )

        return JsonResponse({
            'status': 'success',
            'id': proveedor.id,
            'text': f"{proveedor.razon_social} ({proveedor.cuit or 'S/C'})",
            'razon_social': proveedor.razon_social,
            'cuit': proveedor.cuit or ''
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# =========================================================
# 8) REPORTES Y COMPROBANTES
# =========================================================

class ReciboIngresoPrintView(LoginRequiredMixin, View):
    def get(self, request, pk):
        mov = get_object_or_404(Movimiento, pk=pk)
        
        # 1. Validación de Tipo: Solo Ingresos
        if mov.tipo != Movimiento.TIPO_INGRESO:
            return HttpResponse("Este comprobante es válido solo para movimientos de Ingreso.", status=400)

        # 2. Validación de Estado (SEGURIDAD): Solo Aprobados
        if mov.estado != Movimiento.ESTADO_APROBADO:
            return HttpResponse("No se puede emitir recibo de un movimiento en Borrador o Rechazado.", status=400)

        # 3. Conversión a Letras (Num2Words)
        try:
            monto_letras = num2words(mov.monto, lang='es', to='currency', currency='ARS')
            # Limpieza extra: "con 00/100 centavos" -> "con 00/100"
            monto_letras = monto_letras.upper().replace("EUROS", "PESOS").replace("EURO", "PESO")
        except:
            monto_letras = f"${mov.monto} PESOS"

        # 4. Contexto
        context = {
            'mov': mov,
            'monto_letras': monto_letras,
            'hoy': timezone.now(),
            'municipio': 'COMUNA DE TACUARENDÍ',
            'cuit_municipio': '30-67433889-5', # ¡Asegurate de poner el real!
            'direccion': 'Calle 8 y 5- CP 3587',
            'provincia': 'Santa Fe',
            'logo_url': '/static/finanzas/img/logo-comuna.png',
            'usuario': request.user, # Para que salga "Cajero: Juan"
        }
        
        return render(request, 'finanzas/recibo_print.html', context)