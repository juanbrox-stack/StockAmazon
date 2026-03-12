import streamlit as st
import pandas as pd
import numpy as np
import io

# 1. Función de formateo de SKU (Excel: =TEXTO(A2;"00000"))
def formatear_sku(sku):
    if pd.isna(sku) or sku == "": return ""
    sku_str = str(sku).strip().replace('"', '').replace("'", "")
    if sku_str.isdigit() and len(sku_str) < 5:
        return sku_str.zfill(5)
    return sku_str

# 2. Función de carga ultra-robusta
def cargar_smart(file, sep_pref=';'):
    if file is None: return None
    if file.name.endswith('.xlsx'):
        return pd.read_excel(file, dtype=str)
    
    # Probamos combinaciones de separadores y encodings
    for s in [sep_pref, '\t', ',', ';']:
        for enc in ['ISO-8859-1', 'utf-8', 'latin1', 'cp1252']:
            try:
                file.seek(0)
                df = pd.read_csv(file, sep=s, dtype=str, encoding=enc)
                if len(df.columns) > 1:
                    df.columns = [c.strip().lower() for c in df.columns]
                    return df
            except:
                continue
    return None

st.set_page_config(page_title="Amazon Stock Manager", layout="centered")
st.title("📦 Actualizador de Stock Amazon")

# --- PASO 1: CONFIGURACIÓN Y PORCENTAJES ---
st.header("1️⃣ Configuración y Porcentajes")
col_cfg1, col_cfg2 = st.columns(2)
with col_cfg1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
    prefijo = pais if pais != "ES" else ""
with col_cfg2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

# --- PASO 2: LÍMITES ---
st.header("2️⃣ Límites de Stock")
c_l1, c_l2 = st.columns(2)
with c_l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with c_l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

