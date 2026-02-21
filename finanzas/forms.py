# finanzas/forms.py
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse_lazy
from django.forms import inlineformset_factory
from django.db import models as dj_models

# Modelos
from .models import (
    Movimiento, Beneficiario, ProgramaAyuda, Area, Categoria,
    Atencion, OrdenPago, OrdenPagoLinea, OrdenCompra, OrdenCompraLinea,
    FacturaOC, Vehiculo, HojaRuta, Traslado,
    OrdenTrabajo, OrdenTrabajoMaterial, AdjuntoOrdenTrabajo,
    Proveedor, DocumentoBeneficiario, DocumentoSensible , Beneficiario, Cuenta
)

# =========================================================
# 1) MIXINS Y UTILIDADES
# =========================================================

class EstiloFormMixin:
    """
    Inyecta clases de Bootstrap automáticamente a los widgets.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            widget = field.widget
            attrs = widget.attrs
            existing_class = (attrs.get("class", "") or "").strip()

            if isinstance(widget, (forms.CheckboxInput,)):
                if "form-check-input" not in existing_class:
                    attrs["class"] = f"{existing_class} form-check-input".strip()

            elif isinstance(widget, (forms.RadioSelect,)):
                pass

            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                if "form-select" not in existing_class:
                    attrs["class"] = f"{existing_class} form-select".strip()

            else:
                if "form-control" not in existing_class:
                    attrs["class"] = f"{existing_class} form-control".strip()

            if isinstance(widget, forms.Textarea):
                attrs["rows"] = attrs.get("rows", 3)


_MONEY_CLEAN_RE = re.compile(r"[^\d,.\-]")


def _money_to_decimal(value: str) -> Decimal:
    """
    Parseo inteligente de montos (AR/US).
    """
    s = (value or "").strip()
    s = s.replace(" ", "").replace("\u00a0", "")
    s = _MONEY_CLEAN_RE.sub("", s)

    if not s:
        raise ValidationError("Ingresá un monto válido. Ej: 10.000,00")

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        part = s.split(",")[-1]
        if len(part) in (1, 2):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_dot:
        part = s.split(".")[-1]
        if len(part) in (1, 2):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "")

    try:
        dec = Decimal(s)
    except InvalidOperation:
        raise ValidationError("Ingresá un monto válido. Ej: 10.000,00")

    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MontoDecimalField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return _money_to_decimal(str(value))


def _normalizar_dni(valor: str) -> str:
    if valor is None:
        return ""
    valor = str(valor).strip()
    return re.sub(r"\D+", "", valor)


def _money_formfield_callback(db_field, **kwargs):
    if isinstance(db_field, dj_models.DecimalField):
        required = not (getattr(db_field, "blank", False) or getattr(db_field, "null", False))
        return MontoDecimalField(
            max_digits=db_field.max_digits,
            decimal_places=db_field.decimal_places,
            required=required,
            label=getattr(db_field, "verbose_name", None),
            widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
        )
    return db_field.formfield(**kwargs)


def _select2_single_queryset_for_bound(model_cls, *, instance_pk=None, bound_value=None):
    pk = None
    if instance_pk:
        pk = instance_pk
    else:
        raw = (bound_value or "").strip() if bound_value is not None else ""
        if raw.isdigit():
            pk = int(raw)

    if not pk:
        return model_cls.objects.none()

    return model_cls.objects.filter(pk=pk)


# =========================================================
# 2) MOVIMIENTOS
# =========================================================
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy

# IMPORTANTE: Asegurate de que 'Cuenta' esté importado en tu archivo forms.py
# from .models import Movimiento, Beneficiario, Proveedor, Vehiculo, Categoria, Area, Cuenta, ...

class MovimientoForm(EstiloFormMixin, forms.ModelForm):
    """
    Formulario principal de Caja.
    - INGRESO: Permite vincular Persona (para recibo).
    - GASTO: Permite vincular Persona, Proveedor o Vehículo.
    - TRANSFERENCIA: Solo cuentas internas.
    """

    TPP_NINGUNO = "NINGUNO"

    # Opciones formales adaptadas a la gestión real de la Comuna
    TIPO_PAGO_CHOICES = [
        (TPP_NINGUNO, "No aplica / Ninguno"),
        ("EFECTIVO", "Dinero en Efectivo (Caja)"),
        ("TRANSFERENCIA", "Transferencia Bancaria"),
        ("MERCADERIA", "Entrega de Mercadería / Alimentos"),
        ("MATERIALES", "Materiales de Construcción"),
        ("PASAJES", "Pasajes / Traslados"),
        ("VALE", "Vale de Retiro / Orden de Compra"),
    ]

    fecha_operacion = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )

    monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.TextInput(attrs={
            "inputmode": "decimal",
            "autocomplete": "off",
            "placeholder": "Ej: 10000,00",
        })
    )

    # 🚀 MEJORA TESORERÍA: Conectamos los selectores a las cajas reales
    cuenta_origen = forms.ModelChoiceField(
        queryset=Cuenta.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select fw-bold"}),
        empty_label="Seleccione Caja / Banco..."
    )
    
    cuenta_destino = forms.ModelChoiceField(
        queryset=Cuenta.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select fw-bold"}),
        empty_label="Seleccione Caja / Banco..."
    )

    litros = MontoDecimalField(
        max_digits=10, decimal_places=2, required=False,
        widget=forms.TextInput(attrs={
            "inputmode": "decimal",
            "autocomplete": "off",
            "placeholder": "Ej: 40 o 40,5",
        })
    )
    precio_unitario = MontoDecimalField(
        max_digits=14, decimal_places=2, required=False,
        widget=forms.TextInput(attrs={
            "inputmode": "decimal",
            "autocomplete": "off",
            "placeholder": "Ej: 1250,00",
        })
    )

    # Transformamos el texto libre en un Select estricto
    tipo_pago_persona = forms.ChoiceField(
        choices=TIPO_PAGO_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select fw-bold"}),
        label="Modalidad de Asistencia"
    )

    # AJAX Beneficiario
    beneficiario = forms.ModelChoiceField(
        queryset=Beneficiario.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar persona en padrón (DNI / Apellido / Nombre)...",
        })
    )

    # Campos Persona Nueva
    persona_nueva_dni = forms.CharField(
        required=False,
        label="DNI/CUIL (Persona nueva)",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "placeholder": "Solo números"})
    )
    persona_nueva_apellido = forms.CharField(
        required=False,
        label="Apellido (Persona nueva)",
        widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    persona_nueva_nombre = forms.CharField(
        required=False,
        label="Nombre (Persona nueva)",
        widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    persona_nueva_direccion = forms.CharField(
        required=False,
        label="Dirección (Persona nueva)",
        widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    persona_nueva_barrio = forms.CharField(
        required=False,
        label="Barrio (Persona nueva)",
        widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    persona_nueva_telefono = forms.CharField(
        required=False,
        label="Teléfono (Persona nueva)",
        widget=forms.TextInput(attrs={"autocomplete": "off"})
    )

    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.all().order_by("nombre"),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:oc_proveedores_suggest"),
            "data-placeholder": "Buscar proveedor (Razón Social / CUIT)...",
        })
    )

    vehiculo = forms.ModelChoiceField(
        queryset=Vehiculo.objects.filter(activo=True).order_by("patente"),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:vehiculo_autocomplete"),
            "data-placeholder": "Buscar vehículo (Patente / Descripción)...",
        })
    )

    class Meta:
        model = Movimiento
        fields = [
            "tipo", "fecha_operacion", "monto",
            "cuenta_origen", "cuenta_destino", # 🚀 AHORA USAMOS LAS REALES
            "categoria", "area",
            "proveedor", "proveedor_cuit", "proveedor_nombre",
            "beneficiario", "beneficiario_dni", "beneficiario_nombre",
            "tipo_pago_persona",
            "programa_ayuda", "programa_ayuda_texto",
            "vehiculo", "vehiculo_texto",
            "litros", "precio_unitario", "tipo_combustible",
            "descripcion", "observaciones",
        ]
        # Re-etiquetado corporativo
        labels = {
            "fecha_operacion": "Fecha de operación",
            "cuenta_origen": "Cuenta Origen (Salida de fondos)",
            "cuenta_destino": "Cuenta Destino (Ingreso de fondos)",
            "programa_ayuda_texto": "Detalle de bienes / elementos entregados",
            "observaciones": "Notas Internas (Uso administrativo - No se imprime)",
            "descripcion": "Descripción Pública (Visible en el comprobante)",
        }
        widgets = {
            "proveedor_cuit": forms.TextInput(attrs={"readonly": "readonly", "class": "bg-light"}),
            "proveedor_nombre": forms.TextInput(attrs={"readonly": "readonly", "class": "bg-light"}),
            "beneficiario_dni": forms.TextInput(attrs={"readonly": "readonly", "class": "bg-light"}),
            "beneficiario_nombre": forms.TextInput(attrs={"readonly": "readonly", "class": "bg-light"}),
            "vehiculo_texto": forms.TextInput(attrs={"readonly": "readonly", "class": "bg-light"}),
            "programa_ayuda_texto": forms.TextInput(attrs={"placeholder": "Ej: 1 bolsón de mercadería, 2 chapas de zinc, etc."}),
            "observaciones": forms.Textarea(attrs={"rows": 2, "placeholder": "Anotaciones exclusivas para el equipo de gestión..."}),
            "descripcion": forms.Textarea(attrs={"rows": 2, "placeholder": "El sistema autocompletará este campo al seleccionar una categoría o persona..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["categoria"].queryset = Categoria.objects.order_by("nombre")
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by("nombre")

        # Cargar opción seleccionada en Select2 Ajax
        bound_ben = None
        if self.is_bound:
            bound_ben = (self.data.get(self.add_prefix("beneficiario")) or self.data.get("beneficiario") or "").strip()

        instance_ben_pk = getattr(self.instance, "beneficiario_id", None) if self.instance else None
        self.fields["beneficiario"].queryset = _select2_single_queryset_for_bound(
            Beneficiario,
            instance_pk=instance_ben_pk,
            bound_value=bound_ben,
        )

        try:
            if self.is_bound:
                tipo_val = (self.data.get(self.add_prefix("tipo")) or self.data.get("tipo") or "").strip()
            else:
                tipo_val = (getattr(self.instance, "tipo", "") or "").strip()

            modo = self._modo(tipo_val)

            cat_ing = getattr(Categoria, "TIPO_INGRESO", "INGRESO")
            cat_gas = getattr(Categoria, "TIPO_GASTO", "GASTO")
            cat_amb = getattr(Categoria, "TIPO_AMBOS", "AMBOS")

            qs_cat = Categoria.objects.order_by("nombre")
            if modo == "INGRESO":
                qs_cat = qs_cat.filter(tipo__in=[cat_ing, cat_amb])
            elif modo == "GASTO":
                qs_cat = qs_cat.filter(tipo__in=[cat_gas, cat_amb])

            self.fields["categoria"].queryset = qs_cat
        except Exception:
            pass

        # Campos opcionales por defecto (validación real en clean)
        for fn in (
            "programa_ayuda", "programa_ayuda_texto"
        ):
            if fn in self.fields:
                self.fields[fn].required = False

        self._persona_a_crear = None

    # --- HELPERS ---

    def _modo(self, tipo: str) -> str:
        t = (tipo or "").strip().upper()
        if "ING" in t: return "INGRESO"
        if "GAS" in t or "EGR" in t or "SAL" in t: return "GASTO"
        if "TRANS" in t: return "TRANSFERENCIA"
        return ""

    def _tp_is_none(self, value) -> bool:
        v = (value or "").strip().upper()
        return not v or v in {self.TPP_NINGUNO, "NO", "N/A", "NA"}

    def _es_ayuda_social(self, cleaned) -> bool:
        cat = cleaned.get("categoria")
        if cleaned.get("programa_ayuda"): return True
        if cat and getattr(cat, "es_ayuda_social", False): return True
        return not self._tp_is_none(cleaned.get("tipo_pago_persona"))

    def _es_combustible(self, cleaned) -> bool:
        cat = cleaned.get("categoria")
        if any([cleaned.get("litros"), cleaned.get("precio_unitario"), (cleaned.get("tipo_combustible") or "").strip()]):
            return True
        return cat and getattr(cat, "es_combustible", False)

    # --- VALIDACIÓN (CLEAN) ---

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        modo = self._modo(tipo)

        if not modo:
            self.add_error("tipo", "Seleccione el tipo de operación.")
            return cleaned

        if not (cleaned.get("descripcion") or "").strip():
            self.add_error("descripcion", "La descripción pública es obligatoria.")

        # 🚀 VALIDACIÓN DE CAJAS REALES
        co = cleaned.get("cuenta_origen")
        cd = cleaned.get("cuenta_destino")

        if modo == "INGRESO":
            if not cd: self.add_error("cuenta_destino", "Para un INGRESO debe indicar a qué Caja/Banco entra el dinero.")
            cleaned["cuenta_origen"] = None
        elif modo == "GASTO":
            if not co: self.add_error("cuenta_origen", "Para un GASTO debe indicar de qué Caja/Banco sale el dinero.")
            cleaned["cuenta_destino"] = None
        elif modo == "TRANSFERENCIA":
            if not co: self.add_error("cuenta_origen", "Falta indicar la cuenta origen.")
            if not cd: self.add_error("cuenta_destino", "Falta indicar la cuenta destino.")
            if co == cd: self.add_error("cuenta_destino", "La cuenta de origen y destino deben ser distintas.")

        # LIMPIEZA INICIAL SEGÚN MODO
        if modo == "TRANSFERENCIA":
            for k in ["proveedor", "programa_ayuda", "vehiculo", "beneficiario", "litros", "precio_unitario"]:
                cleaned[k] = None
            for k in ["proveedor_cuit", "proveedor_nombre", "vehiculo_texto", "tipo_combustible", "beneficiario_dni", "beneficiario_nombre"]:
                cleaned[k] = ""
            cleaned["tipo_pago_persona"] = self.TPP_NINGUNO
            self._persona_a_crear = None
            return cleaned

        if modo == "INGRESO":
            for k in ["proveedor", "programa_ayuda", "vehiculo", "litros", "precio_unitario"]:
                cleaned[k] = None
            for k in ["proveedor_cuit", "proveedor_nombre", "vehiculo_texto", "tipo_combustible"]:
                cleaned[k] = ""
            cleaned["tipo_pago_persona"] = self.TPP_NINGUNO

        # LÓGICA DE PERSONA
        ben = cleaned.get("beneficiario")
        new_dni = _normalizar_dni(cleaned.get("persona_nueva_dni"))
        new_ape = (cleaned.get("persona_nueva_apellido") or "").strip()
        new_nom = (cleaned.get("persona_nueva_nombre") or "").strip()
        intentando_crear = bool(new_dni or new_ape or new_nom)

        if ben and intentando_crear:
            raise ValidationError("Seleccionó una persona del padrón y completó datos nuevos. Elija solo una opción.")

        if intentando_crear:
            if not new_dni:
                self.add_error("persona_nueva_dni", "Falta indicar el DNI para la persona nueva.")
            elif len(new_dni) not in (7, 8, 9, 11):
                self.add_error("persona_nueva_dni", "DNI inválido. Verifique la cantidad de dígitos.")
            else:
                existente = Beneficiario.objects.filter(dni=new_dni).first()
                if existente:
                    cleaned["beneficiario"] = existente
                    ben = existente
                else:
                    if not new_ape or not new_nom:
                        self.add_error("persona_nueva_apellido", "Debe indicar Apellido y Nombre.")
                    else:
                        self._persona_a_crear = {
                            "dni": new_dni, "apellido": new_ape, "nombre": new_nom,
                            "direccion": cleaned.get("persona_nueva_direccion", ""),
                            "barrio": cleaned.get("persona_nueva_barrio", ""),
                            "telefono": cleaned.get("persona_nueva_telefono", "")
                        }

        # Actualizar campos espejo de Persona
        if ben:
            cleaned["beneficiario_dni"] = ben.dni or ""
            cleaned["beneficiario_nombre"] = f"{ben.apellido}, {ben.nombre}".strip()
        else:
            cleaned["beneficiario_dni"] = ""
            cleaned["beneficiario_nombre"] = ""

        # LÓGICA ESPECÍFICA DE GASTO
        if modo == "GASTO":
            prov = cleaned.get("proveedor")
            veh = cleaned.get("vehiculo")
            es_ayuda = self._es_ayuda_social(cleaned)

            if not es_ayuda:
                cleaned["tipo_pago_persona"] = self.TPP_NINGUNO
                cleaned["programa_ayuda"] = None

            req_persona = es_ayuda or (not prov and not veh)
            if req_persona and not ben and not self._persona_a_crear:
                self.add_error("beneficiario", "Para este tipo de gasto debe vincular a un Beneficiario, Proveedor o Vehículo.")

            if es_ayuda and self._tp_is_none(cleaned.get("tipo_pago_persona")):
                self.add_error("tipo_pago_persona", "Debe seleccionar una Modalidad de Asistencia.")

            if prov:
                cleaned["proveedor_cuit"] = prov.cuit or ""
                cleaned["proveedor_nombre"] = prov.nombre or ""
            else:
                cleaned["proveedor_cuit"] = ""
                cleaned["proveedor_nombre"] = ""

            if self._es_combustible(cleaned):
                if not veh: self.add_error("vehiculo", "Debe seleccionar un Vehículo para el registro de combustible.")
                if cleaned.get("litros") is None: self.add_error("litros", "Falta indicar la cantidad de litros.")
                if not cleaned.get("tipo_combustible"): self.add_error("tipo_combustible", "Debe indicar el tipo de combustible.")
                if veh:
                    cleaned["vehiculo_texto"] = f"{veh.patente} - {veh.descripcion}".strip(" -")
            else:
                cleaned["litros"] = None
                cleaned["precio_unitario"] = None
                cleaned["tipo_combustible"] = ""
                cleaned["vehiculo"] = None
                cleaned["vehiculo_texto"] = ""

        return cleaned

    # --- SAVE ---

    def save(self, commit=True):
        mov = super().save(commit=False)
        modo = self._modo(self.cleaned_data.get("tipo"))

        if modo == "INGRESO":
            mov.cuenta_origen = None # 🚀 AHORA LIMPIAMOS EL OBJETO REAL
            mov.proveedor = None
            mov.proveedor_cuit = ""
            mov.proveedor_nombre = ""
            mov.programa_ayuda = None
            mov.programa_ayuda_texto = ""
            mov.vehiculo = None
            mov.vehiculo_texto = ""
            mov.litros = None
            mov.precio_unitario = None
            mov.tipo_combustible = ""
            mov.tipo_pago_persona = self.TPP_NINGUNO

        elif modo == "TRANSFERENCIA":
            mov.proveedor = None
            mov.proveedor_cuit = ""
            mov.proveedor_nombre = ""
            mov.programa_ayuda = None
            mov.programa_ayuda_texto = ""
            mov.vehiculo = None
            mov.vehiculo_texto = ""
            mov.litros = None
            mov.precio_unitario = None
            mov.tipo_combustible = ""
            mov.beneficiario = None
            mov.beneficiario_dni = ""
            mov.beneficiario_nombre = ""
            mov.tipo_pago_persona = self.TPP_NINGUNO

        else: # GASTO
            mov.cuenta_destino = None # 🚀 AHORA LIMPIAMOS EL OBJETO REAL

        if self._persona_a_crear:
            data = self._persona_a_crear
            ben, _ = Beneficiario.objects.get_or_create(
                dni=data["dni"],
                defaults={
                    "apellido": data["apellido"], "nombre": data["nombre"],
                    "direccion": data["direccion"], "barrio": data["barrio"],
                    "telefono": data["telefono"], "activo": True
                }
            )
            if not ben.activo:
                ben.activo = True
                ben.save(update_fields=["activo"])
            
            mov.beneficiario = ben
            mov.beneficiario_dni = ben.dni or ""
            mov.beneficiario_nombre = f"{ben.apellido}, {ben.nombre}".strip()
        else:
            ben = self.cleaned_data.get("beneficiario")
            if ben:
                if not ben.activo:
                    ben.activo = True
                    ben.save(update_fields=["activo"])
                mov.beneficiario = ben
                mov.beneficiario_dni = ben.dni or ""
                mov.beneficiario_nombre = f"{ben.apellido}, {ben.nombre}".strip()
            elif modo != "INGRESO": 
                mov.beneficiario = None
                mov.beneficiario_dni = ""
                mov.beneficiario_nombre = ""

        if modo == "GASTO":
            prov = self.cleaned_data.get("proveedor")
            if prov:
                mov.proveedor = prov
                mov.proveedor_cuit = prov.cuit or ""
                mov.proveedor_nombre = prov.nombre or ""
            else:
                mov.proveedor = None
                mov.proveedor_cuit = ""
                mov.proveedor_nombre = ""

            veh = self.cleaned_data.get("vehiculo")
            if veh:
                mov.vehiculo = veh
                mov.vehiculo_texto = f"{veh.patente} - {veh.descripcion}".strip(" -")
            else:
                mov.vehiculo = None
                mov.vehiculo_texto = ""
                mov.litros = None
                mov.precio_unitario = None
                mov.tipo_combustible = ""

        if commit:
            mov.save()
            self.save_m2m()
        return mov

# =========================================================
# 3) ÓRDENES DE COMPRA (OC) Y FORMULARIOS RÁPIDOS
# =========================================================
from django import forms
from django.utils import timezone
from django.forms import inlineformset_factory
from django.urls import reverse_lazy

from .models import OrdenCompra, OrdenCompraLinea, Proveedor, Beneficiario
from .mixins import EstiloFormMixin 

class OrdenCompraForm(EstiloFormMixin, forms.ModelForm):
    RUBROS_CHOICES = [
        ("AS", "AS - Ayudas sociales"),
        ("CB", "CB - Combustible"),
        ("OB", "OB - Obras y materiales"),
        ("SV", "SV - Servicios contratados"),
        ("PE", "PE - Personal / jornales"),
        ("HI", "HI - Herramientas / insumos"),
        ("OT", "OT - Otros"),
    ]

    TIPO_NUMERO_CHOICES = [
        ('AUTO', 'Automático (Sistema)'),
        ('MANUAL', 'Manual (Talonario)'),
    ]
    
    tipo_numeracion = forms.ChoiceField(
        choices=TIPO_NUMERO_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "btn-check"}),
        initial='AUTO',
        required=False,
        label="Modo de Numeración"
    )

    fecha_oc = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=lambda: timezone.now().date())
    
    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.filter(activo=True),
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:oc_proveedores_suggest"),
            "data-placeholder": "Buscar proveedor...",
        })
    )

    # Selector de Persona (Vecino)
    persona = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True), # Solo activos
        required=False,
        label="Beneficiario / Vecino (Opcional)",
        widget=forms.Select(attrs={
            "class": "form-select select2", 
            "data-placeholder": "Buscar vecino (Ayuda Social)...",
            "id": "id_persona_select" 
        })
    )

    rubro_principal = forms.ChoiceField(choices=RUBROS_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))

    class Meta:
        model = OrdenCompra
        fields = ["fecha_oc", "numero", "area", "proveedor", "proveedor_nombre", "proveedor_cuit", "persona", "rubro_principal", "observaciones"]
        widgets = {
            "proveedor_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "proveedor_cuit": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "numero": forms.TextInput(attrs={"class": "bg-light", "placeholder": "Automático al guardar"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_numeracion")
        numero = cleaned.get("numero")
        
        if tipo == 'MANUAL' and not numero:
            self.add_error('numero', 'Si elige numeración Manual, debe ingresar el N° de Comprobante.')
        
        p = cleaned.get("proveedor")
        if p:
            cleaned["proveedor_nombre"] = p.nombre
            cleaned["proveedor_cuit"] = p.cuit or ""
            
        return cleaned

# ✅ FORMULARIO RÁPIDO PARA EL MODAL
class BeneficiarioQuickForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = ['nombre', 'apellido', 'dni', 'direccion', 'telefono']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}),
            'dni': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Solo números'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Domicilio actual'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Celular / WhatsApp'}),
        }

OrdenCompraLineaFormSet = inlineformset_factory(
    OrdenCompra, OrdenCompraLinea,
    fields=["categoria", "area", "descripcion", "monto"],
    extra=0,
    can_delete=True,
    widgets={
        "monto": forms.NumberInput(attrs={"class": "form-control text-end no-arrow", "step": "0.01", "placeholder": "0.00"}),
        "descripcion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Detalle del ítem..."}),
        "categoria": forms.Select(attrs={"class": "form-select"}),
        "area": forms.Select(attrs={"class": "form-select"}),
    }
)


# =========================================================
# 4) ÓRDENES DE PAGO
# =========================================================

class OrdenPagoForm(EstiloFormMixin, forms.ModelForm):
    fecha_orden = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    factura_fecha = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    factura_monto = MontoDecimalField(
        max_digits=14, decimal_places=2, required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off", "placeholder": "Ej: 125000,00"})
    )

    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.all(), required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:oc_proveedores_suggest"),
            "data-placeholder": "Buscar proveedor...",
        })
    )

    class Meta:
        model = OrdenPago
        fields = [
            "numero", "fecha_orden", "proveedor", "proveedor_nombre", "proveedor_cuit", "area",
            "condicion_pago", "medio_pago_previsto", "observaciones",
            "factura_tipo", "factura_numero", "factura_fecha", "factura_monto"
        ]
        widgets = {
            "proveedor_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "proveedor_cuit": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("proveedor")
        if p:
            cleaned["proveedor_cuit"] = p.cuit or ""
            cleaned["proveedor_nombre"] = p.nombre or ""
        return cleaned

def _money_formfield_callback(f, **kwargs):
    from django.db import models
    if isinstance(f, models.DecimalField):
        return MontoDecimalField(
            max_digits=f.max_digits,
            decimal_places=f.decimal_places,
            widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "form-control text-end", "placeholder": "0,00"}),
            **kwargs
        )
    return f.formfield(**kwargs)


OrdenPagoLineaFormSet = inlineformset_factory(
    OrdenPago, OrdenPagoLinea,
    fields="__all__", extra=1, can_delete=True,
    formfield_callback=_money_formfield_callback
)

# =========================================================
# 5) PERSONAS (SOCIAL)
# =========================================================

class BeneficiarioForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = [
            "nombre", "apellido", "dni", "fecha_nacimiento",
            "direccion", "barrio", "telefono",
            "notas",
            "paga_servicios", "detalle_servicios",
            "tipo_vinculo", "sector_laboral", "fecha_ingreso",
            "percibe_beneficio", "beneficio_detalle", "beneficio_organismo", "beneficio_monto_aprox",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "fecha_ingreso": forms.DateInput(attrs={"type": "date"}),
            "beneficio_monto_aprox": forms.TextInput(attrs={
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "Ej: 50000,00"
            }),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dni"].required = True
        if not self.instance.pk:
            self.instance.activo = True

    def clean_nombre(self):
        v = (self.cleaned_data.get("nombre") or "").strip()
        if not v:
            raise ValidationError("Este campo es obligatorio.")
        return v

    def clean_apellido(self):
        v = (self.cleaned_data.get("apellido") or "").strip()
        if not v:
            raise ValidationError("Este campo es obligatorio.")
        return v

    def clean_dni(self):
        dni_raw = self.cleaned_data.get("dni", "")
        dni = _normalizar_dni(dni_raw)

        if not dni:
            raise ValidationError("Ingrese DNI/CUIL (solo números).")

        if len(dni) not in (7, 8, 9, 11):
            raise ValidationError("DNI/CUIL inválido. Verifique la cantidad de dígitos.")

        qs = Beneficiario.objects.filter(dni=dni)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            e = qs.first()
            raise ValidationError(f"Ya existe una persona con ese DNI/CUIL: {e.apellido}, {e.nombre} (ID {e.id}).")
        return dni

    def clean(self):
        cleaned = super().clean()
        nombre = (cleaned.get("nombre") or "").strip().lower()
        apellido = (cleaned.get("apellido") or "").strip().lower()
        fecha = cleaned.get("fecha_nacimiento")

        if nombre and apellido and fecha:
            qs = Beneficiario.objects.filter(nombre__iexact=nombre, apellido__iexact=apellido, fecha_nacimiento=fecha)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Posible duplicado: ya existe una persona con el mismo Nombre, Apellido y Fecha de Nacimiento.")
        return cleaned


class AtencionForm(EstiloFormMixin, forms.ModelForm):
    fecha_atencion = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=lambda: timezone.now().date()
    )
    hora_atencion = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        required=False,
        initial=lambda: timezone.now().time()
    )
    persona = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True).order_by("apellido", "nombre"),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar persona en padrón...",
        })
    )

    class Meta:
        from .models import Atencion
        model = Atencion
        fields = "__all__"
        widgets = {
            "persona_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "persona_dni": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "persona_barrio": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "resultado": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("persona")
        if p:
            cleaned["persona_nombre"] = f"{p.apellido}, {p.nombre}".strip()
            cleaned["persona_dni"] = p.dni or ""
            cleaned["persona_barrio"] = p.barrio or ""
        return cleaned


# =========================================================
# 3) ÓRDENES DE COMPRA (OC) Y FORMULARIOS RÁPIDOS
# =========================================================
from django import forms
from django.utils import timezone
from django.forms import inlineformset_factory
from django.urls import reverse_lazy

from .models import OrdenCompra, OrdenCompraLinea, Proveedor, Beneficiario
# Asumo que tenés un mixin de estilos, si no, borrá "EstiloFormMixin"
from .mixins import EstiloFormMixin 

class OrdenCompraForm(EstiloFormMixin, forms.ModelForm):
    RUBROS_CHOICES = [
        ("AS", "AS - Ayudas sociales"),
        ("CB", "CB - Combustible"),
        ("OB", "OB - Obras y materiales"),
        ("SV", "SV - Servicios contratados"),
        ("PE", "PE - Personal / jornales"),
        ("HI", "HI - Herramientas / insumos"),
        ("OT", "OT - Otros"),
    ]

    TIPO_NUMERO_CHOICES = [
        ('AUTO', 'Automático (Sistema)'),
        ('MANUAL', 'Manual (Talonario)'),
    ]
    
    tipo_numeracion = forms.ChoiceField(
        choices=TIPO_NUMERO_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "btn-check"}),
        initial='AUTO',
        required=False,
        label="Modo de Numeración"
    )

    fecha_oc = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=lambda: timezone.now().date())
    
    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.filter(activo=True),
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:oc_proveedores_suggest"),
            "data-placeholder": "Buscar proveedor...",
        })
    )

    # Selector de Persona (Vecino)
    persona = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True), # Solo activos
        required=False,
        label="Beneficiario / Vecino (Opcional)",
        widget=forms.Select(attrs={
            "class": "form-select select2", 
            "data-placeholder": "Buscar vecino (Ayuda Social)...",
            "id": "id_persona_select" # ID explícito para actualizarlo via JS
        })
    )

    rubro_principal = forms.ChoiceField(choices=RUBROS_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))

    class Meta:
        model = OrdenCompra
        fields = ["fecha_oc", "numero", "area", "proveedor", "proveedor_nombre", "proveedor_cuit", "persona", "rubro_principal", "observaciones"]
        widgets = {
            "proveedor_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "proveedor_cuit": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "numero": forms.TextInput(attrs={"class": "bg-light", "placeholder": "Automático al guardar"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_numeracion")
        numero = cleaned.get("numero")
        
        if tipo == 'MANUAL' and not numero:
            self.add_error('numero', 'Si elige numeración Manual, debe ingresar el N° de Comprobante.')
        
        p = cleaned.get("proveedor")
        if p:
            cleaned["proveedor_nombre"] = p.nombre
            cleaned["proveedor_cuit"] = p.cuit or ""
            
        return cleaned

# ✅ NUEVO FORMULARIO RÁPIDO PARA EL MODAL
class BeneficiarioQuickForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = ['nombre', 'apellido', 'dni', 'direccion', 'telefono']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}),
            'dni': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Solo números'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Domicilio actual'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Celular / WhatsApp'}),
        }

OrdenCompraLineaFormSet = inlineformset_factory(
    OrdenCompra, OrdenCompraLinea,
    fields=["categoria", "area", "descripcion", "monto"],
    extra=0,
    can_delete=True,
    widgets={
        "monto": forms.NumberInput(attrs={"class": "form-control text-end no-arrow", "step": "0.01", "placeholder": "0.00"}),
        "descripcion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Detalle del ítem..."}),
        "categoria": forms.Select(attrs={"class": "form-select"}),
        "area": forms.Select(attrs={"class": "form-select"}),
    }
)


# =========================================================
# 4) ÓRDENES DE PAGO
# =========================================================

class OrdenPagoForm(EstiloFormMixin, forms.ModelForm):
    fecha_orden = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    factura_fecha = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    factura_monto = MontoDecimalField(
        max_digits=14, decimal_places=2, required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off", "placeholder": "Ej: 125.000,00"})
    )

    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.all(), required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:oc_proveedores_suggest"),
            "data-placeholder": "Buscar proveedor...",
        })
    )

    class Meta:
        model = OrdenPago
        fields = [
            "numero", "fecha_orden", "proveedor", "proveedor_nombre", "proveedor_cuit", "area",
            "condicion_pago", "medio_pago_previsto", "observaciones",
            "factura_tipo", "factura_numero", "factura_fecha", "factura_monto"
        ]
        widgets = {
            "proveedor_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "proveedor_cuit": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("proveedor")
        if p:
            cleaned["proveedor_cuit"] = p.cuit or ""
            cleaned["proveedor_nombre"] = p.nombre or ""
        return cleaned


OrdenPagoLineaFormSet = inlineformset_factory(
    OrdenPago, OrdenPagoLinea,
    fields="__all__", extra=1, can_delete=True,
    formfield_callback=_money_formfield_callback
)

# =========================================================
# 5) PERSONAS (SOCIAL)
# =========================================================

class BeneficiarioForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Beneficiario
        fields = [
            "nombre", "apellido", "dni", "fecha_nacimiento",
            "direccion", "barrio", "telefono",
            "notas",
            "paga_servicios", "detalle_servicios",
            "tipo_vinculo", "sector_laboral", "fecha_ingreso",
            "percibe_beneficio", "beneficio_detalle", "beneficio_organismo", "beneficio_monto_aprox",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "fecha_ingreso": forms.DateInput(attrs={"type": "date"}),
            "beneficio_monto_aprox": forms.TextInput(attrs={
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "Ej: 50.000,00"
            }),
            "notas": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dni"].required = True
        if not self.instance.pk:
            self.instance.activo = True

    def clean_nombre(self):
        v = (self.cleaned_data.get("nombre") or "").strip()
        if not v:
            raise ValidationError("Este campo es obligatorio.")
        return v

    def clean_apellido(self):
        v = (self.cleaned_data.get("apellido") or "").strip()
        if not v:
            raise ValidationError("Este campo es obligatorio.")
        return v

    def clean_dni(self):
        dni_raw = self.cleaned_data.get("dni", "")
        dni = _normalizar_dni(dni_raw)

        if not dni:
            raise ValidationError("Ingresá DNI/CUIL (solo números).")

        if len(dni) not in (7, 8, 9, 11):
            raise ValidationError("DNI/CUIL inválido. Verificá la cantidad de dígitos.")

        qs = Beneficiario.objects.filter(dni=dni)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            e = qs.first()
            raise ValidationError(f"Ya existe una persona con ese DNI/CUIL: {e.apellido}, {e.nombre} (ID {e.id}).")
        return dni

    def clean(self):
        cleaned = super().clean()
        nombre = (cleaned.get("nombre") or "").strip().lower()
        apellido = (cleaned.get("apellido") or "").strip().lower()
        fecha = cleaned.get("fecha_nacimiento")

        if nombre and apellido and fecha:
            qs = Beneficiario.objects.filter(nombre__iexact=nombre, apellido__iexact=apellido, fecha_nacimiento=fecha)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Posible duplicado: ya existe una persona con mismo Nombre, Apellido y Fecha de Nacimiento.")
        return cleaned


class AtencionForm(EstiloFormMixin, forms.ModelForm):
    fecha_atencion = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=lambda: timezone.now().date()
    )
    hora_atencion = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        required=False,
        initial=lambda: timezone.now().time()
    )
    persona = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True).order_by("apellido", "nombre"),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar persona...",
        })
    )

    class Meta:
        model = Atencion
        fields = "__all__"
        widgets = {
            "persona_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "persona_dni": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "persona_barrio": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "resultado": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("persona")
        if p:
            cleaned["persona_nombre"] = f"{p.apellido}, {p.nombre}".strip()
            cleaned["persona_dni"] = p.dni or ""
            cleaned["persona_barrio"] = p.barrio or ""
        return cleaned


# =========================================================
# 6) FLOTA Y LOGÍSTICA
# =========================================================

class VehiculoForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = "__all__"
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 3, "class": "form-control", "placeholder": "Detalles mecánicos, service, etc..."}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.TextInput(attrs={"placeholder": "Ej: Toyota, Ford..."}),
        }


class HojaRutaForm(EstiloFormMixin, forms.ModelForm):
    fecha = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=lambda: timezone.now().date()
    )
    hora_salida = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        required=False,
        initial=lambda: timezone.now().time()
    )
    chofer = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True).order_by("apellido", "nombre"),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar chofer...",
        })
    )

    class Meta:
        model = HojaRuta
        fields = ["vehiculo", "chofer", "chofer_nombre", "fecha", "hora_salida", "odometro_inicio", "observaciones"]
        widgets = {
            "chofer_nombre": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "odometro_inicio": forms.NumberInput(attrs={"placeholder": "000000"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehiculo"].queryset = Vehiculo.objects.filter(activo=True).order_by("patente")

    def clean(self):
        cleaned = super().clean()
        c = cleaned.get("chofer")
        if c:
            cleaned["chofer_nombre"] = f"{c.apellido}, {c.nombre}".strip()
        return cleaned


class HojaRutaCierreForm(EstiloFormMixin, forms.ModelForm):
    hora_llegada = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        required=False,
        initial=lambda: timezone.now().time()
    )

    class Meta:
        model = HojaRuta
        fields = ["odometro_fin", "hora_llegada", "observaciones"]
        widgets = {
            "odometro_fin": forms.NumberInput(attrs={"placeholder": "000000"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }


# =========================================================
# 7) ÓRDENES DE TRABAJO (OT)
# =========================================================

class TrasladoForm(EstiloFormMixin, forms.ModelForm):
    pasajeros = forms.ModelMultipleChoiceField(
        queryset=Beneficiario.objects.filter(activo=True).order_by("apellido", "nombre"),
        required=False,
        widget=forms.SelectMultiple(attrs={
            "class": "select2-ajax-multi",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar pasajeros...",
        })
    )

    class Meta:
        model = Traslado
        fields = ["origen", "destino", "motivo", "pasajeros", "otros_pasajeros"]
        widgets = {"otros_pasajeros": forms.TextInput(attrs={"placeholder": "Nombres de no empadronados"})}


class OrdenTrabajoForm(EstiloFormMixin, forms.ModelForm):
    fecha_ot = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
        initial=lambda: timezone.now().date()
    )
    
    solicitante = forms.ModelChoiceField(
        queryset=Beneficiario.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar solicitante...",
        })
    )
    
    responsable = forms.ModelChoiceField(
        queryset=Beneficiario.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:persona_autocomplete"),
            "data-placeholder": "Buscar responsable...",
        })
    )

    vehiculo = forms.ModelChoiceField(
        queryset=Vehiculo.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "select2-ajax",
            "data-ajax-url": reverse_lazy("finanzas:vehiculo_autocomplete"),
            "data-placeholder": "Buscar vehículo...",
        })
    )

    class Meta:
        model = OrdenTrabajo
        exclude = ['creado_por', 'fecha_creacion']
        
        widgets = {
            "solicitante_texto": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "responsable_texto": forms.TextInput(attrs={"class": "bg-light", "readonly": "readonly"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "trabajos_realizados": forms.Textarea(attrs={"rows": 3}),
            "numero": forms.TextInput(attrs={"placeholder": "Automático o manual"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'numero' in self.fields:
            self.fields['numero'].required = False

        def set_queryset(field_name, model_class):
            val = None
            if self.is_bound:
                val = self.data.get(field_name)
            elif self.instance.pk:
                val = getattr(self.instance, f"{field_name}_id", None)
            
            if val:
                self.fields[field_name].queryset = model_class.objects.filter(pk=val)
            else:
                self.fields[field_name].queryset = model_class.objects.none()

        set_queryset('solicitante', Beneficiario)
        set_queryset('responsable', Beneficiario)
        set_queryset('vehiculo', Vehiculo)

    def clean(self):
        cleaned = super().clean()
        s = cleaned.get("solicitante")
        r = cleaned.get("responsable")
        
        if s:
            cleaned["solicitante_texto"] = f"{s.apellido}, {s.nombre}".strip()
        if r:
            cleaned["responsable_texto"] = f"{r.apellido}, {r.nombre}".strip()
        return cleaned


OrdenTrabajoMaterialFormSet = inlineformset_factory(
    OrdenTrabajo, OrdenTrabajoMaterial,
    fields="__all__", 
    extra=0,
    can_delete=True,
    formfield_callback=_money_formfield_callback
)

AdjuntoOrdenTrabajoFormSet = inlineformset_factory(
    OrdenTrabajo, AdjuntoOrdenTrabajo,
    fields="__all__", 
    extra=0,
    can_delete=True 
)

# =========================================================
# 8) DOCUMENTOS DIGITALES (LEGAJO)
# =========================================================

class DocumentoBeneficiarioForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentoBeneficiario
        fields = ['tipo', 'archivo', 'descripcion']
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'archivo': forms.FileInput(attrs={'class': 'form-control'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: DNI frente y dorso, CUD 2026...'}),
        }


# Agregá esto junto a tus otros forms
class DocumentoSensibleForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentoSensible
        fields = ['tipo', 'archivo', 'descripcion']
        widgets = {
            'descripcion': forms.TextInput(attrs={'placeholder': 'Referencia interna (Opcional)'}),
        }


# =========================================================
# 9) PROVEEDORES Y COMERCIOS (Agenda Limpia)
# =========================================================

class ProveedorForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            "nombre", "cuit", "direccion", "telefono", "email", 
            "rubro", "alias", "cbu", "activo",
            # --- Campos DReI ---
            "es_contribuyente_drei", "padron_drei" # Solo dejamos Padrón para ID
        ]
        widgets = {
            "direccion": forms.TextInput(attrs={"placeholder": "Calle y Número"}),
            "cuit": forms.TextInput(attrs={"placeholder": "Sin guiones"}),
            "padron_drei": forms.TextInput(attrs={"placeholder": "Dejar vacío para generar automáticamente"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['es_contribuyente_drei'].widget.attrs.update({'class': 'form-check-input'})
        self.fields['padron_drei'].widget.attrs.update({'class': 'form-control drei-field'})

    def clean(self):
        cleaned = super().clean()
        es_drei = cleaned.get("es_contribuyente_drei")
        
        # 🚀 FIX: Quitamos la validación que obligaba a cargar el padrón manualmente, 
        # así el models.py puede autogenerarlo si viene vacío.
        
        if not es_drei:
            # Si lo destildan, limpiamos el padrón para que no quede basura
            cleaned["padron_drei"] = ""

        return cleaned


# =========================================================
# 10) DECLARACIONES JURADAS DREI (Con Alícuota Manual)
# =========================================================
from .models import DeclaracionJuradaDrei, RubroDrei
from django.core.exceptions import ValidationError

class DeclaracionJuradaDreiForm(EstiloFormMixin, forms.ModelForm):
    # 🚀 FIX: El usuario ingresa plata con comas.
    ingresos_declarados = MontoDecimalField(
        max_digits=15, decimal_places=2,
        widget=forms.TextInput(attrs={
            "inputmode": "decimal", 
            "autocomplete": "off", 
            "placeholder": "Facturación bruta...",
            "class": "form-control text-end fw-bold text-success fs-5"
        })
    )

    class Meta:
        model = DeclaracionJuradaDrei
        # 🚀 FIX: Agregamos actividad y alicuota_manual a la vista
        fields = ["anio", "mes", "actividad", "ingresos_declarados", "alicuota_manual", "observaciones"]
        widgets = {
            "anio": forms.NumberInput(attrs={"placeholder": "Ej: 2026", "class": "form-control fw-bold text-center"}),
            "mes": forms.Select(attrs={"class": "form-select fw-bold text-center"}),
            "actividad": forms.Select(attrs={"class": "form-select fw-medium"}),
            
            # 🚀 FIX EXPERTO: Actualizamos las instrucciones visuales para la nueva matemática
            "alicuota_manual": forms.NumberInput(attrs={
                "step": "0.001", # Permite decimales como 0.5 o 0.75 sin tirar error de HTML
                "class": "form-control text-end fw-bold fs-5 text-teal",
                "placeholder": "Ej: 0.5",
                "title": "Ejemplo: Para un 5% escriba 5. Para medio por ciento escriba 0.5"
            }),
            "observaciones": forms.Textarea(attrs={"rows": 2, "placeholder": "Aclaraciones o notas internas..."}),
        }

    def __init__(self, *args, comercio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.comercio = comercio
        
        # Hacemos que el combo de actividades sea buscable (si usás select2 en frontend)
        self.fields['actividad'].queryset = RubroDrei.objects.filter(activo=True)
        self.fields['actividad'].empty_label = "Seleccione la Actividad Gravada..."
        
        if not self.instance.pk:
            from django.utils import timezone
            self.fields['anio'].initial = timezone.now().year
            
            mes_actual = timezone.now().month
            mes_sugerido = mes_actual - 1 if mes_actual > 1 else 12
            self.fields['mes'].initial = mes_sugerido
            
            if mes_sugerido == 12:
                self.fields['anio'].initial = timezone.now().year - 1

    def clean(self):
        cleaned = super().clean()
        anio = cleaned.get("anio")
        mes = cleaned.get("mes")

        # Evitar duplicados de DDJJ
        if anio and mes and self.comercio:
            qs = DeclaracionJuradaDrei.objects.filter(comercio=self.comercio, anio=anio, mes=mes)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            
            if qs.exists():
                raise ValidationError(f"Este comercio ya presentó la DDJJ para el período {mes}/{anio}.")
                
        return cleaned