from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.forms import inlineformset_factory

from .models import (
    # Núcleo contable / social
    Movimiento,
    Beneficiario,
    ProgramaAyuda,
    Area,
    Categoria,
    # Atenciones sociales
    Atencion,
    # Órdenes de pago
    OrdenPago,
    OrdenPagoLinea,
    # Órdenes de compra
    OrdenCompra,
    OrdenCompraLinea,
    FacturaOC,
    # Flota / vehículos
    Vehiculo,
    ViajeVehiculo,
    ViajeVehiculoTramo,
    # Órdenes de trabajo
    OrdenTrabajo,
    OrdenTrabajoMaterial,
    AdjuntoOrdenTrabajo,
)


# =====================================================
#   CAMPOS COMPARTIDOS
# =====================================================

class MontoDecimalField(forms.DecimalField):
    """
    Campo decimal que acepta montos con:
      - puntos como separador de miles (50.000 -> 50000)
      - coma como separador decimal (50.000,50 -> 50000.50)

    Ejemplos aceptados:
      "50000"
      "50.000"
      "50.000,00"
      "1.234.567,89"

    Mejora: si NO hay coma, no tocamos los puntos (para no romper "1234.56").
    """

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return super().to_python(value)

            if "," in value and "." in value:
                # Formato tipo 1.234.567,89
                value = value.replace(".", "").replace(",", ".")
            elif "," in value:
                # Formato tipo 1234,56
                value = value.replace(",", ".")
            # Si solo hay ".", lo dejamos como está (decimal clásico en Python)

        return super().to_python(value)


# =====================================================
#   FORMULARIO MOVIMIENTO
# =====================================================

