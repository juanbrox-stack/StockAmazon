import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import io
from datetime import datetime

# --- 1. CONFIGURACIÓN DE PERSISTENCIA ---
CONFIG_FILE = "amazon_config.json"

def cargar_config_pro():
    """Carga la configuración guardada o devuelve una por defecto."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "blacklist": "112, 1509, 3909, IT112",
        "ht": {
            "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Envlo gratuito": 1, "Fitness": 1, "No prime": 1, "Prime Nacional": 0, "Envío estandar": 3},
            "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 3, "Preventa": 5},
            "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5, "Envio 10 dias": 5, "Portes gratuitos": 2},
            "IT": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 2, "Sin tarifa": 5, "Lanzamientos": 10, "Descatalogados o bloqueados": 5, "Almacenpais": 1, "Preventa": 5}
        }
    }

def guardar_config_pro(blacklist_text, ht_dict):
    """Guarda los cambios en el archivo JSON local."""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"blacklist": blacklist_text, "ht": ht_dict}, f, indent=4)

# --- 2. FUNCIONES DE PROCESAMIENTO ---
def formatear_sku_excel(val):
    """Lógica Excel: =TEXTO(A2; '00000')."""
    if pd.isna(val) or str(val).strip() == "": return ""
    val_str = str(val).strip().split('.')[0] # Limpiar decimales .0
    if val_str.isdigit():
        return val_str.zfill(5)
    return val_str

def cargar_excel_pro(file, skip=0):
    if file is None: return None
    try:
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

# --- 3. INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Amazon Stock Manager Pro", layout="wide")

# Inicializar configuración en la sesión
if 'config' not in st.session_state:
    st.session_state.config = cargar_config_pro()

st.title("📦 Amazon Stock & Rework Manager")

# --- PANEL LATERAL / SUPERIOR DE CONTROL ---
with st.sidebar:
    st.header("⚙️ Configuración Global")
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100
    
    if st.button("💾 GUARDAR TODO (Memoria Permanente)"):
        st.session_state.config["blacklist"] = st.session_state.temp_bl
        guardar_config_pro(st.session_state.temp_bl, st.session_state.config["ht"])
        st.success("¡Configuración guardada!")

# --- CUERPO PRINCIPAL ---
col_main, col_bl = st.columns([2, 1])

with col_bl:
    st.subheader("🚫 Blacklist Editable")
    bl_txt = st.text_area("SKUs a bloquear (un SKU por línea o comas):", 
                          value=st.session_state.config["blacklist"], 
                          height=250, key="temp_bl")
    # Procesar la lista de bloqueo para el motor
    blacklist_set = set([formatear_sku_excel(x.strip()) for x in bl_txt.replace('\n', ',').split(',') if x.strip()])

with col_main:
    st.subheader("⏱️ Handling Times (Tiempos de Preparación)")
    ht_pais = st.session_state.config["ht"].get(pais, {})
    ht_actualizados = {}
    
    with st.expander(f"Editar tiempos para {pais}", expanded=False):
        c_ht = st.columns(2)
        for i, (msg, val) in enumerate(ht_pais.items()):
            nuevo_v = c_ht[i % 2].number_input(msg, value=int(val), key=f"ht_inp_{pais}_{msg}")
            ht_actualizados[msg.lower()] = nuevo_v
            # Actualizar en memoria de sesión
            st.session_state.config["ht"][pais][msg] = nuevo_v

    st.subheader("📤 Carga de Ficheros")
    f_list_file = st.file_uploader("1. Informe Listings Amazon (.xlsx)", type=["xlsx"])
    f_mas_file = st.file_uploader("2. Stock Massalaves (Central ES)", type=["xlsx"])
    f_loc_file = st.file_uploader(f"3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
    
    with st.expander("Ficheros Auxiliares (HB, Familias)"):
        f_hb_file = st.file_uploader("4. Fichero Heavy & Bulky (HB)", type=["xlsx"])
        f_aux_file = st.file_uploader("5. Auxiliar Plytix (Familias)", type=["xlsx"])

# --- 4. MOTOR DE CÁLCULO ---
if st.button("🚀 GENERAR FICHERO DE STOCK"):
    if not (f_list_file and f_mas_file and f_hb_file and f_aux_file):
        st.error("Por favor, sube todos los archivos obligatorios.")
    else:
        # Cargar datos
        df_list = cargar_excel_pro(f_list_file)
        df_mas = cargar_excel_pro(f_mas_file)
        df_local = cargar_excel_pro(f_loc_file)
        df_hb_data = cargar_excel_pro(f_hb_file)
        df_aux_data = cargar_excel_pro(f_aux_file)

        # Filtro FBA
        col_ff = next((c for c in df_list.columns if 'fulfillment-channel' in c), None)
        if col_ff: df_list = df_list[df_list[col_ff] != "AMAZON_EU"].copy()

        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        # --- LÓGICA DE CRUCE (SKU ESPEJO) ---
        df_list['is_s'] = df_list[col_sku].str.startswith('S')
        
        def extraer_base(sku):
            s = str(sku).upper()
            if s.startswith('S'): s = s[1:]
            for p in ['FR', 'IT', 'DE']:
                if s.startswith(p): s = s[len(p):]
            return s

        df_list['sku_f_busqueda'] = df_list[col_sku].apply(extraer_base).apply(formatear_sku_excel)
        
        # Crear mapas de stock
        def create_stk_map(df):
            if df is None: return pd.Series()
            c_ref = next(c for c in df.columns if any(x in c for x in ['referencia', 'sku']))
            c_stk = next(c for c in df.columns if any(x in c for x in ['disponible', 'operativo']))
            df['key'] = df[c_ref].apply(formatear_sku_excel)
            df['stk_val'] = df[c_stk].astype(str).str.replace(',', '.').replace('nan', '0')
            return df.drop_duplicates('key').set_index('key')['stk_val']

        map_mas = create_stk_map(df_mas)
        map_loc = create_stk_map(df_local)

        # Asignar Stock Base
        df_list['use_local'] = df_list[col_sku].str.contains(f"^{pais}|^S{pais}", case=False, na=False) & (df_local is not None)
        
        df_list['stk_b'] = 0.0
        df_list.loc[df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(map_loc).fillna("0").astype(float)
        df_list.loc[~df_list['use_local'], 'stk_b'] = df_list['sku_f_busqueda'].map(map_mas).fillna("0").astype(float)

        # Bloqueos (Panel de Blacklist)
        # Comprobamos tanto el SKU de Amazon como el SKU base
        df_list['bloqueado'] = (
            df_list[col_sku].apply(formatear_sku_excel).isin(blacklist_set) | 
            df_list['sku_f_busqueda'].isin(blacklist_set)
        )

        # Límites por familia
        df_aux_data['key_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku_excel)
        fam_map = df_aux_data.drop_duplicates('key_aux').set_index('key_aux').iloc[:, 1]
        df_list['familia'] = df_list['sku_f_busqueda'].map(fam_map).fillna("RESTO").str.upper()

        lim_hb, lim_col, lim_jar, lim_rest = 15, 10, 10, 40 # Valores base
        skus_hb_list = set(df_hb_data.iloc[:, 0].apply(formatear_sku_excel))

        def calc_qty(row):
            if row['bloqueado']: return 0
            # Definir límite
            l = lim_rest
            if row[col_sku] in skus_hb_list or row['sku_f_busqueda'] in skus_hb_list or "HB" in row['familia']: l = lim_hb
            elif "DESCANSO" in row['familia']: l = lim_col
            elif "JARDIN" in row['familia'] or "JARDÍN" in row['familia']: l = lim_jar
            
            if row['stk_b'] < l: return 0
            mult = p_rework if row['is_s'] else p_normal
            return int(np.ceil(row['stk_b'] * mult))

        df_list['quantity'] = df_list.apply(calc_qty, axis=1)

        # Formatear Salida
        final = pd.DataFrame()
        final['sku'] = df_list[col_sku] # El SKU original con su S o prefijo
        final['quantity'] = df_list['quantity']
        final['merchant-shipping-group-name'] = df_list[col_msg]
        # Asignar HT desde el diccionario actualizado
        final['handling-time'] = final['merchant-shipping-group-name'].str.lower().map(ht_actualizados).fillna(2).astype(int)

        st.divider()
        st.subheader("✅ Resultado Final")
        st.dataframe(final.head(15), use_container_width=True)
        
        # Descarga
        tsv = final.to_csv(sep='\t', index=False)
        fecha_str = datetime.now().strftime("%Y%m%d")
        st.download_button(
            label=f"📥 Descargar STOCK_{tienda}_{pais}.txt",
            data=tsv,
            file_name=f"{fecha_str}_STOCK_{tienda}_{pais}.txt",
            mime="text/plain"
        )

# --- 5. NOTA PARA EL USUARIO ---
st.info("💡 RECUERDA: Si añades SKUs a la Blacklist o cambias los tiempos, pulsa el botón 'GUARDAR TODO' en la barra lateral para que la app lo recuerde siempre.")