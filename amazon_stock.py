import streamlit as st
import pandas as pd
import numpy as np
import io
import csv
from datetime import datetime
from io import BytesIO

# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER LA PRIMERA LÍNEA)
st.set_page_config(page_title="Amazon Stock Manager Pro", layout="wide")

# --- FUNCIONES DE UTILIDAD ---

def robust_read_csv(uploaded_file):
    """Lectura todoterreno para CSV y TXT (Amazon)"""
    if uploaded_file is None: return None
    
    # Lista de codificaciones a probar (común para errores de 'utf-8')
    encodings = ['utf-8', 'latin-1', 'cp1252']
    
    if uploaded_file.name.endswith('.json'):
        return pd.read_json(uploaded_file)

    for enc in encodings:
        try:
            uploaded_file.seek(0)
            # engine='python' y sep=None detectan automáticamente si es coma o tabulación
            return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc)
        except Exception:
            try:
                # Segundo intento: Ignorando comillas (soluciona error de Amazon)
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=None, engine='python', 
                                   encoding=enc, quoting=csv.QUOTE_NONE)
            except Exception:
                continue
    return None

def convertir_a_excel(uploaded_file):
    """Lógica para el botón de conversión rápida"""
    df_conv = robust_read_csv(uploaded_file)
    if df_conv is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_conv.to_excel(writer, index=False)
            return output.getvalue()
        except Exception as e:
            st.error(f"Error al generar Excel: {e}")
    return None

def formatear_sku_excel(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    val_str = str(val).strip().split('.')[0]
    if val_str.isdigit():
        return val_str.zfill(5)
    return val_str

def procesar_serie_skus(serie):
    return serie.fillna("").apply(formatear_sku_excel)

def cargar_excel_pro(file, skip=0):
    if file is None: return None
    try:
        # Intentamos leer Excel normal
        if file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file, skiprows=skip, dtype=str)
        else:
            # Si se sube un CSV/TXT en los slots de abajo, lo procesamos robustamente
            df = robust_read_csv(file)
        
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

# --- INTERFAZ PRINCIPAL ---

st.title("📦 Amazon Stock Manager & Converter")

# --- BLOQUE 1: CONVERSOR MULTI-ARCHIVO ---
with st.expander("🛠️ CONVERSOR DE FICHEROS A EXCEL (En bloque)", expanded=False):
    st.info("Sube aquí tus listings .txt o stocks .csv para bajarlos como .xlsx")
    archivos_para_convertir = st.file_uploader(
        "Arrastra tus ficheros aquí", 
        type=['csv', 'txt', 'json'], 
        accept_multiple_files=True,
        key="conversor_bloque"
    )
    
    if archivos_para_convertir:
        cols = st.columns(2)
        for i, f in enumerate(archivos_para_convertir):
            with cols[i % 2]:
                excel_data = convertir_a_excel(f)
                if excel_data:
                    nombre_out = f.name.rsplit('.', 1)[0] + ".xlsx"
                    st.download_button(
                        label=f"📥 Bajar {nombre_out}",
                        data=excel_data,
                        file_name=nombre_out,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{f.name}_{i}"
                    )

st.divider()

# --- BLOQUE 2: LÓGICA DE ACTUALIZACIÓN DE STOCK ---
st.header("1️⃣ Configuración de Tienda")
col_t1, col_t2, col_t3 = st.columns(3)
with col_t1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
with col_t2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
with col_t3:
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

# Handling Times
mapas_defecto = {
    "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Envío estándar": 3},
    "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Almacenpais": 3},
    "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Almacenpais": 1},
    "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Almacenpais": 1}
}

ht_editables = {}
with st.expander(f"⏱️ Editar Handling Times para {pais}"):
    current_map = mapas_defecto.get(pais, mapas_defecto["ES"])
    cols_ht = st.columns(4)
    for i, (msg, val) in enumerate(current_map.items()):
        ht_editables[msg.lower()] = cols_ht[i % 4].number_input(msg, value=val)