class MovimientoForm(forms.ModelForm):
    """
    Formulario principal de Movimiento.

    Incluye:
    - Campos del modelo Movimiento.
    - Campos extras para completar/actualizar datos de Beneficiario
      (beneficiario_direccion / beneficiario_barrio).
    """

    fecha_operacion = forms.DateField(
        label="Fecha de operación",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    # Usamos el campo inteligente para que acepte 50.000 y 50.000,00
    monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "class": "form-control",
            }
        ),
    )

    # Campos extra para censo de personas (no están en Movimiento, pero sí en Beneficiario)
    beneficiario_direccion = forms.CharField(
        label="Domicilio beneficiario",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Calle, número, etc.",
            }
        ),
    )
    beneficiario_barrio = forms.CharField(
        label="Barrio beneficiario",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Barrio / zona",
            }
        ),
    )

    # Campos que NO se pueden tocar cuando el movimiento está aprobado/rechazado
    CAMPOS_BLOQUEADOS_EN_APROBADO = (
        "tipo",
        "fecha_operacion",
        "monto",
        "cuenta_origen_texto",
        "cuenta_destino_texto",
    )

    class Meta:
        model = Movimiento
        fields = [
            # Bloque A: generales
            "tipo",
            "fecha_operacion",
            "monto",
            # Bloque C: cuentas (texto)
            "cuenta_origen_texto",
            "cuenta_destino_texto",
            # Bloque B: clasificación
            "categoria",
            "area",
            # Bloque D: proveedor
            "proveedor_cuit",
            "proveedor_nombre",
            # Bloque E: beneficiario (parte modelo)
            "beneficiario_dni",
            "beneficiario_nombre",
            "tipo_pago_persona",
            # Bloque F: programa ayuda
            "programa_ayuda",
            "programa_ayuda_texto",
            # Bloque G: vehículo / combustible
            "vehiculo",
            "vehiculo_texto",
            "litros",
            "precio_unitario",
            "tipo_combustible",
            # Bloque H: detalle
            "descripcion",
            "observaciones",
        ]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "cuenta_origen_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Caja chica DS",
                }
            ),
            "cuenta_destino_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Solo si es transferencia",
                }
            ),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "proveedor_cuit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "CUIT (opcional)"}
            ),
            "proveedor_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre proveedor (se guarda para reusar)",
                }
            ),
            "beneficiario_dni": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "DNI (opcional)"}
            ),
            "beneficiario_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre y apellido (para censo de ayudas / trabajos)",
                }
            ),
            "tipo_pago_persona": forms.Select(attrs={"class": "form-select"}),
            "programa_ayuda": forms.Select(attrs={"class": "form-select"}),
            "programa_ayuda_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Plan invierno 2025",
                }
            ),
            "vehiculo": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "vehiculo_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Hilux blanca - PTT123",
                }
            ),
            "litros": forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
            "precio_unitario": forms.NumberInput(
                attrs={"step": "0.01", "class": "form-control"}
            ),
            "tipo_combustible": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Diesel, Nafta Súper",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Descripción corta del movimiento",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={"rows": 3, "class": "form-control"}
            ),
        }
        labels = {
            "tipo_pago_persona": "Tipo de pago a la persona",
            "vehiculo": "Vehículo (flota)",
            "vehiculo_texto": "Vehículo (texto libre)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = getattr(self, "instance", None)

        # Prefijar fecha de operación en hoy para nuevos movimientos (solo cuando no hay POST)
        if (
            (not instance or not instance.pk)
            and not self.data
            and "fecha_operacion" in self.fields
            and not self.initial.get("fecha_operacion")
        ):
            self.initial["fecha_operacion"] = timezone.now().date()

        # Si el movimiento ya tiene beneficiario, precargar domicilio/barrio en GET
        beneficiario = getattr(instance, "beneficiario", None)
        if beneficiario and not self.data:
            if beneficiario.direccion and not self.initial.get("beneficiario_direccion"):
                self.initial["beneficiario_direccion"] = beneficiario.direccion
            if beneficiario.barrio and not self.initial.get("beneficiario_barrio"):
                self.initial["beneficiario_barrio"] = beneficiario.barrio

        # Orden de categorías
        self.fields["categoria"].queryset = Categoria.objects.order_by("nombre")

        # Solo áreas activas
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"

        # Solo programas activos
        self.fields["programa_ayuda"].queryset = (
            ProgramaAyuda.objects.filter(activo=True).order_by("nombre")
        )
        self.fields["programa_ayuda"].empty_label = "---------"

        # Vehículos activos para el FK
        if "vehiculo" in self.fields:
            self.fields["vehiculo"].queryset = Vehiculo.objects.filter(
                activo=True
            ).order_by("patente", "descripcion")
            self.fields["vehiculo"].required = False
            self.fields["vehiculo"].empty_label = "---------"

        # Aplicar modo “núcleo contable bloqueado” para movimientos aprobados / rechazados
        self._aplicar_restricciones_por_estado()

    def _aplicar_restricciones_por_estado(self):
        instance = getattr(self, "instance", None)
        if not instance or not instance.pk:
            return

        esta_aprobado = getattr(instance, "esta_aprobado", False)
        esta_rechazado = getattr(instance, "esta_rechazado", False)

        if not (esta_aprobado or esta_rechazado):
            return

        for name in self.CAMPOS_BLOQUEADOS_EN_APROBADO:
            field = self.fields.get(name)
            if field:
                field.disabled = True
                field.widget.attrs["readonly"] = "readonly"

    def clean(self):
        cleaned_data = super().clean()

        tipo = cleaned_data.get("tipo")
        categoria = cleaned_data.get("categoria")
        tipo_pago_persona = cleaned_data.get("tipo_pago_persona")
        dni = cleaned_data.get("beneficiario_dni")
        nombre = cleaned_data.get("beneficiario_nombre")
        cuenta_origen = cleaned_data.get("cuenta_origen_texto")
        cuenta_destino = cleaned_data.get("cuenta_destino_texto")

        errors = {}

        # Coherencia tipo ↔ categoría (si el helper existe en el modelo)
        if tipo and categoria and hasattr(categoria, "aplica_a_tipo_movimiento"):
            if not categoria.aplica_a_tipo_movimiento(tipo):
                errors["categoria"] = (
                    "La categoría seleccionada no es compatible con el tipo de movimiento."
                )

        # Reglas mínimas para transferencias
        if tipo == Movimiento.TIPO_TRANSFERENCIA:
            if not cuenta_origen or not cuenta_origen.strip():
                errors["cuenta_origen_texto"] = (
                    "Para una transferencia indicá la cuenta de origen."
                )
            if not cuenta_destino or not cuenta_destino.strip():
                errors["cuenta_destino_texto"] = (
                    "Para una transferencia indicá la cuenta de destino."
                )

        # Si no es un pago a persona, no aplicamos validaciones extra de sueldo/changa
        if (
            not tipo_pago_persona
            or tipo_pago_persona == Movimiento.PAGO_PERSONA_NINGUNO
        ):
            if errors:
                raise ValidationError(errors)
            return cleaned_data

        # Validaciones específicas para sueldo / changa
        if tipo != Movimiento.TIPO_GASTO:
            errors["tipo"] = (
                "Para marcar sueldo o changa/jornal, el movimiento debe ser un gasto."
            )

        if categoria and not getattr(categoria, "es_personal", False):
            errors["categoria"] = (
                "La categoría seleccionada no está marcada como 'personal'. "
                "Revisá el maestro de categorías o elegí otra categoría adecuada."
            )

        if not dni and not nombre:
            msg = (
                "Si marcás sueldo o changa/jornal, completá al menos el DNI "
                "o el apellido y nombre de la persona."
            )
            errors["beneficiario_dni"] = msg
            errors["beneficiario_nombre"] = msg

        if errors:
            raise ValidationError(errors)

        return cleaned_data


# =====================================================
#   ÓRDENES DE PAGO
# =====================================================

class OrdenPagoForm(forms.ModelForm):
    fecha_orden = forms.DateField(
        label="Fecha de orden",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    factura_fecha = forms.DateField(
        label="Fecha de factura",
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    factura_monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Monto facturado (opcional)",
            }
        ),
    )

    class Meta:
        model = OrdenPago
        fields = [
            "numero",
            "fecha_orden",
            "proveedor",
            "proveedor_nombre",
            "proveedor_cuit",
            "area",
            "condicion_pago",
            "medio_pago_previsto",
            "observaciones",
            "factura_tipo",
            "factura_numero",
            "factura_fecha",
            "factura_monto",
        ]
        widgets = {
            "numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: OP-0001/2025",
                }
            ),
            "proveedor": forms.Select(attrs={"class": "form-select"}),
            "proveedor_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre proveedor (para impresión)",
                }
            ),
            "proveedor_cuit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "CUIT (opcional)"}
            ),
            "area": forms.Select(attrs={"class": "form-select"}),
            "condicion_pago": forms.Select(attrs={"class": "form-select"}),
            "medio_pago_previsto": forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Notas internas de la orden",
                }
            ),
            "factura_tipo": forms.Select(attrs={"class": "form-select"}),
            "factura_numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Número de factura (opcional)",
                }
            ),
        }
        labels = {
            "numero": "Número de orden",
            "proveedor": "Proveedor (maestro)",
            "proveedor_nombre": "Proveedor (texto en orden)",
            "proveedor_cuit": "CUIT proveedor",
            "area": "Área que solicita / imputa",
            "condicion_pago": "Condición de pago",
            "medio_pago_previsto": "Medio de pago previsto",
            "observaciones": "Observaciones",
            "factura_tipo": "Tipo de comprobante",
            "factura_numero": "Número de factura",
            "factura_monto": "Monto de factura",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fecha por defecto = hoy (solo en alta / GET)
        if not self.instance.pk and not self.data and "fecha_orden" in self.fields:
            self.initial.setdefault("fecha_orden", timezone.now().date())

        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"

        # Proveedor activo (usamos el modelo remoto del FK de OrdenPago)
        proveedor_model = OrdenPago._meta.get_field("proveedor").remote_field.model
        self.fields["proveedor"].queryset = proveedor_model.objects.filter(
            activo=True
        ).order_by("nombre")
        self.fields["proveedor"].empty_label = "---------"

        # Placeholders amigables en selects (a nivel de widget/UX, no de lógica)
        self.fields["condicion_pago"].empty_label = "---------"
        self.fields["medio_pago_previsto"].empty_label = "---------"
        self.fields["factura_tipo"].empty_label = "---------"

    def clean(self):
        cleaned_data = super().clean()

        factura_tipo = cleaned_data.get("factura_tipo")
        factura_numero = cleaned_data.get("factura_numero")
        factura_monto = cleaned_data.get("factura_monto")
        factura_fecha = cleaned_data.get("factura_fecha")

        # Si hay datos de factura, pedimos al menos tipo
        if (factura_numero or factura_monto or factura_fecha) and not factura_tipo:
            self.add_error("factura_tipo", "Seleccioná el tipo de comprobante.")

        return cleaned_data


class OrdenPagoLineaForm(forms.ModelForm):
    # Campo de monto con soporte para puntos de miles y coma decimal
    monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-sm text-end",
                "step": "0.01",
            }
        ),
    )

    class Meta:
        model = OrdenPagoLinea
        fields = ["categoria", "area", "descripcion", "monto"]
        widgets = {
            "categoria": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "area": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Detalle del gasto / concepto",
                }
            ),
        }
        labels = {
            "descripcion": "Descripción",
            "monto": "Monto",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.order_by("nombre")
        self.fields["categoria"].empty_label = "---------"
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"  # opcional

    def clean(self):
        cleaned_data = super().clean()
        categoria = cleaned_data.get("categoria")
        area = cleaned_data.get("area")
        descripcion = cleaned_data.get("descripcion")
        monto = cleaned_data.get("monto")

        # Form totalmente vacío → lo ignora el formset
        if not (categoria or area or descripcion or monto):
            return cleaned_data

        if monto is not None and monto <= 0:
            self.add_error("monto", "El monto debe ser mayor que cero.")

        return cleaned_data


OrdenPagoLineaFormSet = inlineformset_factory(
    OrdenPago,
    OrdenPagoLinea,
    form=OrdenPagoLineaForm,
    extra=3,
    can_delete=True,
)


# =====================================================
#   BENEFICIARIO (CENSO)
# =====================================================

class BeneficiarioForm(forms.ModelForm):
    """Formulario para editar datos de la persona / beneficiario (censo)."""

    class Meta:
        model = Beneficiario
        fields = [
            "apellido",
            "nombre",
            "dni",
            "direccion",
            "barrio",
            "telefono",
            "paga_servicios",
            "detalle_servicios",
            "tipo_vinculo",
            "sector_laboral",
            # Beneficios sociales / pensión
            "percibe_beneficio",
            "beneficio_detalle",
            "beneficio_organismo",
            "beneficio_monto_aprox",
            # Notas y estado
            "notas",
            "activo",
        ]
        widgets = {
            "apellido": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Apellido"}
            ),
            "nombre": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nombre"}
            ),
            "dni": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "DNI"}
            ),
            "direccion": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Domicilio"}
            ),
            "barrio": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Barrio / zona"}
            ),
            "telefono": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Teléfono"}
            ),
            "paga_servicios": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "detalle_servicios": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Agua potable – Medidor 123, Lote 5 Manzana 3",
                }
            ),
            "tipo_vinculo": forms.Select(
                attrs={"class": "form-select"}
            ),
            "sector_laboral": forms.Select(
                attrs={"class": "form-select"}
            ),
            # Beneficios sociales
            "percibe_beneficio": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "beneficio_detalle": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: AUH, jubilación mínima, pensión no contributiva",
                }
            ),
            "beneficio_organismo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: ANSES, PAMI, Provincia, Nación",
                }
            ),
            "beneficio_monto_aprox": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Monto mensual aprox. (opcional)",
                }
            ),
            "notas": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Notas"}
            ),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "direccion": "Domicilio",
            "paga_servicios": "Paga servicios a la comuna",
            "detalle_servicios": "Detalle de servicios / referencia",
            "tipo_vinculo": "Tipo de vínculo laboral",
            "sector_laboral": "Área / sector en la comuna",
            # Beneficios
            "percibe_beneficio": "Percibe pensión o beneficio social",
            "beneficio_detalle": "Detalle del beneficio",
            "beneficio_organismo": "Organismo / programa",
            "beneficio_monto_aprox": "Monto aproximado mensual",
        }


