import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PERSISTENCIA ---
CONFIG_FILE = "amazon_config_v4.json"
HB_CACHE = "cache_hb.parquet"
FAM_CACHE = "cache_fam.parquet"

def cargar_config_segura():
    config_base = {"blacklists": {}, "ht": {
        "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Envío estandar": 3},
        "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Almacenpais": 1},
        "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Almacenpais": 1},
        "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Almacenpais": 3}
    }}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                config_base["blacklists"].update(saved.get("blacklists", {}))
                config_base["ht"].update(saved.get("ht", {}))
        except: pass
    return config_base

# --- 2. FUNCIONES DE APOYO ---
def formatear_sku_excel(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    val_str = str(val).strip().split('.')[0]
    return val_str.zfill(5) if val_str.isdigit() else val_str

def cargar_excel_pro(file, skip=0):
    if file is None: return None
    df = pd.read_excel(file, skiprows=skip, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("")

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Amazon Stock Pro", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = cargar_config_segura()

st.title("📦 Amazon Stock Manager: Memoria Inteligente")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🏪 Configuración")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    store_key = f"{tienda}_{pais}"
    
    st.divider()
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100
    
    if st.button("💾 GUARDAR BLACKLIST Y TIEMPOS"):
        st.session_state.config["blacklists"][store_key] = st.session_state.get('temp_bl_val', "")
        with open(CONFIG_FILE, "w") as f:
            json.dump(st.session_state.config, f, indent=4)
        st.success("¡Memoria de configuración actualizada!")

# --- CUERPO PRINCIPAL ---
col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader(f"🚫 Blacklist: {store_key}")
    bl_previa = st.session_state.config.get("blacklists", {}).get(store_key, "")
    bl_txt = st.text_area("SKUs bloqueados:", value=bl_previa, height=200, key=f"bl_in_{store_key}")
    st.session_state.temp_bl_val = bl_txt
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])

with col_main:
    # --- SECCIÓN DE ARCHIVOS AUXILIARES CON MEMORIA ---
    st.subheader("📂 Archivos Auxiliares (Memoria Permanente)")
    st.info("⚠️ Se recomienda la actualización de estos ficheros semanalmente.")
    
    c_aux1, c_aux2 = st.columns(2)
    
    # Lógica HB
    with c_aux1:
        st.write("**1. Fichero HB (Heavy & Bulky)**")
        if os.path.exists(HB_CACHE):
            st.success("✅ Fichero HB cargado desde memoria.")
        f_hb = st.file_uploader("Actualizar HB (.xlsx)", type=["xlsx"], key="up_hb")
        if f_hb:
            df_hb_new = cargar_excel_pro(f_hb)
            df_hb_new.to_parquet(HB_CACHE)
            st.warning("🔄 Memoria HB actualizada con el nuevo archivo.")

    # Lógica Familias
    with c_aux2:
        st.write("**2. Auxiliar Familias (Plytix)**")
        if os.path.exists(FAM_CACHE):
            st.success("✅ Fichero Familias cargado desde memoria.")
        f_fam = st.file_uploader("Actualizar Familias (.xlsx)", type=["xlsx"], key="up_fam")
        if f_fam:
            df_fam_new = cargar_excel_pro(f_fam)
            df_fam_new.to_parquet(FAM_CACHE)
            st.warning("🔄 Memoria Familias actualizada.")

    st.divider()
    st.subheader("📤 Carga de Inventarios Diarios")
    f_list = st.file_uploader("1. Informe Listings Amazon", type=["xlsx"])
    f_mas = st.file_uploader("2. Stock Massalaves", type=["xlsx"])
    f_loc = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None

# --- 4. MOTOR DE CÁLCULO ---
if st.button("🚀 GENERAR STOCK"):
    # Verificar si tenemos los archivos auxiliares (ya sea en caché o subidos ahora)
    has_hb = os.path.exists(HB_CACHE) or f_hb is not None
    has_fam = os.path.exists(FAM_CACHE) or f_fam is not None
    
    if not (f_list and f_mas and has_hb and has_fam):
        st.error("Error: Faltan archivos. Asegúrate de que los auxiliares estén en memoria o súbelos ahora.")
    else:
        # Cargar los diarios
        df_list = cargar_excel_pro(f_list)
        df_mas_data = cargar_excel_pro(f_mas)
        df_loc_data = cargar_excel_pro(f_loc)
        
        # Cargar los auxiliares desde caché
        df_hb_data = pd.read_parquet(HB_CACHE)
        df_aux_data = pd.read_parquet(FAM_CACHE)

        # (Lógica de procesamiento igual a la anterior...)
        col_ff = next((c for c in df_list.columns if 'fulfillment-channel' in c), None)
        if col_ff: df_list = df_list[df_list[col_ff] != "AMAZON_EU"].copy()
        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        def extraer_base(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:]
            for p in ['FR', 'IT', 'DE']:
                if s.startswith(p): s = s[len(p):]
            return s

        df_list['sku_f_busqueda'] = df_list[col_sku].apply(extraer_base).apply(formatear_sku_excel)
        
        def create_map(df):
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia', 'sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible', 'operativo']))
            df['key'] = df[c_ref].apply(formatear_sku_excel)
            df['stk_v'] = df[c_stk].astype(str).str.replace(',', '.').replace('nan', '0')
            return df.drop_duplicates('key').set_index('key')['stk_v']

        m_mas = create_map(df_mas_data)
        m_loc = create_map(df_loc_data) if f_loc else None

        df_list['is_s'] = df_list[col_sku].str.startswith('S')
        df_list['stk_b'] = df_list['sku_f_busqueda'].map(m_mas).fillna("0").astype(float)
        # (Aquí se podría añadir lógica de stock local si m_loc existe)

        df_list['bloqueado'] = (df_list[col_sku].apply(formatear_sku_excel).isin(blacklist_set) | 
                                df_list['sku_f_busqueda'].isin(blacklist_set))

        # Aplicar límites con la memoria de auxiliares
        df_aux_data['key_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku_excel)
        f_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['fam'] = df_list['sku_f_busqueda'].map(f_map).fillna("RESTO").str.upper()
        skus_hb_set = set(df_hb_data.iloc[:, 0].apply(formatear_sku_excel))

        def final_qty(row):
            if row['bloqueado']: return 0
            lim = 15 if (row[col_sku] in skus_hb_set or "HB" in row['fam']) else 40
            if row['stk_b'] < lim: return 0
            return int(np.ceil(row['stk_b'] * (p_rework if row['is_s'] else p_normal)))

        df_list['quantity'] = df_list.apply(final_qty, axis=1)

        res = pd.DataFrame()
        res['sku'] = df_list[col_sku]
        res['quantity'] = df_list['quantity']
        res['merchant-shipping-group-name'] = df_list[col_msg]
        
        st.success("✅ Proceso completado con éxito utilizando archivos en memoria.")
        st.dataframe(res.head(10))
        st.download_button("📥 Descargar TXT", res.to_csv(sep='\t', index=False), f"STOCK_{store_key}.txt")