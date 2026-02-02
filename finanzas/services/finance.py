# finanzas/services/finance.py
from decimal import Decimal
from datetime import date
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.apps import apps
from finanzas.models import Movimiento, OrdenPago, OrdenTrabajo, Proveedor, Beneficiario, Categoria

class FinanceService:
    """
    Servicio central para la lógica financiera y contable.
    Maneja Dashboards, Filtros de Movimientos y Reglas de Negocio.
    """

    @staticmethod
    def obtener_metricas_dashboard(user) -> dict:
        """
        Calcula todos los indicadores para el Home/Dashboard.
        """
        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)

        # 1. Movimientos del Mes (Aprobados)
        qs_mes = Movimiento.objects.filter(
            estado=Movimiento.ESTADO_APROBADO,
            fecha_operacion__gte=primer_dia_mes,
            fecha_operacion__lte=hoy,
        )

        agregados = qs_mes.aggregate(
            ingresos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO)),
            gastos=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO)),
            ayudas=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO, categoria__es_ayuda_social=True)),
            personal=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO, categoria__es_personal=True)),
            servicios=Sum("monto", filter=Q(tipo=Movimiento.TIPO_INGRESO, categoria__es_servicio=True)),
            combustible=Sum("monto", filter=Q(tipo=Movimiento.TIPO_GASTO, categoria__es_combustible=True)),
        )

        ingresos = agregados["ingresos"] or Decimal("0.00")
        gastos = agregados["gastos"] or Decimal("0.00")

        # 2. Órdenes de Pago Pendientes
        op_pendientes_qs = OrdenPago.objects.exclude(
            estado__in=[OrdenPago.ESTADO_PAGADA, OrdenPago.ESTADO_ANULADA]
        )
        op_stats = {
            "cantidad": op_pendientes_qs.count(),
            "monto": sum(op.total_monto for op in op_pendientes_qs) # Calculado en python para usar property
        }

        # 3. Flota (Métricas básicas)
        viajes_mes, km_mes = FinanceService._calcular_flota_mes(hoy, primer_dia_mes)

        # 4. Tareas Pendientes (Agenda)
        tareas_pendientes = 0
        Tarea = FinanceService._get_tarea_model()
        if Tarea:
            tareas_pendientes = Tarea.objects.filter(
                responsable=user,
                estado__in=[Tarea.ESTADO_PENDIENTE, Tarea.ESTADO_EN_PROCESO]
            ).count()

        return {
            "hoy": hoy,
            "primer_dia_mes": primer_dia_mes,
            "total_ingresos_mes": ingresos,
            "total_gastos_mes": gastos,
            "saldo_mes": ingresos - gastos,
            "ayudas_mes": agregados["ayudas"] or 0,
            "personal_mes": agregados["personal"] or 0,
            "servicios_mes": agregados["servicios"] or 0,
            "combustible_mes": agregados["combustible"] or 0,
            "viajes_mes": viajes_mes,
            "total_km_mes": km_mes,
            "cantidad_ordenes_pendientes": op_stats["cantidad"],
            "total_ordenes_pendientes": op_stats["monto"],
            "tareas_pendientes_usuario": tareas_pendientes,
            "ultimos_movimientos": Movimiento.objects.filter(estado=Movimiento.ESTADO_APROBADO)
                                    .select_related("categoria", "area")
                                    .order_by("-fecha_operacion", "-id")[:5]
        }

    @staticmethod
    def filtrar_movimientos(params: dict, user_roles: dict) -> object:
        """
        Filtra el listado de movimientos según parámetros GET y roles.
        """
        qs = Movimiento.objects.select_related("categoria", "area", "proveedor", "beneficiario")

        # Filtro de Rol: Consulta Política solo ve Aprobados
        estado = (params.get("estado") or Movimiento.ESTADO_APROBADO).strip()
        if user_roles.get("es_consulta_politica"):
            estado = Movimiento.ESTADO_APROBADO

        # Filtros Estándar
        if tipo := params.get("tipo"):
            qs = qs.filter(tipo=tipo)
        
        if fecha_desde := params.get("desde"):
            qs = qs.filter(fecha_operacion__gte=fecha_desde)
            
        if fecha_hasta := params.get("hasta"):
            qs = qs.filter(fecha_operacion__lte=fecha_hasta)

        if estado != "TODOS":
            qs = qs.filter(estado=estado)

        # Buscador de Texto (Search)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(descripcion__icontains=q)
                | Q(categoria__nombre__icontains=q)
                | Q(beneficiario__nombre__icontains=q)
                | Q(beneficiario__apellido__icontains=q)
                | Q(proveedor__nombre__icontains=q)
                | Q(programa_ayuda_texto__icontains=q)
            )

        return qs.order_by("-fecha_operacion", "-id")

    @staticmethod
    def vincular_entidades(movimiento, form_data: dict):
        """
        Busca o crea Proveedor/Beneficiario basado en los datos del formulario
        y los vincula al movimiento. (Lógica que antes estaba suelta en views).
        """
        # 1. Proveedor
        cuit = (form_data.get("proveedor_cuit") or "").strip()
        nombre_prov = (form_data.get("proveedor_nombre") or "").strip()
        
        if cuit or nombre_prov:
            if cuit:
                prov, created = Proveedor.objects.get_or_create(
                    cuit=cuit, defaults={"nombre": nombre_prov or ""}
                )
                if not created and nombre_prov and not prov.nombre:
                    prov.nombre = nombre_prov
                    prov.save()
            else:
                prov, _ = Proveedor.objects.get_or_create(
                    nombre=nombre_prov or "Proveedor sin nombre"
                )
            movimiento.proveedor = prov

        # 2. Beneficiario
        dni = (form_data.get("beneficiario_dni") or "").strip()
        nombre_benef = (form_data.get("beneficiario_nombre") or "").strip()
        
        if dni or nombre_benef:
            defaults = {
                "nombre": nombre_benef, 
                "direccion": form_data.get("beneficiario_direccion", ""),
                "barrio": form_data.get("beneficiario_barrio", "")
            }
            
            if dni:
                # Separar nombre y apellido simple si viene junto
                if nombre_benef and " " in nombre_benef:
                    parts = nombre_benef.split(" ", 1)
                    defaults["apellido"], defaults["nombre"] = parts[0], parts[1]
                
                benef, created = Beneficiario.objects.get_or_create(dni=dni, defaults=defaults)
                
                # Actualizar dirección si es nueva
                if not created and (defaults["direccion"] or defaults["barrio"]):
                    if defaults["direccion"] and not benef.direccion: benef.direccion = defaults["direccion"]
                    if defaults["barrio"] and not benef.barrio: benef.barrio = defaults["barrio"]
                    benef.save()
            else:
                benef, _ = Beneficiario.objects.get_or_create(nombre=nombre_benef, apellido="")
            
            movimiento.beneficiario = benef

    @staticmethod
    def _calcular_flota_mes(hoy, primer_dia):
        """Helper interno para métricas de flota seguras."""
        try:
            from finanzas.models import ViajeVehiculo
            qs = ViajeVehiculo.objects.filter(fecha_salida__gte=primer_dia, fecha_salida__lte=hoy)
            viajes = qs.count()
            
            # Cálculo seguro de KM (campo km_recorridos vs calculo manual)
            total_km = Decimal("0.00")
            for v in qs:
                if getattr(v, "km_recorridos", None):
                    total_km += v.km_recorridos
                elif v.odometro_final and v.odometro_inicial:
                    diff = v.odometro_final - v.odometro_inicial
                    if diff > 0: total_km += diff
            return viajes, total_km
        except ImportError:
            return 0, 0

    @staticmethod
    def _get_tarea_model():
        try:
            return apps.get_model("agenda", "Tarea")
        except LookupError:
            return None