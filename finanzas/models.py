from decimal import Decimal

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class Area(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"

    def __str__(self):
        return self.nombre


class Cuenta(models.Model):
    TIPO_CAJA = "CAJA"
    TIPO_BANCO = "BANCO"
    TIPO_OTRO = "OTRO"
    TIPO_CHOICES = [
        (TIPO_CAJA, "Caja"),
        (TIPO_BANCO, "Banco"),
        (TIPO_OTRO, "Otro"),
    ]

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_BANCO)
    numero_cuenta = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cuenta"
        verbose_name_plural = "Cuentas"

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    TIPO_INGRESO = "INGRESO"
    TIPO_GASTO = "GASTO"
    TIPO_AMBOS = "AMBOS"
    TIPO_CHOICES = [
        (TIPO_INGRESO, "Ingreso"),
        (TIPO_GASTO, "Gasto"),
        (TIPO_AMBOS, "Ambos"),
    ]

    # Grupos para franja de gastos en navbar / reportes
    GRUPO_VEHICULOS = "VEHICULOS"
    GRUPO_INSUMOS = "INSUMOS"
    GRUPO_CONSTRUCCION = "CONSTRUCCION"
    GRUPO_AYUDAS = "AYUDAS"
    GRUPO_OTROS = "OTROS"
    GRUPO_CHOICES = [
        (GRUPO_VEHICULOS, "Vehículos"),
        (GRUPO_INSUMOS, "Insumos generales"),
        (GRUPO_CONSTRUCCION, "Construcción / Obra"),
        (GRUPO_AYUDAS, "Ayudas sociales"),
        (GRUPO_OTROS, "Otros"),
    ]

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default=TIPO_GASTO,
        db_index=True,
        help_text=(
            "Define si la categoría se usa para INGRESOS, GASTOS o en AMBOS. "
            "Las vistas de movimientos pueden filtrar automáticamente por tipo."
        ),
    )
    grupo = models.CharField(
        max_length=20,
        choices=GRUPO_CHOICES,
        default=GRUPO_OTROS,
        help_text=(
            "Sirve para agrupar gastos en vistas "
            "(vehículos, insumos, construcción, ayudas, etc.)"
        ),
    )
    es_ayuda_social = models.BooleanField(
        default=False,
        help_text="Marca si esta categoría corresponde a ayudas sociales a personas u hogares.",
    )
    es_servicio = models.BooleanField(
        default=False,
        help_text="Marca si esta categoría corresponde a cobro de servicios municipales (agua, tasas, etc.).",
    )
    es_combustible = models.BooleanField(
        default=False,
        help_text="Marca si esta categoría es de combustible.",
    )
    es_personal = models.BooleanField(
        default=False,
        help_text="Marca si esta categoría corresponde a sueldos, jornales u otros gastos de personal.",
    )
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre

    # ===== Helpers de compatibilidad con movimientos =====

    def aplica_a_tipo_movimiento(self, tipo_movimiento: str) -> bool:
        """
        Indica si esta categoría es compatible con un tipo de Movimiento dado.

        Reglas actuales:
        - Para INGRESO: categorías marcadas como INGRESO o AMBOS.
        - Para GASTO: categorías marcadas como GASTO o AMBOS.
        - Para TRANSFERENCIA: por ahora no se restringe desde el modelo; la UI
          puede decidir qué mostrar (por ej. una o dos categorías específicas).
        """
        if not tipo_movimiento:
            return True

        if tipo_movimiento == "INGRESO":
            return self.tipo in {self.TIPO_INGRESO, self.TIPO_AMBOS}
        if tipo_movimiento == "GASTO":
            return self.tipo in {self.TIPO_GASTO, self.TIPO_AMBOS}
        # Para transferencias no forzamos nada desde el modelo.
        return True


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200)
    cuit = models.CharField(max_length=20, blank=True, db_index=True)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        if self.cuit:
            return f"{self.nombre} ({self.cuit})"
        return self.nombre


class Beneficiario(models.Model):
    TIPO_VINCULO_NINGUNO = "NINGUNO"
    TIPO_VINCULO_PLANTA = "PLANTA"
    TIPO_VINCULO_JORNAL = "JORNAL"
    TIPO_VINCULO_EVENTUAL = "EVENTUAL"
    TIPO_VINCULO_HONORARIO = "HONORARIO"

    TIPO_VINCULO_CHOICES = [
        (TIPO_VINCULO_NINGUNO, "Sin vínculo laboral"),
        (TIPO_VINCULO_PLANTA, "Planta permanente"),
        (TIPO_VINCULO_JORNAL, "Jornalizado"),
        (TIPO_VINCULO_EVENTUAL, "Eventual / changuista"),
        (TIPO_VINCULO_HONORARIO, "Honorarios / contratad@"),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    dni = models.CharField(max_length=20, blank=True, db_index=True)
    direccion = models.CharField(max_length=255, blank=True)
    barrio = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    notas = models.TextField(blank=True)

    # Relación con servicios municipales
    paga_servicios = models.BooleanField(
        default=False,
        help_text="Indica si esta persona paga servicios a la comuna (agua, tasas, etc.).",
    )
    detalle_servicios = models.CharField(
        max_length=255,
        blank=True,
        help_text="Detalle del servicio (N° conexión, lote, referencia de pago, etc.).",
    )

    # Relación laboral con la comuna (sueldos, changas, etc.)
    tipo_vinculo = models.CharField(
        max_length=20,
        choices=TIPO_VINCULO_CHOICES,
        default=TIPO_VINCULO_NINGUNO,
        help_text="Vínculo laboral con la comuna (planta, jornal, eventual, honorarios).",
    )
    sector_laboral = models.ForeignKey(
        "Area",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beneficiarios_laborales",
        help_text="Área o sector en el que trabaja para la comuna (si corresponde).",
    )

    # ===== Beneficios sociales / pensiones =====
    percibe_beneficio = models.BooleanField(
        default=False,
        help_text="Indica si percibe pensión o algún beneficio social (AUH, PNC, jubilación, etc.).",
    )
    beneficio_detalle = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ej: AUH, Pensión no contributiva, Jubilación mínima, Potenciar Trabajo, Tarjeta Alimentar, etc.",
    )
    beneficio_organismo = models.CharField(
        max_length=120,
        blank=True,
        help_text="Organismo que lo otorga. Ej: ANSES, Provincia, Comuna, ONG, etc.",
    )
    beneficio_monto_aprox = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monto aproximado mensual (si se conoce).",
    )

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Beneficiario"
        verbose_name_plural = "Beneficiarios"

    def __str__(self):
        return f"{self.apellido}, {self.nombre}"

    @property
    def tiene_vinculo_laboral(self) -> bool:
        """True si tiene algún tipo de vínculo laboral con la comuna."""
        return self.tipo_vinculo != self.TIPO_VINCULO_NINGUNO

    # ===== Helpers pensados para historial de ayudas / movilidad =====

    @property
    def movimientos_ayudas_sociales(self):
        """
        Movimientos de gasto APROBADOS que son ayudas sociales (dinero, materiales, etc.)
        asociados a esta persona.

        Se usa en la ficha de persona para el historial clásico de ayudas económicas.
        """
        from .models import Movimiento  # import local para evitar acople circular

        return self.movimientos.filter(
            estado=Movimiento.ESTADO_APROBADO,
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_ayuda_social=True,
        )

    @property
    def viajes_ayuda_movilidad(self):
        """
        Viajes en los que la persona fue beneficiaria trasladada
        (ayuda de movilidad / transporte).

        Filtra solo viajes en estado CERRADO para usar en el historial social /
        ficha de persona.
        """
        from .models import ViajeVehiculo  # import local

        # related_name="viajes_trasladado" viene de ViajeVehiculo.beneficiarios
        return self.viajes_trasladado.filter(
            estado=ViajeVehiculo.ESTADO_CERRADO
        )

    @property
    def viajes_vehiculo_todos(self):
        """
        Atajo para obtener todos los viajes vehiculares donde la persona fue trasladada,
        sin filtrar por estado. Útil para vistas internas o reportes.
        """
        return self.viajes_trasladado.all()

    @property
    def cantidad_viajes_ayuda_movilidad(self) -> int:
        """
        Cantidad de viajes cerrados donde la persona fue beneficiaria trasladada.
        """
        return self.viajes_ayuda_movilidad.count()

    @property
    def total_km_viajes_ayuda_movilidad(self) -> int:
        """
        Suma de km recorridos en viajes de ayuda de movilidad (solo viajes cerrados).

        Depende de la propiedad km_recorridos de ViajeVehiculo.
        """
        return sum(v.km_recorridos for v in self.viajes_ayuda_movilidad)

    @property
    def cantidad_atenciones(self) -> int:
        """Cantidad de atenciones sociales registradas para esta persona."""
        return self.atenciones.count()

    @property
    def ultima_atencion(self):
        """Última atención registrada (o None si nunca fue atendida)."""
        return self.atenciones.order_by("-fecha_atencion", "-id").first()


