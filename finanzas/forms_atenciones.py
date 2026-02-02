# finanzas/forms_atenciones.py
from django import forms
from django.utils import timezone

from .models import Atencion, Beneficiario, Area


class AtencionForm(forms.ModelForm):
    """
    PRO:
    - Permite vincular a persona (Beneficiario) o cargar datos manuales.
    - Si hay persona, guarda snapshot en persona_nombre/dni/barrio.
    - Si no hay persona, exige persona_nombre.
    """

    next = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Atencion
        fields = [
            "persona",
            "persona_nombre",
            "persona_dni",
            "persona_barrio",
            "area",
            "fecha_atencion",
            "hora_atencion",
            "motivo_principal",
            "canal",
            "prioridad",
            "descripcion",
            "resultado",
            "requiere_seguimiento",
            "estado",
            "origen_interno",
            "next",
        ]
        widgets = {
            "persona": forms.Select(attrs={
                "class": "form-select js-persona-select",
                "data-placeholder": "Buscar persona por apellido, nombre o DNI…",
            }),
            "persona_nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Apellido y nombre (si no está empadronada)"}),
            "persona_dni": forms.TextInput(attrs={"class": "form-control", "placeholder": "DNI (opcional)"}),
            "persona_barrio": forms.TextInput(attrs={"class": "form-control", "placeholder": "Barrio (opcional)"}),

            "area": forms.Select(attrs={"class": "form-select"}),

            "fecha_atencion": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "hora_atencion": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),

            "motivo_principal": forms.Select(attrs={"class": "form-select"}),
            "canal": forms.TextInput(attrs={"class": "form-control", "placeholder": "PRESENCIAL / WHATSAPP / TELÉFONO…"}),
            "prioridad": forms.TextInput(attrs={"class": "form-control", "placeholder": "BAJA / MEDIA / ALTA…"}),

            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "resultado": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "origen_interno": forms.TextInput(attrs={"class": "form-control", "placeholder": "Derivación interna, referencia, etc. (opcional)"}),

            "estado": forms.Select(attrs={"class": "form-select"}),
            "requiere_seguimiento": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Defaults útiles
        if not self.initial.get("fecha_atencion"):
            self.initial["fecha_atencion"] = timezone.now().date()

        # Áreas activas
        self.fields["area"].queryset = Area.objects.filter(activo=True).order_by("nombre")

        # Personas activas (para select tradicional; si usás select2 AJAX igual sirve)
        self.fields["persona"].queryset = Beneficiario.objects.filter(activo=True).order_by("apellido", "nombre")
        self.fields["persona"].required = False

        # Manual también opcional, pero lo validamos en clean()
        self.fields["persona_nombre"].required = False
        self.fields["persona_dni"].required = False
        self.fields["persona_barrio"].required = False

    def clean(self):
        cleaned = super().clean()
        persona = cleaned.get("persona")
        persona_nombre = (cleaned.get("persona_nombre") or "").strip()

        # Regla PRO: tiene que existir persona o, al menos, nombre manual
        if not persona and not persona_nombre:
            self.add_error("persona", "Seleccioná una persona o cargá el nombre manual.")
            self.add_error("persona_nombre", "Este campo es obligatorio si no seleccionás una persona.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Si hay persona, guardamos snapshot
        if obj.persona_id:
            p = obj.persona
            obj.persona_nombre = f"{p.apellido}, {p.nombre}"
            obj.persona_dni = p.dni or ""
            obj.persona_barrio = p.barrio or ""

        if commit:
            obj.save()
            self.save_m2m()

        return obj
