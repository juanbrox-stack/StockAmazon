import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# --- 1. CONFIGURACIÓN Y PERSISTENCIA ---
CONFIG_FILE = "amazon_config_v8.json" # Nueva versión para forzar limpieza si fuera necesario
HB_CACHE = "cache_hb.parquet"
FAM_CACHE = "cache_fam.parquet"

def cargar_config_segura():
    # Estructura MAESTRA: Si algo no está en el JSON, se cogerá de aquí
    defaults = {
        "blacklists": {}, 
        "limites": {
            "HB": 15, 
            "DESCANSO": 10, 
            "JARDIN": 10, 
            "RESTO": 40
        },
        "ht": {
            "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Envío estandar": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Envlo gratuito": 1, "Fitness": 1, "No prime": 1, "Prime Nacional": 0},
            "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Almacenpais": 1, "Sin tarifa": 5, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Preventa": 5},
            "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Almacenpais": 1, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Preventa": 5, "Envio 10 dias": 5, "Portes gratuitos": 2},
            "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Almacenpais": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Preventa": 5}
        }
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                
                # 1. Sincronizar Blacklists
                if "blacklists" in saved: 
                    defaults["blacklists"].update(saved["blacklists"])
                
                # 2. Sincronizar Límites (Fusión Inteligente)
                if "limites" in saved:
                    # Mantenemos los valores que ya tenías pero añadimos los que falten
                    for k, v in saved["limites"].items():
                        defaults["limites"][k] = v
                
                # 3. Sincronizar Handling Times país por país
                if "ht" in saved:
                    for p in defaults["ht"]:
                        if p in saved["ht"]:
                            defaults["ht"][p].update(saved["ht"][p])
        except:
            pass
    return defaults

# --- 2. FUNCIONES AUXILIARES ---
def formatear_sku_excel(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    val_str = str(val).strip().split('.')[0]
    return val_str.zfill(5) if val_str.isdigit() else val_str

def cargar_excel_pro(file):
    if file is None: return None
    df = pd.read_excel(file, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("")

# --- 3. INICIALIZACIÓN ---
st.set_page_config(page_title="Amazon Stock Manager Pro", layout="wide")
if 'config' not in st.session_state:
    st.session_state.config = cargar_config_segura()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("🏪 Entorno")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    store_key = f"{tienda}_{pais}"
    
    st.divider()
    st.subheader("🛡️ Límites de Seguridad")
    
    # Creamos los inputs usando la configuración sincronizada
    conf_lims = st.session_state.config["limites"]
    
    # Renderizado dinámico de TODOS los límites definidos en defaults
    limites_editados = {}
    for etiqueta, valor in conf_lims.items():
        # Usamos etiquetas más legibles para el usuario
        label_display = f"Límite {etiqueta}" if etiqueta != "HB" else "Límite HB / Especiales"
        nuevo_val = st.number_input(label_display, value=int(valor), key=f"lim_{etiqueta}")
        limites_editados[etiqueta] = nuevo_val
    
    # Actualizamos el estado de la sesión con los nuevos valores del sidebar
    st.session_state.config["limites"] = limites_editados

    st.divider()
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100
    
    if st.button("💾 GUARDAR CONFIGURACIÓN TOTAL"):
        # Capturamos la blacklist antes de guardar el JSON
        st.session_state.config["blacklists"][store_key] = st.session_state.get('bl_val_tmp', "")
        with open(CONFIG_FILE, "w") as f:
            json.dump(st.session_state.config, f, indent=4)
        st.success("Configuración, Límites y Tiempos guardados.")

# --- 5. INTERFAZ PRINCIPAL ---
col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader(f"🚫 Blacklist: {store_key}")
    bl_previa = st.session_state.config["blacklists"].get(store_key, "")
    bl_txt = st.text_area("SKUs bloqueados:", value=bl_previa, height=200, key=f"bl_area_{store_key}")
    st.session_state.bl_val_tmp = bl_txt
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])

with col_main:
    st.subheader("⏱️ Handling Times (Tiempos de Preparación)")
    ht_pais_actual = st.session_state.config["ht"].get(pais, {})
    ht_mapeo_final = {} 
    
    with st.expander(f"Editar Tiempos para {pais}", expanded=True):
        cols_ht = st.columns(3)
        for i, (nombre, valor) in enumerate(ht_pais_actual.items()):
            v_edit = cols_ht[i % 3].number_input(nombre, value=int(valor), key=f"ht_in_{store_key}_{nombre}")
            ht_mapeo_final[nombre.lower()] = v_edit
            st.session_state.config["ht"][pais][nombre] = v_edit

    st.divider()
    st.subheader("📂 Archivos en Memoria")
    c1, c2 = st.columns(2)
    with c1:
        if os.path.exists(HB_CACHE): st.success("✅ HB Cargado")
        f_hb = st.file_uploader("Actualizar HB", type=["xlsx"])
        if f_hb: cargar_excel_pro(f_hb).to_parquet(HB_CACHE); st.rerun()
    with c2:
        if os.path.exists(FAM_CACHE): st.success("✅ Familias Cargado")
        f_fam = st.file_uploader("Actualizar Familias", type=["xlsx"])
        if f_fam: cargar_excel_pro(f_fam).to_parquet(FAM_CACHE); st.rerun()

    st.subheader("📤 Inventarios Diarios")
    f_list = st.file_uploader("1. Informe Listings", type=["xlsx"])
    f_mas = st.file_uploader("2. Stock Central", type=["xlsx"])
    f_loc = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None

# --- 6. MOTOR DE CÁLCULO ---
if st.button("🚀 GENERAR ACTUALIZACIÓN"):
    if not (f_list and f_mas and os.path.exists(HB_CACHE) and os.path.exists(FAM_CACHE)):
        st.error("Faltan archivos o memoria vacía.")
    else:
        df_list = cargar_excel_pro(f_list)
        df_mas_data = cargar_excel_pro(f_mas)
        df_loc_data = cargar_excel_pro(f_loc)
        df_hb_data = pd.read_parquet(HB_CACHE)
        df_aux_data = pd.read_parquet(FAM_CACHE)

        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)
        
        # Mapeos Stock
        def get_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia','sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible','operativo']))
            df['k'] = df[c_ref].apply(formatear_sku_excel)
            return df.drop_duplicates('k').set_index('k')[c_stk].astype(str).str.replace(',','.').astype(float)

        m_mas = get_map(df_mas_data)
        m_loc = get_map(df_loc_data)

        # SKU Base
        df_list['sku_base'] = df_list[col_sku].apply(lambda x: str(x).upper().replace('S','',1) if str(x).upper().startswith('S') else str(x))
        df_list['sku_base'] = df_list['sku_base'].apply(lambda x: x[2:] if x[:2] in ['FR','IT','DE'] else x).apply(formatear_sku_excel)

        # Cruce Stock
        df_list['stk_f'] = df_list['sku_base'].map(m_mas).fillna(0)
        
        # Familias y HB
        df_aux_data['k'] = df_aux_data.iloc[:,0].apply(formatear_sku_excel)
        fam_map = df_aux_data.set_index('k').iloc[:,1]
        df_list['familia'] = df_list['sku_base'].map(fam_map).fillna("RESTO").str.upper()
        hb_set = set(df_hb_data.iloc[:,0].apply(formatear_sku_excel))

        def calc(row):
            if row[col_sku] in blacklist_set or row['sku_base'] in blacklist_set: return 0
            
            # LÓGICA DE LÍMITES DINÁMICA
            l = limites_editados["RESTO"]
            if row['sku_base'] in hb_set or "HB" in row['familia']: 
                l = limites_editados["HB"]
            elif any(x in row['familia'] for x in ["DESCANSO", "COLCHON", "ALMOHADA"]): 
                l = limites_editados["DESCANSO"]
            elif "JARDIN" in row['familia'] or "JARDÍN" in row['familia']: 
                l = limites_editados["JARDIN"]
            
            if row['stk_f'] < l: return 0
            mult = p_rework if row[col_sku].startswith('S') else p_normal
            return int(np.ceil(row['stk_f'] * mult))

        df_list['quantity'] = df_list.apply(calc, axis=1)

        # SALIDA
        res = pd.DataFrame()
        res['sku'] = df_list[col_sku]
        res['quantity'] = df_list['quantity']
        res['merchant-shipping-group-name'] = df_list[col_msg]
        res['handling-time'] = res['merchant-shipping-group-name'].str.lower().map(ht_mapeo_final).fillna(2).astype(int)

        st.success(f"✅ Proceso finalizado para {store_key}")
        st.dataframe(res.head(10))
        st.download_button("📥 Descargar TXT", res.to_csv(sep='\t', index=False), f"STOCK_{store_key}.txt")