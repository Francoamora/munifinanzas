from django import forms
from .models import Insumo, MovimientoStock, Prestamo
from finanzas.models import Beneficiario

class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = ['nombre', 'categoria', 'codigo', 'unidad', 'stock_actual', 'stock_minimo', 'es_herramienta', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'unidad': forms.Select(attrs={'class': 'form-select'}),
            'stock_actual': forms.NumberInput(attrs={'class': 'form-control'}),
            'stock_minimo': forms.NumberInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'es_herramienta': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class MovimientoStockForm(forms.ModelForm):
    """
    Formulario para movimientos MANUALES (Compras, Consumo, Ajustes).
    BLINDADO: No permite seleccionar Préstamo/Devolución para evitar errores de consistencia.
    """
    class Meta:
        model = MovimientoStock
        fields = ['insumo', 'tipo', 'cantidad', 'referencia']
        widgets = {
            'insumo': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
            'referencia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Compra mensual o Reparación Plaza'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 🔒 BLINDAJE DE SEGURIDAD
        # Redefinimos las opciones para ocultar Préstamo y Devolución.
        # Esas operaciones deben hacerse OBLIGATORIAMENTE desde el módulo de Préstamos.
        OPCIONES_PERMITIDAS = [
            ('ENTRADA', '🟢 Entrada / Compra'),
            ('SALIDA', '🔴 Salida / Consumo Final'),
            ('AJUSTE', '⚖️ Ajuste Inventario'),
        ]
        self.fields['tipo'].choices = OPCIONES_PERMITIDAS

class PrestamoForm(forms.ModelForm):
    """
    Formulario exclusivo para el circuito de PAÑOL (Salida con devolución esperada).
    """
    responsable = forms.ModelChoiceField(
        queryset=Beneficiario.objects.filter(activo=True).order_by('apellido'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Persona responsable de la devolución."
    )

    class Meta:
        model = Prestamo
        fields = ['insumo', 'responsable', 'cantidad', 'observaciones_salida']
        widgets = {
            'insumo': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
            'observaciones_salida': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Estado de la herramienta (ej: Nueva, Usada, Sin mango...)'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo permitir prestar cosas marcadas como "Es Herramienta" en la base de datos
        self.fields['insumo'].queryset = Insumo.objects.filter(es_herramienta=True)