import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import io
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PERSISTENCIA ---
CONFIG_FILE = "amazon_config_final.json"
HB_CACHE = "cache_hb.parquet"
FAM_CACHE = "cache_fam.parquet"

def cargar_config_segura():
    config_base = {
        "blacklists": {}, 
        "ht": {
            "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Envlo gratuito": 1, "Fitness": 1, "No prime": 1, "Prime Nacional": 0, "Envío estandar": 3},
            "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 3, "Preventa": 5},
            "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5, "Envio 10 dias": 5, "Portes gratuitos": 2},
            "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Sin tarifa": 5, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5}
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                if "blacklists" in saved: config_base["blacklists"].update(saved["blacklists"])
                if "ht" in saved: config_base["ht"].update(saved["ht"])
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

st.title("📦 Amazon Stock Manager: Versión Full con Memoria")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🏪 Configuración")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    store_key = f"{tienda}_{pais}"
    
    st.divider()
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100
    
    if st.button("💾 GUARDAR TODO (Blacklist y HT)"):
        st.session_state.config["blacklists"][store_key] = st.session_state.get('temp_bl_val', "")
        with open(CONFIG_FILE, "w") as f:
            json.dump(st.session_state.config, f, indent=4)
        st.success("¡Configuración guardada!")

# --- CUERPO PRINCIPAL ---
col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader(f"🚫 Blacklist: {store_key}")
    bl_previa = st.session_state.config.get("blacklists", {}).get(store_key, "")
    bl_txt = st.text_area("SKUs bloqueados:", value=bl_previa, height=250, key=f"bl_in_{store_key}")
    st.session_state.temp_bl_val = bl_txt
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])

with col_main:
    # --- MEMORIA DE ARCHIVOS AUXILIARES ---
    st.subheader("📂 Archivos Auxiliares (Persistentes)")
    st.info("⚠️ Se recomienda la actualización de estos ficheros semanalmente.")
    
    c_aux1, c_aux2 = st.columns(2)
    with c_aux1:
        st.write("**Fichero HB (Heavy & Bulky)**")
        if os.path.exists(HB_CACHE): st.success("✅ HB en memoria")
        f_hb = st.file_uploader("Actualizar HB", type=["xlsx"], key="up_hb")
        if f_hb: 
            cargar_excel_pro(f_hb).to_parquet(HB_CACHE)
            st.rerun()

    with c_aux2:
        st.write("**Fichero Familias (Plytix)**")
        if os.path.exists(FAM_CACHE): st.success("✅ Familias en memoria")
        f_fam = st.file_uploader("Actualizar Familias", type=["xlsx"], key="up_fam")
        if f_fam: 
            cargar_excel_pro(f_fam).to_parquet(FAM_CACHE)
            st.rerun()

    st.divider()
    st.subheader("⏱️ Handling Times (Tiempos de Preparación)")
    ht_pais_data = st.session_state.config["ht"].get(pais, {})
    ht_map_final = {}
    
    with st.expander(f"Editar tiempos para {pais}", expanded=False):
        c_ht = st.columns(3)
        for i, (msg, val) in enumerate(ht_pais_data.items()):
            nuevo_v = c_ht[i % 3].number_input(msg, value=int(val), key=f"ht_inp_{store_key}_{msg}")
            ht_map_final[msg.lower()] = nuevo_v
            st.session_state.config["ht"][pais][msg] = nuevo_v

    st.subheader("📤 Carga de Inventarios Diarios")
    f_list = st.file_uploader("1. Informe Listings Amazon", type=["xlsx"])
    f_mas = st.file_uploader("2. Stock Massalaves", type=["xlsx"])
    f_loc = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None

# --- 4. MOTOR DE CÁLCULO ---
if st.button("🚀 GENERAR ACTUALIZACIÓN"):
    if not (f_list and f_mas and os.path.exists(HB_CACHE) and os.path.exists(FAM_CACHE)):
        st.error("Faltan archivos (Listings, Massalaves o Auxiliares en memoria).")
    else:
        # Carga de datos
        df_list = cargar_excel_pro(f_list)
        df_mas_data = cargar_excel_pro(f_mas)
        df_loc_data = cargar_excel_pro(f_loc)
        df_hb_data = pd.read_parquet(HB_CACHE)
        df_aux_data = pd.read_parquet(FAM_CACHE)

        # Filtro FBA
        col_ff = next((c for c in df_list.columns if 'fulfillment-channel' in c), None)
        if col_ff: df_list = df_list[df_list[col_ff] != "AMAZON_EU"].copy()
        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        # Lógica SKU Base
        def extraer_base(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:]
            for p in ['FR', 'IT', 'DE']:
                if s.startswith(p): s = s[len(p):]
            return s

        df_list['sku_f_busqueda'] = df_list[col_sku].apply(extraer_base).apply(formatear_sku_excel)
        
        # Mapeo de Stock
        def create_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia', 'sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible', 'operativo']))
            df['key'] = df[c_ref].apply(formatear_sku_excel)
            df['stk_v'] = df[c_stk].astype(str).str.replace(',', '.').replace('nan', '0')
            return df.drop_duplicates('key').set_index('key')['stk_v']

        m_mas = create_map(df_mas_data)
        m_loc = create_map(df_loc_data)

        # Asignación de Stock Local vs Central
        df_list['is_s'] = df_list[col_sku].str.startswith('S')
        df_list['use_local'] = df_list[col_sku].str.contains(f"^{pais}|^S{pais}", case=False, na=False) & (f_loc is not None)
        
        df_list['stk_b'] = 0.0
        df_list.loc[df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_loc).fillna("0").astype(float)
        df_list.loc[~df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_mas).fillna("0").astype(float)

        # Bloqueos y Límites
        df_list['bloqueado'] = (df_list[col_sku].apply(formatear_sku_excel).isin(blacklist_set) | 
                                df_list['sku_f_busqueda'].isin(blacklist_set))

        df_aux_data['key_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku_excel)
        f_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['fam'] = df_list['sku_f_busqueda'].map(f_map).fillna("RESTO").str.upper()
        skus_hb_set = set(df_hb_data.iloc[:, 0].apply(formatear_sku_excel))

        def final_qty(row):
            if row['bloqueado']: return 0
            # Definición de límites
            lim = 40
            if row[col_sku] in skus_hb_set or row['sku_f_busqueda'] in skus_hb_set or "HB" in row['fam']: lim = 15
            elif "DESCANSO" in row['fam'] or "COLCHON" in row['fam']: lim = 10
            elif "JARDIN" in row['fam'] or "JARDÍN" in row['fam']: lim = 10
            
            if row['stk_b'] < lim: return 0
            return int(np.ceil(row['stk_b'] * (p_rework if row['is_s'] else p_normal)))

        df_list['quantity'] = df_list.apply(final_qty, axis=1)

        # Preparación Salida
        res = pd.DataFrame()
        res['sku'] = df_list[col_sku]
        res['quantity'] = df_list['quantity']
        res['merchant-shipping-group-name'] = df_list[col_msg]
        # MAPEADO DE HANDLING TIME (Recuperado)
        res['handling-time'] = res['merchant-shipping-group-name'].str.lower().map(ht_map_final).fillna(2).astype(int)

        st.success(f"✅ Archivo generado para {store_key}")
        st.dataframe(res.head(15), use_container_width=True)
        
        tsv = res.to_csv(sep='\t', index=False)
        st.download_button(f"📥 Descargar STOCK_{store_key}.txt", tsv, f"{datetime.now().strftime('%Y%m%d')}_STOCK_{store_key}.txt")