from decimal import Decimal
from datetime import timedelta
from django.db import models, transaction  # <--- ESTA ES LA CLAVE QUE FALTA
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum, Q, F     # <--- ESTA TAMBIÉN ES IMPORTANTE

# =========================================================
# 1. NÚCLEO / AUXILIARES
# =========================================================

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
    TIPO_CHOICES = [(TIPO_CAJA, "Caja"), (TIPO_BANCO, "Banco"), (TIPO_OTRO, "Otro")]

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_BANCO)
    numero_cuenta = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)
    
    # === CAMPO NUEVO (SOLUCIÓN DEL ERROR DE IMPORTACIÓN) ===
    saldo = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    # =======================================================

    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cuenta"
        verbose_name_plural = "Cuentas"

    def __str__(self):
        return f"{self.nombre} (${self.saldo})"


class Categoria(models.Model):
    TIPO_INGRESO = "INGRESO"
    TIPO_GASTO = "GASTO"
    TIPO_AMBOS = "AMBOS"
    TIPO_CHOICES = [(TIPO_INGRESO, "Ingreso"), (TIPO_GASTO, "Gasto"), (TIPO_AMBOS, "Ambos")]

    GRUPO_VEHICULOS = "VEHICULOS"
    GRUPO_INSUMOS = "INSUMOS"
    GRUPO_CONSTRUCCION = "CONSTRUCCION"
    GRUPO_AYUDAS = "AYUDAS"
    GRUPO_OTROS = "OTROS"
    GRUPO_CHOICES = [
        (GRUPO_VEHICULOS, "Vehículos"),
        (GRUPO_INSUMOS, "Insumos"),
        (GRUPO_CONSTRUCCION, "Obra Pública"),
        (GRUPO_AYUDAS, "Ayudas Sociales"),
        (GRUPO_OTROS, "Otros"),
    ]

    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=TIPO_GASTO, db_index=True)
    grupo = models.CharField(max_length=20, choices=GRUPO_CHOICES, default=GRUPO_OTROS)

    es_ayuda_social = models.BooleanField(default=False)
    es_servicio = models.BooleanField(default=False)
    es_combustible = models.BooleanField(default=False)
    es_personal = models.BooleanField(default=False)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre

    def aplica_a_tipo_movimiento(self, tipo_movimiento):
        if not tipo_movimiento:
            return True
        if tipo_movimiento == "INGRESO":
            return self.tipo in {self.TIPO_INGRESO, self.TIPO_AMBOS}
        if tipo_movimiento == "GASTO":
            return self.tipo in {self.TIPO_GASTO, self.TIPO_AMBOS}
        return True


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200)
    cuit = models.CharField(max_length=20, blank=True, db_index=True)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)

    # === CAMPOS NUEVOS AGREGADOS ===
    rubro = models.CharField(max_length=100, blank=True, null=True, help_text="Ej: Ferretería, Combustible")
    cbu = models.CharField(max_length=100, blank=True, null=True, verbose_name="CBU/CVU")
    alias = models.CharField(max_length=100, blank=True, null=True, verbose_name="Alias Bancario")
    # ===============================

    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return f"{self.nombre} ({self.cuit})" if self.cuit else self.nombre