# =====================================================
#   ATENCIONES SOCIALES
# =====================================================

class AtencionForm(forms.ModelForm):
    """
    Registro de ATENCIONES SOCIALES (módulo social, sin plata):

    - Atención a X persona (del censo o por texto)
    - Qué vino a pedir / plantear
    - Qué se hizo / qué quedó pendiente

    La fecha/hora de la atención se setea automáticamente.
    """

    class Meta:
        model = Atencion
        fields = [
            "fecha_atencion",
            "persona",
            "persona_nombre",
            "persona_dni",
            "persona_barrio",
            "motivo_principal",
            "descripcion",
            "canal",
            "estado",
            "prioridad",
            "requiere_seguimiento",
            "tarea_seguimiento",
            "area",
            "origen_interno",
            "resultado",
        ]
        widgets = {
            "persona": forms.Select(attrs={"class": "form-select"}),
            "persona_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre y apellido (si no está en el censo)",
                }
            ),
            "persona_dni": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "DNI (si no está en el censo)",
                }
            ),
            "persona_barrio": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Barrio / zona para ubicar a la familia",
                }
            ),
            "motivo_principal": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Qué vino a pedir / cuál es la situación",
                }
            ),
            "canal": forms.Select(attrs={"class": "form-select"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "requiere_seguimiento": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "tarea_seguimiento": forms.Select(attrs={"class": "form-select"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "origen_interno": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Derivado por escuela, CAPS, juzgado, etc.",
                }
            ),
            "resultado": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Qué se hizo / acordó / resolvió en la atención",
                }
            ),
        }
        labels = {
            "persona": "Persona (censo)",
            "persona_nombre": "Nombre y apellido",
            "persona_dni": "DNI",
            "persona_barrio": "Barrio / referencia",
            "motivo_principal": "Motivo principal",
            "descripcion": "Detalle de la situación / pedido",
            "canal": "Canal de ingreso",
            "estado": "Estado de la atención",
            "prioridad": "Prioridad",
            "requiere_seguimiento": "¿Requiere seguimiento?",
            "tarea_seguimiento": "Tarea asociada (agenda)",
            "area": "Área responsable",
            "origen_interno": "Origen interno / externo",
            "resultado": "Resultado / acciones realizadas",
        }

    def __init__(self, *args, **kwargs):
        # Permite pasar persona_inicial desde la vista (p.ej. ficha de censo)
        persona_inicial = kwargs.pop("persona_inicial", None)
        super().__init__(*args, **kwargs)

        # Guardamos la fecha original para no pisarla en edición
        self._fecha_original = getattr(self.instance, "fecha_atencion", None)

        # La fecha NO la edita el usuario → campo oculto pero con valor válido
        if "fecha_atencion" in self.fields:
            field = self.fields["fecha_atencion"]
            field.required = False
            field.widget = forms.HiddenInput()

            # En alta (sin instancia y sin POST) seteamos un valor inicial correcto
            if not self.instance.pk and not self.data:
                if isinstance(field, forms.DateTimeField):
                    default_fecha = timezone.now()
                else:
                    # Caso típico: DateField → solo fecha
                    default_fecha = timezone.now().date()
                self.initial.setdefault("fecha_atencion", default_fecha)

        # Bootstrapeo de widgets (respetando hidden)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.HiddenInput):
                continue

            existing_classes = widget.attrs.get("class", "")
            classes = existing_classes.split() if existing_classes else []

            if isinstance(widget, forms.Select):
                base_class = "form-select"
            elif isinstance(widget, forms.CheckboxInput):
                base_class = "form-check-input"
            elif isinstance(widget, forms.Textarea):
                base_class = "form-control"
                widget.attrs.setdefault("rows", 4)
            else:
                base_class = "form-control"

            if base_class and base_class not in classes:
                classes.append(base_class)
                widget.attrs["class"] = " ".join(classes)

        # Personas activas del censo
        if "persona" in self.fields:
            benef_qs = Beneficiario.objects.filter(activo=True).order_by(
                "apellido",
                "nombre",
            )
            self.fields["persona"].queryset = benef_qs
            self.fields["persona"].empty_label = "---------"

            def _benef_label(persona):
                apellido = (persona.apellido or "").strip()
                nombre = (persona.nombre or "").strip()
                base = f"{apellido} {nombre}".strip() or "(Sin nombre)"
                dni = getattr(persona, "dni", None)
                if dni:
                    return f"{base} – DNI {dni}"
                return base

            self.fields["persona"].label_from_instance = _benef_label

            # Preseleccionar persona inicial si viene desde la ficha
            if persona_inicial and not self.instance.pk and not self.data:
                try:
                    if hasattr(persona_inicial, "pk"):
                        pk = persona_inicial.pk
                    else:
                        pk = int(persona_inicial)
                    benef_qs.get(pk=pk)
                    self.initial.setdefault("persona", pk)
                except (Beneficiario.DoesNotExist, ValueError, TypeError):
                    pass

        # Áreas activas
        if "area" in self.fields:
            self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
                "nombre"
            )
            self.fields["area"].empty_label = "---------"

        # Tarea de seguimiento opcional
        if "tarea_seguimiento" in self.fields:
            self.fields["tarea_seguimiento"].required = False
            if hasattr(self.fields["tarea_seguimiento"], "empty_label"):
                self.fields["tarea_seguimiento"].empty_label = "---------"

    def clean(self):
        cleaned_data = super().clean()

        persona = cleaned_data.get("persona")
        persona_nombre = cleaned_data.get("persona_nombre")
        persona_dni = cleaned_data.get("persona_dni")
        persona_barrio = cleaned_data.get("persona_barrio")

        # Tiene que haber al menos alguna identificación de la persona
        if not persona and not (persona_nombre or persona_dni or persona_barrio):
            msg = (
                "Cargá la persona desde el censo o completá al menos el nombre "
                "o el DNI."
            )
            raise ValidationError(
                {
                    "persona": msg,
                    "persona_nombre": msg,
                }
            )

        return cleaned_data

    def save(self, commit=True):
        """
        - Garantiza una fecha_atencion válida aunque el campo esté oculto.
        - Copia datos básicos de la persona del censo a los campos de texto.
        """
        instance = super().save(commit=False)

        # 1) Resolver fecha_atencion de forma robusta
        fecha_form = self.cleaned_data.get("fecha_atencion")
        field = self.fields.get("fecha_atencion")

        if fecha_form:
            # Si el form la limpió bien, usamos ese valor
            instance.fecha_atencion = fecha_form
        elif self._fecha_original is not None:
            # En edición, si no vino nada, preservamos la original
            instance.fecha_atencion = self._fecha_original
        else:
            # Alta sin fecha en cleaned_data → seteamos un valor válido
            if isinstance(field, forms.DateTimeField):
                default_fecha = timezone.now()
            else:
                default_fecha = timezone.now().date()
            instance.fecha_atencion = default_fecha

        # 2) Si hay persona del censo, copiamos textos de respaldo
        persona = getattr(instance, "persona", None)
        if persona:
            # Nombre
            if not instance.persona_nombre:
                apellido = (persona.apellido or "").strip()
                nombre = (persona.nombre or "").strip()
                base = f"{apellido}, {nombre}".strip(", ").strip()
                if base:
                    instance.persona_nombre = base

            # DNI
            if not instance.persona_dni and getattr(persona, "dni", None):
                instance.persona_dni = persona.dni

            # Barrio
            if not instance.persona_barrio and getattr(persona, "barrio", None):
                instance.persona_barrio = persona.barrio

        if commit:
            instance.save()
            self.save_m2m()

        return instance