# =========================
#   ATENCIONES SOCIALES
# =========================

class Atencion(models.Model):
    """
    Registro de atenciones a personas (tipo mesa de entrada social):
    reclamos, consultas, pedidos de ayuda, etc.

    No pisa Agenda: se integra con el censo (Beneficiario) y puede
    vincular una Tarea de agenda de seguimiento si hace falta.
    """

    # Motivo principal / tipo de demanda
    MOTIVO_CONSULTA = "CONSULTA"
    MOTIVO_RECLAMO = "RECLAMO"
    MOTIVO_SOLICITUD_AYUDA = "SOLICITUD_AYUDA"
    MOTIVO_TRAMITE = "TRAMITE"
    MOTIVO_DENUNCIA = "DENUNCIA"
    MOTIVO_OTRO = "OTRO"

    MOTIVO_CHOICES = [
        (MOTIVO_CONSULTA, "Consulta / información"),
        (MOTIVO_RECLAMO, "Reclamo"),
        (MOTIVO_SOLICITUD_AYUDA, "Solicitud de ayuda"),
        (MOTIVO_TRAMITE, "Trámite / gestión administrativa"),
        (MOTIVO_DENUNCIA, "Denuncia / situación grave"),
        (MOTIVO_OTRO, "Otro"),
    ]

    # Canal de atención
    CANAL_PRESENCIAL = "PRESENCIAL"
    CANAL_TELEFONICO = "TELEFONICO"
    CANAL_WHATSAPP = "WHATSAPP"
    CANAL_VISITA = "VISITA_DOMICILIO"
    CANAL_OTRO = "OTRO"

    CANAL_CHOICES = [
        (CANAL_PRESENCIAL, "Presencial en comuna"),
        (CANAL_TELEFONICO, "Telefónico"),
        (CANAL_WHATSAPP, "WhatsApp / redes"),
        (CANAL_VISITA, "Visita a domicilio"),
        (CANAL_OTRO, "Otro canal"),
    ]

    # Estado de seguimiento
    ESTADO_ABIERTA = "ABIERTA"
    ESTADO_EN_SEGUIMIENTO = "EN_SEGUIMIENTO"
    ESTADO_CERRADA = "CERRADA"

    ESTADO_CHOICES = [
        (ESTADO_ABIERTA, "Abierta"),
        (ESTADO_EN_SEGUIMIENTO, "En seguimiento"),
        (ESTADO_CERRADA, "Cerrada"),
    ]

    # Prioridad percibida
    PRIORIDAD_BAJA = "BAJA"
    PRIORIDAD_MEDIA = "MEDIA"
    PRIORIDAD_ALTA = "ALTA"
    PRIORIDAD_URGENTE = "URGENTE"

    PRIORIDAD_CHOICES = [
        (PRIORIDAD_BAJA, "Baja"),
        (PRIORIDAD_MEDIA, "Media"),
        (PRIORIDAD_ALTA, "Alta"),
        (PRIORIDAD_URGENTE, "Urgente"),
    ]

    # Persona atendida (censo + texto libre)
    persona = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atenciones",
        help_text="Persona atendida (si está cargada en el censo).",
    )
    persona_nombre = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nombre de la persona atendida (texto libre, si no está en el censo).",
    )
    persona_dni = models.CharField(
        max_length=20,
        blank=True,
        help_text="DNI para casos donde aún no se cargó el censo.",
    )
    persona_barrio = models.CharField(
        max_length=100,
        blank=True,
        help_text="Barrio o paraje de la persona atendida.",
    )

    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atenciones",
        help_text="Área que tomó nota / intervino en la atención.",
    )

    fecha_atencion = models.DateField(
        default=timezone.now,
        db_index=True,
        help_text="Fecha en la que se realizó / registró la atención.",
    )
    hora_atencion = models.TimeField(
        null=True,
        blank=True,
        help_text="Hora aproximada de la atención (opcional).",
    )

    motivo_principal = models.CharField(
        max_length=20,
        choices=MOTIVO_CHOICES,
        default=MOTIVO_CONSULTA,
        help_text="Motivo principal que trae la persona.",
    )
    canal = models.CharField(
        max_length=20,
        choices=CANAL_CHOICES,
        default=CANAL_PRESENCIAL,
        help_text="Canal por el cual se tomó la atención.",
    )
    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDAD_CHOICES,
        default=PRIORIDAD_MEDIA,
        help_text="Prioridad social percibida de la situación.",
    )

    descripcion = models.TextField(
        blank=True,
        help_text="Descripción de lo que planteó la persona (resumen claro).",
    )
    resultado = models.TextField(
        blank=True,
        help_text="Qué se hizo en el momento: orientación, derivación, ayuda concreta, etc.",
    )

    requiere_seguimiento = models.BooleanField(
        default=False,
        help_text="Marcá si requiere seguimiento futuro (llamado, visita, gestión).",
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_CERRADA,
        help_text="Estado de la atención respecto al seguimiento.",
    )

    tarea_seguimiento = models.ForeignKey(
        "agenda.Tarea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atenciones",
        help_text="Tarea en Agenda vinculada para el seguimiento (si existe).",
    )

    origen_interno = models.CharField(
        max_length=200,
        blank=True,
        help_text="Referencia interna: operativo, escuela, institución, barrio, etc.",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atenciones_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atenciones_actualizadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Atención a persona"
        verbose_name_plural = "Atenciones a personas"
        ordering = ["-fecha_atencion", "-id"]
        indexes = [
            models.Index(fields=["fecha_atencion", "estado"]),
            models.Index(fields=["persona_dni"]),
        ]
        permissions = [
            (
                "ver_panel_atenciones",
                "Puede ver el panel resumido de atenciones sociales",
            ),
        ]

    def __str__(self):
        if self.persona:
            nombre = f"{self.persona.apellido}, {self.persona.nombre}"
        else:
            nombre = self.persona_nombre or "Persona sin identificar"
        fecha = self.fecha_atencion.strftime("%d/%m/%Y") if self.fecha_atencion else ""
        return f"{fecha} – {nombre} ({self.get_motivo_principal_display()})"

    @property
    def persona_resumen(self) -> str:
        """Nombre + DNI, ya mezclando censo y texto libre."""
        if self.persona:
            base = f"{self.persona.apellido}, {self.persona.nombre}"
        else:
            base = self.persona_nombre or "Sin nombre"
        if self.persona_dni:
            return f"{base} ({self.persona_dni})"
        return base

    @property
    def esta_abierta(self) -> bool:
        return self.estado == self.ESTADO_ABIERTA

    @property
    def esta_en_seguimiento(self) -> bool:
        return self.estado == self.ESTADO_EN_SEGUIMIENTO

    @property
    def esta_cerrada(self) -> bool:
        return self.estado == self.ESTADO_CERRADA


class Vehiculo(models.Model):
    patente = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    area = models.ForeignKey("Area", on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)

    # Opcional: kilometraje y horómetro de referencia
    kilometraje_referencia = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Kilometraje de referencia (último servicio / alta). Opcional.",
    )
    horometro_referencia = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Horómetro de referencia (si aplica). Opcional.",
    )

    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"

    def __str__(self):
        return f"{self.patente} - {self.descripcion}".strip(" -")

    @property
    def etiqueta_busqueda(self) -> str:
        """
        Etiqueta amigable para autocompletados:
        combina patente + descripción.
        """
        if self.descripcion:
            return f"{self.patente} – {self.descripcion}"
        return self.patente

    @property
    def km_acumulados_viajes(self) -> int:
        """
        Suma de km recorridos en viajes vehiculares registrados.
        No es cacheado: usar para reportes puntuales, no en listas enormes.
        """
        return sum(
            viaje.km_recorridos
            for viaje in self.viajes_vehiculo.all()
        )