class ProgramaAyuda(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Programa de ayuda"
        verbose_name_plural = "Programas de ayuda"

    def __str__(self):
        return self.nombre


class SerieOC(models.Model):
    nombre = models.CharField(max_length=100)
    prefijo = models.CharField(max_length=20, blank=True)
    siguiente_numero = models.PositiveIntegerField(default=1)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Serie de OC"
        verbose_name_plural = "Series de OC"

    def __str__(self):
        return self.nombre


# =========================================================
# 2. FLOTA Y LOGÍSTICA
# =========================================================

class Vehiculo(models.Model):
    # Tipos de Vehículo (Normalizados)
    TIPO_CAMIONETA = "CAMIONETA"
    TIPO_CAMION = "CAMION"
    TIPO_MAQUINARIA = "MAQUINARIA"
    TIPO_AUTO = "AUTO"
    TIPO_OTRO = "OTRO"
    
    TIPOS_CHOICES = [
        (TIPO_CAMIONETA, "Camioneta / Utilitario"),
        (TIPO_CAMION, "Camión"),
        (TIPO_MAQUINARIA, "Maquinaria Pesada"),
        (TIPO_AUTO, "Automóvil"),
        (TIPO_OTRO, "Otro"),
    ]

    # Identificación
    patente = models.CharField(max_length=20, unique=True, help_text="Dominio sin espacios")
    descripcion = models.CharField(max_length=200, help_text="Nombre interno (ej: Móvil 1)")
    marca = models.CharField(max_length=100, blank=True, null=True)
    modelo = models.CharField(max_length=100, blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=TIPOS_CHOICES, default=TIPO_CAMIONETA)
    
    # Datos Técnicos
    chasis = models.CharField(max_length=100, blank=True, null=True)
    motor = models.CharField(max_length=100, blank=True, null=True)
    
    # Estado y Control
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    activo = models.BooleanField(default=True)
    
    # Contadores (Se actualizan automáticos al cerrar Hoja de Ruta)
    kilometraje_referencia = models.DecimalField(max_digits=12, decimal_places=1, default=0)
    horometro_referencia = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)
    
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Vehículo"
        verbose_name_plural = "Vehículos"
        ordering = ["activo", "patente"]

    def __str__(self):
        return f"{self.patente} - {self.descripcion}"

    def save(self, *args, **kwargs):
        self.patente = self.patente.upper().strip()  # Siempre mayúsculas
        super().save(*args, **kwargs)


class HojaRuta(models.Model):
    ESTADO_ABIERTA = "ABIERTA"
    ESTADO_CERRADA = "CERRADA"
    ESTADO_CHOICES = [(ESTADO_ABIERTA, "En curso"), (ESTADO_CERRADA, "Finalizada")]

    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="hojas_ruta")

    # Chofer (Conexión con Beneficiarios/Personal)
    chofer = models.ForeignKey(
        "Beneficiario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hojas_ruta_chofer",
    )
    chofer_nombre = models.CharField(max_length=150, blank=True, help_text="Nombre de respaldo")

    # Datos del Viaje
    fecha = models.DateField(default=timezone.now)
    hora_salida = models.TimeField(null=True, blank=True)
    hora_llegada = models.TimeField(null=True, blank=True)
    destino = models.CharField(max_length=200, blank=True, help_text="Destino principal o zona")

    # Kilometraje
    odometro_inicio = models.DecimalField(max_digits=12, decimal_places=1)
    odometro_fin = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)
    
    # Campo calculado guardado en DB para reportes rápidos (evita Sum con F expressions complejas)
    km_recorridos = models.DecimalField(max_digits=10, decimal_places=1, default=0)

    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_ABIERTA)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Hoja de Ruta"
        verbose_name_plural = "Hojas de Ruta"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"HR #{self.id} - {self.vehiculo} ({self.fecha})"

    def clean(self):
        super().clean()
        # Validación de Chofer
        if not self.chofer and not self.chofer_nombre:
            raise ValidationError("Debe indicar un chofer (seleccionado o nombre manual).")

        # Validación de Odómetro
        if self.odometro_fin and self.odometro_inicio:
            if self.odometro_fin < self.odometro_inicio:
                raise ValidationError({"odometro_fin": "El odómetro final no puede ser menor al inicial."})

    def save(self, *args, **kwargs):
        # 1. Sincronizar nombre de chofer
        if self.chofer:
            self.chofer_nombre = f"{self.chofer.apellido}, {self.chofer.nombre}"
        
        # 2. Calcular Km Recorridos automáticamente
        if self.odometro_fin and self.odometro_inicio:
            self.km_recorridos = self.odometro_fin - self.odometro_inicio
        else:
            self.km_recorridos = 0

        # 3. Detectar cambio de estado para actualizar vehículo
        # Si cerramos la hoja, actualizamos el vehículo con el último KM
        if self.pk:
            old_instance = HojaRuta.objects.filter(pk=self.pk).first()
            if old_instance and old_instance.estado != self.ESTADO_CERRADA and self.estado == self.ESTADO_CERRADA:
                if self.odometro_fin:
                    self.vehiculo.kilometraje_referencia = self.odometro_fin
                    self.vehiculo.save()

        super().save(*args, **kwargs)


