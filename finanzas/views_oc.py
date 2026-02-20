from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta

from .models import OrdenCompra, Proveedor, Vehiculo, SerieOC, Movimiento, Beneficiario
from .forms import OrdenCompraForm, OrdenCompraLineaFormSet, BeneficiarioQuickForm
from .mixins import StaffRequiredMixin, OperadorSocialRequiredMixin, roles_ctx

# ==================== LISTADO Y DETALLE ====================

class OCListView(OperadorSocialRequiredMixin, ListView):
    model = OrdenCompra
    template_name = "finanzas/oc_list.html"
    context_object_name = "ordenes"
    paginate_by = 30
    ordering = ["-id"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("proveedor", "area", "persona")
        q = self.request.GET.get("q")
        estado = self.request.GET.get("estado", "PENDIENTES")
        rubro = self.request.GET.get("rubro")
        fecha_desde = self.request.GET.get("fecha_desde")
        fecha_hasta = self.request.GET.get("fecha_hasta")
        
        # Filtro de Búsqueda
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) | 
                Q(proveedor__nombre__icontains=q) |
                Q(proveedor__cuit__icontains=q) |
                Q(proveedor_nombre__icontains=q) |
                Q(persona__nombre__icontains=q) |
                Q(persona__apellido__icontains=q)
            )
        
        # Filtro de Estado
        if estado == "PENDIENTES":
            qs = qs.filter(estado__in=[OrdenCompra.ESTADO_BORRADOR, OrdenCompra.ESTADO_AUTORIZADA])
        elif estado != "TODAS":
            qs = qs.filter(estado=estado)
            
        # Filtro de Rubro
        if rubro:
            qs = qs.filter(rubro_principal=rubro)
            
        # Filtro de Fechas con Escudo Anti-SQLite
        if fecha_desde:
            try:
                desde_date = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
                qs = qs.filter(fecha_oc__gte=desde_date)
            except ValueError:
                pass
                
        if fecha_hasta:
            try:
                hasta_date = datetime.strptime(fecha_hasta, "%Y-%m-%d").date() + timedelta(days=1)
                qs = qs.filter(fecha_oc__lt=hasta_date)
            except ValueError:
                pass
            
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Inyectamos permisos y roles
        ctx.update(roles_ctx(self.request.user))
        
        # Validación: Solo calcular KPIs si el usuario es de Finanzas o Superadmin
        es_finanzas = self.request.user.is_superuser or self.request.user.groups.filter(name='Finanzas').exists()
        ctx['es_finanzas'] = es_finanzas
        
        if es_finanzas:
            # Los KPIs se calculan sobre el queryset YA FILTRADO
            qs_filtrado = self.get_queryset()
            
            # 1. Total emitido (excluye anuladas) - USAMOS LINEAS__MONTO PARA EVITAR ERROR 500
            ctx['kpi_total_emitido'] = qs_filtrado.exclude(
                estado=OrdenCompra.ESTADO_ANULADA
            ).aggregate(t=Sum('lineas__monto'))['t'] or 0
            
            # 2. Deuda Latente (Borradores y Autorizadas del filtro actual)
            ctx['kpi_deuda_pendiente'] = qs_filtrado.filter(
                estado__in=[OrdenCompra.ESTADO_BORRADOR, OrdenCompra.ESTADO_AUTORIZADA]
            ).aggregate(t=Sum('lineas__monto'))['t'] or 0
            
            # 3. Cantidades
            ctx['kpi_cantidad_ocs'] = qs_filtrado.exclude(estado=OrdenCompra.ESTADO_ANULADA).count()
            ctx['kpi_cantidad_anuladas'] = qs_filtrado.filter(estado=OrdenCompra.ESTADO_ANULADA).count()
            
        # Pasamos opciones del modelo de forma segura
        ctx['RUBROS_OC'] = getattr(OrdenCompra, 'RUBROS_CHOICES', getattr(OrdenCompra, 'RUBRO_CHOICES', []))
        ctx['rubro_actual'] = self.request.GET.get("rubro", "")
        
        return ctx

class OCDetailView(OperadorSocialRequiredMixin, DetailView):
    model = OrdenCompra
    template_name = "finanzas/oc_detail.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        total = self.object.lineas.aggregate(suma=Sum('monto'))['suma'] or 0
        ctx['total_oc'] = total
        ctx.update(roles_ctx(self.request.user))
        return ctx

# ==================== CREACIÓN Y EDICIÓN (CORE) ====================

