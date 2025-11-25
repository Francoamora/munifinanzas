from decimal import Decimal

from django.db import models
from django.conf import settings


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
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_GASTO)
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


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200)
    cuit = models.CharField(max_length=20, blank=True)
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
    dni = models.CharField(max_length=20, blank=True)
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
        Area,
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


class Vehiculo(models.Model):
    patente = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"

    def __str__(self):
        return f"{self.patente} - {self.descripcion}".strip(" -")


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
#   ORDEN DE PAGO (NUEVO)
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
    def total_monto(self):
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
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    fecha_operacion = models.DateField()
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
        Categoria, on_delete=models.PROTECT, related_name="movimientos"
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

    # Bloque G: combustible / vehículo
    vehiculo_texto = models.CharField("Vehículo", max_length=200, blank=True)
    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cargas_combustible",
    )
    litros = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    precio_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    tipo_combustible = models.CharField(max_length=50, blank=True)

    # Bloque H: detalle
    descripcion = models.CharField(max_length=255, blank=True)
    observaciones = models.TextField(blank=True)

    estado = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_APROBADO,  # más adelante se puede pasar a BORRADOR por defecto
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

    # ===== Helpers semánticos para reportes / vistas =====

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
