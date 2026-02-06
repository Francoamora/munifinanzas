from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from .models import OrdenCompra, Proveedor, Vehiculo, SerieOC, Movimiento
from .forms import OrdenCompraForm, OrdenCompraLineaFormSet
from .mixins import StaffRequiredMixin, OperadorSocialRequiredMixin, roles_ctx

# ==================== LISTADO Y DETALLE ====================

class OCListView(OperadorSocialRequiredMixin, ListView):
    model = OrdenCompra
    template_name = "finanzas/oc_list.html"
    context_object_name = "ordenes"
    paginate_by = 20
    ordering = ["-id"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("proveedor", "area")
        q = self.request.GET.get("q")
        estado = self.request.GET.get("estado")
        
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) | 
                Q(proveedor__nombre__icontains=q) |
                Q(proveedor__cuit__icontains=q) |
                Q(proveedor_nombre__icontains=q) |
                Q(observaciones__icontains=q)
            )
        
        if estado and estado != "TODAS":
            qs = qs.filter(estado=estado)
            
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(roles_ctx(self.request.user))
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
                # Usamos el número que escribió el usuario
                # (Ya se validó en forms.py que no esté vacío)
                self.object.numero = form.cleaned_data['numero']
                # Opcional: Agregar prefijo si querés estandarizar, ej: "MAN-0052"
                # self.object.numero = f"MAN-{form.cleaned_data['numero']}"
            else:
                # --- LÓGICA AUTOMÁTICA ---
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
                # -------------------------

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
        ctx.update(roles_ctx(self.request.user))
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        ctx = self.get_context_data()
        lineas = ctx["lineas"]
        
        if form.is_valid() and lineas.is_valid():
            # En edición NO regeneramos número, mantenemos el que tiene
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

# ==================== APIS PARA SELECT2 ====================

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