class Traslado(models.Model):
    """
    Detalle de pasajeros transportados dentro de una Hoja de Ruta.
    Ideal para Acción Social o traslados médicos.
    """
    hoja_ruta = models.ForeignKey(HojaRuta, on_delete=models.CASCADE, related_name="traslados")
    origen = models.CharField(max_length=150, default="Base / Localidad")
    destino = models.CharField(max_length=150)
    motivo = models.CharField(max_length=200, blank=True)
    
    pasajeros = models.ManyToManyField("Beneficiario", related_name="historial_traslados", blank=True)
    otros_pasajeros = models.CharField(max_length=255, blank=True, help_text="Nombres de no empadronados")

    class Meta:
        verbose_name = "Traslado"
        verbose_name_plural = "Traslados"
        ordering = ["id"]

    def __str__(self):
        return f"{self.origen} -> {self.destino}"


# =========================================================
# 3. SOCIAL (Beneficiarios y Atenciones)
# =========================================================

class Beneficiario(models.Model):
    TIPO_VINCULO_NINGUNO = "NINGUNO"
    TIPO_VINCULO_PLANTA = "PLANTA"
    TIPO_VINCULO_JORNAL = "JORNAL"
    TIPO_VINCULO_EVENTUAL = "EVENTUAL"
    TIPO_VINCULO_HONORARIO = "HONORARIO"
    TIPO_VINCULO_CHOICES = [
        (TIPO_VINCULO_NINGUNO, "Sin vínculo"),
        (TIPO_VINCULO_PLANTA, "Planta"),
        (TIPO_VINCULO_JORNAL, "Jornal"),
        (TIPO_VINCULO_EVENTUAL, "Eventual"),
        (TIPO_VINCULO_HONORARIO, "Honorarios"),
    ]

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    dni = models.CharField(max_length=20, blank=True, db_index=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    barrio = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=50, blank=True)

    notas = models.TextField(blank=True, help_text="Observaciones generales sobre la situación social")
    paga_servicios = models.BooleanField(default=False)
    detalle_servicios = models.CharField(max_length=255, blank=True)

    tipo_vinculo = models.CharField(max_length=20, choices=TIPO_VINCULO_CHOICES, default=TIPO_VINCULO_NINGUNO)
    sector_laboral = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name="beneficiarios_laborales")
    fecha_ingreso = models.DateField(null=True, blank=True)

    percibe_beneficio = models.BooleanField(default=False)
    beneficio_detalle = models.CharField(max_length=255, blank=True)
    beneficio_organismo = models.CharField(max_length=120, blank=True)
    beneficio_monto_aprox = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    activo = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Beneficiario"
        verbose_name_plural = "Beneficiarios"
        ordering = ["apellido", "nombre"]

    def __str__(self):
        return f"{self.apellido}, {self.nombre}"

    @property
    def nombre_completo(self):
        return f"{self.apellido}, {self.nombre}"

    def get_total_ayudas_historico(self):
        total = self.movimientos.filter(
            tipo=Movimiento.TIPO_GASTO,
            estado=Movimiento.ESTADO_APROBADO,
            categoria__es_ayuda_social=True
        ).aggregate(t=Sum("monto"))["t"]
        return total or 0

    def get_ultimas_ayudas(self):
        return self.movimientos.filter(
            tipo=Movimiento.TIPO_GASTO,
            categoria__es_ayuda_social=True
        ).select_related("categoria", "orden_pago").order_by("-fecha_operacion")[:10]

    # Pasajero (historial por Traslados)
    def get_historial_viajes(self):
        return self.historial_traslados.select_related("hoja_ruta", "hoja_ruta__vehiculo").order_by("-hoja_ruta__fecha", "-id")

    def get_cantidad_viajes(self):
        return self.historial_traslados.count()

    # Chofer (historial por Hojas)
    def get_historial_conduccion(self):
        return self.hojas_ruta_chofer.select_related("vehiculo").order_by("-fecha", "-id")

    def get_cantidad_conducciones(self):
        return self.hojas_ruta_chofer.count()

    def get_atenciones_abiertas(self):
        return self.atenciones.filter(estado__in=["ABIERTA", "EN_SEGUIMIENTO"]).count()


