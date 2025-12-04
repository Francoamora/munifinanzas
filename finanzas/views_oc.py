# finanzas/views_oc.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count, F
from django.forms import ModelForm
from django.forms.models import inlineformset_factory
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import ListView, CreateView, UpdateView, DetailView

# Reusamos mixins y helpers de tu views.py (misma fuente de verdad)
from .views import (
    StaffRequiredMixin,
    OperadorFinanzasRequiredMixin,
    MovimientosAccessMixin,  # por si lo usamos más adelante
    _roles_ctx,
    es_staff_finanzas,
    _parse_date_or_none,
)

# Modelos base que ya existen
from .models import Movimiento, Proveedor, Vehiculo


# ===============================
#   IMPORTS CON AIRBAG (OC)
# ===============================

"""
La idea es usar estos modelos/forms para Órdenes de Compra.

- Si YA existen en models/forms, las vistas se activan normal.
- Si TODAVÍA NO existen, usamos forms de respaldo (fallback) definidos acá.
  Solo si directamente no existen los modelos, mostramos 404 “no configurado”.
"""

# ---- Modelos de OC ----
try:
    from .models import (
        OrdenCompra,      # modelo principal de OC
        OrdenCompraLinea, # líneas de la OC
        FacturaOC,        # facturas asociadas a la OC
        SerieOC,          # series / numeración de OC (opcional)
    )
except Exception:
    OrdenCompra = None
    OrdenCompraLinea = None
    FacturaOC = None
    SerieOC = None

# ---- Formularios de OC (intento de importar desde forms.py) ----
try:
    from .forms import (
        OrdenCompraForm,
        OrdenCompraLineaFormSet,
        FacturaOCForm,
    )
except Exception:
    OrdenCompraForm = None
    OrdenCompraLineaFormSet = None
    FacturaOCForm = None

# ---- Fallback de formularios si los modelos YA existen pero los forms no ----
if OrdenCompra is not None and OrdenCompraForm is None:
    # Form simple para OrdenCompra
    class OrdenCompraForm(ModelForm):
        class Meta:
            model = OrdenCompra
            fields = "__all__"

    # Formset para las líneas de la OC.
    if OrdenCompraLinea is not None:
        OrdenCompraLineaFormSet = inlineformset_factory(
            OrdenCompra,
            OrdenCompraLinea,
            fields="__all__",   # después, si querés, refinamos campos
            extra=1,
            can_delete=True,
        )
    else:
        OrdenCompraLineaFormSet = None

    # Form simple para FacturaOC (por si lo usamos luego)
    if FacturaOC is not None:
        class FacturaOCForm(ModelForm):
            class Meta:
                model = FacturaOC
                fields = "__all__"
    else:
        FacturaOCForm = None


# ===============================
#   PLACEHOLDER SI NO HAY OC
# ===============================

if OrdenCompra is None or OrdenCompraLinea is None or OrdenCompraForm is None or OrdenCompraLineaFormSet is None:
    """
    Modo seguro: si el módulo de OC no está completo (modelo principal o líneas o forms),
    cualquier intento de usar estas vistas devuelve 404 explícito.
    """

    class _OCNotConfiguredView(View):
        def dispatch(self, request, *args, **kwargs):
            raise Http404(
                "El módulo de Órdenes de Compra aún no está configurado. "
                "Hablá con el administrador del sistema."
            )

    class OCListView(_OCNotConfiguredView):
        pass

    class OCCreateView(_OCNotConfiguredView):
        pass

    class OCUpdateView(_OCNotConfiguredView):
        pass

    class OCDetailView(_OCNotConfiguredView):
        pass

    class OCCambiarEstadoView(_OCNotConfiguredView):
        pass

    class OCGenerarMovimientoView(_OCNotConfiguredView):
        pass

