import json
from decimal import Decimal
from datetime import datetime, timedelta, date
from itertools import chain
from operator import attrgetter
from .models import Cuenta, Categoria, Movimiento

# Django Imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q, Count, F, Avg, Value, CharField
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
    roles_ctx, 
    es_staff_finanzas, 
    puede_ver_historial_economico,
    SoloFinanzasMixin, 
    OperadorOperativoRequiredMixin, 
    GeneroRequiredMixin,
    StaffRequiredMixin, 
    OperadorFinanzasRequiredMixin, 
    OperadorSocialRequiredMixin,
    MovimientosAccessMixin, 
    DashboardAccessMixin, 
    OrdenPagoAccessMixin,
    OrdenPagoEditMixin, 
    PersonaCensoAccessMixin, 
    PersonaCensoEditMixin
)

# === MODELOS LOCALES (Finanzas) ===
from .models import (
    Movimiento, Categoria, Area, Proveedor, Beneficiario,
    OrdenPago, OrdenPagoLinea, OrdenCompra, OrdenCompraLinea, 
    Vehiculo, ProgramaAyuda, HojaRuta, 
    OrdenTrabajo, OrdenTrabajoMaterial, Atencion,
    DocumentoBeneficiario, DocumentoSensible, Cuenta,
    RubroDrei, DeclaracionJuradaDrei, LiquidacionDrei # 🚀 IMPORTACIONES DREI
)

# === FORMULARIOS ===
from .forms import (
    MovimientoForm, BeneficiarioForm, OrdenPagoForm, OrdenPagoLineaFormSet,
    OrdenCompraForm, OrdenCompraLineaFormSet,
    OrdenTrabajoForm, OrdenTrabajoMaterialFormSet,
    DocumentoBeneficiarioForm, DocumentoSensibleForm,
    ProveedorForm, DeclaracionJuradaDreiForm          # 🚀 IMPORTACIONES DREI FORMS
)

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

def _resolver_proveedor_y_beneficiario(form, movimiento) -> None:
    """Sincroniza FKs con campos de texto (snapshot)."""
    cleaned = form.cleaned_data
    
    # Proveedor
    prov_obj = cleaned.get("proveedor")
    if prov_obj:
        movimiento.proveedor = prov_obj
        # CORRECCIÓN CLAVE: Usamos .nombre en lugar de .razon_social
        movimiento.proveedor_nombre = prov_obj.nombre 
        movimiento.proveedor_cuit = prov_obj.cuit or ""
    
    # Beneficiario
    ben_obj = cleaned.get("beneficiario")
    if ben_obj:
        movimiento.beneficiario = ben_obj
        movimiento.beneficiario_nombre = f"{ben_obj.apellido}, {ben_obj.nombre}".strip()
        # Verificamos si el modelo tiene dni antes de asignarlo para evitar errores
        if hasattr(movimiento, 'beneficiario_dni'):
            movimiento.beneficiario_dni = ben_obj.dni or ""