class ProgramaAyuda(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Programa de ayuda"
        verbose_name_plural = "Programas de ayuda"

    def __str__(self):
        return self.nombre


# =========================
#   ÓRDENES DE COMPRA (OC)
# =========================

class SerieOC(models.Model):
    """
    Serie / numeración para Órdenes de Compra.
    Ejemplo: SERIE 2025, prefijo 'OC-2025-'.
    """
    nombre = models.CharField(max_length=100)
    prefijo = models.CharField(
        max_length=20,
        blank=True,
        help_text="Prefijo opcional para la numeración (ej: 'OC-2025-' o 'AS-').",
    )
    siguiente_numero = models.PositiveIntegerField(
        default=1,
        help_text="Próximo número correlativo para esta serie.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Serie de OC"
        verbose_name_plural = "Series de OC"

    def __str__(self):
        base = self.nombre or "Serie OC"
        if self.prefijo:
            return f"{base} ({self.prefijo})"
        return base


class OrdenCompra(models.Model):
    """
    Orden de Compra: registra autorizaciones de gasto antes de la Orden de Pago.
    Puede vincularse luego a movimientos aprobados.
    """

    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_AUTORIZADA = "AUTORIZADA"
    ESTADO_CERRADA = "CERRADA"
    ESTADO_ANULADA = "ANULADA"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_AUTORIZADA, "Autorizada"),
        (ESTADO_CERRADA, "Cerrada"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    # Rubros macro para OC (alineado con views_oc)
    RUBRO_AYUDAS = "AS"
    RUBRO_COMBUSTIBLE = "CB"
    RUBRO_OBRAS = "OB"
    RUBRO_SERVICIOS = "SV"
    RUBRO_PERSONAL = "PE"
    RUBRO_HERRAMIENTAS = "HI"
    RUBRO_OTROS = "OT"

    RUBRO_CHOICES = [
        (RUBRO_AYUDAS, "Ayudas sociales"),
        (RUBRO_COMBUSTIBLE, "Combustible"),
        (RUBRO_OBRAS, "Obras y materiales"),
        (RUBRO_SERVICIOS, "Servicios contratados"),
        (RUBRO_PERSONAL, "Personal / jornales / changas"),
        (RUBRO_HERRAMIENTAS, "Herramientas / insumos generales"),
        (RUBRO_OTROS, "Otros"),
    ]

    serie = models.ForeignKey(
        SerieOC,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra",
        help_text="Serie opcional para numeración (puede quedar vacía).",
    )
    numero = models.CharField(
        max_length=30,
        blank=True,
        help_text=(
            "Número interno de la OC. Si lo dejás vacío y usás serie, se puede "
            "autogenerar desde la serie. En la impresión se muestra junto con rubro/serie."
        ),
    )
    fecha_oc = models.DateField(
        help_text="Fecha de emisión de la orden de compra.",
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
        db_index=True,
    )

    rubro_principal = models.CharField(
        max_length=2,
        choices=RUBRO_CHOICES,
        blank=True,
        help_text="Rubro macro de la OC (para filtros rápidos).",
    )

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra",
    )
    proveedor_nombre = models.CharField(
        max_length=200,
        blank=True,
        help_text="Texto que se imprime en la OC (por si cambiás el proveedor en el maestro).",
    )
    proveedor_cuit = models.CharField(max_length=20, blank=True)

    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra",
    )

    observaciones = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_actualizadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orden de compra"
        verbose_name_plural = "Órdenes de compra"
        ordering = ["-fecha_oc", "-id"]

    def __str__(self):
        numero = self.numero_completo
        proveedor = (
            self.proveedor_nombre
            or (self.proveedor.nombre if self.proveedor else "")
        )
        return f"{numero} - {proveedor}".strip(" -")

    @property
    def numero_completo(self) -> str:
        """
        Número 'humano' para mostrar en la UI e impresos.

        Prioriza:
        - serie.prefijo, si existe (ej: 'AS-' o 'OC-2025-')
        - si no hay serie: usa el código de rubro (AS, CB, etc.) como prefijo
        - luego el número interno (o el ID como último recurso)
        """
        base = self.numero or (self.pk and str(self.pk)) or ""
        prefijo = ""

        if self.serie and self.serie.prefijo:
            prefijo = self.serie.prefijo
        elif self.rubro_principal:
            prefijo = f"{self.rubro_principal}-"

        if prefijo and base:
            return f"{prefijo}{base}"
        if base:
            return base
        if self.pk:
            return f"OC {self.pk}"
        return "(sin número)"

    @property
    def total_monto(self) -> Decimal:
        """
        Suma de montos de las líneas de la OC.
        """
        from django.db.models import Sum as _Sum

        total = self.lineas.aggregate(total=_Sum("monto"))["total"]
        if total is None:
            return Decimal("0.00")
        return total

    @property
    def esta_pendiente(self) -> bool:
        """
        Consideramos pendiente todo lo que no esté cerrado ni anulado.
        """
        return self.estado not in {
            self.ESTADO_CERRADA,
            self.ESTADO_ANULADA,
        }

    @property
    def categoria_principal(self):
        """
        Devuelve una categoría "representativa" de la OC para generar movimientos.
        Estrategia: primera categoría no nula de las líneas.
        """
        linea = (
            self.lineas.select_related("categoria")
            .filter(categoria__isnull=False)
            .order_by("id")
            .first()
        )
        return linea.categoria if linea else None