# =====================================================
#   ÓRDENES DE COMPRA
# =====================================================

class OrdenCompraForm(forms.ModelForm):
    """
    Form principal de Orden de Compra.
    Enlazado al template finanzas/orden_compra_form.html
    """

    fecha_oc = forms.DateField(
        label="Fecha OC",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = OrdenCompra
        fields = [
            "serie",
            "numero",
            "fecha_oc",
            "estado",
            "rubro_principal",
            "proveedor",
            "proveedor_nombre",
            "proveedor_cuit",
            "area",
            "observaciones",
        ]
        widgets = {
            "serie": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Número interno de la OC (opcional)",
                }
            ),
            "estado": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "rubro_principal": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "proveedor": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "proveedor_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Texto que se imprime en la OC",
                }
            ),
            "proveedor_cuit": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "CUIT del proveedor (opcional)",
                }
            ),
            "area": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Notas / condiciones particulares de la OC",
                }
            ),
        }
        labels = {
            "numero": "Número de OC",
            "rubro_principal": "Rubro principal",
            "proveedor": "Proveedor (maestro)",
            "proveedor_nombre": "Proveedor (texto en OC)",
            "proveedor_cuit": "CUIT proveedor",
            "area": "Área solicitante",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fecha OC por defecto = hoy (solo en alta / GET)
        if not self.instance.pk and not self.data and "fecha_oc" in self.fields:
            self.initial.setdefault("fecha_oc", timezone.now().date())

        # Solo áreas activas
        if "area" in self.fields:
            self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
                "nombre"
            )
            self.fields["area"].empty_label = "---------"

        # Solo proveedores activos (desde el FK de OrdenCompra)
        if "proveedor" in self.fields:
            proveedor_model = OrdenCompra._meta.get_field("proveedor").remote_field.model
            self.fields["proveedor"].queryset = proveedor_model.objects.filter(
                activo=True
            ).order_by("nombre")
            self.fields["proveedor"].empty_label = "---------"

        # Serie opcional
        if "serie" in self.fields:
            self.fields["serie"].empty_label = "---------" 