class Atencion(models.Model):
    MOTIVO_CHOICES = [
        ("CONSULTA", "Consulta"),
        ("RECLAMO", "Reclamo"),
        ("SOLICITUD_AYUDA", "Solicitud de ayuda"),
        ("TRAMITE", "Trámite"),
        ("DENUNCIA", "Denuncia"),
        ("OTRO", "Otro"),
    ]
    ESTADO_CHOICES = [("ABIERTA", "Abierta"), ("EN_SEGUIMIENTO", "En seguimiento"), ("CERRADA", "Cerrada")]

    persona = models.ForeignKey(Beneficiario, on_delete=models.SET_NULL, null=True, blank=True, related_name="atenciones")
    persona_nombre = models.CharField(max_length=200, blank=True)
    persona_dni = models.CharField(max_length=20, blank=True)
    persona_barrio = models.CharField(max_length=100, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_atencion = models.DateField(default=timezone.now, db_index=True)
    hora_atencion = models.TimeField(null=True, blank=True)
    motivo_principal = models.CharField(max_length=20, choices=MOTIVO_CHOICES, default="CONSULTA")
    canal = models.CharField(max_length=20, default="PRESENCIAL")
    prioridad = models.CharField(max_length=10, default="MEDIA")
    descripcion = models.TextField(blank=True)
    resultado = models.TextField(blank=True)
    requiere_seguimiento = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="CERRADA")
    tarea_seguimiento = models.ForeignKey("agenda.Tarea", on_delete=models.SET_NULL, null=True, blank=True, related_name="atenciones")
    origen_interno = models.CharField(max_length=200, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="atenciones_creadas")
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="atenciones_actualizadas")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Atención"
        verbose_name_plural = "Atenciones"
        ordering = ["-fecha_atencion", "-id"]

    def __str__(self):
        return f"{self.fecha_atencion} - {self.persona or self.persona_nombre}"


# =========================================================
# 4. COMPRAS Y PAGOS (OC / OP)
# =========================================================

class OrdenCompra(models.Model):
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

    # Opciones para el select de Rubros (Sincronizado con Forms y Template)
    RUBRO_CHOICES = [
        ("AS", "Ayudas Sociales"),
        ("CB", "Combustible"),
        ("OB", "Obras y Materiales"),
        ("SV", "Servicios"),
        ("PE", "Personal / Jornales"),
        ("HI", "Herramientas e Insumos"),
        ("OT", "Otros / General"),
    ]

    serie = models.ForeignKey('SerieOC', on_delete=models.SET_NULL, null=True, blank=True)
    numero = models.CharField(max_length=30, blank=True)
    fecha_oc = models.DateField()
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    
    # Ahora usa choices para mostrar el texto lindo en el template
    rubro_principal = models.CharField(max_length=2, choices=RUBRO_CHOICES, default="OT", blank=True)
    
    proveedor = models.ForeignKey('Proveedor', on_delete=models.SET_NULL, null=True, blank=True)
    proveedor_nombre = models.CharField(max_length=200, blank=True) # Snapshot
    proveedor_cuit = models.CharField(max_length=20, blank=True)    # Snapshot
    
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True, blank=True)
    observaciones = models.TextField(blank=True)
    
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Orden de compra"
        verbose_name_plural = "Órdenes de compra"
        ordering = ["-id"]

    def __str__(self):
        return f"OC #{self.numero}"

    @property
    def total_monto(self):
        """Calcula el total de la OC sumando sus líneas."""
        return self.lineas.aggregate(total=Sum('monto'))['total'] or 0


class OrdenCompraLinea(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="lineas")
    categoria = models.ForeignKey('Categoria', on_delete=models.PROTECT, null=True, blank=True)
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True, blank=True)
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    # Opcional: Beneficiario si la compra es para alguien específico (Social)
    beneficiario = models.ForeignKey('Beneficiario', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.descripcion} (${self.monto})"


