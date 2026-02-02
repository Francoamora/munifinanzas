import re
from django.core.management.base import BaseCommand
from inventario.models import Insumo, CategoriaInsumo, MovimientoStock, Prestamo

class Command(BaseCommand):
    help = 'Limpia la base y carga el stock inicial desde el relevamiento 2025'

    def handle(self, *args, **kwargs):
        # === 1. LIMPIEZA TOTAL PREVIA ===
        self.stdout.write(self.style.WARNING('🧹 Limpiando base de datos de inventario...'))
        
        # Borramos en orden para evitar errores de llave foránea
        Prestamo.objects.all().delete()
        MovimientoStock.objects.all().delete()
        Insumo.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('✅ Base limpia. Iniciando carga...'))

        # === 2. DEFINICIÓN DE CATEGORÍAS ===
        CAT_MAQUINARIA = "Maquinaria y Vehículos"
        CAT_HERRAMIENTAS = "Herramientas Menores"
        CAT_OFICINA = "Oficina y Tecnología"
        CAT_PLOMERIA = "Plomería y Agua"
        CAT_CONSTRUCCION = "Materiales de Construcción"
        CAT_ELECTRICIDAD = "Electricidad"
        CAT_CIC = "Muebles e Instalaciones (CIC)"

        # === 3. DATOS CRUDOS ===
        # Formato: (Categoria, Es Herramienta?, Lista de items)
        datos = [
            # MAQUINARIA
            (CAT_MAQUINARIA, True, """
1 DEUZ 65 taller, predio comunal
1 FIAT 60 con retroexcavadora estado desarmado predio comunal
1 JHON DEERE CON PALA FRONTAL en buen estado, predio comunal
1 MINITRACTOR CORTADORA DE PASTO (taller de villa Ocampo)
1 FIAT 800 (taller de villa Ocampo)
1 CAMION MERCEDES accelo
1 FORD 600 MOTOR PERQUIN CON CAJA VOLCABLE regular estado
1 BEDFORD CON CAJA VOLCABLE (no funciona)
1 CAMION MERCEDES 1114 buen estado regularizar documentación
1 KANGOO RENAULT dominio PFI648 (no funciona)
1 SPRINTER MERCEDES dominio AB3351IQ, predio comunal
1 ACOPLADO (Basurero) predio comuna en mal estado
1 MOTONIVELADORA mal estado convenio validad comercial
1 HIDROELEVADOR sociedad con COMUNA DE SAN ANTONIO buen estado
1 MOTO ZANELLA 110 funcionando edificio comunal
1 DISCO TIRO-EXCENTRICO 20 PLATOS buen estado
1 TANQUE ATMOSFERICO buen estado
1 ACOPLADO TANQUE PARA 8000 LTS DE AGUA buen estado
1 ACOPLADO TANQUE REGADOR regular estado
1 NIVELADORA DE ARRASTRE buen estado
1 CORTADORA DE CESPED A3 buen estado
1 CORTADORA DE CESPED DE ARRASTRE buen estado
2 CARRO DE 2 RUEDAS CON ENGANCHE en regular estado
            """),

            # HERRAMIENTAS MENORES
            (CAT_HERRAMIENTAS, True, """
1 COMPRESOR BTA 100 LITROS
1 TALADRO DE BANCO KLD
1 PIEDRA DE BANCO SHIMURA
5 MOTO GUADAÑAS
1 SOLDADORA BANTAM
1 SOLDADORA LASER
7 EQUIPOS DE LLUVIA
1 AMOLADORA GRANDE FORD CON CAJA (ROTA)
1 JUEGO DE TUBOS BAHCO INCOMPLETO
1 AMOLADORA MAKITA
1 AMOLADORA ELECTO
1 AMOLADORA ARGENTEC
1 SOLDADORA SHIMURA
1 TALADRO PERCUTOR MAKITA
1 TALADRO PERCUTOR STANLEY
1 GRUPO ELECTROGENO GAMA
1 GRUPO ELECTROGENO HONDA
1 KIT AMOLADORA RECTA MARCA BREMEN
1 TALADRO DE MANO BLACK DECKER
1 APAREJO 5 TONELADAS
1 PORTATIL CON CABLE 1,5 MILIMETROS X 5 METROS
1 KIT GOMERIA (destalonodora, 2 barrotas)
1 LLAVE CRUZ
1 PISTOLA PARA LAVAR CON RECIPIENTE BTA
1 MANZO DE FUERZA ENCASTRE 1/2
1 ESPATULAS MANGO
1 PINZA PARA ABRIR SEGUROS
1 DESTORNILLADOR PLANO
1 DESTORNILLADOR PHILLIPS
2 PINZAS
1 ESCUADRA
1 APLICADOR PARA CARTUCHOS DE SILICONA
1 PINZA PERRO
1 JUEGO DE LLAVES COMBINADAS varios numeros
1 JUEGO DE LLAVES TUBOS Y LLAVES COMBINADAS varios numeros
1 TUBO 10 MM 32 ENCASTE 1/2 INCOMPLETO
1 TUBO ENCASTE 1/4 INCOMPLETO
1 LLAVE COMBINADAS DE 8 A 19 mm
1 GRASERA MAREA
1 LLAVE REGULABLE MARCA TAPARI
1 CRIQUET GATO TIPO CARRO 3 TONELADAS
1 AMOLADORA MARCA DEWALT
1 MECHA PARA MADERA Nº 22
2 LLAVES DE CAÑO
5 PALAS DE PUNTAS
5 PALAS ANCHAS
2 PICO
1 SOPLETE GARRAFITA
1 PALA LARGA
3 TENAZAS
3 SIERRAS
1 PARESO
2 PICOLORO
2 ESCALERAS
            """),

            # PLOMERÍA (Mezcla insumos y herramientas)
            (CAT_PLOMERIA, False, """
15 MTS CAÑOS PARA EXTENCION DE RED
3 MANGUITOS n°50,60,75
2 BIDONES
4 LLAVES ESCRUSA 63
5 CAÑOS DEL 55
3 CAÑOS DEL 75
1 CAÑOS DEL 90
15 MTS DE MANGUERA DE 1/2
            """),
            (CAT_PLOMERIA, True, """
1 TANQUE CON TORRE BARRIO CARGADERO DE 10.000 LTS
3 BOMBA FUNCIONANDO 5,5 HP
2 BOMBA FUNCIONANDO 1,5 HP
1 BOMBA FUNCIONANDO 3 HP
4 LLAVES FILLON
            """),

            # OFICINA Y TECNOLOGÍA
            (CAT_OFICINA, True, """
1 MONITOR SAMSUNG
2 MONITORES LG
6 MONITORES HP
1 MONITOR CORADIR
1 CPU CORADIR
4 CPU HP
1 CPU PERFORMANCE
1 CPU SFX
2 IMPRESORA SAMSUNG
4 IMPRESORA EPSON
1 IMPRESORA PHACER
1 FOTOCOPIADORA KONICA MINOLTA
2 ROUTER TP-LINK
4 CAMARAS DE SEGURIDAD
6 ESTABILIZADORES TRV
11 AIRES ACONDICIONADOS SPLIT
1 AIRE ACONDICIONADO DE VENTANA
7 ESCRITOTIOS CON CAJONES
2 ESCRITORIO SIN CAJONES
10 MESAS DE PC
2 ARMARIO BAJO PUERTAS BATIENTES
1 ARMARIO BAJO DE PUERTAS CORREDIZAS
8 ARMARIOS ALTOS DE PUERTAS BATIENTES
1 ARMARIO BIBLIOTECA
1 ARMARIO ARCHIVO PARA CARPETA COLGANTE
2 MOSTRADORES CON CAJONES
1 CONTENDOR PARA GUARDAR ARCHIVOS
1 SILLON EJECUTIVO
5 SILLAS ERGONOMICAS
19 SILLAS FIJAS NEGRAS
1 MESA DE REUNIONES DE 3 METROS DE LARGO
5 TANDEM DE 4 CUERPOS
2 CALCULADORAS ELECTRICAS CASIO
1 CALCULADORA MANUAL
2 CAJONERAS
3 BANQUETERAS
1 ALARMA
1 MESAS PLASTICA
1 HELADERA BRIKET
1 ARMARIO DESPENSERO
1 PAVA ELECTRICA WINCO
10 CAMARAS DE VIGILANCIAS
1 MONITOR DELL
1 CPU DELL
1 TECLADO DELL
1 MOUSE DELL
1 IMPRESORA PERIFERICA EPSON
1 LECTOR ELECTRONICO HONEYWELL
1 CAJA FUERTE AITCG LECTOR ELECTRONICO
            """),

            # CONSTRUCCIÓN Y OBRAS
            (CAT_CONSTRUCCION, True, """
1 HORMIGONERA CON MOTOR 1 HP MARCA DUROL
1 AMOLADORA GRANDE
2 CARRETILLA DE CHAPA
6 BALDES PLASTICO ALBAÑILERIA
2 MARTILLOS
3 PALAS ANCHAS OBRAS
1 CINTA METRICA 50 MTS
1 SIERRA COMPLETA
2 CUCHARAS DE ALBAÑIL
1 PLOMADA
1 CINTA METRICA DE 10 MTS
1 TENAZA OBRAS
1 PALA DE PUNTA OBRAS
2 REGLAS DE 6 MTS C/U DE 10 MM X 0.50
1 FRATACHO
1 GRUPO ELECTROGENO YAMAHA (a reparar)
1 REGLA VIBRADORA CON MOTOR PARA PAVIMENTO
1 GRUPO ELECTROGENO GAMMA 6.500 E
1 ALARGUE DE 15 MTS LARGO MONOFASICO
            """),

            # ELECTRICIDAD
            (CAT_ELECTRICIDAD, False, """
7 MTS DE CABLE TIPO TALLER
1 TERMICA DE 63 AMPERES
5 FOCO VAPOR DE SODIO
1 TERMOCONTRAIBLE DE 4 MM X 1 METRO
4 MORCETOS
            """),
            (CAT_ELECTRICIDAD, True, "1 ARNESES DE SEGURIDAD"),

            # CIC - MUEBLES E INSTALACIONES
            (CAT_CIC, True, """
1 PLAYON POLIDEPORTIVO COMPLETO TERMINADO EN SERVICIO
6 TORRES ILUMINACION DE 7,20 MTS DE ALTURA
2 AIRE ACONDICIONADO PHILCO
1 HELADERA BRIKET CIC
1 CPU PERFORMANCE CIC
2 PAVA ELECTRICA JEFFY LE CHEF
1 TERMOTANQUE FORTTE FIT 60BC
1 COCINA CHEF 600 018027
1 IMPRESORA EPSON (no funciona)
2 TADEM 4 CUERPOS CIC
1 MONITOR LCD MARCA PHILIP
3 ESCRITORIOS CIC 1,50 X 0.80
2 ARMARIOS DE 0.80 X 1.20 X 0.40
1 FREZZER INERLO
1 SPLIT MIDEA
1 SPLIT PHILCO
1 MICROONDAS
20 SILLAS PLASTICAS
2 MESAS REDONDAS
1 BIBLIOTECA CON LIBROS DONADOS
1 CALESITA
1 HAMACA
1 TOBOGAN
15 SILLITAS DE JARDIN
1 TV PLASMA
6 MESITAS
1 ESCRITORIO
            """)
        ]

        total_creados = 0

        # === 4. PROCESAMIENTO ===
        for nombre_cat, es_herramienta, texto_items in datos:
            # Crear Categoría
            categoria, _ = CategoriaInsumo.objects.get_or_create(nombre=nombre_cat)
            
            # Limpiar y separar líneas
            lineas = texto_items.strip().split('\n')
            
            for linea in lineas:
                linea = linea.strip()
                if not linea: continue

                # Regex para separar "10 MARTILLOS" -> 10, "MARTILLOS"
                match = re.match(r'^(\d+)\s+(.+)$', linea)
                
                if match:
                    cantidad = int(match.group(1))
                    resto_nombre = match.group(2).strip()
                    
                    # Heurística para extraer estado/notas del nombre
                    descripcion = ""
                    nombre_final = resto_nombre
                    
                    palabras_clave = ["predio comunal", "taller", "no funciona", "a reparar", "buen estado", "regular estado", "mal estado"]
                    
                    for palabra in palabras_clave:
                        if palabra.lower() in nombre_final.lower():
                            descripcion += f"Nota: {palabra.upper()}. "
                    
                    # Unidad de medida
                    unidad = 'UNIDAD'
                    if 'MTS' in nombre_final.upper() or 'METROS' in nombre_final.upper() or 'CABLE' in nombre_final.upper():
                        unidad = 'MTS'
                    
                    # Crear el Insumo
                    insumo = Insumo.objects.create(
                        nombre=nombre_final[:199],
                        categoria=categoria,
                        stock_actual=cantidad,
                        stock_minimo=1, # Alerta básica
                        unidad=unidad,
                        es_herramienta=es_herramienta,
                        descripcion=descripcion.strip()
                    )

                    # Crear Movimiento Inicial (Para Historial)
                    MovimientoStock.objects.create(
                        insumo=insumo,
                        tipo='ENTRADA',
                        cantidad=cantidad,
                        referencia='Inventario Inicial 2025'
                    )

                    total_creados += 1
                    # Barra de progreso simple en consola
                    if total_creados % 10 == 0:
                        self.stdout.write(f"   Procesados: {total_creados} items...")

        self.stdout.write(self.style.SUCCESS(f'\n✨ ¡ÉXITO! Se cargaron {total_creados} artículos nuevos.'))