class OrdenCompraLineaForm(forms.ModelForm):
    """
    Form de línea de Orden de Compra (detalle de conceptos).
    Se usa en el formset OrdenCompraLineaFormSet.
    """

    monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-sm text-end",
                "step": "0.01",
            }
        ),
    )

    class Meta:
        model = OrdenCompraLinea
        fields = ["categoria", "area", "descripcion", "monto"]
        widgets = {
            "categoria": forms.Select(
                attrs={
                    "class": "form-select form-select-sm",
                }
            ),
            "area": forms.Select(
                attrs={
                    "class": "form-select form-select-sm",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Detalle del bien/servicio contratado",
                }
            ),
        }
        labels = {
            "descripcion": "Descripción",
            "monto": "Monto",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Categorías ordenadas alfabéticamente
        self.fields["categoria"].queryset = Categoria.objects.order_by("nombre")
        self.fields["categoria"].empty_label = "---------"
        # Solo áreas activas
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"  # opcional

    def clean(self):
        cleaned_data = super().clean()
        categoria = cleaned_data.get("categoria")
        area = cleaned_data.get("area")
        descripcion = cleaned_data.get("descripcion")
        monto = cleaned_data.get("monto")

        # Form totalmente vacío → lo ignora el formset
        if not (categoria or area or descripcion or monto):
            return cleaned_data

        if monto is not None and monto <= 0:
            self.add_error("monto", "El monto debe ser mayor que cero.")

        return cleaned_data


OrdenCompraLineaFormSet = inlineformset_factory(
    OrdenCompra,
    OrdenCompraLinea,
    form=OrdenCompraLineaForm,
    extra=1,
    can_delete=True,
)


class FacturaOCForm(forms.ModelForm):
    """
    Formulario para FacturaOC.
    Se piensa para usarse como formset dentro de la OC, por eso NO pedimos 'orden'.
    """

    fecha = forms.DateField(
        label="Fecha del comprobante",
        required=False,
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            },
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    monto = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Monto del comprobante",
            }
        ),
    )

    class Meta:
        model = FacturaOC
        fields = ["tipo", "numero", "fecha", "monto", "observaciones"]
        widgets = {
            "tipo": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Número de factura / ticket",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Notas internas (opcional)",
                }
            ),
        }
        labels = {
            "tipo": "Tipo de comprobante",
            "numero": "Número",
            "monto": "Monto",
            "observaciones": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fecha por defecto = hoy (solo en alta / GET)
        if not self.instance.pk and not self.data and "fecha" in self.fields:
            self.initial.setdefault("fecha", timezone.now().date())


FacturaOCFormSet = inlineformset_factory(
    OrdenCompra,
    FacturaOC,
    form=FacturaOCForm,
    extra=1,
    can_delete=True,
)


# =====================================================
#   FLOTA / VEHÍCULOS / ODÓMETRO
# =====================================================

class VehiculoForm(forms.ModelForm):
    """ABM simple de vehículos, alineado al módulo de flota."""

    class Meta:
        model = Vehiculo
        fields = [
            "patente",
            "descripcion",
            "area",
            "activo",
            "kilometraje_referencia",
            "horometro_referencia",
        ]
        widgets = {
            "patente": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Patente / identificación"}
            ),
            "descripcion": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Descripción corta"}
            ),
            "area": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "kilometraje_referencia": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Ej: 120000"}
            ),
            "horometro_referencia": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.1"}
            ),
        }
        labels = {
            "kilometraje_referencia": "Km referencia (último servicio / alta)",
            "horometro_referencia": "Horómetro referencia",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------" 


class ViajeVehiculoForm(forms.ModelForm):
    """
    Módulo ODÓMETRO PRO:
    - Vehículo, área, chofer
    - Km y horómetro
    - Beneficiarios trasladados (censo)
    - M2M híbrido con movimientos de combustible (sugerido, pero editable).

    Mejora Fase 2:
    - Permite recibir un beneficiario inicial para preseleccionarlo como
      trasladado cuando se abre el form desde la ficha de persona.
    """

    fecha_salida = forms.DateField(
        label="Fecha de salida",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"},
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )
    fecha_regreso = forms.DateField(
        label="Fecha de regreso",
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"},
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    # Campo redefinido para poder controlar bien las etiquetas de combustible
    cargas_combustible = forms.ModelMultipleChoiceField(
        label="Cargas de combustible asociadas",
        required=False,
        queryset=Movimiento.objects.none(),
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select",
                "size": 6,
            }
        ),
    )

    class Meta:
        model = ViajeVehiculo
        fields = [
            "vehiculo",
            "area",
            "chofer",
            "chofer_nombre",
            "fecha_salida",
            "hora_salida",
            "fecha_regreso",
            "hora_regreso",
            "odometro_inicial",
            "odometro_final",
            "horometro_inicial",
            "horometro_final",
            "litros_tanque_inicio",
            "litros_tanque_fin",
            "tipo_recorrido",
            "origen",
            "destino",
            "motivo",
            "observaciones",
            "beneficiarios",
            "otros_beneficiarios",
            "cargas_combustible",
            "estado",
        ]
        widgets = {
            "vehiculo": forms.Select(attrs={"class": "form-select"}),
            "area": forms.Select(attrs={"class": "form-select"}),
            "chofer": forms.Select(attrs={"class": "form-select"}),
            "chofer_nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre chofer (si no está en censo)",
                }
            ),
            "hora_salida": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"},
                format="%H:%M",
            ),
            "hora_regreso": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"},
                format="%H:%M",
            ),
            "odometro_inicial": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Km al salir"}
            ),
            "odometro_final": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Km al regresar"}
            ),
            "horometro_inicial": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.1"}
            ),
            "horometro_final": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.1"}
            ),
            "litros_tanque_inicio": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "litros_tanque_fin": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "tipo_recorrido": forms.Select(attrs={"class": "form-select"}),
            "origen": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Tacuarendí – Comuna",
                }
            ),
            "destino": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Reconquista – Banco / AFIP",
                }
            ),
            "motivo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Motivo general del viaje",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "beneficiarios": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                    "size": 6,
                }
            ),
            "otros_beneficiarios": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej: Familia Pérez, delegación club X",
                }
            ),
            "estado": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "beneficiarios": "Personas trasladadas",
            "otros_beneficiarios": "Otras personas / familias (texto)",
            "cargas_combustible": "Cargas de combustible asociadas",
        }

    def __init__(self, *args, **kwargs):
        # Kwarg opcional para cuando abrimos el form desde la ficha de persona
        beneficiario_inicial = kwargs.pop("beneficiario_inicial", None)
        super().__init__(*args, **kwargs)

        # Fecha por defecto hoy en alta
        if not self.instance.pk and not self.data:
            self.initial.setdefault("fecha_salida", timezone.now().date())

        # Vehículos activos
        self.fields["vehiculo"].queryset = Vehiculo.objects.filter(
            activo=True
        ).order_by("patente", "descripcion")
        self.fields["vehiculo"].empty_label = "---------"

        # Áreas activas
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"

        # Chofer / beneficiarios activos
        benef_qs = Beneficiario.objects.filter(activo=True).order_by(
            "apellido",
            "nombre",
        )
        self.fields["chofer"].queryset = benef_qs
        self.fields["chofer"].empty_label = "---------"
        self.fields["beneficiarios"].queryset = benef_qs

        # Etiqueta amigable: Apellido Nombre – DNI 12345678
        def _benef_label(persona):
            apellido = (persona.apellido or "").strip()
            nombre = (persona.nombre or "").strip()
            base = f"{apellido} {nombre}".strip() or "(Sin nombre)"
            dni = getattr(persona, "dni", None)
            if dni:
                return f"{base} – DNI {dni}"
            return base

        self.fields["chofer"].label_from_instance = _benef_label
        self.fields["beneficiarios"].label_from_instance = _benef_label

        # ===============================
        #   Modo híbrido combustible
        # ===============================
        base_qs = Movimiento.objects.filter(
            categoria__es_combustible=True,
            estado=Movimiento.ESTADO_APROBADO,
            tipo=Movimiento.TIPO_GASTO,  # solo gastos de combustible
        ).order_by("-fecha_operacion", "-id")

        instance = getattr(self, "instance", None)
        seleccion_ids = []

        if instance and instance.pk:
            seleccion_ids = list(
                instance.cargas_combustible.values_list("id", flat=True)
            )

            if instance.vehiculo_id:
                base_qs = base_qs.filter(vehiculo_id=instance.vehiculo_id)

            if instance.fecha_salida:
                # Sugerimos por fecha de salida; después se puede abrir rango si hace falta
                base_qs = base_qs.filter(fecha_operacion=instance.fecha_salida)

            if seleccion_ids:
                base_qs = (
                    base_qs
                    | Movimiento.objects.filter(id__in=seleccion_ids)
                ).distinct()

        campo_cargas = self.fields["cargas_combustible"]
        campo_cargas.queryset = base_qs
        campo_cargas.label_from_instance = self._label_movimiento_combustible

        # Preseleccionar beneficiario cuando venimos desde la ficha de persona
        if beneficiario_inicial and "beneficiarios" in self.fields:
            try:
                if hasattr(beneficiario_inicial, "pk"):
                    benef_pk = beneficiario_inicial.pk
                else:
                    benef_pk = int(beneficiario_inicial)
                # Validamos que esté en el queryset activo
                benef_qs.get(pk=benef_pk)
                # Solo si el form está en alta (sin instancia) y no hay POST
                if not self.instance.pk and not self.data:
                    self.initial.setdefault("beneficiarios", [benef_pk])
            except (Beneficiario.DoesNotExist, ValueError, TypeError):
                pass

    def _label_movimiento_combustible(self, mov: Movimiento) -> str:
        """
        Etiqueta amigable para las cargas de combustible:
        Ej: 19/11/2025 · Fiat Uno ABC123 · $15000.00 · Detalle
        """
        partes = []

        fecha = getattr(mov, "fecha_operacion", None)
        if fecha:
            partes.append(fecha.strftime("%d/%m/%Y"))

        vehiculo = getattr(mov, "vehiculo", None)
        if vehiculo:
            partes.append(str(vehiculo))

        monto = getattr(mov, "monto", None)
        if monto is not None:
            partes.append(f"${monto}")

        detalle = (
            getattr(mov, "descripcion", "")
            or getattr(mov, "observaciones", "")
            or ""
        ).strip()
        if detalle:
            partes.append(detalle[:40])

        if not partes:
            return f"Movimiento #{mov.pk}"

        return " · ".join(partes)

    def clean(self):
        cleaned_data = super().clean()

        fecha_salida = cleaned_data.get("fecha_salida")
        fecha_regreso = cleaned_data.get("fecha_regreso")
        odometro_inicial = cleaned_data.get("odometro_inicial")
        odometro_final = cleaned_data.get("odometro_final")
        horometro_inicial = cleaned_data.get("horometro_inicial")
        horometro_final = cleaned_data.get("horometro_final")

        errors = {}

        if fecha_salida and fecha_regreso and fecha_regreso < fecha_salida:
            errors["fecha_regreso"] = (
                "La fecha de regreso no puede ser anterior a la fecha de salida."
            )

        if (
            odometro_inicial is not None
            and odometro_final is not None
            and odometro_final < odometro_inicial
        ):
            errors["odometro_final"] = (
                "El odómetro final no puede ser menor que el odómetro inicial."
            )

        if (
            horometro_inicial is not None
            and horometro_final is not None
            and horometro_final < horometro_inicial
        ):
            errors["horometro_final"] = (
                "El horómetro final no puede ser menor que el horómetro inicial."
            )

        if errors:
            raise ValidationError(errors)

        return cleaned_data