class OrdenCompraLinea(models.Model):
    orden = models.ForeignKey(
        OrdenCompra,
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ordenes_compra_lineas",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_lineas",
    )
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    beneficiario = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_compra_lineas",
    )

    class Meta:
        verbose_name = "Línea de orden de compra"
        verbose_name_plural = "Líneas de órdenes de compra"

    def __str__(self):
        return f"{self.descripcion} - {self.monto}"


class FacturaOC(models.Model):
    """
    Facturas/comprobantes asociados a una Orden de Compra.
    Se usan para control interno y conciliación.
    """

    FACTURA_TIPO_CHOICES = [
        ("A", "Factura A"),
        ("B", "Factura B"),
        ("C", "Factura C"),
        ("X", "Factura X / Ticket"),
        ("OTRO", "Otro comprobante"),
    ]

    orden = models.ForeignKey(
        OrdenCompra,
        on_delete=models.CASCADE,
        related_name="facturas",
    )
    tipo = models.CharField(
        max_length=10,
        choices=FACTURA_TIPO_CHOICES,
        blank=True,
    )
    numero = models.CharField(max_length=50, blank=True)
    fecha = models.DateField(null=True, blank=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Factura de OC"
        verbose_name_plural = "Facturas de OC"

    def __str__(self):
        base = self.numero or f"Factura OC {self.pk}"
        return base


# =========================
#   ORDEN DE PAGO
# =========================

class OrdenPago(models.Model):
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_AUTORIZADA = "AUTORIZADA"
    ESTADO_FACTURADA = "FACTURADA"
    ESTADO_PAGADA = "PAGADA"
    ESTADO_ANULADA = "ANULADA"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_AUTORIZADA, "Autorizada"),
        (ESTADO_FACTURADA, "Facturada"),
        (ESTADO_PAGADA, "Pagada"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    CONDICION_CONTADO = "CONTADO"
    CONDICION_30 = "30"
    CONDICION_60 = "60"
    CONDICION_OTRO = "OTRO"

    CONDICION_PAGO_CHOICES = [
        (CONDICION_CONTADO, "Contado"),
        (CONDICION_30, "30 días"),
        (CONDICION_60, "60 días"),
        (CONDICION_OTRO, "Otro plazo"),
    ]

    MEDIO_EFECTIVO = "EFECTIVO"
    MEDIO_TRANSFERENCIA = "TRANSFERENCIA"
    MEDIO_CHEQUE = "CHEQUE"
    MEDIO_OTRO = "OTRO"

    MEDIO_PAGO_CHOICES = [
        (MEDIO_EFECTIVO, "Efectivo"),
        (MEDIO_TRANSFERENCIA, "Transferencia bancaria"),
        (MEDIO_CHEQUE, "Cheque"),
        (MEDIO_OTRO, "Otro medio"),
    ]

    FACTURA_TIPO_CHOICES = [
        ("A", "Factura A"),
        ("B", "Factura B"),
        ("C", "Factura C"),
        ("X", "Factura X / Ticket"),
        ("OTRO", "Otro comprobante"),
    ]

    numero = models.CharField(
        max_length=30,
        blank=True,
        help_text="Número interno de la orden (podés completarlo luego).",
    )
    fecha_orden = models.DateField()
    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
        db_index=True,
    )

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago",
    )
    proveedor_nombre = models.CharField(
        max_length=200,
        blank=True,
        help_text="Texto que se imprime en la orden (por si cambiás el proveedor en el maestro).",
    )
    proveedor_cuit = models.CharField(max_length=20, blank=True)

    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago",
    )

    condicion_pago = models.CharField(
        max_length=20,
        choices=CONDICION_PAGO_CHOICES,
        blank=True,
    )
    medio_pago_previsto = models.CharField(
        max_length=20,
        choices=MEDIO_PAGO_CHOICES,
        blank=True,
    )

    observaciones = models.TextField(blank=True)

    factura_tipo = models.CharField(
        max_length=10,
        choices=FACTURA_TIPO_CHOICES,
        blank=True,
    )
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_fecha = models.DateField(null=True, blank=True)
    factura_monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago_actualizadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orden de pago"
        verbose_name_plural = "Órdenes de pago"
        ordering = ["-fecha_orden", "-id"]

    def __str__(self):
        numero = self.numero or f"OP {self.pk}"
        proveedor = (
            self.proveedor_nombre
            or (self.proveedor.nombre if self.proveedor else "")
        )
        return f"{numero} - {proveedor}".strip(" -")

    @property
    def total_monto(self) -> Decimal:
        from django.db.models import Sum as _Sum

        total = self.lineas.aggregate(total=_Sum("monto"))["total"]
        if total is None:
            return Decimal("0.00")
        return total

    @property
    def esta_pendiente(self) -> bool:
        return self.estado not in {
            self.ESTADO_PAGADA,
            self.ESTADO_ANULADA,
        }


