import streamlit as st
import pandas as pd
import numpy as np
import io

# 1. Función de formateo de SKU (Excel: =TEXTO(A2;"00000"))
def formatear_sku(sku):
    if pd.isna(sku) or str(sku).strip() == "": return ""
    # Convertimos a string y quitamos el .0 por si acaso
    sku_str = str(sku).strip().split('.')[0]
    if sku_str.isdigit() and len(sku_str) < 5:
        return sku_str.zfill(5)
    return sku_str

# 2. Función de carga segura para Excel (.xlsx)
def cargar_excel(file, skip=0):
    if file is None: return None
    try:
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        # Limpiar nombres de columnas y asegurar que todo el contenido sea string
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.fillna("") # Cambiamos los nulos por texto vacío
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Amazon Stock Manager Pro", layout="centered")
st.title("📦 Gestión de Stock y Tiempos (Excel)")

# PASO 1: CONFIGURACIÓN
st.header("1️⃣ Configuración y Porcentajes")
col1, col2 = st.columns(2)
with col1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País", ["ES", "IT", "FR", "DE"])
    prefijo = pais if pais != "ES" else ""
with col2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

# PASO 2: LÍMITES
st.header("2️⃣ Ajuste de Límites")
l1, l2 = st.columns(2)
with l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

# PASO 3: CARGA
st.header("3️⃣ Carga de Ficheros (.xlsx)")
f_listing = st.file_uploader("📄 1. Informe Listings Amazon", type=["xlsx"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central)", type=["xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx"])
f_ht_subida = st.file_uploader("⏱️ 6. Fichero Handling Times (Opcional)", type=["xlsx"])
f_bl_gen = st.file_uploader("🚫 7. Blacklist GLOBAL", type=["xlsx"])
f_exc_pais = st.file_uploader(f"📍 8. Excepciones {pais}", type=["xlsx"])

# Datos en memoria (Capturas)
mapas_defecto = {
    "ES": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "DE": {"prime sfp": 0, "fbm hb": 2, "fbm no hb": 3, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "FR": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "IT": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5}
}

if st.button(f"🚀 GENERAR STOCK {tienda.upper()} {pais}"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios.")
    else:
        try:
            df_list = cargar_excel(f_listing)
            df_mas = cargar_excel(f_massalaves)
            df_hb_data = cargar_excel(f_hb)
            df_aux_data = cargar_excel(f_aux)
            
            # Gestión HT
            ht_actual = mapas_defecto[pais]
            if f_ht_subida:
                df_ht_f = cargar_excel(f_ht_subida)
                if df_ht_f is not None:
                    ht_actual = {str(r[0]).strip().lower(): int(r[1]) for r in df_ht_f.values}

            # Identificar columnas
            col_sku = next(c for c in df_list.columns if 'sku' in c)
            col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

            # HB y Bloqueos
            skus_hb = set(df_hb_data.iloc[:, 0].apply(formatear_sku).tolist())
            bloqueados = set()
            if f_bl_gen:
                df_bg = cargar_excel(f_bl_gen)
                bloqueados.update(df_bg.iloc[:, 0].apply(formatear_sku).dropna().tolist())
            if f_exc_pais:
                skip_v = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
                df_ep = cargar_excel(f_exc_pais, skip=skip_v)
                bloqueados.update(df_ep.iloc[:, 0].apply(formatear_sku).dropna().tolist())

            df_local = cargar_excel(f_pais)

            # CRUCE DE STOCK
            def procesar(row):
                sku_amz = str(row[col_sku]).strip()
                sku_base = sku_amz[len(prefijo):] if prefijo and sku_amz.startswith(prefijo) else sku_amz
                sku_f = formatear_sku(sku_base)
                fich = df_local if (prefijo and sku_amz.startswith(prefijo) and df_local is not None) else df_mas
                col_stk = next(c for c in fich.columns if 'disponible' in c or 'operativo' in c)
                col_ref = next(c for c in fich.columns if 'referencia' in c or 'sku' in c)
                match = fich[fich[col_ref].apply(formatear_sku) == sku_f]
                stk = float(str(match[col_stk].values[0]).replace(',', '.')) if not match.empty else 0.0
                return pd.Series([sku_f, stk, sku_f.startswith('S')])

            df_list[['sku_f', 'stk_b', 'es_s']] = df_list.apply(procesar, axis=1)

            # UNIR FAMILIAS
            df_aux_data['sku_f_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku)
            col_fam = df_aux_data.columns[2]
            df_list = df_list.merge(df_aux_data[['sku_f_aux', col_fam]], left_on='sku_f', right_on='sku_f_aux', how='left')
            df_list['familia'] = df_list[col_fam].astype(str).fillna('Resto')

            # LÓGICA FINAL
            def final_row(row):
                sku_a, sku_f, fam = row[col_sku], row['sku_f'], str(row['familia']).upper()
                # Aquí el error ya no ocurrirá porque 'fam' es string siempre
                es_hb = sku_a in skus_hb or sku_f in skus_hb or "HB" in fam or "GAE" in fam
                
                if sku_a in bloqueados or sku_f in bloqueados:
                    return 0, "Descatalogados o bloqueados", ht_actual.get("descatalogados o bloqueados", 5)
                
                if es_hb: lim = lim_hb
                elif "DESCANSO" in fam or "COLCHONES" in fam: lim = lim_colchones
                elif "JARDÍN" in fam or "JARDIN" in fam: lim = lim_jardin
                else: lim = lim_resto
                
                qty = int(np.ceil(row['stk_b'] * (p_rework if row['es_s'] else p_normal))) if row['stk_b'] >= lim else 0
                msg = str(row[col_msg]).strip() if qty > 0 else "Descatalogados o bloqueados"
                ht = ht_actual.get(msg.lower(), 2)
                return qty, msg, ht

            df_list[['quantity', 'msg_f', 'ht_f']] = df_list.apply(lambda r: pd.Series(final_row(r)), axis=1)
            final = df_list[[col_sku, 'quantity', 'msg_f', 'ht_f']]
            final.columns = ['sku', 'quantity', 'merchant-shipping-group-name', 'handling-time']
            
            st.success("✅ Procesado correctamente.")
            st.dataframe(final.head(20))
            st.download_button("Descargar TXT", final.to_csv(sep='\t', index=False), f"STOCK_{tienda}_{pais}.txt")
        except Exception as e:
            st.error(f"Error en el cálculo: {e}")