class ViajeVehiculoTramoForm(forms.ModelForm):
    """Tramos internos de un viaje (urbano/ruta, etc.)."""

    class Meta:
        model = ViajeVehiculoTramo
        fields = [
            "orden",
            "origen",
            "destino",
            "hora_salida",
            "hora_llegada",
            "motivo",
            "observaciones",
        ]
        widgets = {
            "orden": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm text-center",
                    "min": 1,
                }
            ),
            "origen": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Origen",
                }
            ),
            "destino": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Destino",
                }
            ),
            "hora_salida": forms.TimeInput(
                attrs={"type": "time", "class": "form-control form-control-sm"},
                format="%H:%M",
            ),
            "hora_llegada": forms.TimeInput(
                attrs={"type": "time", "class": "form-control form-control-sm"},
                format="%H:%M",
            ),
            "motivo": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Motivo / tarea del tramo",
                }
            ),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control form-control-sm",
                    "rows": 2,
                    "placeholder": "Notas (opcional)",
                }
            ),
        }


ViajeVehiculoTramoFormSet = inlineformset_factory(
    ViajeVehiculo,
    ViajeVehiculoTramo,
    form=ViajeVehiculoTramoForm,
    extra=1,
    can_delete=True,
)


# =====================================================
#   ÓRDENES DE TRABAJO
# =====================================================

