from django.db import models
from django.conf import settings
from django.utils import timezone

# Importamos modelos de finanzas
from finanzas.models import OrdenPago, Movimiento, Beneficiario, Proveedor, Area, Vehiculo

# =========================================================
# 1. GESTIÓN DE TAREAS Y PENDIENTES
# =========================================================

class Tarea(models.Model):
    # ... (TUS CONSTANTES DE TIPO, ORIGEN, PRIORIDAD, ESTADO, AMBITO IGUAL QUE ANTES) ...
    TIPO_PAGO_VENCIMIENTO = "PAGO_VENCIMIENTO"
    TIPO_DOCUMENTACION = "DOCUMENTACION"
    TIPO_REUNION_EVENTO = "REUNION_EVENTO"
    TIPO_GESTION_ADMIN = "GESTION_ADMIN"
    TIPO_OTRO = "OTRO"

    TIPO_CHOICES = [
        (TIPO_PAGO_VENCIMIENTO, "Pago / vencimiento"),
        (TIPO_DOCUMENTACION, "Documentación"),
        (TIPO_REUNION_EVENTO, "Reunión / evento"),
        (TIPO_GESTION_ADMIN, "Gestión administrativa"),
        (TIPO_OTRO, "Otro"),
    ]

    ORIGEN_MANUAL = "MANUAL"
    ORIGEN_SISTEMA = "SISTEMA"
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, "Manual"),
        (ORIGEN_SISTEMA, "Sistema"),
    ]

    PRIORIDAD_BAJA = "BAJA"
    PRIORIDAD_MEDIA = "MEDIA"
    PRIORIDAD_ALTA = "ALTA"
    PRIORIDAD_CRITICA = "CRITICA"
    PRIORIDAD_CHOICES = [
        (PRIORIDAD_BAJA, "Baja"),
        (PRIORIDAD_MEDIA, "Media"),
        (PRIORIDAD_ALTA, "Alta"),
        (PRIORIDAD_CRITICA, "Crítica"),
    ]

    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_COMPLETADA = "COMPLETADA"
    ESTADO_CANCELADA = "CANCELADA"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_EN_PROCESO, "En proceso"),
        (ESTADO_COMPLETADA, "Completada"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    AMBITO_FINANZAS = "FINANZAS"
    AMBITO_SOCIAL = "SOCIAL"
    AMBITO_GENERAL = "GENERAL"
    AMBITO_CHOICES = [
        (AMBITO_FINANZAS, "Finanzas"),
        (AMBITO_SOCIAL, "Social"),
        (AMBITO_GENERAL, "General"),
    ]

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_OTRO)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default=PRIORIDAD_MEDIA)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    fecha_recordatorio = models.DateField(null=True, blank=True)
    fecha_completada = models.DateTimeField(null=True, blank=True)

    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tareas_responsable",
    )
    ambito = models.CharField(max_length=10, choices=AMBITO_CHOICES, default=AMBITO_GENERAL)

    orden_pago = models.ForeignKey(OrdenPago, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")
    movimiento = models.ForeignKey(Movimiento, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")
    persona = models.ForeignKey(Beneficiario, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_creadas")
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_actualizadas")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        ordering = ["fecha_vencimiento", "-prioridad", "-id"]

    def __str__(self):
        return f"{self.titulo} ({self.get_estado_display()})"


# =========================================================
# 2. OPERATIVO Y FLOTA (HOJA DE RUTA) - CORREGIDO
# =========================================================

class HojaRuta(models.Model):
    fecha = models.DateField(default=timezone.now)
    
    # ✅ FIX: related_name único para evitar choque con finanzas.HojaRuta
    vehiculo = models.ForeignKey(
        Vehiculo, 
        on_delete=models.CASCADE, 
        related_name='hojas_ruta_agenda' 
    )
    
    chofer = models.CharField(max_length=100, blank=True)
    destino = models.CharField(max_length=200, blank=True)
    km_salida = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    km_regreso = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    km_recorridos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    combustible_litros = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)
    
    # ✅ FIX: related_name único
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='hojas_ruta_creadas_agenda'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hoja de Ruta"
        verbose_name_plural = "Hojas de Ruta"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Viaje {self.id} - {self.vehiculo} ({self.fecha})"

    def save(self, *args, **kwargs):
        if self.km_regreso > self.km_salida:
            self.km_recorridos = self.km_regreso - self.km_salida
        super().save(*args, **kwargs)


# =========================================================
# 3. ATENCIÓN AL VECINO - CORREGIDO
# =========================================================

class Atencion(models.Model):
    TIPO_GENERAL = "GENERAL"
    TIPO_SOCIAL = "SOCIAL"
    TIPO_OBRAS = "OBRAS"
    TIPO_CHOICES = [
        (TIPO_GENERAL, "General / Trámite"),
        (TIPO_SOCIAL, "Acción Social"),
        (TIPO_OBRAS, "Reclamo Obras/Servicios"),
    ]

    fecha_atencion = models.DateField(default=timezone.now)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_GENERAL)
    
    # ✅ FIX: related_name único
    persona = models.ForeignKey(
        Beneficiario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="atenciones_agenda"
    )
    
    nombre_temporal = models.CharField(max_length=150, blank=True)
    motivo = models.CharField(max_length=255)
    detalle = models.TextField(blank=True)
    
    # ✅ FIX: related_name único
    derivado_a = models.ForeignKey(
        Area, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="atenciones_derivadas_agenda"
    )
    
    resuelto = models.BooleanField(default=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Atención"
        verbose_name_plural = "Atenciones"
        ordering = ["-fecha_atencion", "-id"]

    def __str__(self):
        return f"{self.fecha_atencion} - {self.motivo}"