class OrdenPagoLinea(models.Model):
    orden = models.ForeignKey(
        OrdenPago,
        on_delete=models.CASCADE,
        related_name="lineas",
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ordenes_pago_lineas",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago_lineas",
    )
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    beneficiario = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_pago_lineas",
    )

    class Meta:
        verbose_name = "Línea de orden de pago"
        verbose_name_plural = "Líneas de órdenes de pago"

    def __str__(self):
        return f"{self.descripcion} - {self.monto}"


class Movimiento(models.Model):
    TIPO_INGRESO = "INGRESO"
    TIPO_GASTO = "GASTO"
    TIPO_TRANSFERENCIA = "TRANSFERENCIA"
    TIPO_CHOICES = [
        (TIPO_INGRESO, "Ingreso"),
        (TIPO_GASTO, "Gasto"),
        (TIPO_TRANSFERENCIA, "Transferencia"),
    ]

    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_APROBADO = "APROBADO"
    ESTADO_RECHAZADO = "RECHAZADO"
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_APROBADO, "Aprobado"),
        (ESTADO_RECHAZADO, "Rechazado"),
    ]

    # Tipo de pago vinculado a persona (solo si hay beneficiario)
    PAGO_PERSONA_NINGUNO = "NINGUNO"
    PAGO_PERSONA_SUELDO = "SUELDO"
    PAGO_PERSONA_CHANGA = "CHANGA"

    PAGO_PERSONA_CHOICES = [
        (PAGO_PERSONA_NINGUNO, "Ninguno / genérico"),
        (PAGO_PERSONA_SUELDO, "Pago de sueldo (planta permanente)"),
        (PAGO_PERSONA_CHANGA, "Pago de changa / jornal / eventual"),
    ]

    # ===== Orden de pago / forma de pago (LEGACY) =====
    CONDICION_CONTADO = "CONTADO"
    CONDICION_30 = "30"
    CONDICION_60 = "60"
    CONDICION_OTRO = "OTRO"

    CONDICION_PAGO_CHOICES = [
        (CONDICION_CONTADO, "Contado"),
        (CONDICION_30, "30 días"),
        (CONDICION_60, "60 días"),
        (CONDICION_OTRO, "Otro plazo"),
    ]

    MEDIO_EFECTIVO = "EFECTIVO"
    MEDIO_TRANSFERENCIA = "TRANSFERENCIA"
    MEDIO_CHEQUE = "CHEQUE"
    MEDIO_OTRO = "OTRO"

    MEDIO_PAGO_CHOICES = [
        (MEDIO_EFECTIVO, "Efectivo"),
        (MEDIO_TRANSFERENCIA, "Transferencia bancaria"),
        (MEDIO_CHEQUE, "Cheque"),
        (MEDIO_OTRO, "Otro medio"),
    ]

    FACTURA_TIPO_CHOICES = [
        ("A", "Factura A"),
        ("B", "Factura B"),
        ("C", "Factura C"),
        ("X", "Factura X / Ticket"),
        ("OTRO", "Otro comprobante"),
    ]

    # ---- Orden de pago legacy (quedan) ----
    condicion_pago = models.CharField(
        max_length=20,
        choices=CONDICION_PAGO_CHOICES,
        blank=True,
    )
    medio_pago = models.CharField(
        max_length=20,
        choices=MEDIO_PAGO_CHOICES,
        blank=True,
    )
    orden_pago_fecha = models.DateField(null=True, blank=True)
    orden_pago_observaciones = models.CharField(max_length=255, blank=True)

    # ---- Factura asociada legacy (quedan) ----
    factura_tipo = models.CharField(
        max_length=10,
        choices=FACTURA_TIPO_CHOICES,
        blank=True,
    )
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_fecha = models.DateField(null=True, blank=True)

    # Bloque A: datos generales
    tipo = models.CharField(
        max_length=15,
        choices=TIPO_CHOICES,
        db_index=True,
    )
    fecha_operacion = models.DateField(db_index=True)
    fecha_carga = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)

    # Bloque C: cuentas (texto libre en la UI)
    cuenta_origen = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        related_name="movimientos_origen",
        null=True,
        blank=True,
    )
    cuenta_destino = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT,
        related_name="movimientos_destino",
        null=True,
        blank=True,
    )
    cuenta_origen_texto = models.CharField("Cuenta origen", max_length=200, blank=True)
    cuenta_destino_texto = models.CharField("Cuenta destino", max_length=200, blank=True)

    # Bloque B: clasificación contable
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="movimientos",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    # Bloque D/E: proveedor / beneficiario como texto + vínculo opcional
    proveedor_cuit = models.CharField("CUIT proveedor", max_length=20, blank=True)
    proveedor_nombre = models.CharField("Nombre proveedor", max_length=200, blank=True)
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    beneficiario_dni = models.CharField("DNI beneficiario", max_length=20, blank=True)
    beneficiario_nombre = models.CharField(
        "Nombre beneficiario", max_length=200, blank=True
    )
    beneficiario = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    tipo_pago_persona = models.CharField(
        max_length=20,
        choices=PAGO_PERSONA_CHOICES,
        default=PAGO_PERSONA_NINGUNO,
        help_text=(
            "Si el movimiento está vinculado a una persona, indicá si es sueldo "
            "de planta permanente o pago de changa/jornal. Dejá 'Ninguno' para ayudas sociales u otros casos."
        ),
    )

    # Bloque F: programa de ayuda (texto + FK opcional para futuro)
    programa_ayuda_texto = models.CharField(
        "Programa de ayuda", max_length=200, blank=True
    )
    programa_ayuda = models.ForeignKey(
        ProgramaAyuda,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
    )

    # Bloque F bis: relación con Orden de pago (nuevo módulo)
    orden_pago = models.ForeignKey(
        "OrdenPago",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Si este movimiento proviene de una Orden de pago, se vincula acá.",
    )

    # Bloque F ter: relación con Orden de compra (nuevo módulo)
    oc = models.ForeignKey(
        "OrdenCompra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Si este movimiento proviene de una Orden de compra, se vincula acá.",
    )

    # Bloque G: combustible / vehículo
    vehiculo_texto = models.CharField("Vehículo", max_length=200, blank=True)
    vehiculo = models.ForeignKey(
        "Vehiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cargas_combustible",
    )
    litros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    tipo_combustible = models.CharField(max_length=50, blank=True)

    # Bloque H: detalle
    descripcion = models.CharField(max_length=255, blank=True)
    observaciones = models.TextField(blank=True)

    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_APROBADO,  # más adelante se puede pasar a BORRADOR por defecto
        db_index=True,
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_creados",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_actualizados",
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ["-fecha_operacion", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.monto} - {self.fecha_operacion}"

    # ===== Validaciones de negocio =====

    def clean(self):
        """
        Reglas de coherencia básica:
        - Categoría compatible con tipo de movimiento.
        - Para combustible: debe ser GASTO y tener vehículo asignado.
        """
        super().clean()
        errors = {}

        # Coherencia tipo ↔ categoría
        if self.categoria and self.tipo:
            try:
                if not self.categoria.aplica_a_tipo_movimiento(self.tipo):
                    errors["categoria"] = (
                        "La categoría seleccionada no es compatible con el tipo de movimiento."
                    )
            except Exception:
                # Si por alguna razón falla, no rompemos el guardado.
                pass

        # Reglas específicas para combustible
        if self.categoria and getattr(self.categoria, "es_combustible", False):
            if self.tipo and self.tipo != self.TIPO_GASTO:
                errors["tipo"] = (
                    "Los movimientos de combustible deben registrarse como GASTO."
                )
            if self.vehiculo is None:
                errors["vehiculo"] = (
                    "Para las cargas de combustible tenés que seleccionar un vehículo."
                )

        if errors:
            raise ValidationError(errors)

    # ===== Helpers semánticos para reportes / vistas =====

    @property
    def es_ingreso(self) -> bool:
        return self.tipo == self.TIPO_INGRESO

    @property
    def es_gasto(self) -> bool:
        return self.tipo == self.TIPO_GASTO

    @property
    def es_transferencia(self) -> bool:
        return self.tipo == self.TIPO_TRANSFERENCIA

    @property
    def es_pago_servicio(self) -> bool:
        """
        True si es un ingreso marcado como servicio (ej: cobro de agua u otro servicio municipal).
        Útil para balances y ficha de persona.
        """
        return (
            self.tipo == self.TIPO_INGRESO
            and getattr(self.categoria, "es_servicio", False)
        )

    @property
    def es_ayuda_social(self) -> bool:
        """
        True si es un gasto marcado como ayuda social.
        """
        return (
            self.tipo == self.TIPO_GASTO
            and getattr(self.categoria, "es_ayuda_social", False)
        )

    @property
    def es_gasto_personal(self) -> bool:
        """
        True si corresponde a sueldos/jornales u otros gastos de personal
        (categorías marcadas como es_personal).
        """
        return (
            self.tipo == self.TIPO_GASTO
            and getattr(self.categoria, "es_personal", False)
        )

    @property
    def es_combustible(self) -> bool:
        """
        True si es un gasto de combustible según la categoría.
        """
        return (
            self.tipo == self.TIPO_GASTO
            and getattr(self.categoria, "es_combustible", False)
        )

    @property
    def es_carga_combustible_valida(self) -> bool:
        """
        Indica si el movimiento es una carga de combustible "usable" para reportes
        de flota: gasto de combustible APROBADO + vehículo asignado + litros > 0.
        """
        if not self.es_combustible:
            return False
        if not self.esta_aprobado:
            return False
        if self.vehiculo is None:
            return False
        if self.litros is None:
            return False
        try:
            return self.litros > 0
        except TypeError:
            return False

    @property
    def es_pago_sueldo_persona(self) -> bool:
        """
        True si este movimiento es un pago de sueldo a una persona específica.
        """
        return (
            self.es_gasto_personal
            and self.tipo_pago_persona == self.PAGO_PERSONA_SUELDO
            and self.beneficiario is not None
        )

    @property
    def es_pago_changa_persona(self) -> bool:
        """
        True si este movimiento es un pago de changa/jornal a una persona específica.
        """
        return (
            self.es_gasto_personal
            and self.tipo_pago_persona == self.PAGO_PERSONA_CHANGA
            and self.beneficiario is not None
        )

    # ===== Helpers de estado (para usar en templates / vistas) =====

    @property
    def esta_borrador(self) -> bool:
        return self.estado == self.ESTADO_BORRADOR

    @property
    def esta_aprobado(self) -> bool:
        return self.estado == self.ESTADO_APROBADO

    @property
    def esta_rechazado(self) -> bool:
        return self.estado == self.ESTADO_RECHAZADO

    @property
    def afecta_saldo(self) -> bool:
        """
        Indica si debería contarse en saldos y reportes.
        (Por diseño: solo los aprobados impactan.)
        """
        return self.esta_aprobado