class OCCreateView(OperadorSocialRequiredMixin, CreateView):
    model = OrdenCompra
    form_class = OrdenCompraForm
    template_name = "finanzas/oc_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas"] = OrdenCompraLineaFormSet(self.request.POST)
        else:
            ctx["lineas"] = OrdenCompraLineaFormSet()
        
        ctx["beneficiario_form"] = BeneficiarioQuickForm()
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        lineas = ctx["lineas"]
        
        if form.is_valid() and lineas.is_valid():
            self.object = form.save(commit=False)
            self.object.creado_por = self.request.user
            self.object.estado = OrdenCompra.ESTADO_BORRADOR
            
            tipo_num = form.cleaned_data.get('tipo_numeracion')

            if tipo_num == 'MANUAL':
                self.object.numero = form.cleaned_data['numero']
            else:
                serie, created = SerieOC.objects.get_or_create(
                    nombre="General", 
                    defaults={'prefijo': 'OC', 'siguiente_numero': 1, 'activo': True}
                )
                prefijo = serie.prefijo or "OC"
                numero_str = str(serie.siguiente_numero).zfill(6)
                self.object.numero = f"{prefijo}-{numero_str}"
                self.object.serie = serie
                serie.siguiente_numero += 1
                serie.save()

            if self.object.proveedor:
                self.object.proveedor_nombre = self.object.proveedor.nombre
                self.object.proveedor_cuit = self.object.proveedor.cuit or ""

            self.object.save()
            
            lineas.instance = self.object
            lineas.save()
            
            messages.success(self.request, f"Orden de Compra #{self.object.numero} creada exitosamente.")
            return redirect("finanzas:oc_detail", pk=self.object.pk)
        
        messages.error(self.request, "Error al crear la orden. Revise los campos marcados en rojo.")
        return self.render_to_response(self.get_context_data(form=form))

