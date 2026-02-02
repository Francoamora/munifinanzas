# inventario/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

# Importamos el Beneficiario de Finanzas para vincular personas reales
from finanzas.models import Beneficiario

class CategoriaInsumo(models.Model):
    """Ej: Construcción, Herramientas, Limpieza, Repuestos, Alimentos."""
    nombre = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

class Insumo(models.Model):
    UNIDADES = [
        ('UNIDAD', 'Unidad'),
        ('KG', 'Kilogramos'),
        ('LT', 'Litros'),
        ('MTS', 'Metros'),
        ('BOLSA', 'Bolsa'),
        ('CAJA', 'Caja'),
    ]

    nombre = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaInsumo, on_delete=models.PROTECT, related_name="insumos")
    codigo = models.CharField(max_length=50, blank=True, null=True, help_text="Código interno o de barra")
    unidad = models.CharField(max_length=20, choices=UNIDADES, default='UNIDAD')
    
    # Stock
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=5, help_text="Alerta cuando baje de esto")
    
    # Diferencia entre una Pala (Activo) y Cemento (Consumible)
    es_herramienta = models.BooleanField(default=False, verbose_name="¿Es Herramienta/Activo?", 
        help_text="Si se marca, habilita el sistema de Préstamos/Pañol.")
    
    descripcion = models.TextField(blank=True, null=True)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        tipo = "🔧" if self.es_herramienta else "📦"
        return f"{tipo} {self.nombre} ({self.stock_actual} {self.unidad})"

    class Meta:
        ordering = ['categoria', 'nombre']

class MovimientoStock(models.Model):
    """
    Registro histórico (LOG) de todo lo que entra y sale.
    No se edita directamente para mantener la integridad.
    """
    TIPOS = [
        ('ENTRADA', '🟢 Entrada / Compra'),
        ('SALIDA', '🔴 Salida / Consumo'),
        ('PRESTAMO', '🟠 Salida por Préstamo'),
        ('DEVOLUCION', '🔵 Reingreso por Devolución'),
        ('AJUSTE', '⚖️ Ajuste Inventario'),
    ]

    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE, related_name="movimientos")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Referencia de texto para búsquedas rápidas en el historial
    referencia = models.CharField(max_length=255, blank=True, null=True, 
        help_text="Ej: 'Préstamo a Juan Perez' o 'Compra OC-005'")

    def save(self, *args, **kwargs):
        # Lógica automática BLINDADA
        if not self.pk: # Solo al crear el movimiento
            if self.tipo in ['ENTRADA', 'DEVOLUCION']:
                self.insumo.stock_actual += self.cantidad
            elif self.tipo in ['SALIDA', 'PRESTAMO']:
                # Validar stock negativo
                if self.insumo.stock_actual < self.cantidad:
                    raise ValidationError(f"No hay stock suficiente de {self.insumo.nombre}. Stock actual: {self.insumo.stock_actual}")
                self.insumo.stock_actual -= self.cantidad
            elif self.tipo == 'AJUSTE':
                self.insumo.stock_actual += self.cantidad
            
            self.insumo.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.insumo.nombre} ({self.cantidad})"

# ==========================================
# 🆕 EL CEREBRO DEL PAÑOL: PRÉSTAMOS
# ==========================================
class Prestamo(models.Model):
    """
    Controla quién tiene qué cosa y si la devolvió.
    """
    ESTADOS = [
        ('PENDIENTE', '🟠 Pendiente de Devolución'),
        ('DEVUELTO', '✅ Devuelto / Cerrado'),
        ('PERDIDO', '❌ Perdido / No Devuelto'),
    ]

    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, limit_choices_to={'es_herramienta': True})
    # Vinculamos con la base de datos de Personas de Finanzas
    responsable = models.ForeignKey(Beneficiario, on_delete=models.PROTECT, related_name="herramientas_prestadas", verbose_name="Responsable")
    
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    fecha_salida = models.DateTimeField(default=timezone.now)
    fecha_devolucion = models.DateTimeField(null=True, blank=True)
    
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    observaciones_salida = models.TextField(blank=True, null=True, help_text="Estado al salir (ej: Nueva, Usada)")
    observaciones_devolucion = models.TextField(blank=True, null=True, help_text="Estado al volver (ej: Rota, Ok)")
    
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-fecha_salida']
        verbose_name = "Préstamo de Herramienta"
        verbose_name_plural = "Pañol / Préstamos"

    def __str__(self):
        return f"{self.insumo.nombre} -> {self.responsable} ({self.estado})"

    def clean(self):
        # Validación extra al crear
        if not self.pk and self.estado == 'PENDIENTE':
            if self.insumo.stock_actual < self.cantidad:
                raise ValidationError(f"No hay suficiente stock de {self.insumo.nombre} para prestar.")

    def save(self, *args, **kwargs):
        es_nuevo = not self.pk
        super().save(*args, **kwargs)

        # 1. Si es NUEVO, generamos el Movimiento de SALIDA (Resta Stock)
        if es_nuevo and self.estado == 'PENDIENTE':
            MovimientoStock.objects.create(
                insumo=self.insumo,
                tipo='PRESTAMO',
                cantidad=self.cantidad,
                usuario=self.creado_por,
                referencia=f"Préstamo a {self.responsable.apellido}, {self.responsable.nombre}"
            )

    def registrar_devolucion(self, usuario, estado_herramienta="", fecha=None):
        """
        Método mágico para llamar desde la Vista o Botón "Devolver".
        """
        if self.estado != 'PENDIENTE':
            return False # Ya estaba devuelto

        self.estado = 'DEVUELTO'
        self.fecha_devolucion = fecha or timezone.now()
        self.observaciones_devolucion = estado_herramienta
        self.save()

        # Generamos el Movimiento de DEVOLUCIÓN (Suma Stock)
        MovimientoStock.objects.create(
            insumo=self.insumo,
            tipo='DEVOLUCION',
            cantidad=self.cantidad,
            usuario=usuario,
            referencia=f"Devolución de {self.responsable.apellido}, {self.responsable.nombre}"
        )
        return True