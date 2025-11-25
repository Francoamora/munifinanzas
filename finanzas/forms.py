from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.forms import inlineformset_factory

from .models import (
    Movimiento,
    Beneficiario,
    ProgramaAyuda,
    Area,
    Categoria,
    OrdenPago,
    OrdenPagoLinea,
)


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
            "monto": forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = getattr(self, "instance", None)

        # Prefijar fecha de operación en hoy para nuevos movimientos (solo cuando no hay POST)
        if (
            not instance or not instance.pk
        ) and not self.data and "fecha_operacion" in self.fields and not self.initial.get(
            "fecha_operacion"
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
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by("nombre")
        self.fields["area"].empty_label = "---------"

        # Solo programas activos
        self.fields["programa_ayuda"].queryset = (
            ProgramaAyuda.objects.filter(activo=True).order_by("nombre")
        )
        self.fields["programa_ayuda"].empty_label = "---------"

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

        if (
            not tipo_pago_persona
            or tipo_pago_persona == Movimiento.PAGO_PERSONA_NINGUNO
        ):
            return cleaned_data

        errors = {}

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


# =========================
#   FORMULARIOS ORDEN PAGO
# =========================

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
            "factura_monto": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Monto facturado (opcional)",
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

        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by("nombre")
        self.fields["area"].empty_label = "---------"

        # Proveedor activo (usamos el modelo remoto del FK de OrdenPago)
        proveedor_model = OrdenPago._meta.get_field("proveedor").remote_field.model
        self.fields["proveedor"].queryset = proveedor_model.objects.filter(
            activo=True
        ).order_by("nombre")
        self.fields["proveedor"].empty_label = "---------"

        self.fields["condicion_pago"].empty_label = "---------"
        self.fields["medio_pago_previsto"].empty_label = "---------"
        self.fields["factura_tipo"].empty_label = "---------"


class OrdenPagoLineaForm(forms.ModelForm):
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
            "monto": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm text-end",
                    "step": "0.01",
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
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by("nombre")
        self.fields["area"].empty_label = "---------"  # opcional


OrdenPagoLineaFormSet = inlineformset_factory(
    OrdenPago,
    OrdenPagoLinea,
    form=OrdenPagoLineaForm,
    extra=3,
    can_delete=True,
)


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
            # ===== Beneficios sociales / pensión (NUEVO) =====
            "percibe_beneficio",
            "beneficio_detalle",
            "beneficio_organismo",
            "beneficio_monto_aprox",
            # ===== Notas y estado =====
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
