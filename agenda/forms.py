from django import forms
from django.utils import timezone

from .models import Tarea


class DateInput(forms.DateInput):
    input_type = "date"


class TareaForm(forms.ModelForm):
    class Meta:
        model = Tarea
        fields = [
            # texto
            "titulo",
            "responsable",
            "descripcion",

            # clasificación
            "tipo",
            "prioridad",
            "estado",
            "ambito",

            # fechas clave
            "fecha_vencimiento",
            "fecha_recordatorio",

            # vínculos opcionales
            "orden_pago",
            "movimiento",
            "persona",
            "proveedor",

            # origen (oculto)
            "origen",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={
                "placeholder": "Ej: Presentar balance de noviembre",
                "autocomplete": "off",
            }),
            "responsable": forms.Select(attrs={
                "data-placeholder": "Sin responsable",
            }),
            "descripcion": forms.Textarea(attrs={
                "placeholder": "Detalles, contexto, pasos a seguir…",
                "rows": 5,
            }),

            "tipo": forms.Select(),
            "prioridad": forms.Select(),
            "estado": forms.Select(),
            "ambito": forms.Select(),

            "fecha_vencimiento": DateInput(),
            "fecha_recordatorio": DateInput(),

            "orden_pago": forms.Select(),
            "movimiento": forms.Select(),
            "persona": forms.Select(),
            "proveedor": forms.Select(),

            "origen": forms.HiddenInput(),
        }

    # ==========================================================
    # Inicialización PRO con bootstrap + defaults + validaciones
    # ==========================================================
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ---------- 1) Estilos Bootstrap automáticos ----------
        for name, field in self.fields.items():
            widget = field.widget

            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, DateInput)):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")

            widget.attrs.setdefault("aria-label", field.label or name)

        # ---------- 2) Labels ----------
        self.fields["titulo"].label = "Título"
        self.fields["responsable"].label = "Responsable"
        self.fields["descripcion"].label = "Descripción"

        self.fields["tipo"].label = "Tipo"
        self.fields["prioridad"].label = "Prioridad"
        self.fields["estado"].label = "Estado"
        self.fields["ambito"].label = "Ámbito"

        self.fields["fecha_vencimiento"].label = "Fecha de vencimiento"
        self.fields["fecha_recordatorio"].label = "Recordatorio (opcional)"

        self.fields["orden_pago"].label = "Orden de pago"
        self.fields["movimiento"].label = "Movimiento"
        self.fields["persona"].label = "Persona"
        self.fields["proveedor"].label = "Proveedor"

        # ---------- 3) Help texts ----------
        self.fields["titulo"].help_text = "Sé claro y corto, así se ve prolijo en el listado."
        self.fields["fecha_vencimiento"].help_text = "Es la fecha que define la urgencia en agenda."
        self.fields["fecha_recordatorio"].help_text = "Si lo cargás, la tarea se marca como “por vencer”."

        # ---------- 4) Required ----------
        self.fields["titulo"].required = True
        self.fields["fecha_vencimiento"].required = True

        # ---------- 5) Empty labels ----------
        for fname in ["responsable", "orden_pago", "movimiento", "persona", "proveedor"]:
            if fname in self.fields and isinstance(self.fields[fname].widget, forms.Select):
                self.fields[fname].empty_label = "---------"

        # ---------- 6) Defaults si es nueva ----------
        if not self.instance.pk:
            self.fields["estado"].initial = Tarea.ESTADO_PENDIENTE
            self.fields["prioridad"].initial = Tarea.PRIORIDAD_MEDIA
            self.fields["tipo"].initial = Tarea.TIPO_OTRO
            self.fields["ambito"].initial = Tarea.AMBITO_GENERAL
            self.fields["origen"].initial = Tarea.ORIGEN_MANUAL

        # ---------- 7) Min hoy (por si JS no corre) ----------
        hoy = timezone.localdate()
        for fname in ["fecha_vencimiento", "fecha_recordatorio"]:
            if fname in self.fields:
                self.fields[fname].widget.attrs.setdefault("min", hoy.isoformat())

    # ==========================================================
    # 8) VALIDACIÓN SERVER-SIDE
    # ==========================================================
    def clean(self):
        cleaned = super().clean()

        venc = cleaned.get("fecha_vencimiento")
        rec = cleaned.get("fecha_recordatorio")
        hoy = timezone.localdate()

        if not venc:
            self.add_error("fecha_vencimiento", "El vencimiento es obligatorio.")
            return cleaned

        if venc < hoy:
            self.add_error("fecha_vencimiento", "El vencimiento no puede ser una fecha pasada.")

        if rec:
            if rec < hoy:
                self.add_error("fecha_recordatorio", "El recordatorio no puede ser una fecha pasada.")
            if rec > venc:
                self.add_error("fecha_recordatorio", "El recordatorio no puede ser posterior al vencimiento.")

        return cleaned