else:
    # ===============================
    #   HELPER: AUTONUMERAR OC
    # ===============================

    def _autonumerar_oc_si_corresponde(orden: "OrdenCompra") -> None:
        """
        Si orden.numero está vacío, genera un número tipo:
          SERIE-001, SERIE-002, ...
        usando como prefijo:
          1) serie (si existe y no está vacía, string o FK),
          2) rubro_principal (AS, CB, OB, ...) si no hay serie.

        No pisa un número existente.
        """
        numero_actual = (getattr(orden, "numero", "") or "").strip()
        if numero_actual:
            # Ya tiene número (manual o antiguo), no hacemos nada.
            return

        # 1) Intentar con serie (puede ser texto o FK, usamos str())
        serie_valor = getattr(orden, "serie", "") or ""
        prefijo = str(serie_valor).strip() if serie_valor else ""

        # 2) Si no hay serie, probar con rubro_principal
        if not prefijo:
            rubro_valor = getattr(orden, "rubro_principal", "") or ""
            prefijo = str(rubro_valor).strip()

        if not prefijo:
            # Sin prefijo, no podemos generar algo consistente.
            return

        # Buscar OCs con mismo prefijo: PREFIJO-XXX
        qs = OrdenCompra.objects.filter(numero__startswith=f"{prefijo}-").only("numero")

        max_n = 0
        for oc in qs:
            try:
                suf = oc.numero.split("-", 1)[1]
                n = int(suf)
                if n > max_n:
                    max_n = n
            except Exception:
                # Si el formato no es PREFIJO-NNN, lo ignoramos
                continue

        siguiente = max_n + 1
        orden.numero = f"{prefijo}-{siguiente:03d}"  # CB-001, CB-002, ...

    # ===============================
    #    VISTAS REALES DE OC
    # ===============================

    class OCListView(OperadorFinanzasRequiredMixin, ListView):
        """
        Listado de Órdenes de Compra con filtros:
        - estado
        - rango de fechas
        - búsqueda por proveedor / CUIT / texto
        - rubro principal (AS, CB, OB, SV, PE, HI, OT)
        """
        model = OrdenCompra
        template_name = "finanzas/orden_compra_list.html"
        context_object_name = "ordenes"
        paginate_by = 25

        def get_queryset(self):
            qs = (
                self.model.objects.select_related("proveedor", "area")
                .prefetch_related("lineas")
            )

            estado = (self.request.GET.get("estado") or "PENDIENTES").strip()
            fecha_desde_raw = (self.request.GET.get("desde") or "").strip()
            fecha_hasta_raw = (self.request.GET.get("hasta") or "").strip()
            q = (self.request.GET.get("q") or "").strip()
            rubro = (self.request.GET.get("rubro") or "").strip()

            fecha_desde = _parse_date_or_none(fecha_desde_raw)
            fecha_hasta = _parse_date_or_none(fecha_hasta_raw)

            # Filtro de estado
            if estado == "PENDIENTES":
                qs = qs.exclude(
                    estado__in=[OrdenCompra.ESTADO_CERRADA, OrdenCompra.ESTADO_ANULADA]
                )
            elif estado == "TODAS":
                pass
            elif estado in [
                OrdenCompra.ESTADO_BORRADOR,
                OrdenCompra.ESTADO_AUTORIZADA,
                OrdenCompra.ESTADO_CERRADA,
                OrdenCompra.ESTADO_ANULADA,
            ]:
                qs = qs.filter(estado=estado)

            # Fechas
            if fecha_desde:
                qs = qs.filter(fecha_oc__gte=fecha_desde)
            if fecha_hasta:
                qs = qs.filter(fecha_oc__lte=fecha_hasta)

            # Búsqueda libre
            if q:
                qs = qs.filter(
                    Q(numero__icontains=q)
                    | Q(proveedor_nombre__icontains=q)
                    | Q(proveedor_cuit__icontains=q)
                    | Q(observaciones__icontains=q)
                )

            # Rubro principal
            if rubro:
                qs = qs.filter(rubro_principal=rubro)

            return qs.order_by("-fecha_oc", "-id")

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            user = self.request.user

            estado = (self.request.GET.get("estado") or "PENDIENTES").strip()
            q = (self.request.GET.get("q") or "").strip()
            rubro = (self.request.GET.get("rubro") or "").strip()
            hay_filtros = bool(
                self.request.GET.get("desde")
                or self.request.GET.get("hasta")
                or q
                or rubro
                or estado not in ["PENDIENTES"]
            )

            hoy = timezone.now().date()

            # ✅ total del listado: suma de montos de líneas de las OC mostradas
            total_monto_listado = (
                self.object_list.aggregate(total=Sum("lineas__monto"))["total"]
                or Decimal("0.00")
            )

            # Resumen general por estado (también sumando líneas)
            borradores_qs = OrdenCompra.objects.filter(
                estado=OrdenCompra.ESTADO_BORRADOR
            )
            autorizadas_qs = OrdenCompra.objects.filter(
                estado=OrdenCompra.ESTADO_AUTORIZADA
            )
            cerradas_qs = OrdenCompra.objects.filter(
                estado=OrdenCompra.ESTADO_CERRADA
            )

            resumen_borradores_cantidad = borradores_qs.count()
            resumen_autorizadas_cantidad = autorizadas_qs.count()
            resumen_cerradas_cantidad = cerradas_qs.count()

            resumen_borradores_monto = (
                borradores_qs.aggregate(total=Sum("lineas__monto"))["total"]
                or Decimal("0.00")
            )
            resumen_autorizadas_monto = (
                autorizadas_qs.aggregate(total=Sum("lineas__monto"))["total"]
                or Decimal("0.00")
            )
            resumen_cerradas_monto = (
                cerradas_qs.aggregate(total=Sum("lineas__monto"))["total"]
                or Decimal("0.00")
            )

            # Rubros principales (AS, CB, OB, SV, PE, HI, OT)
            RUBROS_OC = getattr(
                OrdenCompra,
                "RUBRO_CHOICES",
                [
                    ("AS", "Ayudas sociales"),
                    ("CB", "Combustible"),
                    ("OB", "Obras y materiales"),
                    ("SV", "Servicios contratados"),
                    ("PE", "Personal / jornales / changas"),
                    ("HI", "Herramientas / insumos generales"),
                    ("OT", "Otros"),
                ],
            )

            # Resumen por rubro SOLO del listado filtrado
            rubros_resumen = (
                self.object_list.exclude(rubro_principal__isnull=True)
                .exclude(rubro_principal__exact="")
                .values("rubro_principal")
                .annotate(
                    total_monto=Sum("lineas__monto"),
                    cantidad=Count("id"),
                )
                .order_by("-total_monto")
            )

            ctx.update(
                {
                    "hoy": hoy,
                    "estado_actual": estado,
                    "q": q,
                    "rubro_actual": rubro,
                    "hay_filtros": hay_filtros,
                    "total_monto_listado": total_monto_listado,
                    "RUBROS_OC": RUBROS_OC,
                    "rubros_resumen": rubros_resumen,
                    "resumen_borradores_cantidad": resumen_borradores_cantidad,
                    "resumen_borradores_monto": resumen_borradores_monto,
                    "resumen_autorizadas_cantidad": resumen_autorizadas_cantidad,
                    "resumen_autorizadas_monto": resumen_autorizadas_monto,
                    "resumen_cerradas_cantidad": resumen_cerradas_cantidad,
                    "resumen_cerradas_monto": resumen_cerradas_monto,
                }
            )
            ctx.update(_roles_ctx(user))
            return ctx


    class OCCreateView(OperadorFinanzasRequiredMixin, CreateView):
        """
        Alta de Orden de Compra + líneas (muchas líneas por OC).
        Flujo híbrido de estado:
          - Guardar BORRADOR
          - Guardar y AUTORIZAR (solo staff)
        """
        model = OrdenCompra
        form_class = OrdenCompraForm
        template_name = "finanzas/orden_compra_form.html"

        def get_initial(self):
            initial = super().get_initial()
            if "fecha_oc" not in initial:
                initial["fecha_oc"] = timezone.now().date()
            return initial

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            if self.request.POST:
                ctx["lineas_formset"] = OrdenCompraLineaFormSet(self.request.POST)
            else:
                ctx["lineas_formset"] = OrdenCompraLineaFormSet()
            ctx.update(_roles_ctx(self.request.user))
            return ctx

        def form_valid(self, form):
            ctx = self.get_context_data()
            formset = ctx["lineas_formset"]

            if not formset.is_valid():
                return self.form_invalid(form)

            orden = form.save(commit=False)
            user = self.request.user

            if user.is_authenticated:
                if not getattr(orden, "creado_por", None):
                    orden.creado_por = user
                orden.actualizado_por = user

            accion = (self.request.POST.get("accion") or "borrador").strip()
            es_staff = es_staff_finanzas(user)

            if es_staff and accion == "autorizar":
                orden.estado = OrdenCompra.ESTADO_AUTORIZADA
                mensaje = "Orden de compra creada y autorizada correctamente."
            else:
                orden.estado = OrdenCompra.ESTADO_BORRADOR
                if es_staff:
                    mensaje = "Orden de compra creada como borrador."
                else:
                    mensaje = (
                        "Orden de compra creada como borrador. "
                        "Un responsable de finanzas debe autorizarla."
                    )

            if not getattr(orden, "fecha_oc", None):
                orden.fecha_oc = timezone.now().date()

            # ✅ Autonumerar si corresponde (Serie o Rubro)
            _autonumerar_oc_si_corresponde(orden)

            orden.save()
            formset.instance = orden
            formset.save()

            messages.success(self.request, mensaje)
            return redirect("finanzas:oc_detail", pk=orden.pk)


    class OCUpdateView(OperadorFinanzasRequiredMixin, UpdateView):
        model = OrdenCompra
        form_class = OrdenCompraForm
        template_name = "finanzas/orden_compra_form.html"
        context_object_name = "orden"

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            if self.request.POST:
                ctx["lineas_formset"] = OrdenCompraLineaFormSet(
                    self.request.POST, instance=self.object
                )
            else:
                ctx["lineas_formset"] = OrdenCompraLineaFormSet(instance=self.object)
            ctx.update(_roles_ctx(self.request.user))
            return ctx

        def form_valid(self, form):
            ctx = self.get_context_data()
            formset = ctx["lineas_formset"]

            if not formset.is_valid():
                return self.form_invalid(form)

            orden_original = self.get_object()
            orden = form.save(commit=False)
            user = self.request.user
            es_staff = es_staff_finanzas(user)

            # Operadores solo pueden editar borradores
            if not es_staff and orden_original.estado != OrdenCompra.ESTADO_BORRADOR:
                messages.error(
                    self.request,
                    "Solo el staff financiero puede editar órdenes ya autorizadas/cerradas.",
                )
                return redirect("finanzas:oc_detail", pk=orden_original.pk)

            # Conservamos el estado original (no se cambia acá)
            orden.estado = orden_original.estado
            if user.is_authenticated:
                if not getattr(orden, "creado_por", None):
                    orden.creado_por = getattr(orden_original, "creado_por", user)
                orden.actualizado_por = user

            # ✅ Si sigue sin número (y hay serie/rubro), autogeneramos
            _autonumerar_oc_si_corresponde(orden)

            orden.save()
            formset.instance = orden
            formset.save()

            messages.success(self.request, "Orden de compra actualizada correctamente.")
            return redirect("finanzas:oc_detail", pk=orden.pk)


    class OCDetailView(OperadorFinanzasRequiredMixin, DetailView):
        model = OrdenCompra
        template_name = "finanzas/orden_compra_detail.html"
        context_object_name = "orden"

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            orden = self.object

            # Líneas
            lineas = orden.lineas.select_related("categoria", "area")
            total_monto = (
                lineas.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
            )

            # Facturas (si existe el modelo)
            if FacturaOC is not None:
                try:
                    facturas = orden.facturas.all()
                except AttributeError:
                    facturas = FacturaOC.objects.filter(orden=orden)
                total_facturas = (
                    facturas.aggregate(total=Sum("monto"))["total"]
                    or Decimal("0.00")
                )
            else:
                facturas = []
                total_facturas = Decimal("0.00")

            diferencia_facturas = total_facturas - total_monto

            # Movimientos vinculados a esta OC
            movimientos = (
                Movimiento.objects.filter(oc=orden)
                .select_related("categoria", "area")
                .order_by("-fecha_operacion", "-id")
            )
            total_movimientos = (
                movimientos.aggregate(total=Sum("monto"))["total"]
                or Decimal("0.00")
            )
            tiene_movimientos = movimientos.exists()
            diferencia_movimientos = total_movimientos - total_monto

            user = self.request.user

            puede_generar_movimiento = (
                es_staff_finanzas(user)
                and orden.estado == OrdenCompra.ESTADO_CERRADA
                and not tiene_movimientos
            )

            ctx.update(
                {
                    "lineas": lineas,
                    "total_monto": total_monto,
                    "facturas": facturas,
                    "total_facturas": total_facturas,
                    "diferencia_facturas": diferencia_facturas,
                    "movimientos": movimientos,
                    "total_movimientos": total_movimientos,
                    "diferencia_movimientos": diferencia_movimientos,
                    "tiene_movimientos": tiene_movimientos,
                    "puede_generar_movimiento": puede_generar_movimiento,
                }
            )
            ctx.update(_roles_ctx(user))
            return ctx


    class OCCambiarEstadoView(StaffRequiredMixin, View):
        """
        Cambia el estado de una OC:
        - BORRADOR
        - AUTORIZADA
        - CERRADA
        - ANULADA
        """

        def post(self, request, pk, accion):
            orden = get_object_or_404(OrdenCompra, pk=pk)
            estado_anterior = orden.estado

            if accion == "borrador":
                nuevo_estado = OrdenCompra.ESTADO_BORRADOR
                mensaje_ok = "La orden de compra volvió a BORRADOR."
            elif accion == "autorizar":
                nuevo_estado = OrdenCompra.ESTADO_AUTORIZADA
                mensaje_ok = "Orden de compra autorizada correctamente."
            elif accion == "cerrar":
                nuevo_estado = OrdenCompra.ESTADO_CERRADA
                mensaje_ok = "Orden de compra marcada como CERRADA."
            elif accion == "anular":
                nuevo_estado = OrdenCompra.ESTADO_ANULADA
                mensaje_ok = "Orden de compra ANULADA."
            else:
                messages.error(
                    request, "Acción de estado no reconocida para la orden de compra."
                )
                return redirect("finanzas:oc_detail", pk=orden.pk)

            if estado_anterior == nuevo_estado:
                messages.info(request, "La orden ya estaba en ese estado.")
                return redirect("finanzas:oc_detail", pk=orden.pk)

            # Pequeña validación de sanidad: no cerrar/autorizar sin líneas
            if nuevo_estado in [OrdenCompra.ESTADO_AUTORIZADA, OrdenCompra.ESTADO_CERRADA]:
                if not orden.lineas.exists():
                    messages.error(
                        request,
                        "La orden no tiene líneas de detalle. Cargá al menos una antes de autorizar o cerrar.",
                    )
                    return redirect("finanzas:oc_detail", pk=orden.pk)

            orden.estado = nuevo_estado
            if request.user.is_authenticated:
                orden.actualizado_por = request.user
            if not getattr(orden, "fecha_oc", None):
                orden.fecha_oc = timezone.now().date()
            orden.save()

            messages.success(request, mensaje_ok)
            return redirect("finanzas:oc_detail", pk=orden.pk)


    class OCGenerarMovimientoView(StaffRequiredMixin, View):
        """
        Genera un Movimiento de GASTO a partir de una OC CERRADA.

        Reglas:
        - Solo desde OC en estado CERRADA.
        - Solo si aún no hay movimientos vinculados a esa OC.
        - Usa el total de la OC (suma de líneas).
        - Categoría:
            * prioridad: orden.categoria_principal (si existe)
            * si no: categoría única de las líneas (si hay más de una, se cancela).
        - Área:
            * prioridad: orden.area
            * si no: área única de las líneas (si hay más de una, queda en blanco).
        """

        def post(self, request, pk):
            orden = get_object_or_404(OrdenCompra, pk=pk)

            if orden.estado != OrdenCompra.ESTADO_CERRADA:
                messages.error(
                    request,
                    "Solo se puede generar el movimiento cuando la orden está CERRADA.",
                )
                return redirect("finanzas:oc_detail", pk=orden.pk)

            if Movimiento.objects.filter(oc=orden).exists():
                messages.warning(
                    request,
                    (
                        "Esta orden ya tiene movimientos vinculados. "
                        "No se generó otro para evitar duplicados."
                    ),
                )
                return redirect("finanzas:oc_detail", pk=orden.pk)

            # Líneas de la OC (para total, categoría y área)
            lineas = list(orden.lineas.select_related("categoria", "area"))
            if not lineas:
                messages.error(
                    request,
                    "La orden no tiene líneas de detalle. Cargá al menos una antes de generar el movimiento.",
                )
                return redirect("finanzas:oc_detail", pk=orden.pk)

            # ✅ total de la OC: suma de líneas, no campo phantom
            total_orden = (
                Sum("monto")
                and (orden.lineas.aggregate(total=Sum("monto"))["total"])
                or Decimal("0.00")
            )
            total_orden = total_orden or Decimal("0.00")

            if total_orden <= 0:
                messages.error(
                    request,
                    "El total de la orden es cero o negativo. Revisá montos antes de generar el movimiento.",
                )
                return redirect("finanzas:oc_detail", pk=orden.pk)

            # Categoría principal
            categoria = getattr(orden, "categoria_principal", None)
            if categoria is None:
                categorias_ids = {l.categoria_id for l in lineas if l.categoria_id}
                if not categorias_ids:
                    messages.error(
                        request,
                        "Las líneas de la orden no tienen categoría asignada. Completalas antes de generar el movimiento.",
                    )
                    return redirect("finanzas:oc_detail", pk=orden.pk)

                if len(categorias_ids) > 1:
                    messages.error(
                        request,
                        (
                            "La orden tiene líneas con distintas categorías. "
                            "Por ahora solo se puede generar el movimiento automático cuando todas las líneas "
                            "comparten la misma categoría (para no mezclar rubros contables). "
                            "Podés cargar el movimiento manualmente desde el módulo de Movimientos."
                        ),
                    )
                    return redirect("finanzas:oc_detail", pk=orden.pk)

                # Única categoría
                categoria = lineas[0].categoria

            # Área: prioridad al área general de la OC; si no, área única de las líneas
            area = getattr(orden, "area", None)
            if area is None:
                areas_ids = {l.area_id for l in lineas if l.area_id}
                if len(areas_ids) == 1:
                    area = lineas[0].area

            # Datos de proveedor
            proveedor = orden.proveedor
            proveedor_nombre = (
                orden.proveedor_nombre or (proveedor.nombre if proveedor else "")
            )
            proveedor_cuit = orden.proveedor_cuit or (
                proveedor.cuit if proveedor else ""
            )

            # Fecha de operación: preferimos fecha_oc si existe
            fecha_operacion = getattr(orden, "fecha_oc", None) or timezone.now().date()

            descripcion = f"OC {orden.numero or orden.id}"
            if proveedor_nombre:
                descripcion += f" – {proveedor_nombre}"

            movimiento = Movimiento(
                tipo=Movimiento.TIPO_GASTO,
                fecha_operacion=fecha_operacion,
                monto=total_orden,
                categoria=categoria,
                area=area,
                proveedor=proveedor,
                proveedor_nombre=proveedor_nombre or "",
                proveedor_cuit=proveedor_cuit or "",
                descripcion=descripcion,
                observaciones=(
                    f"Movimiento generado automáticamente desde la Orden de compra "
                    f"{orden.numero or orden.id}."
                ),
                tipo_pago_persona=Movimiento.PAGO_PERSONA_NINGUNO,
                oc=orden,
                estado=Movimiento.ESTADO_APROBADO,
            )

            if request.user.is_authenticated:
                if hasattr(movimiento, "creado_por"):
                    movimiento.creado_por = request.user
                if hasattr(movimiento, "actualizado_por"):
                    movimiento.actualizado_por = request.user

            movimiento.save()

            messages.success(
                request,
                "Movimiento de gasto generado y aprobado correctamente a partir de la orden de compra.",
            )
            return redirect("finanzas:movimiento_detail", pk=movimiento.pk)


