import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PERSISTENCIA MULTI-PAÍS ---
CONFIG_FILE = "amazon_config_v2.json"

def cargar_config_completa():
    """Carga la configuración. Ahora 'blacklist' es un diccionario."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    # Configuración inicial por defecto
    return {
        "blacklists": {
            "Jabiru_ES": "112, 1509, 3909",
            "Jabiru_IT": "IT112",
        },
        "ht": {
            "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Envío estandar": 3},
            "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Almacenpais": 1},
            "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Almacenpais": 1},
            "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Almacenpais": 3}
        }
    }

def guardar_config_completa(config_dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_dict, f, indent=4)

# --- 2. FUNCIONES DE APOYO ---
def formatear_sku_excel(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    val_str = str(val).strip().split('.')[0]
    return val_str.zfill(5) if val_str.isdigit() else val_str

def cargar_excel_pro(file, skip=0):
    if file is None: return None
    try:
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Amazon Multi-Store Manager", layout="wide")

if 'config' not in st.session_state:
    st.session_state.config = cargar_config_completa()

st.title("📦 Amazon Stock Manager: Lógica Multi-País")

# --- BARRA LATERAL (CONFIGURACIÓN GLOBAL) ---
with st.sidebar:
    st.header("🏪 Selección de Entorno")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
    
    # Generar la clave única para esta combinación
    store_key = f"{tienda}_{pais}"
    
    st.divider()
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100
    
    if st.button("💾 GUARDAR CAMBIOS (Permanente)"):
        # Guardar la blacklist actual de la sesión en el diccionario global
        st.session_state.config["blacklists"][store_key] = st.session_state.current_bl_text
        guardar_config_completa(st.session_state.config)
        st.success(f"Configuración de {store_key} guardada.")

# --- CUERPO PRINCIPAL ---
col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader(f"🚫 Blacklist: {tienda} - {pais}")
    # Recuperar la blacklist específica para esta tienda/país
    bl_previa = st.session_state.config["blacklists"].get(store_key, "")
    
    # El text_area usa una clave que cambia con el país para forzar el refresco del texto
    bl_txt = st.text_area("SKUs bloqueados para este mercado:", 
                          value=bl_previa, 
                          height=300, 
                          key=f"bl_input_{store_key}")
    
    # Guardamos temporalmente lo que el usuario escribe
    st.session_state.current_bl_text = bl_txt
    
    # Procesar para el motor
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])
    st.info(f"Filtro activo: {len(blacklist_set)} SKUs bloqueados en {pais}.")

with col_main:
    st.subheader("⏱️ Handling Times Específicos")
    ht_pais_data = st.session_state.config["ht"].get(pais, {})
    ht_final = {}
    
    with st.expander("Editar tiempos de esta zona", expanded=False):
        c_ht = st.columns(2)
        for i, (msg, val) in enumerate(ht_pais_data.items()):
            nuevo_v = c_ht[i % 2].number_input(msg, value=int(val), key=f"ht_{store_key}_{msg}")
            ht_final[msg.lower()] = nuevo_v
            # Actualizar en memoria
            st.session_state.config["ht"][pais][msg] = nuevo_v

    st.subheader("📤 Carga de Inventarios")
    f_list = st.file_uploader("1. Informe Listings Amazon", type=["xlsx"])
    f_mas = st.file_uploader("2. Stock Massalaves (Central)", type=["xlsx"])
    f_loc = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
    
    with st.expander("Archivos Auxiliares"):
        f_hb = st.file_uploader("4. Fichero HB", type=["xlsx"])
        f_aux = st.file_uploader("5. Auxiliar Familias", type=["xlsx"])

# --- 4. CÁLCULO ---
if st.button("🚀 GENERAR STOCK"):
    if not (f_list and f_mas and f_hb and f_aux):
        st.error("Faltan archivos para procesar.")
    else:
        df_list = cargar_excel_pro(f_list)
        df_mas_data = cargar_excel_pro(f_mas)
        df_loc_data = cargar_excel_pro(f_loc)
        df_hb_data = cargar_excel_pro(f_hb)
        df_aux_data = cargar_excel_pro(f_aux)

        # Filtro FBA
        col_ff = next((c for c in df_list.columns if 'fulfillment-channel' in c), None)
        if col_ff: df_list = df_list[df_list[col_ff] != "AMAZON_EU"].copy()

        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        # Lógica de SKU Base (Quitar S y Prefijos)
        def extraer_base(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:]
            for p in ['FR', 'IT', 'DE']:
                if s.startswith(p): s = s[len(p):]
            return s

        df_list['sku_f_busqueda'] = df_list[col_sku].apply(extraer_base).apply(formatear_sku_excel)
        
        # Mapas
        def create_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia', 'sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible', 'operativo']))
            df['key'] = df[c_ref].apply(formatear_sku_excel)
            df['stk_v'] = df[c_stk].astype(str).str.replace(',', '.').replace('nan', '0')
            return df.drop_duplicates('key').set_index('key')['stk_v']

        m_mas = create_map(df_mas_data)
        m_loc = create_map(df_loc_data)

        # Stock y Bloqueo
        df_list['is_s'] = df_list[col_sku].str.startswith('S')
        df_list['use_local'] = df_list[col_sku].str.contains(f"^{pais}|^S{pais}", case=False, na=False) & (df_loc_data is not None)
        
        df_list['stk_b'] = 0.0
        df_list.loc[df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_loc).fillna("0").astype(float)
        df_list.loc[~df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(m_mas).fillna("0").astype(float)

        # APLICAR BLACKLIST DINÁMICA
        df_list['bloqueado'] = (
            df_list[col_sku].apply(formatear_sku_excel).isin(blacklist_set) | 
            df_list['sku_f_busqueda'].isin(blacklist_set)
        )

        # Familias
        df_aux_data['key_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku_excel)
        f_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['fam'] = df_list['sku_f_busqueda'].map(f_map).fillna("RESTO").str.upper()
        
        skus_hb_set = set(df_hb_data.iloc[:, 0].apply(formatear_sku_excel))

        def final_qty(row):
            if row['bloqueado']: return 0
            # Límites simplificados
            lim = 15 if (row[col_sku] in skus_hb_set or "HB" in row['fam']) else 40
            if "DESCANSO" in row['fam']: lim = 10
            
            if row['stk_b'] < lim: return 0
            mult = p_rework if row['is_s'] else p_normal
            return int(np.ceil(row['stk_b'] * mult))

        df_list['quantity'] = df_list.apply(final_qty, axis=1)

        # Salida
        res = pd.DataFrame()
        res['sku'] = df_list[col_sku]
        res['quantity'] = df_list['quantity']
        res['merchant-shipping-group-name'] = df_list[col_msg]
        res['handling-time'] = res['merchant-shipping-group-name'].str.lower().map(ht_final).fillna(2).astype(int)

        st.success(f"Procesado finalizado para {store_key}")
        st.dataframe(res.head(10))
        st.download_button(f"📥 Bajar STOCK_{store_key}.txt", res.to_csv(sep='\t', index=False), f"STOCK_{store_key}.txt")