class OCUpdateView(OperadorSocialRequiredMixin, UpdateView):
    model = OrdenCompra
    form_class = OrdenCompraForm
    template_name = "finanzas/oc_form.html"
    context_object_name = "orden"
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.estado != OrdenCompra.ESTADO_BORRADOR and not request.user.is_superuser:
            messages.warning(request, "Solo se pueden editar Órdenes en estado BORRADOR.")
            return redirect("finanzas:oc_detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["lineas"] = OrdenCompraLineaFormSet(self.request.POST, instance=self.object)
        else:
            ctx["lineas"] = OrdenCompraLineaFormSet(instance=self.object)
        
        ctx["beneficiario_form"] = BeneficiarioQuickForm()
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        lineas = ctx["lineas"]
        
        if form.is_valid() and lineas.is_valid():
            self.object = form.save()
            lineas.save()
            messages.success(self.request, "Orden de Compra actualizada correctamente.")
            return redirect("finanzas:oc_detail", pk=self.object.pk)
            
        messages.error(self.request, "Error al actualizar la orden.")
        return self.render_to_response(self.get_context_data(form=form))

# ==================== ACCIONES Y ESTADOS ====================

class OCCambiarEstadoView(OperadorSocialRequiredMixin, View):
    def post(self, request, pk, accion):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        
        if accion == "autorizar" and oc.estado == OrdenCompra.ESTADO_BORRADOR:
            oc.estado = OrdenCompra.ESTADO_AUTORIZADA
        elif accion == "cerrar" and oc.estado == OrdenCompra.ESTADO_AUTORIZADA:
            if not request.user.groups.filter(name='Finanzas').exists() and not request.user.is_superuser:
                 messages.error(request, "Solo Finanzas puede cerrar órdenes manualmente.")
                 return redirect("finanzas:oc_detail", pk=pk)
            oc.estado = OrdenCompra.ESTADO_CERRADA
        elif accion == "anular":
            oc.estado = OrdenCompra.ESTADO_ANULADA
        elif accion == "borrador" and oc.estado == OrdenCompra.ESTADO_ANULADA:
            oc.estado = OrdenCompra.ESTADO_BORRADOR
        else:
            messages.error(request, "Transición de estado no permitida.")
            return redirect("finanzas:oc_detail", pk=pk)
            
        oc.save()
        messages.info(request, f"Estado actualizado a: {oc.get_estado_display()}")
        return redirect("finanzas:oc_detail", pk=pk)

class OCAutorizarMasivoView(StaffRequiredMixin, View):
    """Vista para autorizar múltiples OCs de golpe (Solo Jefaturas/Finanzas)."""
    @transaction.atomic
    def post(self, request):
        oc_ids = request.POST.getlist("oc_ids")
        
        if not oc_ids:
            messages.warning(request, "No seleccionaste ninguna orden para autorizar.")
            return redirect("finanzas:oc_list")
            
        ordenes = OrdenCompra.objects.filter(id__in=oc_ids, estado=OrdenCompra.ESTADO_BORRADOR)
        cantidad = ordenes.count()
        
        if cantidad > 0:
            ordenes.update(estado=OrdenCompra.ESTADO_AUTORIZADA)
            messages.success(request, f"¡Éxito! Se autorizaron {cantidad} Órdenes de Compra.")
        else:
            messages.error(request, "Las órdenes seleccionadas ya estaban autorizadas o no existen.")
            
        return redirect("finanzas:oc_list")

class OCGenerarMovimientoView(StaffRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        
        if oc.estado != OrdenCompra.ESTADO_AUTORIZADA:
            messages.error(request, "Solo se pueden pagar OCs AUTORIZADAS.")
            return redirect("finanzas:oc_detail", pk=pk)

        total = oc.total_monto 
        if total <= 0:
            messages.error(request, "La OC tiene monto cero.")
            return redirect("finanzas:oc_detail", pk=pk)

        primera_linea = oc.lineas.first()
        categoria_ref = primera_linea.categoria if primera_linea else None
        
        if not categoria_ref:
             messages.error(request, "La OC no tiene ítems/categoría para imputar.")
             return redirect("finanzas:oc_detail", pk=pk)

        Movimiento.objects.create(
            tipo=Movimiento.TIPO_GASTO,
            fecha_operacion=timezone.now().date(),
            monto=total,
            categoria=categoria_ref,
            area=oc.area,
            proveedor=oc.proveedor,
            proveedor_nombre=oc.proveedor_nombre,
            proveedor_cuit=oc.proveedor_cuit,
            descripcion=f"Pago OC #{oc.numero} - {oc.observaciones[:50]}",
            estado=Movimiento.ESTADO_APROBADO,
            creado_por=request.user
        )
        
        oc.estado = OrdenCompra.ESTADO_CERRADA
        oc.save()
        
        messages.success(request, f"Pago de ${total} registrado en caja. OC #{oc.numero} cerrada.")
        return redirect("finanzas:oc_detail", pk=pk)

# ==================== APIS PARA AJAX/SELECT2 ====================

@require_POST
@login_required
def api_beneficiario_create(request):
    form = BeneficiarioQuickForm(request.POST)
    if form.is_valid():
        b = form.save(commit=False)
        b.activo = True
        b.save()
        return JsonResponse({
            'success': True,
            'id': b.id,
            'text': f"{b.apellido}, {b.nombre} ({b.dni})",
            'msg': 'Vecino registrado correctamente.'
        })
    else:
        errors = "\n".join([f"{k}: {v[0]}" for k, v in form.errors.items()])
        return JsonResponse({'success': False, 'error': errors})

@require_GET
@login_required
def proveedor_por_cuit(request):
    cuit = request.GET.get("cuit", "").strip()
    try:
        p = Proveedor.objects.get(cuit=cuit, activo=True)
        return JsonResponse({"encontrado": True, "nombre": p.nombre, "id": p.id})
    except Proveedor.DoesNotExist:
        return JsonResponse({"encontrado": False})

@require_GET
@login_required
def proveedor_suggest(request):
    q = request.GET.get("term", "").strip() or request.GET.get("q", "").strip()
    qs = Proveedor.objects.filter(activo=True)
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(cuit__icontains=q))
    
    data = [{
        "id": p.id, 
        "text": f"{p.nombre} ({p.cuit or 'S/C'})",
        "nombre": p.nombre,
        "cuit": p.cuit or ""
    } for p in qs[:20]]
    return JsonResponse({"results": data})

@require_GET
@login_required
def vehiculo_por_patente(request):
    q = request.GET.get("term", "").strip()
    qs = Vehiculo.objects.filter(activo=True)
    if q:
        qs = qs.filter(Q(patente__icontains=q) | Q(descripcion__icontains=q))
    
    data = [{"id": v.id, "text": f"{v.patente} - {v.descripcion}"} for v in qs[:10]]
    return JsonResponse({"results": data})

@require_GET
@login_required
def ocs_pendientes_por_proveedor(request):
    pid = request.GET.get("proveedor_id")
    if not pid:
        return JsonResponse({"results": []})

    qs = OrdenCompra.objects.filter(
        proveedor_id=pid,
        estado=OrdenCompra.ESTADO_AUTORIZADA
    ).order_by("fecha_oc")

    data = []
    for oc in qs:
        total = oc.total_monto 
        data.append({
            "id": oc.id,
            "text": f"OC #{oc.numero} ({oc.fecha_oc.strftime('%d/%m')}) - ${total:,.2f}",
            "total": float(total),
            "fecha": oc.fecha_oc.strftime("%Y-%m-%d"),
            "rubro": oc.get_rubro_principal_display()
        })

    return JsonResponse({"results": data})