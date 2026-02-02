import csv
import os
from decimal import Decimal
from datetime import datetime, date
from django.core.management.base import BaseCommand
from django.conf import settings
from finanzas.models import Movimiento, Cuenta, Categoria

class Command(BaseCommand):
    help = 'Importa SOLO INGRESOS desde el resumen de cuenta del Banco (CSV)'

    def add_arguments(self, parser):
        parser.add_argument('archivo', type=str, help='Nombre del archivo CSV a importar')

    def handle(self, *args, **kwargs):
        archivo_nombre = kwargs['archivo']
        ruta_archivo = os.path.join(settings.BASE_DIR, archivo_nombre)
        
        # 🗓️ FECHA DE CORTE: INICIO DE GESTIÓN
        FECHA_INICIO = date(2025, 12, 10)

        self.stdout.write(self.style.WARNING(f'📂 Iniciando lectura de INGRESOS: {archivo_nombre}'))
        self.stdout.write(f'   📅 Filtrando movimientos a partir del: {FECHA_INICIO.strftime("%d/%m/%Y")}')

        # 1. CUENTA
        numero_cuenta = "527000001803"
        cuenta, _ = Cuenta.objects.get_or_create(
            numero_cuenta=numero_cuenta,
            defaults={'nombre': 'Cuenta Banco Santa Fe', 'tipo': 'BANCO', 'saldo': 0}
        )

        # 2. CATEGORÍA DE INGRESOS AUTOMÁTICOS
        cat_varios_ingreso, _ = Categoria.objects.get_or_create(
            nombre="Ingresos Automáticos (Banco)", 
            defaults={'tipo': 'INGRESO', 'grupo': 'OTROS'}
        )

        total_importados = 0
        total_omitidos_fecha = 0
        total_omitidos_gasto = 0
        total_omitidos_duplicado = 0

        # 3. LEER CSV
        try:
            with open(ruta_archivo, 'r', encoding='utf-8-sig') as csvfile:
                # Buscador de cabecera
                reader_temp = csv.reader(csvfile)
                lineas_a_saltar = 0
                encontrado = False
                for row in reader_temp:
                    if row and len(row) > 3:
                        if row[0].strip() == 'Fecha' and 'Saldo' in row:
                            encontrado = True
                            break
                    lineas_a_saltar += 1
                
                if not encontrado:
                    self.stdout.write(self.style.ERROR('❌ No se encontró la cabecera correcta.'))
                    return

                csvfile.seek(0)
                for _ in range(lineas_a_saltar):
                    next(csvfile)
                
                reader = csv.DictReader(csvfile)

                for fila in reader:
                    # Parsear Fecha
                    fecha_str = fila.get('Fecha', '').strip()
                    if not fecha_str: continue 
                    try:
                        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y').date()
                    except ValueError:
                        continue

                    # --- FILTRO 1: FECHA (Respetar gestión) ---
                    if fecha_obj < FECHA_INICIO:
                        total_omitidos_fecha += 1
                        continue

                    # Parsear Montos
                    credito_str = fila.get('Crédito') or fila.get('Credito') or ''
                    concepto = fila.get('Concepto', 'Movimiento Bancario').strip()

                    # --- FILTRO 2: SOLO INGRESOS ---
                    # Si no hay valor en "Crédito", es un Gasto (o nulo). Lo saltamos.
                    if not credito_str:
                        total_omitidos_gasto += 1
                        continue

                    def limpiar_moneda(valor):
                        if not valor: return Decimal(0)
                        val = valor.replace('$', '').strip()
                        val = val.replace('.', '') # Chau miles
                        val = val.replace(',', '.') # Decimales
                        return Decimal(val)

                    monto = limpiar_moneda(credito_str)
                    if monto == 0: continue

                    # 4. EVITAR DUPLICADOS
                    existe = Movimiento.objects.filter(
                        fecha_operacion=fecha_obj,
                        monto=monto,
                        tipo=Movimiento.TIPO_INGRESO,
                        descripcion=concepto[:255]
                    ).exists()

                    if existe:
                        total_omitidos_duplicado += 1
                    else:
                        # 5. CREAR SOLO EL INGRESO
                        Movimiento.objects.create(
                            fecha_operacion=fecha_obj,
                            tipo=Movimiento.TIPO_INGRESO,
                            monto=monto,
                            descripcion=concepto[:255],
                            categoria=cat_varios_ingreso,
                            cuenta_destino=cuenta, # La plata entra acá
                            cuenta_destino_texto=cuenta.nombre,
                            estado=Movimiento.ESTADO_APROBADO,
                            creado_por_id=1 
                        )
                        total_importados += 1
                        self.stdout.write(f"   ✅ {fecha_str} | +${monto} | {concepto[:30]}...")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
            return

        self.stdout.write(self.style.SUCCESS(f'\n✨ IMPORTACIÓN INTELIGENTE COMPLETADA'))
        self.stdout.write(f'   📥 Ingresos Cargados: {total_importados}')
        self.stdout.write(f'   📅 Omitidos (Gestión anterior): {total_omitidos_fecha}')
        self.stdout.write(f'   📤 Gastos Ignorados (Manual): {total_omitidos_gasto}')
        self.stdout.write(f'   ♻️  Duplicados Ignorados: {total_omitidos_duplicado}')