class AdjuntoMovimiento(models.Model):
    movimiento = models.ForeignKey(
        Movimiento, on_delete=models.CASCADE, related_name="adjuntos"
    )
    archivo = models.FileField(upload_to="comprobantes/")
    descripcion = models.CharField(max_length=255, blank=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjuntos_subidos",
    )
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto de movimiento"
        verbose_name_plural = "Adjuntos de movimientos"

    def __str__(self):
        return f"Adjunto {self.id} de movimiento {self.movimiento_id}"


# =========================
#   FLOTAS / VIAJES / ODÓMETRO
# =========================

class ViajeVehiculo(models.Model):
    """
    Registro de salida/retorno de un vehículo, con odómetro,
    combustible y beneficiarios trasladados.

    Cuando tiene beneficiarios cargados, podemos considerarlo como
    una forma de ayuda de movilidad para esas personas en su historial social.
    """

    TIPO_RECORRIDO_URBANO = "URBANO"
    TIPO_RECORRIDO_RUTA = "RUTA"
    TIPO_RECORRIDO_COMISION = "COMISION"
    TIPO_RECORRIDO_OTRO = "OTRO"

    TIPO_RECORRIDO_CHOICES = [
        (TIPO_RECORRIDO_URBANO, "Urbano / pueblo"),
        (TIPO_RECORRIDO_RUTA, "Ruta / viaje largo"),
        (TIPO_RECORRIDO_COMISION, "Comisión / trámites"),
        (TIPO_RECORRIDO_OTRO, "Otro"),
    ]

    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_CERRADO = "CERRADO"
    ESTADO_ANULADO = "ANULADO"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_CERRADO, "Cerrado"),
        (ESTADO_ANULADO, "Anulado"),
    ]

    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.PROTECT,
        related_name="viajes_vehiculo",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="viajes_vehiculo",
        help_text="Área responsable del uso del vehículo en este viaje.",
    )

    # Chofer/responsable (beneficiario) + texto libre por si acaso
    chofer = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="viajes_como_chofer",
        help_text="Chofer o responsable del vehículo (si está cargado en el censo).",
    )
    chofer_nombre = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nombre del chofer / responsable (texto libre, para casos sin censo).",
    )

    fecha_salida = models.DateField()
    hora_salida = models.TimeField(null=True, blank=True)
    fecha_regreso = models.DateField(null=True, blank=True)
    hora_regreso = models.TimeField(null=True, blank=True)

    odometro_inicial = models.PositiveIntegerField(
        help_text="Lectura de odómetro al momento de la salida (km)."
    )
    odometro_final = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Lectura de odómetro al regreso (km).",
    )

    horometro_inicial = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Horómetro al salir (si aplica, ej: máquinas).",
    )
    horometro_final = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Horómetro al regresar (si aplica).",
    )

    litros_tanque_inicio = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Litros aproximados en tanque al salir (opcional).",
    )
    litros_tanque_fin = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Litros aproximados en tanque al regresar (opcional).",
    )

    tipo_recorrido = models.CharField(
        max_length=20,
        choices=TIPO_RECORRIDO_CHOICES,
        default=TIPO_RECORRIDO_OTRO,
    )

    origen = models.CharField(
        max_length=200,
        help_text="Origen principal del viaje (ej: Tacuarendí - Comuna).",
    )
    destino = models.CharField(
        max_length=200,
        help_text="Destino principal del viaje (ej: Reconquista - Banco / AFIP).",
    )

    motivo = models.CharField(
        max_length=255,
        blank=True,
        help_text="Motivo general del viaje (comisión, traslado de personas, compras, etc.).",
    )
    observaciones = models.TextField(blank=True)

    # Beneficiarios trasladados (personas/familias)
    beneficiarios = models.ManyToManyField(
        Beneficiario,
        related_name="viajes_trasladado",
        blank=True,
        help_text="Personas trasladadas en este viaje (si aplica).",
    )
    otros_beneficiarios = models.CharField(
        max_length=255,
        blank=True,
        help_text="Texto libre para familias/grupos no cargados en el censo. Ej: 'Familia Pérez', 'Delegación club X'.",
    )

    # Vinculación híbrida con movimientos de combustible
    cargas_combustible = models.ManyToManyField(
        "Movimiento",
        related_name="viajes_combustible",
        blank=True,
        help_text=(
            "Movimientos de combustible asociados al viaje. "
            "El sistema puede sugerir automáticamente según fecha/vehículo, "
            "pero siempre se puede ajustar manualmente."
        ),
    )

    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="viajes_creados",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="viajes_actualizados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Viaje de vehículo"
        verbose_name_plural = "Viajes de vehículos"
        ordering = ["-fecha_salida", "-id"]

    def __str__(self):
        base = f"{self.vehiculo} – {self.fecha_salida}"
        if self.origen or self.destino:
            base += f" ({self.origen} → {self.destino})"
        return base

    @property
    def km_recorridos(self) -> int:
        """
        Km recorridos según odómetro.
        Si faltan datos, devuelve 0.
        """
        if self.odometro_inicial is None or self.odometro_final is None:
            return 0
        if self.odometro_final < self.odometro_inicial:
            return 0
        return self.odometro_final - self.odometro_inicial

    @property
    def horas_trabajo(self):
        """
        Horas de trabajo según horómetro.
        """
        if self.horometro_inicial is None or self.horometro_final is None:
            return None
        delta = self.horometro_final - self.horometro_inicial
        return delta if delta >= 0 else None

    @property
    def tiene_beneficiarios(self) -> bool:
        return self.beneficiarios.exists() or bool(self.otros_beneficiarios.strip())