# ===============================
#   APIs auxiliares (proveedor / flota)
# ===============================

@login_required
@require_GET
def proveedor_por_cuit(request):
    """
    Devuelve datos básicos de proveedor por CUIT.
    Respuesta JSON:
      {found: true/false, nombre}
    """
    cuit = (request.GET.get("cuit") or "").strip()
    if not cuit:
        return JsonResponse({"found": False})

    try:
        proveedor = Proveedor.objects.get(cuit=cuit)
    except Proveedor.DoesNotExist:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "nombre": proveedor.nombre or "",
        }
    )


@login_required
@require_GET
def proveedor_suggest(request):
    """
    Autosugerencias de proveedores por texto (nombre o CUIT).
    Respuesta JSON: lista de objetos {id, nombre, cuit}
    """
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})

    qs = Proveedor.objects.filter(
        Q(nombre__icontains=q) | Q(cuit__icontains=q)
    ).order_by("nombre")[:20]

    results = []
    for p in qs:
        results.append(
            {
                "id": p.id,
                "nombre": p.nombre or "",
                "cuit": p.cuit or "",
            }
        )

    return JsonResponse({"results": results})


@login_required
@require_GET
def vehiculo_por_patente(request):
    """
    Búsqueda rápida de vehículo por patente (para flota / combustible).
    Respuesta JSON:
      {found: true/false, descripcion}
    """
    patente = (request.GET.get("patente") or "").strip().upper()
    if not patente:
        return JsonResponse({"found": False})

    try:
        v = Vehiculo.objects.get(patente__iexact=patente)
    except Vehiculo.DoesNotExist:
        return JsonResponse({"found": False})

    descripcion = v.descripcion if hasattr(v, "descripcion") else ""
    return JsonResponse(
        {
            "found": True,
            "descripcion": descripcion,
        }
    )