def _redirect_movimiento_post_save(request, mov, msg: str):
    """Redirección inteligente según estado."""
    messages.success(request, msg)
    # Usamos string "APROBADO" o la constante si está importada
    if str(mov.estado) == "APROBADO": 
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
        # CORRECCIÓN: Ajustamos para recibir 'nombre' en lugar de 'razon_social'
        # ya que tu modelo Proveedor usa 'nombre'. Mantengo el fallback 'razon_social' 
        # por si tu frontend manda eso.
        nombre = request.POST.get('nombre', '').strip()
        if not nombre:
            nombre = request.POST.get('razon_social', '').strip()
            
        cuit = request.POST.get('cuit', '').strip()
        telefono = request.POST.get('telefono', '').strip()

        if not nombre:
            return JsonResponse({'status': 'error', 'message': 'El Nombre es obligatorio.'}, status=400)

        if cuit and Proveedor.objects.filter(cuit=cuit).exists():
            return JsonResponse({'status': 'error', 'message': 'Ya existe un proveedor con ese CUIT.'}, status=400)

        proveedor = Proveedor.objects.create(
            nombre=nombre, # Usando 'nombre'
            cuit=cuit,
            telefono=telefono,
            # No pasamos 'creado_por' porque tu modelo no tiene ese campo. Si lo tiene, agregalo.
        )

        return JsonResponse({
            'status': 'success',
            'id': proveedor.id,
            'text': f"{proveedor.nombre} ({proveedor.cuit or 'S/C'})",
            'razon_social': proveedor.nombre, # Mantengo la key para frontend
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
        
        # --- 1. CEREBRO DEL DASHBOARD (FECHAS NATIVAS) ---
        hoy = date.today()
        filtro = self.request.GET.get('ver', 'mes')
        
        # Filtros base
        fecha_inicio = hoy.replace(day=1) # Por defecto mes
        fecha_fin = hoy
        titulo_periodo = "Mes en Curso"

        if filtro == 'hoy':
            fecha_inicio = hoy
            fecha_fin = hoy
            titulo_periodo = "Día de Hoy"
        elif filtro == 'ayer':
            fecha_inicio = hoy - timedelta(days=1)
            fecha_fin = hoy - timedelta(days=1)
            titulo_periodo = "Día de Ayer"
        elif filtro == 'semana':
            fecha_inicio = hoy - timedelta(days=hoy.weekday())
            fecha_fin = hoy
            titulo_periodo = "Esta Semana"
        elif filtro == 'gestion':
            fecha_inicio = date(2025, 12, 10)
            fecha_fin = hoy
            titulo_periodo = "Gestión (Desde 10/12/2025)"
            
        # =================================================
        # 2. PULSO OPERATIVO (FILTROS BLINDADOS)
        # =================================================
        # Usamos __date (para castear dateTime a Date) o validaciones exactas de año/mes/dia si es un día específico
        
        # ATENCIONES
        if Atencion:
            if filtro in ['hoy', 'ayer']:
                # Búsqueda exacta por día para evitar problemas de horas
                ctx['atenciones_stat'] = Atencion.objects.filter(
                    fecha_atencion__year=fecha_inicio.year,
                    fecha_atencion__month=fecha_inicio.month,
                    fecha_atencion__day=fecha_inicio.day
                ).count()
            else:
                ctx['atenciones_stat'] = Atencion.objects.filter(
                    fecha_atencion__range=[fecha_inicio, fecha_fin]
                ).count()
        else:
            ctx['atenciones_stat'] = 0

        # FLOTA / VIAJES
        if filtro in ['hoy', 'ayer']:
            ctx['viajes_stat'] = HojaRuta.objects.filter(
                fecha__year=fecha_inicio.year,
                fecha__month=fecha_inicio.month,
                fecha__day=fecha_inicio.day
            ).count()
        else:
            ctx['viajes_stat'] = HojaRuta.objects.filter(
                fecha__range=[fecha_inicio, fecha_fin]
            ).count()

        # COMPRAS (OC)
        if filtro in ['hoy', 'ayer']:
            ctx['ocs_stat'] = OrdenCompra.objects.filter(
                fecha_oc__year=fecha_inicio.year,
                fecha_oc__month=fecha_inicio.month,
                fecha_oc__day=fecha_inicio.day
            ).exclude(estado=OrdenCompra.ESTADO_ANULADA).count()
        else:
            ctx['ocs_stat'] = OrdenCompra.objects.filter(
                fecha_oc__range=[fecha_inicio, fecha_fin]
            ).exclude(estado=OrdenCompra.ESTADO_ANULADA).count()

        # =================================================
        # 3. INTELIGENCIA FINANCIERA Y KPIS DE CAJA
        # =================================================
        
        if filtro in ['hoy', 'ayer']:
            movs_periodo = Movimiento.objects.filter(
                estado=Movimiento.ESTADO_APROBADO,
                fecha_operacion__year=fecha_inicio.year,
                fecha_operacion__month=fecha_inicio.month,
                fecha_operacion__day=fecha_inicio.day
            )
            ocs_periodo = OrdenCompraLinea.objects.filter(
                orden__fecha_oc__year=fecha_inicio.year,
                orden__fecha_oc__month=fecha_inicio.month,
                orden__fecha_oc__day=fecha_inicio.day,
                orden__estado__in=[OrdenCompra.ESTADO_AUTORIZADA, OrdenCompra.ESTADO_CERRADA]
            )
            ocs_sociales_periodo = OrdenCompra.objects.filter(
                fecha_oc__year=fecha_inicio.year,
                fecha_oc__month=fecha_inicio.month,
                fecha_oc__day=fecha_inicio.day,
                persona__isnull=False
            ).exclude(estado=OrdenCompra.ESTADO_ANULADA)
        else:
            movs_periodo = Movimiento.objects.filter(
                estado=Movimiento.ESTADO_APROBADO,
                fecha_operacion__range=[fecha_inicio, fecha_fin]
            )
            ocs_periodo = OrdenCompraLinea.objects.filter(
                orden__fecha_oc__range=[fecha_inicio, fecha_fin],
                orden__estado__in=[OrdenCompra.ESTADO_AUTORIZADA, OrdenCompra.ESTADO_CERRADA]
            )
            ocs_sociales_periodo = OrdenCompra.objects.filter(
                fecha_oc__range=[fecha_inicio, fecha_fin],
                persona__isnull=False
            ).exclude(estado=OrdenCompra.ESTADO_ANULADA)

        # Cálculos Financieros
        balance = movs_periodo.aggregate(
            ingresos=Sum("monto", filter=Q(tipo__iexact="INGRESO")),
            gastos=Sum("monto", filter=Q(tipo__iexact="GASTO"))
        )
        ingresos = balance["ingresos"] or 0
        gastos = balance["gastos"] or 0
        saldo_periodo = ingresos - gastos

        deuda_flotante_total = OrdenCompraLinea.objects.filter(
            orden__estado=OrdenCompra.ESTADO_AUTORIZADA
        ).aggregate(t=Sum('monto'))['t'] or 0

        # KPIs Combustible
        combustible_caja = movs_periodo.filter(tipo__iexact="GASTO", categoria__es_combustible=True).aggregate(t=Sum('monto'))['t'] or 0
        combustible_ocs = ocs_periodo.filter(orden__rubro_principal='CB').aggregate(t=Sum('monto'))['t'] or 0
        ctx['combustible_mes'] = combustible_caja + combustible_ocs

        # KPIs Sociales
        social_caja = movs_periodo.filter(tipo__iexact="GASTO", beneficiario__isnull=False).aggregate(t=Sum('monto'))['t'] or 0
        social_ocs = ocs_periodo.filter(orden__persona__isnull=False).aggregate(t=Sum('monto'))['t'] or 0
        
        ctx['ayudas_mes_monto'] = social_caja + social_ocs
        ctx['ayudas_mes_cant'] = (
            movs_periodo.filter(tipo__iexact="GASTO", beneficiario__isnull=False).count() +
            ocs_sociales_periodo.count()
        )

        # =================================================
        # 4. CONTEXTO FINAL
        # =================================================
        ultimos = Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO).select_related("categoria", "beneficiario", "proveedor").order_by("-fecha_operacion", "-id")[:7]

        ctx.update({
            "hoy": hoy,
            "titulo_periodo": titulo_periodo,
            "filtro_activo": filtro,
            "saldo_mes": saldo_periodo,             
            "total_ingresos_mes": ingresos,
            "total_gastos_mes": gastos,
            "deuda_flotante": deuda_flotante_total, 
            "saldo_real_disponible": saldo_periodo - deuda_flotante_total, 
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

class BalanceResumenView(SoloFinanzasMixin, TemplateView):
    template_name = "finanzas/balance_resumen.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 1. CONFIGURACIÓN DE FECHAS
        hoy = timezone.now().date()
        
        # Leemos 'periodo' o 'ver' para compatibilidad con botones del Dashboard
        periodo = self.request.GET.get("periodo") or self.request.GET.get("ver") or "mes"
        
        fecha_desde_str = self.request.GET.get("fecha_desde")
        fecha_hasta_str = self.request.GET.get("fecha_hasta")

        fecha_desde = hoy.replace(day=1)
        fecha_hasta = hoy
        titulo_periodo = "Mes Actual"

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
        elif periodo == "gestion":
            # Fecha de inicio de gestión
            fecha_desde = date(2025, 12, 10) 
            fecha_hasta = hoy
            titulo_periodo = "Gestión (Desde 10/12/2025)"
        elif periodo == "custom" and fecha_desde_str and fecha_hasta_str:
            try:
                fecha_desde = timezone.datetime.strptime(fecha_desde_str, "%Y-%m-%d").date()
                fecha_hasta = timezone.datetime.strptime(fecha_hasta_str, "%Y-%m-%d").date()
                titulo_periodo = f"Del {fecha_desde.strftime('%d/%m')} al {fecha_hasta.strftime('%d/%m')}"
            except ValueError:
                pass

        # 🚀 LA MAGIA ANTI-SQLITE: Creamos el límite exacto del día siguiente a las 00:00:00
        fecha_limite = fecha_hasta + timedelta(days=1)

        # 2. QUERYSETS BASE (MOVIMIENTOS DE CAJA)
        qs_historico = Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO)
        
        # Filtro estricto que atrapa horas ocultas
        qs_periodo = qs_historico.filter(
            fecha_operacion__gte=fecha_desde, 
            fecha_operacion__lt=fecha_limite
        )

        # 3. KPI FINANCIEROS (CAJA)
        ingresos_periodo = qs_periodo.filter(tipo__iexact="INGRESO").aggregate(s=Sum("monto"))["s"] or 0
        gastos_periodo = qs_periodo.filter(tipo__iexact="GASTO").aggregate(s=Sum("monto"))["s"] or 0
        saldo_periodo = ingresos_periodo - gastos_periodo

        # 4. KPI HISTÓRICOS
        hist_ingresos = qs_historico.filter(tipo__iexact="INGRESO").aggregate(s=Sum("monto"))["s"] or 0
        hist_gastos = qs_historico.filter(tipo__iexact="GASTO").aggregate(s=Sum("monto"))["s"] or 0
        saldo_caja = hist_ingresos - hist_gastos
        
        # 5. INDICADOR DE DEUDA FLOTANTE (Para el Balance también)
        # Esto es histórico total, no depende de fechas
        deuda_flotante_total = OrdenCompraLinea.objects.filter(
            orden__estado=OrdenCompra.ESTADO_AUTORIZADA
        ).aggregate(t=Sum('monto'))['t'] or 0

        # 6. DESGLOSES
        top_categorias = (qs_periodo.filter(tipo__iexact="GASTO")
                          .values("categoria__nombre")
                          .annotate(total=Sum("monto"), cantidad=Count("id"))
                          .order_by("-total")[:5])

        top_areas = (qs_periodo.filter(tipo__iexact="GASTO")
                     .values("area__nombre")
                     .annotate(total=Sum("monto"))
                     .order_by("-total")[:5])

        # 7. TERMÓMETRO SOCIAL (LIMPIEZA)
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

        # 8. EFICIENCIA OPERATIVA & COMBUSTIBLE REAL
        qs_viajes = HojaRuta.objects.filter(
            fecha__gte=fecha_desde, 
            fecha__lt=fecha_limite
        )
        total_viajes = qs_viajes.count()
        
        kms_data = qs_viajes.aggregate(total_km=Sum(F('odometro_fin') - F('odometro_inicio')))
        kms_recorridos = kms_data['total_km'] or 0
        
        # Cálculo de COMBUSTIBLE REAL (Caja + OCs) para eficiencia
        # A. Combustible pagado (Caja)
        gasto_combustible_caja = qs_periodo.filter(
            categoria__es_combustible=True
        ).aggregate(s=Sum("monto"))["s"] or 0

        # B. Combustible Comprometido (OCs)
        # Sumamos OCs del periodo que sean de combustible (Rubro CB)
        gasto_combustible_ocs = OrdenCompraLinea.objects.filter(
            orden__fecha_oc__gte=fecha_desde,
            orden__fecha_oc__lt=fecha_limite,
            orden__rubro_principal='CB',
            orden__estado__in=[OrdenCompra.ESTADO_AUTORIZADA, OrdenCompra.ESTADO_CERRADA]
        ).aggregate(s=Sum("monto"))["s"] or 0

        gasto_combustible_total = gasto_combustible_caja + gasto_combustible_ocs
        
        costo_promedio_viaje = gasto_combustible_total / total_viajes if total_viajes > 0 else 0

        # 9. TRAZABILIDAD
        movs_con_op = qs_periodo.filter(orden_pago__isnull=False).count()
        movs_directos = qs_periodo.filter(orden_pago__isnull=True, tipo__iexact="GASTO").count()

        ctx.update({
            "hoy": hoy,
            "titulo_periodo": titulo_periodo,
            "periodo_seleccionado": periodo,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            
            # Finanzas Caja
            "ingresos_periodo": ingresos_periodo,
            "gastos_periodo": gastos_periodo,
            "saldo_periodo": saldo_periodo,
            "movimientos_count": qs_periodo.count(),
            "saldo_caja": saldo_caja,
            
            # Deuda
            "deuda_flotante": deuda_flotante_total,
            
            # Tops
            "top_categorias": top_categorias,
            "top_areas": top_areas,
            "top_beneficiarios": top_beneficiarios,
            "top_barrios": top_barrios,
            
            # Operativo Real
            "total_viajes": total_viajes,
            "kms_recorridos": kms_recorridos,
            "gasto_combustible": gasto_combustible_total, # Ahora incluye OCs
            "costo_promedio_viaje": costo_promedio_viaje,
            
            "movs_con_op": movs_con_op,
            "movs_directos": movs_directos,
        })
        
        if 'roles_ctx' in globals(): 
            ctx.update(roles_ctx(self.request.user))
            
        return ctx


# =========================================================
# 3) PROVEEDORES Y COMERCIOS (MÓDULO TRIBUTARIO PRO)
# =========================================================
from django.db.models.functions import Coalesce 
from django.db.models import DecimalField  # 🚀 FIX: Importamos el campo que faltaba

class ProveedorListView(OperadorOperativoRequiredMixin, ListView):
    model = Proveedor
    template_name = "finanzas/proveedor_list.html"
    context_object_name = "proveedores"
    paginate_by = 20

    def get_queryset(self):
        qs = Proveedor.objects.all().order_by("nombre")
        q = (self.request.GET.get("q") or "").strip()
        
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | 
                Q(cuit__icontains=q) | 
                Q(rubro__icontains=q) |
                Q(padron_drei__icontains=q)
            )
            
        es_drei = self.request.GET.get("drei")
        if es_drei == "si":
            qs = qs.filter(es_contribuyente_drei=True)
            
        # 🚀 FIX: Usamos DecimalField() limpio gracias a la nueva importación
        qs = qs.annotate(
            total_compras=Coalesce(
                Sum(
                    'movimiento__monto', 
                    filter=Q(movimiento__tipo='GASTO', movimiento__estado='APROBADO')
                ),
                Value(0, output_field=DecimalField())
            ),
            deuda_drei=Coalesce(
                Sum(
                    'ddjj_drei__liquidacion__total_a_pagar',
                    filter=Q(ddjj_drei__liquidacion__estado='PENDIENTE')
                ),
                Value(0, output_field=DecimalField())
            ),
            meses_adeudados=Count(
                'ddjj_drei__liquidacion',
                filter=Q(ddjj_drei__liquidacion__estado='PENDIENTE')
            )
        )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        todos = Proveedor.objects.all()
        ctx['kpi_total_proveedores'] = todos.count()
        ctx['kpi_total_drei'] = todos.filter(es_contribuyente_drei=True).count()
        
        deuda_global = LiquidacionDrei.objects.filter(
            estado='PENDIENTE'
        ).aggregate(Sum('total_a_pagar'))['total_a_pagar__sum']
        
        ctx['kpi_deuda_global_drei'] = deuda_global if deuda_global else 0
        ctx['filtro_drei_activo'] = self.request.GET.get("drei") == "si"
        
        return ctx


class ProveedorCreateView(OperadorOperativoRequiredMixin, CreateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = "finanzas/proveedor_form.html"

    def get_success_url(self):
        return reverse_lazy("finanzas:proveedor_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Comercio/Proveedor registrado exitosamente.")
        return super().form_valid(form)


class ProveedorUpdateView(OperadorOperativoRequiredMixin, UpdateView):
    model = Proveedor
    form_class = ProveedorForm
    template_name = "finanzas/proveedor_form.html"
    
    def get_success_url(self):
        return reverse_lazy("finanzas:proveedor_detail", kwargs={"pk": self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, "Datos actualizados correctamente.")
        return super().form_valid(form)


class ProveedorDetailView(OperadorOperativoRequiredMixin, DetailView):
    """ Ficha Administrativa: Compras, Pagos y Datos de Contacto """
    model = Proveedor
    template_name = "finanzas/proveedor_detail.html"
    context_object_name = "proveedor"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ver_dinero = puede_ver_historial_economico(self.request.user)
        
        # Pagos realizados por la comuna a este proveedor
        pagos = Movimiento.objects.filter(
            proveedor=self.object, 
            tipo='GASTO', 
            estado='APROBADO'
        ).order_by("-fecha_operacion")
        
        ctx["ultimos_pagos"] = pagos[:10]
        ctx["total_pagado_historico"] = pagos.aggregate(Sum("monto"))["monto__sum"] or 0 if ver_dinero else None
        ctx["ultimas_ocs"] = OrdenCompra.objects.filter(proveedor=self.object).order_by("-fecha_oc")[:10]
        
        return ctx

# 🚀 NUEVA VISTA: EL EXPEDIENTE TRIBUTARIO (PANEL DEL CONTADOR)
class ProveedorDreiPanelView(OperadorOperativoRequiredMixin, DetailView):
    """ Panel exclusivo para gestión de tasas y declaraciones juradas """
    model = Proveedor
    template_name = "finanzas/proveedor_drei_panel.html"
    context_object_name = "comercio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Sábana de liquidaciones histórica
        liquidaciones = LiquidacionDrei.objects.filter(
            ddjj__comercio=self.object
        ).select_related('ddjj', 'ddjj__presentada_por').order_by('-ddjj__anio', '-ddjj__mes')
        
        ctx["liquidaciones"] = liquidaciones
        
        deuda = liquidaciones.filter(estado='PENDIENTE').aggregate(Sum('total_a_pagar'))['total_a_pagar__sum']
        ctx["deuda_total"] = deuda if deuda else 0
        
        # Formulario para el modal de carga
        ctx["form_ddjj"] = DeclaracionJuradaDreiForm(comercio=self.object)
        return ctx


class DDJJDreiCreateView(OperadorOperativoRequiredMixin, CreateView):
    """ Procesa la DDJJ y genera la boleta. Redirige al Panel DReI. """
    model = DeclaracionJuradaDrei
    form_class = DeclaracionJuradaDreiForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['comercio'] = get_object_or_404(Proveedor, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        comercio = get_object_or_404(Proveedor, pk=self.kwargs['pk'])
        
        ddjj = form.save(commit=False)
        ddjj.comercio = comercio
        ddjj.presentada_por = self.request.user
        ddjj.save()
        
        # Generación de la boleta (Liquidación)
        from datetime import date
        mes_v = ddjj.mes + 1 if ddjj.mes < 12 else 1
        anio_v = ddjj.anio if ddjj.mes < 12 else ddjj.anio + 1
        
        LiquidacionDrei.objects.create(
            ddjj=ddjj,
            fecha_vencimiento=date(anio_v, mes_v, 15),
            total_a_pagar=ddjj.impuesto_determinado,
            estado='PENDIENTE'
        )
        
        messages.success(self.request, f"DDJJ {ddjj.get_mes_display()}/{ddjj.anio} procesada. Boleta generada.")
        return redirect("finanzas:proveedor_drei_panel", pk=comercio.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Error en la declaración. Verifique si el período ya fue cargado.")
        return redirect("finanzas:proveedor_drei_panel", pk=self.kwargs['pk'])
        
# =========================================================
# 4) MOVIMIENTOS
# =========================================================

class MovimientoListView(SoloFinanzasMixin, ListView):
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

class MovimientoCreateView(OperadorSocialRequiredMixin, CreateView):
    """
    MODIFICADO: Permite acceso a Social (para cargar gastos) y Finanzas.
    """
    model = Movimiento
    form_class = MovimientoForm
    template_name = "finanzas/movimiento_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
        return ctx

    def get_success_url(self):
        # Lógica inteligente de redirección:
        # Si es Finanzas, va al listado para seguir auditando.
        # Si es Social, va al Home con un mensaje de éxito (porque NO tiene permiso de ver la lista).
        user = self.request.user
        if user.is_superuser or user.groups.filter(name='Finanzas').exists():
            return reverse_lazy('finanzas:movimiento_list')
        return reverse_lazy('finanzas:home')

    @transaction.atomic
    def form_valid(self, form):
        mov = form.save(commit=False)
        mov.creado_por = self.request.user
        accion = (self.request.POST.get("accion") or "").strip().lower()
        
        # Aprobación automática:
        # Si es Staff Finanzas aprueba directo.
        # Si es Social (y no staff), también dejamos que apruebe gastos menores 
        # (O podés forzar BORRADOR aquí si preferís que Finanzas revise).
        # Por ahora, dejamos que impacte directo para agilidad:
        mov.estado = Movimiento.ESTADO_APROBADO
        msg = "Movimiento registrado correctamente."
        
        if accion == "borrador":
            mov.estado = Movimiento.ESTADO_BORRADOR
            msg = "Guardado como borrador."
        
        # Helper para vincular la entidad correcta
        if hasattr(self, '_resolver_proveedor_y_beneficiario'):
             self._resolver_proveedor_y_beneficiario(form, mov)
        elif '_resolver_proveedor_y_beneficiario' in globals():
             _resolver_proveedor_y_beneficiario(form, mov)
        
        # Defaults de seguridad
        if not mov.tipo_pago_persona: 
            mov.tipo_pago_persona = "NINGUNO"
        
        mov.save()
        
        messages.success(self.request, msg)
        
        # Si hay redirect custom
        if '_redirect_movimiento_post_save' in globals():
            return _redirect_movimiento_post_save(self.request, mov, msg)
            
        return redirect(self.get_success_url())

class MovimientoUpdateView(OperadorFinanzasRequiredMixin, UpdateView):
    # SOLO FINANZAS PUEDE EDITAR (Seguridad)
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
# 6) PERSONAS (SOCIAL Y GÉNERO) - VISTA UNIFICADA
# =========================================================

from django.db.models import Sum, Q, Value, CharField, F
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse
from django.contrib import messages
from itertools import chain
from operator import attrgetter

# Modelos
from .models import Beneficiario, DocumentoBeneficiario, Movimiento, DocumentoSensible, OrdenCompra
from .forms import BeneficiarioForm, DocumentoBeneficiarioForm, DocumentoSensibleForm

# Mixins
from .mixins import (
    puede_ver_historial_economico, 
    PersonaCensoAccessMixin, 
    PersonaCensoEditMixin,
    GeneroRequiredMixin,
    roles_ctx
)

class PersonaListView(PersonaCensoAccessMixin, ListView):
    model = Beneficiario
    template_name = "finanzas/persona_list.html"
    context_object_name = "personas"
    paginate_by = 25

    def get_queryset(self):
        qs = Beneficiario.objects.all().order_by("apellido", "nombre")
        q = (self.request.GET.get("q") or "").strip()
        
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | 
                Q(apellido__icontains=q) | 
                Q(dni__icontains=q)
            )

        estado = self.request.GET.get("estado", "activos")
        if estado == "activos":
            qs = qs.filter(activo=True)
        elif estado == "inactivos":
            qs = qs.filter(activo=False)
        
        # Filtros Avanzados
        vinculo = self.request.GET.get("vinculo")
        if vinculo == "si":
            qs = qs.exclude(tipo_vinculo="NINGUNO")
        
        beneficio = self.request.GET.get("beneficio")
        if beneficio == "si":
            qs = qs.filter(percibe_beneficio=True)
            
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # KPI CARDS
        activos_qs = Beneficiario.objects.filter(activo=True)
        ctx["count_total"] = Beneficiario.objects.count()
        ctx["count_activos"] = activos_qs.count()
        ctx["count_inactivos"] = Beneficiario.objects.filter(activo=False).count()
        ctx["count_empleados"] = activos_qs.exclude(tipo_vinculo="NINGUNO").count()
        
        # Estado filtros
        ctx["estado_actual"] = self.request.GET.get("estado", "activos")
        ctx["q_actual"] = self.request.GET.get("q", "")
        ctx["highlight_id"] = self.request.GET.get("highlight")

        ctx["perms_ver_dinero"] = puede_ver_historial_economico(self.request.user)
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx

class PersonaCreateView(PersonaCensoEditMixin, CreateView):
    model = Beneficiario
    form_class = BeneficiarioForm
    template_name = "finanzas/persona_form.html"
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx
    
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
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx

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
        
        ver_dinero = puede_ver_historial_economico(self.request.user)
        ctx['perms_ver_dinero'] = ver_dinero
        
        # Variables de compatibilidad para el template rediseñado
        ctx['perms_ver_dinero_global'] = ver_dinero
        ctx['perms_ver_dinero_social'] = ver_dinero
        
        if ver_dinero:
            # 🚀 1. INGRESOS / TRIBUTOS (Lo que el vecino le paga a la Comuna)
            ingresos = Movimiento.objects.filter(
                beneficiario=self.object,
                tipo='INGRESO',
                estado=Movimiento.ESTADO_APROBADO
            ).select_related('categoria').order_by('-fecha_operacion')
            
            ctx['pagos_servicios'] = ingresos
            ctx['total_pagado_historico'] = ingresos.aggregate(total=Sum('monto'))['total'] or 0

            # 🚀 2. GASTOS (Jornales y Ayuda Social)
            todos_los_gastos = Movimiento.objects.filter(
                beneficiario=self.object,
                tipo='GASTO',
                estado=Movimiento.ESTADO_APROBADO
            ).select_related('categoria').annotate(
                fecha_ref=F('fecha_operacion')
            )
            
            pagos_ayuda = []
            pagos_laborales = []
            total_caja_ayuda = 0
            total_caja_laboral = 0
            
            # FILTRO INTELIGENTE: ¿Es Ayuda Social o es Pago por Servicio/Jornal?
            for p in todos_los_gastos:
                es_ayuda = (
                    (p.tipo_pago_persona and p.tipo_pago_persona != 'NINGUNO') or 
                    getattr(p.categoria, 'es_ayuda_social', False) or 
                    p.programa_ayuda_id is not None
                )
                
                if es_ayuda:
                    p.tipo_registro = 'CAJA_AYUDA'
                    pagos_ayuda.append(p)
                    total_caja_ayuda += p.monto
                else:
                    p.tipo_registro = 'CAJA_LABORAL'
                    pagos_laborales.append(p)
                    total_caja_laboral += p.monto

            # 🚀 3. Historial de OCs (Materiales / Insumos)
            compras = OrdenCompra.objects.filter(
                persona=self.object
            ).exclude(estado=OrdenCompra.ESTADO_ANULADA).annotate(
                tipo_registro=Value('OC', output_field=CharField()),
                fecha_ref=F('fecha_oc')
            )
            
            total_compras = sum(oc.total_monto for oc in compras)

            # 🚀 4. FUSIÓN Y SEPARACIÓN DE HISTORIALES
            historial_ayuda_unificado = sorted(
                chain(pagos_ayuda, compras),
                key=attrgetter('fecha_ref'),
                reverse=True
            )
            
            historial_laboral_ordenado = sorted(
                pagos_laborales,
                key=attrgetter('fecha_ref'),
                reverse=True
            )

            # Pasamos todo al template
            ctx['historial_unificado'] = historial_ayuda_unificado
            ctx['historial_laboral'] = historial_laboral_ordenado
            ctx['total_ayuda_historica'] = total_caja_ayuda + total_compras
            ctx['total_caja'] = total_caja_ayuda
            ctx['total_especies'] = total_compras
            ctx['total_jornales'] = total_caja_laboral

        else:
            ctx['pagos_servicios'] = []
            ctx['total_pagado_historico'] = 0
            ctx['historial_unificado'] = []
            ctx['historial_laboral'] = []
            ctx['total_ayuda_historica'] = 0
            ctx['total_jornales'] = 0
        
        if 'roles_ctx' in globals(): ctx.update(roles_ctx(self.request.user))
        return ctx

class BeneficiarioUploadView(PersonaCensoEditMixin, CreateView):
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
        messages.success(self.request, "Documento digitalizado correctamente.")
        return redirect('finanzas:persona_detail', pk=beneficiario_id)

    def form_invalid(self, form):
        return redirect('finanzas:persona_detail', pk=self.kwargs['pk'])

class DocumentoSensibleUploadView(GeneroRequiredMixin, CreateView):
    model = DocumentoSensible
    form_class = DocumentoSensibleForm
    template_name = "finanzas/persona_detail.html"

    def form_valid(self, form):
        beneficiario_id = self.kwargs['pk']
        beneficiario = get_object_or_404(Beneficiario, pk=beneficiario_id)
        doc = form.save(commit=False)
        doc.beneficiario = beneficiario
        doc.subido_por = self.request.user
        doc.save()
        messages.success(self.request, "Documento RESERVADO archivado bajo llave.")
        return redirect('finanzas:persona_detail', pk=beneficiario_id)

    def form_invalid(self, form):
        return redirect('finanzas:persona_detail', pk=self.kwargs['pk'])
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


# =========================================================
# FUNCIONES AUXILIARES ORDENES DE COMPRA
# =========================================================

def oc_cambiar_estado(request, pk, accion):
    """
    Permite Autorizar o Anular una OC desde el detalle.
    """
    oc = get_object_or_404(OrdenCompra, pk=pk)
    
    if accion == 'autorizar':
        if oc.estado == OrdenCompra.ESTADO_BORRADOR:
            oc.estado = OrdenCompra.ESTADO_AUTORIZADA
            oc.save()
            messages.success(request, f"OC #{oc.numero} AUTORIZADA correctamente.")
        else:
            messages.warning(request, "La orden no está en borrador.")
            
    elif accion == 'anular':
        if oc.estado != OrdenCompra.ESTADO_CERRADA: # No anular lo ya pagado
            oc.estado = OrdenCompra.ESTADO_ANULADA
            oc.save()
            messages.error(request, f"OC #{oc.numero} ANULADA.")
        else:
            messages.error(request, "No se puede anular una orden ya pagada/cerrada.")
            
    return redirect('finanzas:oc_detail', pk=pk)


def oc_generar_movimiento(request, pk):
    """
    Genera el MOVIMIENTO DE CAJA (Gasto) a partir de una OC Autorizada.
    Si la OC tiene Persona, el Gasto hereda la Persona (Impacto Social).
    """
    oc = get_object_or_404(OrdenCompra, pk=pk)
    
    # Validaciones
    if oc.estado != OrdenCompra.ESTADO_AUTORIZADA:
        messages.error(request, "Solo se pueden pagar órdenes AUTORIZADAS.")
        return redirect('finanzas:oc_detail', pk=pk)

    # Buscar Categoría y Cuenta por defecto
    # Intentamos usar la categoría del primer item, o buscamos "General"
    cat_item = oc.lineas.first().categoria if oc.lineas.exists() else None
    if not cat_item:
        cat_item = Categoria.objects.filter(nombre__icontains="General").first()
        if not cat_item: # Si no existe, agarramos la primera que haya
             cat_item = Categoria.objects.first()

    # Cuenta de origen (Caja principal - ID 1 o la primera)
    cuenta_origen = Cuenta.objects.first() 

    try:
        with transaction.atomic():
            # CREAR EL MOVIMIENTO (EL GASTO REAL)
            mov = Movimiento(
                tipo=Movimiento.TIPO_GASTO,
                fecha_operacion=timezone.now().date(),
                monto=oc.total_monto,
                
                # --- AQUÍ ESTÁ LA MAGIA ---
                # Si la OC tiene persona, el gasto hereda esa persona.
                beneficiario=oc.persona, 
                beneficiario_nombre=str(oc.persona) if oc.persona else "",
                
                proveedor=oc.proveedor,
                proveedor_nombre=oc.proveedor_nombre,
                proveedor_cuit=oc.proveedor_cuit,
                
                categoria=cat_item,
                area=oc.area,
                oc=oc, # Vinculamos la OC al movimiento para trazabilidad
                descripcion=f"Pago OC #{oc.numero} - {oc.proveedor_nombre}",
                estado=Movimiento.ESTADO_APROBADO, # Impacta saldo directo
                cuenta_origen=cuenta_origen, 
                creado_por=request.user
            )
            mov.save()

            # CERRAR LA OC
            oc.estado = OrdenCompra.ESTADO_CERRADA
            oc.save()

        messages.success(request, f"¡Pago registrado! Se generó el gasto y se cerró la OC #{oc.numero}.")
        return redirect('finanzas:movimiento_detail', pk=mov.pk)

    except Exception as e:
        messages.error(request, f"Error al generar el pago: {e}")
        return redirect('finanzas:oc_detail', pk=pk)


# =========================================================
# 🚀 MÓDULO TRIBUTARIO DREI (Vistas de Recaudación)
# =========================================================
from django.db.models.functions import Coalesce 
from django.db.models import DecimalField, Sum, Count, Q, Value
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView
from django.utils import timezone # Importante para la fecha del cobro
from .forms import DeclaracionJuradaDreiForm 
from .models import Proveedor, DeclaracionJuradaDrei, LiquidacionDrei, Cuenta, Categoria, Movimiento

class PadronDreiListView(OperadorOperativoRequiredMixin, ListView):
    """ Panel de Control Global para Recaudación DReI """
    model = Proveedor
    template_name = "finanzas/padron_drei_list.html"
    context_object_name = "contribuyentes"
    paginate_by = 30

    def get_queryset(self):
        qs = Proveedor.objects.filter(es_contribuyente_drei=True).order_by('nombre')
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | 
                Q(cuit__icontains=q) | 
                Q(padron_drei__icontains=q)
            )
        
        # Calculamos la deuda en tiempo real para el semáforo
        qs = qs.annotate(
            deuda_total=Coalesce(
                Sum(
                    'ddjj_drei__liquidacion__total_a_pagar',
                    filter=Q(ddjj_drei__liquidacion__estado='PENDIENTE')
                ),
                Value(0, output_field=DecimalField())
            ),
            meses_adeudados=Count(
                'ddjj_drei__liquidacion',
                filter=Q(ddjj_drei__liquidacion__estado='PENDIENTE')
            )
        )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contribuyentes = Proveedor.objects.filter(es_contribuyente_drei=True)
        ctx['total_contribuyentes'] = contribuyentes.count()
        
        deuda_global = LiquidacionDrei.objects.filter(
            estado='PENDIENTE'
        ).aggregate(Sum('total_a_pagar'))['total_a_pagar__sum']
        
        ctx['deuda_global'] = deuda_global if deuda_global else 0
        return ctx


class ProveedorDreiPanelView(OperadorOperativoRequiredMixin, DetailView):
    """ Panel exclusivo para gestión de tasas y declaraciones juradas de un comercio """
    model = Proveedor
    template_name = "finanzas/proveedor_drei_panel.html"
    context_object_name = "comercio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Sábana de liquidaciones histórica
        liquidaciones = LiquidacionDrei.objects.filter(
            ddjj__comercio=self.object
        ).select_related('ddjj', 'ddjj__presentada_por', 'ddjj__actividad').order_by('-ddjj__anio', '-ddjj__mes')
        
        ctx["liquidaciones"] = liquidaciones
        
        deuda = liquidaciones.filter(estado='PENDIENTE').aggregate(Sum('total_a_pagar'))['total_a_pagar__sum']
        ctx["deuda_total"] = deuda if deuda else 0
        
        # Pasamos el formulario para el modal de nueva DDJJ
        ctx["form_ddjj"] = DeclaracionJuradaDreiForm(comercio=self.object)
        return ctx


class DDJJDreiCreateView(OperadorOperativoRequiredMixin, CreateView):
    """ Procesa la DDJJ y genera la boleta. Redirige al Panel DReI. """
    model = DeclaracionJuradaDrei
    form_class = DeclaracionJuradaDreiForm
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['comercio'] = get_object_or_404(Proveedor, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        comercio = get_object_or_404(Proveedor, pk=self.kwargs['pk'])
        
        ddjj = form.save(commit=False)
        ddjj.comercio = comercio
        ddjj.presentada_por = self.request.user
        ddjj.save()
        
        # Generación de la boleta (Liquidación)
        from datetime import date
        mes_v = ddjj.mes + 1 if ddjj.mes < 12 else 1
        anio_v = ddjj.anio if ddjj.mes < 12 else ddjj.anio + 1
        
        LiquidacionDrei.objects.create(
            ddjj=ddjj,
            fecha_vencimiento=date(anio_v, mes_v, 15),
            total_a_pagar=ddjj.impuesto_determinado,
            estado='PENDIENTE'
        )
        
        messages.success(self.request, f"DDJJ {ddjj.get_mes_display()}/{ddjj.anio} procesada. Boleta generada.")
        return redirect("finanzas:proveedor_drei_panel", pk=comercio.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Error en la declaración. Verifique los datos o si el período ya fue cargado.")
        return redirect("finanzas:proveedor_drei_panel", pk=self.kwargs['pk'])


class LiquidacionDreiPrintView(OperadorOperativoRequiredMixin, DetailView):
    """ Genera la Boleta/Comprobante en formato imprimible """
    model = LiquidacionDrei
    template_name = "finanzas/liquidacion_drei_print.html"
    context_object_name = "liquidacion"

class LiquidacionDreiCobrarView(OperadorOperativoRequiredMixin, DetailView):
    """ Pantalla de Checkout y procesamiento de pago de DReI """
    model = LiquidacionDrei
    template_name = "finanzas/liquidacion_drei_cobrar.html"
    context_object_name = "liquidacion"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Traemos solo las cajas/cuentas activas para recibir el dinero
        ctx['cuentas'] = Cuenta.objects.filter(activa=True)
        return ctx

    def post(self, request, *args, **kwargs):
        liquidacion = self.get_object()
        
        # 1. Seguridad: Evitar doble cobro
        if liquidacion.estado == 'PAGADO':
            messages.warning(request, "Esta liquidación ya fue cobrada anteriormente.")
            return redirect('finanzas:proveedor_drei_panel', pk=liquidacion.ddjj.comercio.pk)

        # 2. Validar que eligió una cuenta
        cuenta_id = request.POST.get('cuenta_id')
        if not cuenta_id:
            messages.error(request, "Debe seleccionar la Caja o Cuenta de destino.")
            return self.get(request, *args, **kwargs)

        cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
        
        # 3. Buscar o crear la Categoría Contable "Recaudación DReI"
        categoria, _ = Categoria.objects.get_or_create(
            nombre="Recaudación DReI",
            tipo="INGRESO",
            defaults={"grupo": "Tributario"}
        )

        # 4. 🚀 FIX EXPERTO: Crear el Movimiento con 'cuenta_destino' y estado 'APROBADO'
        # Esto gatilla la actualización automática de saldo definida en tu modelo Movimiento.
        movimiento = Movimiento.objects.create(
            tipo="INGRESO",
            fecha_operacion=timezone.now().date(),
            monto=liquidacion.total_a_pagar,
            categoria=categoria,
            cuenta_destino=cuenta,             # <--- Atado contablemente a la Caja
            cuenta_destino_texto=cuenta.nombre,
            proveedor=liquidacion.ddjj.comercio,
            descripcion=f"Cobro DReI {liquidacion.ddjj.mes}/{liquidacion.ddjj.anio} - {liquidacion.ddjj.comercio.nombre}",
            estado="APROBADO",                 # <--- Obligatorio para que sume saldo
            creado_por=request.user
        )

        # 5. Marcar la Boleta como Pagada y atarle el recibo
        liquidacion.estado = 'PAGADO'
        liquidacion.movimiento_pago = movimiento
        liquidacion.save()

        messages.success(request, f"¡Cobro procesado con éxito! Se ingresaron ${liquidacion.total_a_pagar} a {cuenta.nombre}.")
        return redirect('finanzas:proveedor_drei_panel', pk=liquidacion.ddjj.comercio.pk)