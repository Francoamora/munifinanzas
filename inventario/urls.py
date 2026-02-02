from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    # === 1. GESTIÓN DE STOCK (TABLERO) ===
    path('', views.StockListView.as_view(), name='stock_list'),
    path('nuevo-articulo/', views.InsumoCreateView.as_view(), name='insumo_create'),
    path('articulo/<int:pk>/historial/', views.InsumoDetailView.as_view(), name='insumo_detail'),

    # === 2. MOVIMIENTOS GENERALES (COMPRAS/CONSUMO) ===
    path('registrar-movimiento/', views.MovimientoCreateView.as_view(), name='movimiento_create'),

    # === 3. GESTIÓN DE PRÉSTAMOS (PAÑOL) - ¡NUEVO! ===
    path('prestamos/', views.PrestamoListView.as_view(), name='prestamo_list'),
    path('prestamos/nuevo/', views.PrestamoCreateView.as_view(), name='prestamo_create'),
    path('prestamos/devolver/<int:pk>/', views.DevolucionView.as_view(), name='prestamo_devolver'),

    # === 4. API (AJAX) ===
    path('api/stock/', views.api_get_insumo_stock, name='api_get_stock'),
]