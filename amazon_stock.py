import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime

# 1. Formateo de SKU estilo Excel (=TEXTO(A2;"00000"))
# Esta función se usa para la SALIDA FINAL y para limpiar claves de cruce
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
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

st.set_page_config(page_title="Amazon Stock Manager Pro", layout="centered")
st.title("📦 Actualizador de Stock de Amazon Seller")

# --- PASO 1: CONFIGURACIÓN ---
st.header("1️⃣ Configuración y Porcentajes")
col1, col2 = st.columns(2)
with col1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
with col2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

# --- PANEL DE HANDLING TIMES ---
st.header("⏱️ Panel de Handling Times")
mapas_defecto = {
    "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Envlo gratuito": 1, "Fitness": 1, "No prime": 1, "Prime Nacional": 0, "Envío estandar": 3},
    "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 3, "Preventa": 5},
    "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5, "Envio 10 dias": 5, "Portes gratuitos": 2},
    "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Sin tarifa": 5, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5}
}

ht_editables = {}
with st.expander(f"Editar tiempos para {pais}"):
    current_map = mapas_defecto[pais]
    cols_ht = st.columns(3)
    for i, (msg, val) in enumerate(current_map.items()):
        ht_editables[msg.lower()] = cols_ht[i % 3].number_input(msg, value=val, key=f"ht_{pais}_{msg}")

# --- PASO 2: LÍMITES Y CARGA ---
st.header("2️⃣ Límites y Ficheros")
l1, l2 = st.columns(2)
with l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

f_listing = st.file_uploader("📄 1. Informe Listings Amazon", type=["xlsx"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central ES)", type=["xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx"])
f_bl_gen = st.file_uploader("🚫 6. Blacklist GLOBAL", type=["xlsx"])
f_exc_pais = st.file_uploader("📍 7. Excepciones País", type=["xlsx"])

if st.button("🚀 GENERAR ACTUALIZACIÓN"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios.")
    else:
        df_list = cargar_excel_pro(f_listing)
        
        # Filtro FBA (Omitir AMAZON_EU)
        col_ff = next((c for c in df_list.columns if 'fulfillment-channel' in c), None)
        if col_ff:
            df_list = df_list[df_list[col_ff] != "AMAZON_EU"].copy()
        
        df_mas = cargar_excel_pro(f_massalaves)
        df_local = cargar_excel_pro(f_pais)
        df_hb_data = cargar_excel_pro(f_hb)
        df_aux_data = cargar_excel_pro(f_aux)
        
        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        # --- LÓGICA INTERNA DE CRUCE (SIN MODIFICAR EL SKU FINAL) ---
        df_list['is_s'] = df_list[col_sku].str.startswith('S')
        
        # Identificar si debe buscar en el almacén local del país
        def es_local(sku):
            s = str(sku).upper()
            return s.startswith(('FR', 'IT', 'DE')) or s.startswith(('SFR', 'SIT', 'SDE'))

        df_list['use_local'] = df_list[col_sku].apply(es_local) & (df_local is not None)
        
        # Función para extraer el SKU numérico "padre" para buscar el stock físico
        def extraer_base_busqueda(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:] # Quitar S de Rework
            for pref in ['FR', 'IT', 'DE']: # Quitar prefijos de país
                if s.startswith(pref): s = s[len(pref):]
            return s

        df_list['sku_interno_busqueda'] = df_list[col_sku].apply(extraer_base_busqueda)
        df_list['sku_f_busqueda'] = procesar_serie_skus(df_list['sku_interno_busqueda'])
        
        # Mapas de stock
        def get_clean_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if 'referencia' in c or 'sku' in c)
            c_stk = next(c for c in df.columns if 'disponible' in c or 'operativo' in c)
            df['key'] = procesar_serie_skus(df[c_ref])
            df['stk_clean'] = df[c_stk].astype(str).str.replace(',', '.')
            return df.drop_duplicates('key').set_index('key')['stk_clean']

        stk_mas_map = get_clean_map(df_mas)
        stk_loc_map = get_clean_map(df_local)
        
        # Asignar Stock del "Padre"
        df_list['stk_b'] = 0.0
        df_list.loc[df_list['use_local'], 'stk_b'] = df_list.loc[df_list['use_local'], 'sku_f_busqueda'].map(stk_loc_map).fillna("0.0").astype(float)
        df_list.loc[~df_list['use_local'], 'stk_b'] = df_list.loc[~df_list['use_local'], 'sku_f_busqueda'].map(stk_mas_map).fillna("0.0").astype(float)
        
        # Familias y Bloqueos (Usando SKU base)
        df_aux_data['key_aux'] = procesar_serie_skus(df_aux_data.iloc[:, 0])
        fam_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['familia'] = df_list['sku_f_busqueda'].map(fam_map).fillna("Resto").astype(str).str.upper()

        bl = set()
        if f_bl_gen: bl.update(procesar_serie_skus(cargar_excel_pro(f_bl_gen).iloc[:,0]))
        if f_exc_pais:
            skip_v = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
            bl.update(procesar_serie_skus(cargar_excel_pro(f_exc_pais, skip=skip_v).iloc[:,0]))

        # Cálculo de Cantidad con el multiplicador correspondiente
        skus_hb = set(procesar_serie_skus(df_hb_data.iloc[:, 0]))
        
        def get_lim(fam, sku_a, sku_f):
            if sku_a in skus_hb or sku_f in skus_hb or "HB" in fam or "GAE" in fam: return lim_hb
            if "DESCANSO" in fam or "COLCHONES" in fam: return lim_colchones
            if "JARDÍN" in fam or "JARDIN" in fam: return lim_jardin
            return lim_resto

        df_list['limite'] = [get_lim(f, a, s) for f, a, s in zip(df_list['familia'], df_list[col_sku], df_list['sku_f_busqueda'])]
        df_list['bloqueado'] = df_list[col_sku].isin(bl) | df_list['sku_f_busqueda'].isin(bl)
        
        df_list['quantity'] = np.where(
            (df_list['stk_b'] >= df_list['limite']) & (~df_list['bloqueado']),
            np.ceil(df_list['stk_b'] * np.where(df_list['is_s'], p_rework, p_normal)).astype(int),
            0
        )

        # SALIDA FINAL (Manteniendo el SKU original tal cual)
        final = pd.DataFrame()
        # Aquí el SKU permanece IGUAL que en el listing, con su S y prefijos
        final['sku'] = df_list[col_sku]
        final['quantity'] = df_list['quantity']
        final['merchant-shipping-group-name'] = df_list[col_msg]
        final['handling-time'] = final['merchant-shipping-group-name'].str.lower().map(ht_editables).fillna(2).astype(int)
        
        st.success(f"✅ ¡Hecho! Los SKUs con S (ej: {final['sku'].iloc[0] if not final.empty else 'S01951'}) mantienen su formato original.")
        st.dataframe(final.head(10))
        
        fecha = datetime.now().strftime("%Y%m%d")
        nombre_descarga = f"{fecha}_STOCK_{tienda}_{pais}.txt"
        st.download_button(label=f"📥 Descargar {nombre_descarga}", data=final.to_csv(sep='\t', index=False), file_name=nombre_descarga)