# --- PASO 3: CARGA SECUENCIAL ---
st.header("3️⃣ Carga de Ficheros")
f_listing = st.file_uploader("📄 1. Informe Listings Amazon (.txt)", type=["txt"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central ES)", type=["csv", "xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["csv", "xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx", "csv"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx", "csv"])
f_ht_custom = st.file_uploader(f"⏱️ 6. Fichero Handling Times {pais}", type=["xlsx", "csv"])
f_bl_gen = st.file_uploader("🚫 7. Blacklist GLOBAL", type=["xlsx", "csv"])
f_exc_pais = st.file_uploader(f"📍 8. Excepciones {pais}", type=["xlsx", "csv"])

# Valores HT por defecto (tus capturas)
mapas_defecto = {
    "ES": {"prime sfp": "0", "fbm hb": "1", "fbm no hb": "2", "sin tarifa": "10", "lanzamientos": "10", "descatalogados o bloqueados": "5"},
    "DE": {"prime sfp": "0", "fbm hb": "2", "fbm no hb": "3", "sin tarifa": "10", "lanzamientos": "10", "descatalogados o bloqueados": "5"},
    "FR": {"prime sfp": "0", "fbm hb": "1", "fbm no hb": "2", "sin tarifa": "10", "lanzamientos": "10", "descatalogados o bloqueados": "5"},
    "IT": {"prime sfp": "0", "fbm hb": "1", "fbm no hb": "2", "sin tarifa": "10", "lanzamientos": "10", "descatalogados o bloqueados": "5"}
}

if st.button(f"🚀 GENERAR STOCK {tienda.upper()} {pais}"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios (Listing, Massalaves, HB y Auxiliar).")
    else:
        try:
            # CARGAS CON VALIDACIÓN
            df_list = cargar_smart(f_listing, sep='\t')
            df_mas = cargar_smart(f_massalaves, sep=';')
            df_hb_data = cargar_smart(f_hb)
            df_aux_data = cargar_smart(f_aux, sep=',')
            
            if df_list is None: st.error("Error al leer el Listing de Amazon."); st.stop()
            if df_mas is None: st.error("Error al leer Stock Massalaves."); st.stop()
            
            # Handling Times
            ht_mapping = mapas_defecto[pais]
            if f_ht_custom:
                df_ht = cargar_smart(f_ht_custom)
                if df_ht is not None:
                    ht_mapping = {str(r[0]).strip().lower(): str(r[1]).strip() for r in df_ht.values}

            # Identificar Columnas
            col_sku_amz = next(c for c in df_list.columns if 'sku' in c)
            col_msg_amz = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

            # Control de HB y Bloqueos
            skus_hb = set(df_hb_data.iloc[:, 0].apply(formatear_sku).tolist()) if df_hb_data is not None else set()
            bloqueados = set()
            if f_bl_gen:
                df_bg = cargar_smart(f_bl_gen)
                if df_bg is not None: bloqueados.update(df_bg.iloc[:, 0].apply(formatear_sku).tolist())
            if f_exc_pais:
                skip = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
                df_ep = pd.read_excel(f_exc_pais, skiprows=skip, dtype=str) if f_exc_pais.name.endswith('xlsx') else cargar_smart(f_exc_pais)
                if df_ep is not None: bloqueados.update(df_ep.iloc[:, 0].apply(formatear_sku).tolist())

            df_local = cargar_smart(f_pais, sep=';')

            # --- CRUCE DE STOCK ---
            def buscar_datos(row):
                sku_amz = str(row[col_sku_amz]).strip()
                sku_clean = sku_amz[len(prefijo):] if prefijo and sku_amz.startswith(prefijo) else sku_amz
                sku_f = formatear_sku(sku_clean)
                
                fich = df_local if (prefijo and sku_amz.startswith(prefijo) and df_local is not None) else df_mas
                # Buscar columna de referencia
                col_ref = next(c for c in fich.columns if 'referencia' in c or 'sku' in c)
                col_stk = next(c for c in fich.columns if 'disponible' in c or 'operativo' in c)
                
                match = fich[fich[col_ref].apply(formatear_sku) == sku_f]
                stk = float(str(match[col_stk].values[0]).replace(',', '.')) if not match.empty else 0.0
                return pd.Series([sku_f, stk, sku_f.startswith('S')])

            df_list[['sku_f', 'stk_b', 'es_s']] = df_list.apply(buscar_datos, axis=1)

            # --- FAMILIAS ---
            df_aux_data['sku_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku)
            col_fam = df_aux_data.columns[2]
            df_list = df_list.merge(df_aux_data[['sku_aux', col_fam]], left_on='sku_f', right_on='sku_aux', how='left')
            df_list['familia'] = df_list[col_fam].fillna('Resto')

            # --- LÓGICA FINAL ---
            def final_row(row):
                sku_a, sku_f, fam = row[col_sku_amz], row['sku_f'], str(row['familia'])
                es_hb = sku_a in skus_hb or sku_f in skus_hb or "HB" in fam
                
                if sku_a in bloqueados or sku_f in bloqueados:
                    return 0, "Descatalogados o bloqueados", ht_mapping.get("descatalogados o bloqueados", 5)
                
                lim = lim_hb if es_hb else (lim_colchones if "Descanso" in fam or "Colchones" in fam else (lim_jardin in fam and lim_jardin or lim_resto))
                qty = int(np.ceil(row['stk_b'] * (p_rework if row['is_s'] else p_normal))) if row['stk_b'] >= lim else 0
                
                msg = str(row[col_msg_amz]).strip() if qty > 0 else "Descatalogados o bloqueados"
                ht = ht_mapping.get(msg.lower(), 2)
                return qty, msg, ht

            df_list[['quantity', 'msg_f', 'ht_f']] = df_list.apply(lambda r: pd.Series(final_row(r)), axis=1)

            final = df_list[[col_sku_amz, 'quantity', 'msg_f', 'ht_f']]
            final.columns = ['sku', 'quantity', 'merchant-shipping-group-name', 'handling-time']
            
            st.success("✅ ¡Procesado!")
            st.dataframe(final.head(20))
            st.download_button("📥 Descargar TXT", final.to_csv(sep='\t', index=False), f"STOCK_{tienda}_{pais}.txt")

        except Exception as e:
            st.error(f"Error técnico durante el cálculo: {e}")