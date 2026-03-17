import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime

# Función optimizada para formatear SKUs
def optimizar_skus(serie):
    return serie.fillna("").astype(str).str.strip().str.split('.').str[0].str.zfill(5).replace("00000", "")

def cargar_excel_pro(file, skip=0):
    if file is None: return None
    try:
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

st.set_page_config(page_title="Amazon Stock & Template Manager", layout="centered")
st.title("🚀 Amazon Stock Pro: Control de Plantillas")

# --- PASO 1: CONFIGURACIÓN Y PORCENTAJES ---
st.header("1️⃣ Configuración y Porcentajes")
col1, col2 = st.columns(2)
with col1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    prefijo = pais if pais != "ES" else ""
with col2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

# --- NUEVA SECCIÓN: REGLAS DE PLANTILLAS ---
st.header("⚙️ Reglas Especiales de Plantilla")
expander = st.expander("Configurar cambios automáticos de plantilla (Opcional)")
with expander:
    st.info("Si no activas estas reglas, se mantendrá la plantilla original del listing.")
    aplicar_regla_cero = st.checkbox("Si el stock calculado es 0, cambiar plantilla")
    plantilla_cero = st.text_input("Nombre de plantilla para stock 0", value="Descatalogados o bloqueados")
    
    aplicar_regla_rework = st.checkbox("Si es Rework (S), forzar plantilla específica")
    plantilla_rework = st.text_input("Nombre de plantilla para Reworks", value="FBM NO HB")

st.header("2️⃣ Límites y Carga")
l1, l2 = st.columns(2)
with l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

f_listing = st.file_uploader("📄 1. Informe Listings Amazon", type=["xlsx"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central)", type=["xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx"])
f_ht_subida = st.file_uploader("⏱️ 6. Fichero HT personalizado (Opcional)", type=["xlsx"])
f_bl_gen = st.file_uploader("🚫 7. Blacklist GLOBAL", type=["xlsx"])
f_exc_pais = st.file_uploader("📍 8. Excepciones País", type=["xlsx"])

# Mapeo Handling Times
mapas_defecto = {
    "ES": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "DE": {"prime sfp": 0, "fbm hb": 2, "fbm no hb": 3, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "FR": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "IT": {"prime sfp": 0, "fbm hb": 2, "fbm no hb": 2, "sin tarifa": 5, "lanzamientos": 10, "descatalogados o bloqueados": 5}
}

if st.button("🚀 GENERAR"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios.")
    else:
        # Carga
        df_list = cargar_excel_pro(f_listing)
        df_mas = cargar_excel_pro(f_massalaves)
        df_hb_data = cargar_excel_pro(f_hb)
        df_aux_data = cargar_excel_pro(f_aux)
        
        col_sku = next(c for c in df_list.columns if 'sku' in c)
        col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

        # 1. Procesar SKUs
        df_list['sku_base'] = df_list[col_sku].str.replace(prefijo, "", 1) if prefijo else df_list[col_sku]
        df_list['sku_f'] = optimizar_skus(df_list['sku_base'])
        
        # 2. Stock y Familias
        df_local = cargar_excel_pro(f_pais)
        fich_stk = df_local if df_local is not None else df_mas
        col_stk = next(c for c in fich_stk.columns if 'disponible' in c or 'operativo' in c)
        col_ref = next(c for c in fich_stk.columns if 'referencia' in c or 'sku' in c)
        
        fich_stk['sku_stk_f'] = optimizar_skus(fich_stk[col_ref])
        df_stk_clean = fich_stk.drop_duplicates('sku_stk_f').set_index('sku_stk_f')[col_stk]
        df_list['stk_b'] = df_list['sku_f'].map(df_stk_clean).fillna("0").str.replace(',', '.').astype(float)
        
        df_aux_data['sku_aux_f'] = optimizar_skus(df_aux_data.iloc[:, 0])
        fam_map = df_aux_data.drop_duplicates('sku_aux_f').set_index('sku_aux_f').iloc[:, 1]
        df_list['familia'] = df_list['sku_f'].map(fam_map).fillna("Resto").astype(str).str.upper()

        # 3. Blacklist
        bl = set()
        if f_bl_gen: bl.update(optimizar_skus(cargar_excel_pro(f_bl_gen).iloc[:,0]))
        if f_exc_pais:
            skip_v = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
            bl.update(optimizar_skus(cargar_excel_pro(f_exc_pais, skip=skip_v).iloc[:,0]))

        # 4. Lógica de Cantidad
        skus_hb = set(optimizar_skus(df_hb_data.iloc[:, 0]))
        df_list['is_s'] = df_list['sku_f'].str.startswith('S')
        
        def get_lim(fam, sku_a, sku_f):
            if sku_a in skus_hb or sku_f in skus_hb or "HB" in fam or "GAE" in fam: return lim_hb
            if "DESCANSO" in fam or "COLCHONES" in fam: return lim_colchones
            if "JARDÍN" in fam or "JARDIN" in fam: return lim_jardin
            return lim_resto

        df_list['limite'] = [get_lim(f, a, s) for f, a, s in zip(df_list['familia'], df_list[col_sku], df_list['sku_f'])]
        df_list['bloqueado'] = df_list[col_sku].isin(bl) | df_list['sku_f'].isin(bl)
        
        df_list['quantity'] = np.where(
            (df_list['stk_b'] >= df_list['limite']) & (~df_list['bloqueado']),
            np.ceil(df_list['stk_b'] * np.where(df_list['is_s'], p_rework, p_normal)).astype(int),
            0
        )

        # 5. LÓGICA DE PLANTILLAS (REPETIR LO DE AMAZON O CAMBIAR)
        df_list['msg_f'] = df_list[col_msg] # Empezamos con la original de Amazon 
        
        if aplicar_regla_cero:
            df_list['msg_f'] = np.where(df_list['quantity'] == 0, plantilla_cero, df_list['msg_f'])
        
        if aplicar_regla_rework:
            df_list['msg_f'] = np.where(df_list['is_s'], plantilla_rework, df_list['msg_f'])

        # 6. Handling Times basados en la plantilla final
        ht_map = mapas_defecto[pais]
        if f_ht_subida:
            df_ht_f = cargar_excel_pro(f_ht_subida)
            ht_map = {str(r[0]).strip().lower(): int(str(r[1]).split('.')[0]) for r in df_ht_f.values}

        df_list['ht_f'] = df_list['msg_f'].str.lower().map(ht_map).fillna(2).astype(int)

        # Salida
        final = df_list[[col_sku, 'quantity', 'msg_f', 'ht_f']]
        final.columns = ['sku', 'quantity', 'merchant-shipping-group-name', 'handling-time']
        
        st.success("✅ Fichero generado respetando las plantillas de Amazon.")
        st.dataframe(final.head(10))
        
        fecha = datetime.now().strftime("%Y%m%d")
        st.download_button(f"📥 Descargar {fecha}_STOCK_{tienda}_{pais}.txt", 
                           final.to_csv(sep='\t', index=False), 
                           f"{fecha}_STOCK_{tienda}_{pais}.txt")