st.header("2️⃣ Carga de Ficheros para Proceso")
f1, f2, f3 = st.columns(3)
with f1:
    f_listing = st.file_uploader("📄 Informe Listings Amazon", type=["xlsx", "txt", "csv"])
    f_massalaves = st.file_uploader("🏢 Stock Massalaves (Central)", type=["xlsx", "csv"])
with f2:
    f_hb = st.file_uploader("🐘 Fichero Heavy & Bulky (HB)", type=["xlsx", "csv"])
    f_aux = st.file_uploader("🏷️ Auxiliar Familias", type=["xlsx", "csv"])
with f3:
    f_bl_gen = st.file_uploader("🚫 Blacklist GLOBAL", type=["xlsx", "csv"])
    f_exc_pais = st.file_uploader("📍 Excepciones País", type=["xlsx", "csv"])

if st.button("🚀 GENERAR FICHERO DE CARGA AMAZON"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Por favor, sube al menos el Listing, Stock Massalaves, HB y Auxiliar.")
    else:
        # Usamos la carga robusta por si suben TXT/CSV en lugar de XLSX
        df_list = robust_read_csv(f_listing) if not f_listing.name.endswith('.xlsx') else cargar_excel_pro(f_listing)
        df_mas = cargar_excel_pro(f_massalaves)
        df_hb_data = cargar_excel_pro(f_hb)
        df_aux_data = cargar_excel_pro(f_aux)
        
        # Identificar columnas críticas
        try:
            col_sku = next(c for c in df_list.columns if 'sku' in c)
            col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)
            
            # Limpieza básica
            df_list = df_list.dropna(subset=[col_sku])
            df_list['is_s'] = df_list[col_sku].str.startswith('S')
            
            # Extraer SKU base para cruzar con stock físico
            def extraer_base(sku):
                s = str(sku).upper()
                if s.startswith('S'): s = s[1:]
                for pref in ['FR', 'IT', 'DE']:
                    if s.startswith(pref): s = s[len(pref):]
                return s

            df_list['sku_f_busqueda'] = procesar_serie_skus(df_list[col_sku].apply(extraer_base))

            # Mapa de Stock Central
            c_ref_mas = next(c for c in df_mas.columns if 'referencia' in c or 'sku' in c)
            c_stk_mas = next(c for c in df_mas.columns if 'disponible' in c or 'operativo' in c or 'comercial' in c)
            df_mas['key'] = procesar_serie_skus(df_mas[c_ref_mas])
            stk_map = df_mas.drop_duplicates('key').set_index('key')[c_stk_mas].astype(str).str.replace(',', '.').astype(float)

            # Cruce de Stock
            df_list['stk_fisico'] = df_list['sku_f_busqueda'].map(stk_map).fillna(0).astype(float)
            
            # Cálculo final
            df_list['quantity'] = np.where(
                df_list['is_s'],
                (df_list['stk_fisico'] * p_rework).astype(int),
                (df_list['stk_fisico'] * p_normal).astype(int)
            )

            # Formatear salida final para Amazon (TXT separado por tabuladores)
            final = pd.DataFrame()
            final['sku'] = df_list[col_sku]
            final['quantity'] = df_list['quantity']
            final['merchant-shipping-group-name'] = df_list[col_msg]
            final['handling-time'] = final['merchant-shipping-group-name'].str.lower().map(ht_editables).fillna(2).astype(int)

            st.success("✅ Proceso completado.")
            st.dataframe(final.head())

            # Descarga del resultado
            buffer = io.StringIO()
            final.to_csv(buffer, sep='\t', index=False)
            
            fecha = datetime.now().strftime("%Y%m%d")
            st.download_button(
                label="📥 Descargar TXT para Amazon",
                data=buffer.getvalue(),
                file_name=f"{fecha}_STOCK_{tienda}_{pais}.txt",
                mime="text/plain"
            )
        except Exception as e:
            st.error(f"Error en el cruce de datos: {e}")