class FacturaOC(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="facturas")
    tipo = models.CharField(max_length=10, blank=True) # A, B, C
    numero = models.CharField(max_length=50, blank=True)
    fecha = models.DateField(null=True, blank=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    observaciones = models.TextField(blank=True)


class OrdenPago(models.Model):
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_AUTORIZADA = "AUTORIZADA"
    ESTADO_PAGADA = "PAGADA"
    ESTADO_ANULADA = "ANULADA"
    
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_AUTORIZADA, "Autorizada"),
        (ESTADO_PAGADA, "Pagada"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    numero = models.CharField(max_length=30, blank=True)
    fecha_orden = models.DateField()
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR, db_index=True)
    
    proveedor = models.ForeignKey('Proveedor', on_delete=models.SET_NULL, null=True, blank=True)
    proveedor_nombre = models.CharField(max_length=200, blank=True)
    proveedor_cuit = models.CharField(max_length=20, blank=True)
    
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True, blank=True)
    condicion_pago = models.CharField(max_length=20, blank=True) # Contado, Cheque, Transferencia
    medio_pago_previsto = models.CharField(max_length=20, blank=True)
    observaciones = models.TextField(blank=True)

    # Datos de la factura principal que origina el pago
    factura_tipo = models.CharField(max_length=10, blank=True)
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_fecha = models.DateField(null=True, blank=True)
    factura_monto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Orden de pago"
        verbose_name_plural = "Órdenes de pago"
        ordering = ["-fecha_orden", "-id"]

    def __str__(self):
        return f"OP #{self.numero}"

    @property
    def total_monto(self):
        return self.lineas.aggregate(Sum("monto"))["monto__sum"] or 0


class OrdenPagoLinea(models.Model):
    orden = models.ForeignKey(OrdenPago, on_delete=models.CASCADE, related_name="lineas")
    categoria = models.ForeignKey('Categoria', on_delete=models.PROTECT, null=True, blank=True)
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True, blank=True)
    descripcion = models.CharField(max_length=255)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    beneficiario = models.ForeignKey('Beneficiario', on_delete=models.SET_NULL, null=True, blank=True)


# =========================================================
# 5. SERVICIOS Y OPERATIVO (OT)
# =========================================================