class ViajeVehiculoTramo(models.Model):
    """
    Tramos internos de un viaje (ej: Tacuarendí → Las Toscas → Reconquista → Tacuarendí).
    Opcional, pero muy útil para reportes finos.
    """

    viaje = models.ForeignKey(
        ViajeVehiculo,
        on_delete=models.CASCADE,
        related_name="tramos",
    )
    orden = models.PositiveIntegerField(
        default=1,
        help_text="Orden del tramo dentro del viaje (1, 2, 3, ...).",
    )

    origen = models.CharField(max_length=200)
    destino = models.CharField(max_length=200)
    hora_salida = models.TimeField(null=True, blank=True)
    hora_llegada = models.TimeField(null=True, blank=True)
    motivo = models.CharField(max_length=255, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Tramo de viaje"
        verbose_name_plural = "Tramos de viajes"
        ordering = ["viaje", "orden"]

    def __str__(self):
        return f"{self.viaje_id} – {self.orden}: {self.origen} → {self.destino}"


# =========================
#   ÓRDENES DE TRABAJO
# =========================

class OrdenTrabajo(models.Model):
    """
    Orden de Trabajo general de la comuna.
    Sirve para mecánica, mantenimiento, trabajos a vecinos/instituciones, etc.
    Puede vincularse a movimientos de ingreso.
    """

    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_FINALIZADA = "FINALIZADA"
    ESTADO_ENTREGADA = "ENTREGADA"
    ESTADO_ANULADA = "ANULADA"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_EN_PROCESO, "En proceso"),
        (ESTADO_FINALIZADA, "Finalizada"),
        (ESTADO_ENTREGADA, "Entregada al solicitante"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    TIPO_MECANICA = "MECANICA"
    TIPO_ELECTRICA = "ELECTRICA"
    TIPO_OBRA = "OBRA"
    TIPO_SERVICIO = "SERVICIO"
    TIPO_OTRO = "OTRO"

    TIPO_TRABAJO_CHOICES = [
        (TIPO_MECANICA, "Mecánica / vehículos"),
        (TIPO_ELECTRICA, "Eléctrica / luminarias"),
        (TIPO_OBRA, "Obra / albañilería"),
        (TIPO_SERVICIO, "Servicio a vecino / institución"),
        (TIPO_OTRO, "Otro"),
    ]

    PRIORIDAD_BAJA = "BAJA"
    PRIORIDAD_MEDIA = "MEDIA"
    PRIORIDAD_ALTA = "ALTA"
    PRIORIDAD_URGENTE = "URGENTE"

    PRIORIDAD_CHOICES = [
        (PRIORIDAD_BAJA, "Baja"),
        (PRIORIDAD_MEDIA, "Media"),
        (PRIORIDAD_ALTA, "Alta"),
        (PRIORIDAD_URGENTE, "Urgente"),
    ]

    numero = models.CharField(
        max_length=30,
        blank=True,
        help_text="Número interno de OT (ej: OT-0001/2025). Opcional.",
    )
    fecha_ot = models.DateField(
        help_text="Fecha de la orden de trabajo.",
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_BORRADOR,
        db_index=True,
    )
    tipo_trabajo = models.CharField(
        max_length=20,
        choices=TIPO_TRABAJO_CHOICES,
        default=TIPO_OTRO,
        help_text="Tipo principal de trabajo realizado.",
    )

    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDAD_CHOICES,
        default=PRIORIDAD_MEDIA,
    )

    # Solicitante: persona del censo o texto libre
    solicitante = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo_solicitadas",
        help_text="Persona solicitante (si está cargada en el censo).",
    )
    solicitante_texto = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nombre del solicitante (texto libre, para instituciones o casos sin censo).",
    )

    area = models.ForeignKey(
        Area,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo",
        help_text="Área responsable que realiza el trabajo.",
    )

    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo",
        help_text="Vehículo utilizado (si corresponde).",
    )

    # Personal responsable principal
    responsable = models.ForeignKey(
        Beneficiario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo_responsable",
        help_text="Responsable principal del trabajo (personal de la comuna).",
    )
    responsable_texto = models.CharField(
        max_length=200,
        blank=True,
        help_text="Texto libre para responsable, por si no está en censo.",
    )

    descripcion = models.TextField(
        help_text="Descripción del trabajo a realizar (pedido inicial).",
    )
    trabajos_realizados = models.TextField(
        blank=True,
        help_text="Detalle de trabajos efectivamente realizados (se completa al finalizar).",
    )

    # Montos de referencia para poder vincular luego a un Movimiento de ingreso
    importe_estimado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Importe estimado a cobrar (si aplica).",
    )
    importe_final = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Importe final acordado/cobrado (si aplica).",
    )

    categoria_ingreso = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo_ingreso",
        help_text="Categoría contable para el ingreso (si la OT genera cobro).",
    )

    movimiento_ingreso = models.ForeignKey(
        Movimiento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo",
        help_text="Movimiento de ingreso generado a partir de esta OT (opcional).",
    )

    observaciones = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordenes_trabajo_actualizadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orden de trabajo"
        verbose_name_plural = "Órdenes de trabajo"
        ordering = ["-fecha_ot", "-id"]

    def __str__(self):
        base = self.numero or f"OT {self.pk}"
        if self.solicitante or self.solicitante_texto:
            nombre = self.solicitante_texto or f"{self.solicitante.apellido}, {self.solicitante.nombre}"
            return f"{base} – {nombre}"
        return base

    @property
    def esta_cobrada(self) -> bool:
        return self.movimiento_ingreso is not None

    @property
    def puede_generar_movimiento(self) -> bool:
        """
        Para usar en templates: solo si tiene categoría, importe y aún no generó movimiento.
        """
        return (
            self.movimiento_ingreso is None
            and self.categoria_ingreso is not None
            and (self.importe_final or self.importe_estimado)
        )

    # ========= NUMERACIÓN AUTOMÁTICA OT =========

    def _generar_numero_ot(self) -> str:
        """
        Genera un número tipo OT-0001/2025 por año calendario.
        Solo se usa si el campo viene vacío.
        """
        from django.utils import timezone as _tz  # import local

        fecha = getattr(self, "fecha_ot", None) or _tz.now().date()
        year = fecha.year

        Model = self.__class__
        qs = Model.objects.filter(numero__endswith=f"/{year}").only("numero")

        max_n = 0
        for ot in qs:
            numero_ot = (ot.numero or "").strip()
            try:
                # Esperamos formato OT-0001/2025
                antes_slash, _ = numero_ot.split("/", 1)
                suf = antes_slash.split("-", 1)[1]
                n = int(suf)
            except Exception:
                continue
            if n > max_n:
                max_n = n

        siguiente = max_n + 1
        return f"OT-{siguiente:04d}/{year}"

    def save(self, *args, **kwargs):
        """
        Solo para nuevas órdenes:
        - Si numero viene vacío, generamos uno automático.
        - Si ya trae numero (manual), lo respetamos.
        """
        numero_actual = (self.numero or "").strip()
        if not self.pk and not numero_actual:
            self.numero = self._generar_numero_ot()
        super().save(*args, **kwargs)


