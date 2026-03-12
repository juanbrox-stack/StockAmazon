import streamlit as st
import pandas as pd
import numpy as np
import io

# 1. Función de formateo de SKU (Efecto Excel: =TEXTO(A2;"00000"))
def formatear_sku(sku):
    if pd.isna(sku) or str(sku).strip() == "": return ""
    # Convertimos a string y quitamos el .0 si Excel lo leyó como número
    sku_str = str(sku).strip().split('.')[0]
    if sku_str.isdigit() and len(sku_str) < 5:
        return sku_str.zfill(5)
    return sku_str

# 2. Función de carga segura para Excel
def cargar_excel(file, skip=0):
    if file is None: return None
    try:
        df = pd.read_excel(file, skiprows=skip, dtype=str)
        # Limpiar nombres de columnas
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error al leer {file.name}: {e}")
        return None

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Amazon Stock Manager XL", layout="centered")
st.title("📦 Amazon Stock Pro (Versión Excel)")
st.markdown("---")

# --- PASO 1: CONFIGURACIÓN GENERAL ---
st.header("1️⃣ Configuración de Tienda y Canal")
col_c1, col_c2 = st.columns(2)
with col_c1:
    tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
    pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
    prefijo = pais if pais != "ES" else ""
with col_c2:
    p_normal = st.slider("% Stock Estándar", 0, 100, 80) / 100
    p_rework = st.slider("% Stock Rework (S)", 0, 100, 20) / 100

st.markdown("---")

# --- PASO 2: LÍMITES POR CATEGORÍA ---
st.header("2️⃣ Ajuste de Límites Mínimos")
col_l1, col_l2 = st.columns(2)
with col_l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with col_l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

st.markdown("---")

# --- PASO 3: CARGA SECUENCIAL ---
st.header("3️⃣ Carga de Ficheros (.xlsx)")
f_listing = st.file_uploader("📄 1. Informe Listings Amazon", type=["xlsx"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central ES)", type=["xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx"])

st.subheader("Bloqueos")
f_bl_gen = st.file_uploader("🚫 6. Blacklist GLOBAL", type=["xlsx"])
f_exc_pais = st.file_uploader(f"📍 7. Excepciones {pais}", type=["xlsx"])

st.markdown("---")

# Diccionario de Handling Times por País (Datos de tus capturas)
mapas_ht = {
    "ES": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "DE": {"prime sfp": 0, "fbm hb": 2, "fbm no hb": 3, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "FR": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5},
    "IT": {"prime sfp": 0, "fbm hb": 1, "fbm no hb": 2, "sin tarifa": 10, "lanzamientos": 10, "descatalogados o bloqueados": 5}
}

# --- PROCESAMIENTO ---
if st.button(f"🚀 GENERAR ACTUALIZACIÓN PARA {tienda.upper()} {pais}"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios (Listing, Stock, HB o Auxiliar).")
    else:
        try:
            # Carga de datos
            df_list = cargar_excel(f_listing)
            df_mas = cargar_excel(f_massalaves)
            df_hb_data = cargar_excel(f_hb)
            df_aux_data = cargar_excel(f_aux)
            
            # Identificar columnas clave en Listing
            col_sku = next(c for c in df_list.columns if 'sku' in c)
            col_msg = next(c for c in df_list.columns if 'merchant-shipping-group' in c)

            # Preparar HB y Blacklists
            skus_hb = set(df_hb_data.iloc[:, 0].apply(formatear_sku).tolist()) if df_hb_data is not None else set()
            bloqueados = set()
            if f_bl_gen:
                df_bg = cargar_excel(f_bl_gen)
                bloqueados.update(df_bg.iloc[:, 0].apply(formatear_sku).dropna().tolist())
            if f_exc_pais:
                # Salto de 2 filas para España/Italia según tus ficheros
                skip_val = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
                df_ep = cargar_excel(f_exc_pais, skip=skip_val)
                bloqueados.update(df_ep.iloc[:, 0].apply(formatear_sku).dropna().tolist())

            df_local = cargar_excel(f_pais)

            # --- LÓGICA DE CRUCE DE STOCK ---
            def procesar_fila(row):
                sku_amz = str(row[col_sku]).strip()
                sku_base = sku_amz[len(prefijo):] if prefijo and sku_amz.startswith(prefijo) else sku_amz
                sku_f = formatear_sku(sku_base)
                
                # Decidir almacén
                fich = df_local if (prefijo and sku_amz.startswith(prefijo) and df_local is not None) else df_mas
                col_stk = next(c for c in fich.columns if 'disponible' in c or 'operativo' in c)
                col_ref = next(c for c in fich.columns if 'referencia' in c or 'sku' in c)
                
                match = fich[fich[col_ref].apply(formatear_sku) == sku_f]
                stk = float(str(match[col_stk].values[0]).replace(',', '.')) if not match.empty else 0.0
                return pd.Series([sku_f, stk, sku_f.startswith('S')])

            df_list[['sku_f', 'stk_b', 'es_s']] = df_list.apply(procesar_fila, axis=1)

            # --- UNIR FAMILIAS ---
            df_aux_data['sku_f_aux'] = df_aux_data.iloc[:, 0].apply(formatear_sku)
            col_fam_name = df_aux_data.columns[2]
            df_list = df_list.merge(df_aux_data[['sku_f_aux', col_fam_name]], left_on='sku_f', right_on='sku_f_aux', how='left')
            df_list['familia'] = df_list[col_fam_name].fillna('Resto')

            # --- CÁLCULO FINAL ---
            def calculo_final(row):
                sku_a, sku_f, fam = row[col_sku], row['sku_f'], str(row['familia'])
                es_hb = sku_a in skus_hb or sku_f in skus_hb or "HB" in fam
                
                if sku_a in bloqueados or sku_f in bloqueados:
                    return 0, "Descatalogados o bloqueados", 5
                
                # Selección de límite
                if es_hb: lim = lim_hb
                elif "Descanso" in fam or "Colchones" in fam: lim = lim_colchones
                elif "Jardín" in fam: lim = lim_jardin
                else: lim = lim_resto
                
                qty = 0
                if row['stk_b'] >= lim:
                    factor = p_rework if row['es_s'] else p_normal
                    qty = int(np.ceil(row['stk_b'] * factor))
                
                if qty == 0:
                    return 0, "Descatalogados o bloqueados", 5
                
                msg = str(row[col_msg]).strip()
                ht = mapas_ht[pais].get(msg.lower(), 2)
                return qty, msg, ht

            df_list[['quantity', 'msg_f', 'ht_f']] = df_list.apply(lambda r: pd.Series(calculo_final(r)), axis=1)

            # --- SALIDA ---
            final = df_list[[col_sku, 'quantity', 'msg_f', 'ht_f']]
            final.columns = ['sku', 'quantity', 'merchant-shipping-group-name', 'handling-time']
            
            st.success("✅ Procesamiento completado.")
            st.dataframe(final.head(20))
            
            output = io.StringIO()
            final.to_csv(output, sep='\t', index=False)
            st.download_button(f"📥 Descargar STOCK_{tienda}_{pais}.txt", output.getvalue(), f"STOCK_{tienda}_{pais}.txt")

        except Exception as e:
            st.error(f"Error técnico: {e}")