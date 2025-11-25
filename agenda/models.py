from django.db import models
from django.conf import settings
from django.utils import timezone

from finanzas.models import OrdenPago, Movimiento, Beneficiario, Proveedor


class Tarea(models.Model):
    # ===== tipos =====
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

    # ===== origen =====
    ORIGEN_MANUAL = "MANUAL"
    ORIGEN_SISTEMA = "SISTEMA"
    ORIGEN_CHOICES = [
        (ORIGEN_MANUAL, "Manual"),
        (ORIGEN_SISTEMA, "Sistema"),
    ]

    # ===== prioridad =====
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

    # ===== estado =====
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

    # ===== ámbito =====
    AMBITO_FINANZAS = "FINANZAS"
    AMBITO_SOCIAL = "SOCIAL"
    AMBITO_GENERAL = "GENERAL"
    AMBITO_CHOICES = [
        (AMBITO_FINANZAS, "Finanzas"),
        (AMBITO_SOCIAL, "Social"),
        (AMBITO_GENERAL, "General"),
    ]

    # ===== texto =====
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)

    # ===== clasificación =====
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_OTRO)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default=ORIGEN_MANUAL)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default=PRIORIDAD_MEDIA)

    # ===== estado =====
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)

    # ===== fechas =====
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    fecha_recordatorio = models.DateField(null=True, blank=True)
    fecha_completada = models.DateTimeField(null=True, blank=True)

    # ===== responsabilidad y ámbito =====
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_responsable",
    )
    ambito = models.CharField(max_length=10, choices=AMBITO_CHOICES, default=AMBITO_GENERAL)

    # ===== vínculos opcionales =====
    orden_pago = models.ForeignKey(
        OrdenPago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    movimiento = models.ForeignKey(
        Movimiento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    persona = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas",
    )

    # ===== auditoría =====
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tareas_actualizadas",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tarea / Pendiente"
        verbose_name_plural = "Tareas / Pendientes"
        ordering = ["fecha_vencimiento", "-prioridad", "-id"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["fecha_vencimiento"]),
            models.Index(fields=["responsable"]),
            models.Index(fields=["ambito"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["prioridad"]),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.get_estado_display()})"

    @property
    def esta_vencida(self) -> bool:
        hoy = timezone.now().date()
        return (
            self.estado in {self.ESTADO_PENDIENTE, self.ESTADO_EN_PROCESO}
            and self.fecha_vencimiento < hoy
        )

    @property
    def vence_hoy(self) -> bool:
        hoy = timezone.now().date()
        return self.fecha_vencimiento == hoy

    def marcar_completada(self, user=None):
        self.estado = self.ESTADO_COMPLETADA
        self.fecha_completada = timezone.now()
        if user and user.is_authenticated:
            self.actualizado_por = user
        self.save(update_fields=["estado", "fecha_completada", "actualizado_por", "actualizado_en"])
