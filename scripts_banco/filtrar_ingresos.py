import pandas as pd
import os

# --- CONFIGURACIÓN ---
ARCHIVO_ENTRADA = 'rn.xls - Sheet1.csv'
ARCHIVO_SALIDA = 'ingresos_limpios.csv'

print(f"🚀 INICIANDO MODO EXCEL BINARIO...")

try:
    print(f"📂 Leyendo archivo como Excel (.xls)...")
    
    # 1. LEER COMO EXCEL (Forzamos el motor 'xlrd' para archivos viejos)
    # Aunque se llame .csv, por dentro es un .xls
    df = pd.read_excel(
        ARCHIVO_ENTRADA, 
        skiprows=12,      # Saltamos las cabeceras del banco
        engine='xlrd'     # Motor específico para Excel 97-2003
    )
    
    print(f"✅ Archivo interpretado correctamente.")
    print(f"👀 Columnas detectadas: {list(df.columns)}")

    # 2. FILTRADO (Detectar la columna Crédito)
    # Buscamos la columna sin importar mayúsculas o tildes
    col_credito = next((c for c in df.columns if 'credito' in str(c).lower() or 'crédito' in str(c).lower()), None)
    
    if not col_credito:
        raise ValueError(f"No encontré la columna 'Crédito'. Columnas disponibles: {list(df.columns)}")

    print(f"🎯 Columna de ingresos detectada: '{col_credito}'")

    # Filtramos: Que no sea vacía Y que sea mayor a 0
    df_ingresos = df[df[col_credito].notnull()].copy()
    
    # Aseguramos que sea numérico
    df_ingresos[col_credito] = pd.to_numeric(df_ingresos[col_credito], errors='coerce')
    df_ingresos = df_ingresos[df_ingresos[col_credito] > 0]

    # 3. GUARDAR (Ahora sí como CSV limpio)
    # Seleccionamos columnas útiles si existen
    cols_posibles = ['Fecha', 'Concepto', col_credito, 'Saldo', 'CUIT Transferencia']
    cols_finales = [c for c in cols_posibles if c in df_ingresos.columns]
    
    df_ingresos[cols_finales].to_csv(ARCHIVO_SALIDA, index=False, encoding='utf-8-sig', sep=';')

    # RESUMEN
    total = df_ingresos[col_credito].sum()
    print("\n" + "="*40)
    print(f"🏆 ¡LOGRADO!")
    print(f"📄 Movimientos recuperados: {len(df_ingresos)}")
    print(f"💰 Total Ingresos: ${total:,.2f}")
    print(f"💾 Archivo generado: {ARCHIVO_SALIDA}")
    print("="*40)

except ImportError:
    print("❌ ERROR: Te falta instalar la librería 'xlrd'.")
    print("   Ejecutá: pip install xlrd")
except Exception as e:
    print(f"❌ ERROR: {e}")