class OrdenTrabajo(models.Model):
    # --- CONSTANTES DE ESTADO ---
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_EN_PROCESO = "EN_PROCESO"
    ESTADO_FINALIZADA = "FINALIZADA"
    ESTADO_ENTREGADA = "ENTREGADA"
    ESTADO_ANULADA = "ANULADA"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador (Pendiente)"),
        (ESTADO_EN_PROCESO, "En Ejecución"),
        (ESTADO_FINALIZADA, "Finalizada (Técnica)"),
        (ESTADO_ENTREGADA, "Entregada / Certificada"),
        (ESTADO_ANULADA, "Anulada"),
    ]

    PRIORIDAD_CHOICES = [
        ("BAJA", "Baja"),
        ("NORMAL", "Normal"),
        ("ALTA", "Alta"),
        ("URGENTE", "Urgente"),
        ("CRITICA", "Crítica (Emergencia)"),
    ]

    # --- IDENTIFICACIÓN ---
    # Usamos db_index=True para búsquedas rápidas sin bloquear la migración por datos viejos
    numero = models.CharField(
        max_length=30, 
        blank=True, 
        db_index=True, 
        help_text="Se genera automático (Ej: OT-2026-005)"
    )
    fecha_ot = models.DateField(default=timezone.now, verbose_name="Fecha de Solicitud")
    
    # --- TIEMPOS (KPIs) ---
    fecha_inicio = models.DateTimeField(null=True, blank=True, verbose_name="Inicio Real")
    fecha_fin = models.DateTimeField(null=True, blank=True, verbose_name="Finalización Real")

    # --- ACTORES ---
    solicitante = models.ForeignKey(
        'Beneficiario', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="ots_solicitadas"
    )
    solicitante_texto = models.CharField(max_length=200, blank=True, help_text="Nombre snapshot o externo")
    
    responsable = models.ForeignKey(
        'Beneficiario', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="ots_asignadas"
    )
    responsable_texto = models.CharField(max_length=200, blank=True, help_text="Capataz o encargado")
    
    # --- RECURSOS ---
    vehiculo = models.ForeignKey('Vehiculo', on_delete=models.SET_NULL, null=True, blank=True)
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True, blank=True)
    
    # --- DETALLES ---
    titulo = models.CharField(max_length=150, blank=True, verbose_name="Título Corto")
    descripcion = models.TextField(verbose_name="Descripción detallada")
    tipo_trabajo = models.CharField(max_length=100, blank=True, help_text="Ej: Electricidad, Albañilería")
    ubicacion = models.CharField(max_length=250, blank=True, verbose_name="Lugar / Dirección")
    
    prioridad = models.CharField(max_length=20, choices=PRIORIDAD_CHOICES, default="NORMAL")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    
    # --- CIERRE ---
    trabajos_realizados = models.TextField(blank=True, verbose_name="Informe Técnico Final")
    observaciones_internas = models.TextField(blank=True, verbose_name="Notas Privadas")
    
    # --- AUDITORÍA ---
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Orden de Trabajo"
        verbose_name_plural = "Órdenes de Trabajo"
        ordering = ["-id"]

    def __str__(self):
        titulo_mostrar = self.titulo if self.titulo else (self.descripcion[:40] + "...")
        return f"{self.numero} - {titulo_mostrar}"

    def save(self, *args, **kwargs):
        # 1. Generación automática de NÚMERO (OT-AÑO-ID)
        if not self.numero:
            year = timezone.now().year
            # Buscamos el último ID para predecir el siguiente (método seguro simple)
            last_ot = OrdenTrabajo.objects.all().order_by('id').last()
            next_id = (last_ot.id + 1) if last_ot else 1
            self.numero = f"OT-{year}-{next_id:04d}"
        
        # 2. Snapshot de Nombres (Congelamos el nombre por si borran la persona)
        if self.solicitante and not self.solicitante_texto:
            self.solicitante_texto = f"{self.solicitante.apellido}, {self.solicitante.nombre}"
        if self.responsable and not self.responsable_texto:
            self.responsable_texto = f"{self.responsable.apellido}, {self.responsable.nombre}"
            
        super().save(*args, **kwargs)

    @property
    def costo_total_materiales(self):
        """Calcula el costo total sumando los materiales asociados."""
        return sum(item.subtotal for item in self.materiales.all())

    @property
    def duracion_horas(self):
        """Calcula duración si hay fecha inicio y fin."""
        if self.fecha_inicio and self.fecha_fin:
            diff = self.fecha_fin - self.fecha_inicio
            return round(diff.total_seconds() / 3600, 2)
        return 0


class OrdenTrabajoMaterial(models.Model):
    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.CASCADE, related_name="materiales")
    descripcion = models.CharField(max_length=255, verbose_name="Material / Insumo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    unidad = models.CharField(max_length=20, default="Unidad", help_text="Mts, Kg, Lts, Cajas")
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Material de OT"
        verbose_name_plural = "Materiales de OT"

    def __str__(self):
        return f"{self.descripcion} (x{self.cantidad})"

    @property
    def subtotal(self):
        """Cantidad * Costo Unitario"""
        return self.cantidad * self.costo_unitario


class AdjuntoOrdenTrabajo(models.Model):
    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to="ots_docs/%Y/%m/", verbose_name="Foto / Documento")
    descripcion = models.CharField(max_length=200, blank=True)
    
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto de OT"
        verbose_name_plural = "Adjuntos"

    def __str__(self):
        return self.descripcion or self.archivo.name


# =========================================================
# 5. MOVIMIENTOS (CAJA)
# =========================================================

