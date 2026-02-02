import sqlite3
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from finanzas.models import Beneficiario

class Command(BaseCommand):
    help = 'Importa personas desde una base de datos SQLite vieja (db_vieja.sqlite3)'

    def handle(self, *args, **kwargs):
        # 1. Conectar a la base vieja
        db_path = os.path.join(settings.BASE_DIR, 'db_vieja.sqlite3')
        
        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f"No encuentro el archivo: {db_path}"))
            self.stdout.write("Asegurate de subir 'db_vieja.sqlite3' a la misma carpeta que manage.py")
            return

        self.stdout.write(self.style.WARNING(f"Leyendo base de datos vieja: {db_path}..."))
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # Para acceder por nombre de columna
        cursor = conn.cursor()

        # 2. Buscar la tabla de personas
        # En el archivo que pasaste se llama 'finanzas_beneficiario'
        try:
            cursor.execute("SELECT * FROM finanzas_beneficiario")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            self.stdout.write(self.style.ERROR("No encontré la tabla 'finanzas_beneficiario' en la base vieja."))
            return

        total = len(rows)
        creados = 0
        existentes = 0
        errores = 0

        self.stdout.write(f"Encontré {total} personas para procesar.")

        # 3. Recorrer e importar
        for row in rows:
            try:
                dni_raw = str(row['dni']).strip()
                
                # Verificar si ya existe en la base NUEVA
                if Beneficiario.objects.filter(dni=dni_raw).exists():
                    existentes += 1
                    # Opcional: imprimir los que ya están
                    # self.stdout.write(f"Saltando DNI {dni_raw} (ya existe)")
                    continue

                # Mapear datos (Cuidado: NO importamos IDs foráneos como sector_laboral para no romper)
                Beneficiario.objects.create(
                    nombre=row['nombre'],
                    apellido=row['apellido'],
                    dni=dni_raw,
                    direccion=row['direccion'],
                    barrio=row['barrio'],
                    telefono=row['telefono'] or "",
                    # Datos sociales
                    notas=row['notas'] or "",
                    activo=bool(row['activo']),
                    detalle_servicios=row['detalle_servicios'] or "",
                    paga_servicios=bool(row['paga_servicios']),
                    tipo_vinculo=row['tipo_vinculo'] or "NINGUNO",
                    beneficio_detalle=row['beneficio_detalle'] or "",
                    beneficio_organismo=row['beneficio_organismo'] or "",
                    beneficio_monto_aprox=row['beneficio_monto_aprox'] or 0,
                    percibe_beneficio=bool(row['percibe_beneficio']),
                    # Forzamos sector laboral nulo para evitar error de integridad
                    sector_laboral=None 
                )
                creados += 1
                
                # Barra de progreso simple
                if creados % 50 == 0:
                    self.stdout.write(f"Procesados: {creados}...")

            except Exception as e:
                errores += 1
                self.stdout.write(self.style.ERROR(f"Error importando DNI {row['dni']}: {e}"))

        conn.close()

        # 4. Resumen final
        self.stdout.write(self.style.SUCCESS('----------------------------------'))
        self.stdout.write(self.style.SUCCESS(f'IMPORTACIÓN FINALIZADA'))
        self.stdout.write(self.style.SUCCESS(f'✅ Nuevos creados: {creados}'))
        self.stdout.write(self.style.WARNING(f'⏭️ Ya existían (saltados): {existentes}'))
        if errores > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errores: {errores}'))
        self.stdout.write(self.style.SUCCESS('----------------------------------'))