class OrdenTrabajoForm(forms.ModelForm):
    """
    OT general (no solo mecánica):
    - Permite registrar trabajos a vecinos, instituciones, vehículos, etc.
    - Integra con Movimiento de ingreso (vía botón en la vista).
    """

    fecha_ot = forms.DateField(
        label="Fecha OT",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"},
            format="%Y-%m-%d",
        ),
        input_formats=["%Y-%m-%d"],
    )

    importe_estimado = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Importe estimado (opcional)",
            }
        ),
    )
    importe_final = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Importe final acordado (opcional)",
            }
        ),
    )

    class Meta:
        model = OrdenTrabajo
        fields = [
            "numero",
            "fecha_ot",
            "estado",
            "tipo_trabajo",
            "prioridad",
            "solicitante",
            "solicitante_texto",
            "area",
            "vehiculo",
            "responsable",
            "responsable_texto",
            "descripcion",
            "trabajos_realizados",
            "importe_estimado",
            "importe_final",
            "categoria_ingreso",
            # movimiento_ingreso se maneja desde la vista/botón y no lo mostramos acá
            "observaciones",
        ]
        widgets = {
            "numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Dejar vacío para generar automáticamente "
                        "(ej: OT-0001/2025)"
                    ),
                }
            ),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "tipo_trabajo": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "solicitante": forms.Select(attrs={"class": "form-select"}),
            "solicitante_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Nombre de vecino/a o institución (si no está en censo)"
                    ),
                }
            ),
            "area": forms.Select(attrs={"class": "form-select"}),
            "vehiculo": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.Select(attrs={"class": "form-select"}),
            "responsable_texto": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Responsable (texto libre, opcional)",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Descripción del trabajo solicitado",
                }
            ),
            "trabajos_realizados": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Detalle de trabajos efectivamente realizados",
                }
            ),
            "categoria_ingreso": forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Notas internas",
                }
            ),
        }
        labels = {
            "solicitante": "Solicitante (censo)",
            "solicitante_texto": "Solicitante (texto)",
            "responsable": "Responsable (censo)",
            "responsable_texto": "Responsable (texto)",
            "categoria_ingreso": "Categoría contable del ingreso",
            "prioridad": "Prioridad",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Fecha por defecto hoy
        if not self.instance.pk and not self.data:
            self.initial.setdefault("fecha_ot", timezone.now().date())

        # Censo activos
        benef_qs = Beneficiario.objects.filter(activo=True).order_by(
            "apellido",
            "nombre",
        )
        self.fields["solicitante"].queryset = benef_qs
        self.fields["solicitante"].empty_label = "---------"
        self.fields["responsable"].queryset = benef_qs
        self.fields["responsable"].empty_label = "---------"

        # Etiqueta Apellido Nombre – DNI para solicitante / responsable
        def _benef_label(persona):
            apellido = (persona.apellido or "").strip()
            nombre = (persona.nombre or "").strip()
            base = f"{apellido} {nombre}".strip() or "(Sin nombre)"
            dni = getattr(persona, "dni", None)
            if dni:
                return f"{base} – DNI {dni}"
            return base

        self.fields["solicitante"].label_from_instance = _benef_label
        self.fields["responsable"].label_from_instance = _benef_label

        # Áreas activas
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by(
            "nombre"
        )
        self.fields["area"].empty_label = "---------"

        # Vehículos activos
        self.fields["vehiculo"].queryset = Vehiculo.objects.filter(
            activo=True
        ).order_by("patente", "descripcion")
        self.fields["vehiculo"].empty_label = "---------"

        # Categorías de ingreso
        self.fields["categoria_ingreso"].queryset = Categoria.objects.filter(
            tipo__in=[Categoria.TIPO_INGRESO, Categoria.TIPO_AMBOS]
        ).order_by("nombre")
        self.fields["categoria_ingreso"].empty_label = "---------" 


class OrdenTrabajoMaterialForm(forms.ModelForm):
    """Materiales / insumos usados en una OT (para control interno)."""

    cantidad = MontoDecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-sm text-end",
                "step": "0.01",
            }
        ),
    )
    costo_unitario = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-sm text-end",
                "step": "0.01",
            }
        ),
    )
    costo_total = MontoDecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-sm text-end",
                "step": "0.01",
                "readonly": "readonly",
            }
        ),
    )

    class Meta:
        model = OrdenTrabajoMaterial
        fields = ["descripcion", "cantidad", "unidad", "costo_unitario", "costo_total"]
        widgets = {
            "descripcion": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Descripción del material / insumo",
                }
            ),
            "unidad": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Ej: unidad, m, m2, litros, kg",
                }
            ),
        }
        labels = {
            "descripcion": "Descripción",
            "cantidad": "Cant.",
            "unidad": "Unidad",
            "costo_unitario": "Costo unit.",
            "costo_total": "Costo total",
        }

    def clean(self):
        cleaned_data = super().clean()
        descripcion = cleaned_data.get("descripcion")
        cantidad = cleaned_data.get("cantidad")
        unidad = cleaned_data.get("unidad")
        costo_unitario = cleaned_data.get("costo_unitario")

        # Form completamente vacío → lo ignora el formset
        if not (descripcion or cantidad or unidad or costo_unitario):
            return cleaned_data

        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que cero.")

        if cantidad is not None and costo_unitario is not None:
            cleaned_data["costo_total"] = cantidad * costo_unitario

        return cleaned_data


OrdenTrabajoMaterialFormSet = inlineformset_factory(
    OrdenTrabajo,
    OrdenTrabajoMaterial,
    form=OrdenTrabajoMaterialForm,
    extra=1,
    can_delete=True,
)


class AdjuntoOrdenTrabajoForm(forms.ModelForm):
    """Adjuntos de OT (fotos, comprobantes, etc.)."""

    class Meta:
        model = AdjuntoOrdenTrabajo
        fields = ["archivo", "descripcion"]
        widgets = {
            "archivo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Descripción / contexto del archivo (opcional)",
                }
            ),
        }
        labels = {
            "archivo": "Archivo",
            "descripcion": "Descripción",
        }