class Movimiento(models.Model):
    TIPO_INGRESO = "INGRESO"
    TIPO_GASTO = "GASTO"
    TIPO_TRANSFERENCIA = "TRANSFERENCIA"
    TIPO_CHOICES = [(TIPO_INGRESO, "Ingreso"), (TIPO_GASTO, "Gasto"), (TIPO_TRANSFERENCIA, "Transferencia")]

    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_APROBADO = "APROBADO"
    ESTADO_RECHAZADO = "RECHAZADO"
    ESTADO_CHOICES = [(ESTADO_BORRADOR, "Borrador"), (ESTADO_APROBADO, "Aprobado"), (ESTADO_RECHAZADO, "Rechazado")]

    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, db_index=True)
    fecha_operacion = models.DateField(db_index=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)

    # Cuentas implicadas
    cuenta_origen = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="movimientos_origen", null=True, blank=True)
    cuenta_destino = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="movimientos_destino", null=True, blank=True)
    cuenta_origen_texto = models.CharField(max_length=200, blank=True)
    cuenta_destino_texto = models.CharField(max_length=200, blank=True)

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="movimientos")
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)

    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)
    proveedor_cuit = models.CharField(max_length=20, blank=True)
    proveedor_nombre = models.CharField(max_length=200, blank=True)

    beneficiario = models.ForeignKey(Beneficiario, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos")
    beneficiario_dni = models.CharField(max_length=20, blank=True)
    beneficiario_nombre = models.CharField(max_length=200, blank=True)
    tipo_pago_persona = models.CharField(max_length=20, default="NINGUNO")

    programa_ayuda = models.ForeignKey(ProgramaAyuda, on_delete=models.SET_NULL, null=True, blank=True)
    programa_ayuda_texto = models.CharField(max_length=200, blank=True)

    orden_pago = models.ForeignKey(OrdenPago, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos")
    oc = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos")

    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.SET_NULL, null=True, blank=True, related_name="cargas_combustible")
    vehiculo_texto = models.CharField(max_length=200, blank=True)
    litros = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tipo_combustible = models.CharField(max_length=50, blank=True)

    # ✅ CONEXIÓN PRO: Movimiento ↔ Hoja de Ruta (día/turno)
    hoja_ruta = models.ForeignKey(
        HojaRuta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Si corresponde, imputar este movimiento a una Hoja de Ruta (día/turno).",
    )

    descripcion = models.CharField(max_length=255, blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=ESTADO_APROBADO)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="movimientos_actualizados")
    fecha_carga = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    # Legacy / Facturación
    condicion_pago = models.CharField(max_length=20, blank=True)
    medio_pago = models.CharField(max_length=20, blank=True)
    orden_pago_fecha = models.DateField(null=True, blank=True)
    orden_pago_observaciones = models.CharField(max_length=255, blank=True)
    factura_tipo = models.CharField(max_length=10, blank=True)
    factura_numero = models.CharField(max_length=50, blank=True)
    factura_fecha = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ["-fecha_operacion", "-id"] # Ordenar por fecha y luego por ID descendente

    def __str__(self):
        return f"${self.monto} ({self.get_tipo_display()}) - {self.fecha_operacion}"

    @property
    def esta_borrador(self):
        return self.estado == self.ESTADO_BORRADOR

    @property
    def esta_aprobado(self):
        return self.estado == self.ESTADO_APROBADO

    def save(self, *args, **kwargs):
        """
        Logica Maestra:
        1. Vinculaciones automáticas (Hoja Ruta, Beneficiario, Vehiculo).
        2. IMPACTO EN SALDO DE CUENTAS (Si es nuevo y aprobado).
        """
        # Detectamos si es nuevo antes de guardar
        es_nuevo = self.pk is None

        # 1) Coherencia hoja_ruta -> vehículo
        if self.hoja_ruta_id:
            if not self.vehiculo_id:
                self.vehiculo_id = self.hoja_ruta.vehiculo_id
            elif self.vehiculo_id != self.hoja_ruta.vehiculo_id:
                self.vehiculo_id = self.hoja_ruta.vehiculo_id

        # 2) Auto-link inteligente por fecha/vehículo
        if (not self.hoja_ruta_id) and self.vehiculo_id and self.fecha_operacion and self.categoria_id:
            cat = getattr(self, "categoria", None)
            if cat is None:
                cat = Categoria.objects.only("id", "grupo", "es_combustible").get(pk=self.categoria_id)

            es_flota = (cat.grupo == Categoria.GRUPO_VEHICULOS) or bool(cat.es_combustible)
            if es_flota:
                hr = HojaRuta.objects.filter(
                    vehiculo_id=self.vehiculo_id,
                    fecha=self.fecha_operacion
                ).order_by("-id").first()
                if hr:
                    self.hoja_ruta_id = hr.id

        # 3) Sync beneficiario espejo
        if self.beneficiario_id:
            self.beneficiario_nombre = self.beneficiario.nombre_completo
            if self.beneficiario.dni:
                self.beneficiario_dni = self.beneficiario.dni

        # GUARDAMOS EL MOVIMIENTO
        super().save(*args, **kwargs)

        # 4) 💰 IMPACTO EN SALDO DE CUENTAS 💰
        # Solo impactamos si es NUEVO y está APROBADO.
        # (Para editar montos ya guardados, se recomienda borrar y crear de nuevo o lógica avanzada de reversión)
        if es_nuevo and self.estado == self.ESTADO_APROBADO:
            with transaction.atomic():
                
                # A. INGRESO: Suma a Cuenta Destino
                if self.tipo == self.TIPO_INGRESO and self.cuenta_destino:
                    self.cuenta_destino.saldo = F('saldo') + self.monto
                    self.cuenta_destino.save()
                
                # B. GASTO: Resta de Cuenta Origen
                elif self.tipo == self.TIPO_GASTO and self.cuenta_origen:
                    self.cuenta_origen.saldo = F('saldo') - self.monto
                    self.cuenta_origen.save()
                
                # C. TRANSFERENCIA: Resta Origen -> Suma Destino
                elif self.tipo == self.TIPO_TRANSFERENCIA:
                    if self.cuenta_origen:
                        self.cuenta_origen.saldo = F('saldo') - self.monto
                        self.cuenta_origen.save()
                    if self.cuenta_destino:
                        self.cuenta_destino.saldo = F('saldo') + self.monto
                        self.cuenta_destino.save()

    def delete(self, *args, **kwargs):
        """
        Al borrar un movimiento APROBADO, debemos REVERTIR el impacto en el saldo.
        """
        if self.estado == self.ESTADO_APROBADO:
            with transaction.atomic():
                if self.tipo == self.TIPO_INGRESO and self.cuenta_destino:
                    self.cuenta_destino.saldo = F('saldo') - self.monto # Revertir ingreso
                    self.cuenta_destino.save()
                
                elif self.tipo == self.TIPO_GASTO and self.cuenta_origen:
                    self.cuenta_origen.saldo = F('saldo') + self.monto # Devolver gasto
                    self.cuenta_origen.save()

                elif self.tipo == self.TIPO_TRANSFERENCIA:
                    if self.cuenta_origen:
                        self.cuenta_origen.saldo = F('saldo') + self.monto
                        self.cuenta_origen.save()
                    if self.cuenta_destino:
                        self.cuenta_destino.saldo = F('saldo') - self.monto
                        self.cuenta_destino.save()

        super().delete(*args, **kwargs)