class OrdenTrabajoMaterial(models.Model):
    """
    Materiales o insumos utilizados en una Orden de Trabajo.
    No genera contabilidad por sí mismo, pero sirve para control interno.
    """

    orden = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name="materiales",
    )
    descripcion = models.CharField(max_length=255)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unidad = models.CharField(
        max_length=50,
        blank=True,
        help_text="Ej: unidad, m, m2, litros, kg, etc.",
    )
    costo_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo unitario estimado (opcional, para control).",
    )
    costo_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo total (se puede calcular a partir de cantidad x costo unitario).",
    )

    class Meta:
        verbose_name = "Material de OT"
        verbose_name_plural = "Materiales de OT"

    def __str__(self):
        return f"{self.descripcion} ({self.cantidad} {self.unidad or ''})"

    def save(self, *args, **kwargs):
        if self.costo_unitario is not None and self.cantidad is not None:
            self.costo_total = self.costo_unitario * self.cantidad
        super().save(*args, **kwargs)


class AdjuntoOrdenTrabajo(models.Model):
    """
    Adjuntos de una OT (fotos antes/después, comprobantes, etc.).
    """

    orden_trabajo = models.ForeignKey(
        OrdenTrabajo,
        on_delete=models.CASCADE,
        related_name="adjuntos",
    )
    archivo = models.FileField(upload_to="ordenes_trabajo/")
    descripcion = models.CharField(max_length=255, blank=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjuntos_ot_subidos",
    )
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto de orden de trabajo"
        verbose_name_plural = "Adjuntos de órdenes de trabajo"

    def __str__(self):
        return f"Adjunto OT {self.orden_trabajo_id} – {self.id}"
