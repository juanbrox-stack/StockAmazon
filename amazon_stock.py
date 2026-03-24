import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PERSISTENCIA ---
CONFIG_FILE = "amazon_config_v5.json"
HB_CACHE = "cache_hb.parquet"
FAM_CACHE = "cache_fam.parquet"

def cargar_config_segura():
    config_base = {
        "blacklists": {}, 
        "limites": {"HB": 15, "DESCANSO": 10, "JARDIN": 10, "RESTO": 40},
        "ht": {
            "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Envío estandar": 3},
            "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Almacenpais": 1},
            "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Almacenpais": 1},
            "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Almacenpais": 3}
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                config_base["blacklists"].update(saved.get("blacklists", {}))
                config_base["ht"].update(saved.get("ht", {}))
                if "limites" in saved: config_base["limites"].update(saved["limites"])
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
st.set_page_config(page_title="Amazon Stock Manager Pro", layout="wide")
if 'config' not in st.session_state:
    st.session_state.config = cargar_config_segura()

st.title("📦 Amazon Stock Manager: Gestión de Límites y Familias")

with st.sidebar:
    st.header("🏪 Configuración")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    store_key = f"{tienda}_{pais}"
    
    st.divider()
    # PANEL DE LÍMITES EDITABLE
    st.subheader("🛡️ Límites de Seguridad")
    lims = st.session_state.config["limites"]
    lim_hb = st.number_input("Límite HB / Especiales", value=lims["HB"])
    lim_des = st.number_input("Límite Descanso/Colchón", value=lims["DESCANSO"])
    lim_jar = st.number_input("Límite Jardín", value=lims["JARDIN"])
    lim_resto = st.number_input("Límite Resto Catálogo", value=lims["RESTO"])
    
    # Guardar límites en la sesión
    st.session_state.config["limites"] = {"HB": lim_hb, "DESCANSO": lim_des, "JARDIN": lim_jar, "RESTO": lim_resto}

    if st.button("💾 GUARDAR TODO"):
        st.session_state.config["blacklists"][store_key] = st.session_state.get('temp_bl_val', "")
        with open(CONFIG_FILE, "w") as f:
            json.dump(st.session_state.config, f, indent=4)
        st.success("¡Configuración y Límites guardados!")

col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader(f"🚫 Blacklist: {store_key}")
    bl_previa = st.session_state.config.get("blacklists", {}).get(store_key, "")
    bl_txt = st.text_area("SKUs bloqueados:", value=bl_previa, height=200, key=f"bl_in_{store_key}")
    st.session_state.temp_bl_val = bl_txt
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])

with col_main:
    st.subheader("📂 Archivos Auxiliares")
    st.info("⚠️ Actualiza semanalmente para que los límites por familia sean correctos.")
    c_aux1, c_aux2 = st.columns(2)
    with c_aux1:
        if os.path.exists(HB_CACHE): st.success("✅ HB en memoria")
        f_hb = st.file_uploader("Actualizar HB", type=["xlsx"])
        if f_hb: cargar_excel_pro(f_hb).to_parquet(HB_CACHE); st.rerun()
    with c_aux2:
        if os.path.exists(FAM_CACHE): st.success("✅ Familias en memoria")
        f_fam = st.file_uploader("Actualizar Familias", type=["xlsx"])
        if f_fam: cargar_excel_pro(f_fam).to_parquet(FAM_CACHE); st.rerun()

    st.divider()
    st.subheader("📤 Inventarios Diarios")
    f_list = st.file_uploader("1. Listings Amazon", type=["xlsx"])
    f_mas = st.file_uploader("2. Stock Massalaves", type=["xlsx"])
    f_loc = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None

# --- 4. MOTOR ---
if st.button("🚀 GENERAR STOCK"):
    if not (f_list and f_mas and os.path.exists(HB_CACHE) and os.path.exists(FAM_CACHE)):
        st.error("Faltan archivos obligatorios o memoria vacía.")
    else:
        df_list = cargar_excel_pro(f_list)
        df_mas_data = cargar_excel_pro(f_mas)
        df_loc_data = cargar_excel_pro(f_loc)
        df_hb_data = pd.read_parquet(HB_CACHE)
        df_aux_data = pd.read_parquet(FAM_CACHE)

        # Filtro FBA y SKUs
        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)
        
        def extraer_base(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:]
            for p in ['FR', 'IT', 'DE']:
                if s.startswith(p): s = s[len(p):]
            return s

        df_list['sku_f_busqueda'] = df_list[col_sku].apply(extraer_base).apply(formatear_sku_excel)
        
        # Mapeo Stock
        def create_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia', 'sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible', 'operativo']))
            df['key'] = df[c_ref].apply(formatear_sku_excel)
            df['stk_v'] = df[c_stk].astype(str).str.replace(',', '.').replace('nan', '0')
            return df.drop_duplicates('key').set_index('key')['stk_v']

        m_mas = create_map(df_mas_data)
        m_loc = create_map(df_loc_data)

        # Cruce de datos
        df_list['stk_b'] = 0.0
        df_list['use_local'] = df_list[col_sku].str.contains(f"^{pais}|^S{pais}", case=False, na=False) & (f_loc is not None)
        df_list.loc[df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_loc).fillna("0").astype(float)
        df_list.loc[~df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_mas).fillna("0").astype(float)

        # IDENTIFICACIÓN DE FAMILIAS
        df_aux_data['key_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku_excel)
        f_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['fam'] = df_list['sku_f_busqueda'].map(f_map).fillna("RESTO").str.upper()
        skus_hb_set = set(df_hb_data.iloc[:, 0].apply(formatear_sku_excel))

        def calc_final(row):
            if row[col_sku].apply(formatear_sku_excel) in blacklist_set or row['sku_f_busqueda'] in blacklist_set:
                return 0
            
            # Aplicar límites desde el panel lateral
            l = lim_resto
            if row[col_sku] in skus_hb_set or row['sku_f_busqueda'] in skus_hb_set or "HB" in row['fam']: l = lim_hb
            elif any(x in row['fam'] for x in ["DESCANSO", "COLCHON", "ALMOHADA"]): l = lim_des
            elif "JARDIN" in row['fam'] or "JARDÍN" in row['fam']: l = lim_jar
            
            if row['stk_b'] < l: return 0
            return int(np.ceil(row['stk_b'] * (p_rework if row[col_sku].startswith('S') else p_normal)))

        df_list['quantity'] = df_list.apply(calc_final, axis=1)
        
        # Salida...
        st.success("✅ Stock generado con éxito.")
        st.dataframe(df_list[[col_sku, 'quantity', 'fam', 'stk_b']].head(10))