class AdjuntoMovimiento(models.Model):
    movimiento = models.ForeignKey(Movimiento, on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to="comprobantes/")
    descripcion = models.CharField(max_length=255, blank=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

class DocumentoBeneficiario(models.Model):
    # Tipos de documentos comunes
    TIPO_DNI = "DNI"
    TIPO_CUD = "CUD"
    TIPO_INFORME = "INFORME"
    TIPO_NOTA = "NOTA"
    TIPO_RECIBO = "RECIBO"
    TIPO_OTRO = "OTRO"
    
    TIPOS_CHOICES = [
        (TIPO_DNI, "DNI / Identificación"),
        (TIPO_CUD, "Certificado Discapacidad"),
        (TIPO_INFORME, "Informe Social"),
        (TIPO_NOTA, "Nota / Solicitud"),
        (TIPO_RECIBO, "Recibo Firmado"),
        (TIPO_OTRO, "Otro Documento"),
    ]

    # Relación con tu modelo de Persona (Beneficiario)
    beneficiario = models.ForeignKey(Beneficiario, on_delete=models.CASCADE, related_name="documentos")
    
    tipo = models.CharField(max_length=20, choices=TIPOS_CHOICES, default=TIPO_OTRO)
    archivo = models.FileField(upload_to="legajos_digitales/%Y/%m/")
    descripcion = models.CharField(max_length=255, blank=True, help_text="Breve descripción del archivo")
    
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento Digital"
        verbose_name_plural = "Documentos Digitales"
        ordering = ['-fecha_subida']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.beneficiario}"

    @property
    def es_imagen(self):
        # Helper para saber si mostrar preview o icono
        nombre = self.archivo.name.lower()
        return nombre.endswith('.jpg') or nombre.endswith('.png') or nombre.endswith('.jpeg')