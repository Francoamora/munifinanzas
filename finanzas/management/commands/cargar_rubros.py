import csv
from django.core.management.base import BaseCommand
from finanzas.models import RubroDrei

class Command(BaseCommand):
    help = 'Carga el nomenclador de rubros DReI desde el archivo oficial AFIP_F883.txt'

    def add_arguments(self, parser):
        parser.add_argument('archivo_txt', type=str, help='Ruta al archivo TXT/CSV con los rubros')

    def handle(self, *args, **kwargs):
        ruta_txt = kwargs['archivo_txt']
        
        try:
            # Usamos encoding utf-8-sig por si el archivo viene con caracteres especiales de Windows
            with open(ruta_txt, mode='r', encoding='utf-8-sig') as file:
                reader = csv.reader(file, delimiter=';') 
                
                # Saltamos la primera fila (Cabeceras: COD_ACTIVIDAD; DESC_ACTIVIDAD; DESCL_ACTIVIDA)
                next(reader, None) 
                
                creados = 0
                actualizados = 0
                
                for row in reader:
                    # Verificamos que la fila tenga al menos las columnas necesarias
                    if len(row) >= 2:
                        codigo = row[0].strip()
                        
                        # Usamos la descripción larga (columna 3) si existe, sino la corta (columna 2)
                        if len(row) >= 3 and row[2].strip():
                            descripcion = row[2].strip()
                        else:
                            descripcion = row[1].strip()
                        
                        if codigo and descripcion:
                            # Truncamos a 255 caracteres para que no explote el modelo de Django
                            descripcion_truncada = descripcion[:255]
                            
                            # get_or_create busca por código, si no existe lo crea
                            obj, created = RubroDrei.objects.get_or_create(
                                codigo=codigo,
                                defaults={
                                    'descripcion': descripcion_truncada,
                                    'alicuota': 0.00000, # 0% por defecto inicial
                                    'minimo_mensual': 0.00 # $0 mínimo inicial
                                }
                            )
                            if created:
                                creados += 1
                            else:
                                actualizados += 1
                                
            self.stdout.write(self.style.SUCCESS(f'¡Inyección Exitosa! Se cargaron {creados} rubros nuevos y se omitieron/actualizaron {actualizados} existentes.'))
            
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Error Fatal: No se encontró el archivo en la ruta -> {ruta_txt}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error inesperado: {str(e)}'))