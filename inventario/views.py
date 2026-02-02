from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from .models import Insumo, MovimientoStock, Prestamo
from .forms import InsumoForm, MovimientoStockForm, PrestamoForm

# ==========================================
# 1. GESTIÓN DE STOCK (ARTÍCULOS)
# ==========================================

class StockListView(LoginRequiredMixin, ListView):
    model = Insumo
    template_name = "inventario/stock_list.html"
    context_object_name = "insumos"
    
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(nombre__icontains=q)
        return qs

class InsumoCreateView(LoginRequiredMixin, CreateView):
    model = Insumo
    form_class = InsumoForm
    template_name = "inventario/insumo_form.html"
    success_url = reverse_lazy('inventario:stock_list')

    def form_valid(self, form):
        messages.success(self.request, "Artículo creado.")
        return super().form_valid(form)

class InsumoDetailView(LoginRequiredMixin, DetailView):
    model = Insumo
    template_name = "inventario/insumo_detail.html"
    context_object_name = "insumo"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Traemos los movimientos ordenados del más reciente al más viejo
        context['movimientos'] = self.object.movimientos.all().order_by('-fecha')
        return context

# ==========================================
# 2. MOVIMIENTOS GENERALES (Entradas/Salidas)
# ==========================================

class MovimientoCreateView(LoginRequiredMixin, CreateView):
    model = MovimientoStock
    form_class = MovimientoStockForm
    template_name = "inventario/movimiento_form.html"
    success_url = reverse_lazy('inventario:stock_list')

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, "Stock actualizado.")
        return super().form_valid(form)

# ==========================================
# 3. GESTIÓN DE PRÉSTAMOS (PAÑOL)
# ==========================================

class PrestamoListView(LoginRequiredMixin, ListView):
    """Muestra quién tiene qué cosa."""
    model = Prestamo
    template_name = "inventario/prestamo_list.html"
    context_object_name = "prestamos"
    ordering = ['-fecha_salida']

    def get_queryset(self):
        # Filtro para ver solo pendientes o todo
        qs = super().get_queryset()
        ver = self.request.GET.get('ver')
        if ver == 'pendientes':
            qs = qs.filter(estado='PENDIENTE')
        return qs

class PrestamoCreateView(LoginRequiredMixin, CreateView):
    """Saca una herramienta y la asigna a una persona."""
    model = Prestamo
    form_class = PrestamoForm
    template_name = "inventario/prestamo_form.html"
    success_url = reverse_lazy('inventario:prestamo_list')

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        try:
            # Esto dispara la lógica del modelo que resta stock automáticamente
            return super().form_valid(form)
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

class DevolucionView(LoginRequiredMixin, View):
    """Botón mágico para devolver."""
    def post(self, request, pk):
        prestamo = get_object_or_404(Prestamo, pk=pk)
        
        # Llamamos al método del modelo que suma el stock y cierra el préstamo
        exito = prestamo.registrar_devolucion(usuario=request.user)
        
        if exito:
            messages.success(request, f"Devolución de {prestamo.insumo.nombre} registrada.")
        else:
            messages.warning(request, "Este préstamo ya estaba cerrado.")
            
        return redirect('inventario:prestamo_list')

# ==========================================
# 4. API (AJAX) - ¡LA QUE FALTABA!
# ==========================================

def api_get_insumo_stock(request):
    """Devuelve el stock actual de un insumo para mostrarlo en formularios."""
    insumo_id = request.GET.get('id')
    if not insumo_id:
        return JsonResponse({'error': 'No ID provided'}, status=400)
    
    insumo = get_object_or_404(Insumo, pk=insumo_id)
    
    return JsonResponse({
        'id': insumo.id,
        'nombre': insumo.nombre,
        'stock': float(insumo.stock_actual),
        'unidad': insumo.get_unidad_display(),
        'es_herramienta': insumo.es_herramienta,
        'minimo': float(insumo.stock_minimo)
    })