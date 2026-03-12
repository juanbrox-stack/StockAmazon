import streamlit as st
import pandas as pd
import numpy as np
import io

# Función para formatear SKU a 5 dígitos (=Texto(A2;"00000"))
def formatear_sku(sku):
    sku_str = str(sku).strip()
    if sku_str.isdigit() and len(sku_str) < 5:
        return sku_str.zfill(5)
    return sku_str

# Función de carga inteligente con detección de codificación
def cargar_smart(file, sep=';'):
    if file is None: return None
    if file.name.endswith('.xlsx'):
        return pd.read_excel(file, dtype=str)
    for encoding in ['utf-8', 'ISO-8859-1', 'latin1', 'cp1252']:
        try:
            file.seek(0)
            return pd.read_csv(file, sep=sep, dtype=str, encoding=encoding)
        except: continue
    return None

st.set_page_config(page_title="Amazon Stock Manager", layout="centered")

st.title("📦 Actualizador de Stock Amazon")
st.markdown("---")

# --- PASO 1: CONFIGURACIÓN DE TIENDA ---
st.header("1️⃣ Selección de Tienda y País")
tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
prefijo = pais if pais != "ES" else ""
st.markdown("---")

# --- PASO 2: CONFIGURACIÓN DE LÍMITES ---
st.header("2️⃣ Configuración de Límites")
col_l1, col_l2 = st.columns(2)
with col_l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with col_l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)
st.markdown("---")

# --- PASO 3: CARGA DE FICHEROS (SECUENCIAL) ---
st.header("3️⃣ Carga de Ficheros")

f_listing = st.file_uploader("📄 1. Informe de todos los listings (Amazon .txt)", type=["txt"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central ES)", type=["csv", "xlsx"])

f_pais = None
if pais != "ES":
    f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["csv", "xlsx"])

f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx", "csv"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx", "csv"])

st.subheader("Bloqueos y Excepciones")
f_bl_gen = st.file_uploader("🚫 6. Blacklist GLOBAL (Todas las tiendas)", type=["xlsx", "csv"])
f_exc_pais = st.file_uploader(f"📍 7. Excepciones Específicas {pais}", type=["xlsx", "csv"])

st.markdown("---")

# --- PASO 4: PROCESAMIENTO ---
if st.button(f"🚀 GENERAR ACTUALIZACIÓN PARA {tienda.upper()}"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Por favor, sube los archivos obligatorios (Listing, Massalaves, HB y Auxiliar).")
    else:
        try:
            # Carga de datos
            df_list = cargar_smart(f_listing, sep='\t')
            df_mas = cargar_smart(f_massalaves, sep=';')
            df_hb_data = cargar_smart(f_hb)
            df_aux_data = cargar_smart(f_aux, sep=',')
            
            # Preparar sets de control con formato 00000
            skus_hb = set(df_hb_data.iloc[:, 0].apply(formatear_sku).tolist())
            
            # Procesar Blacklist Global
            bloqueados = set()
            if f_bl_gen:
                df_bg = pd.read_excel(f_bl_gen, dtype=str) if f_bl_gen.name.endswith('xlsx') else cargar_smart(f_bl_gen)
                bloqueados.update(df_bg.iloc[:, 0].apply(formatear_sku).dropna().tolist())
            
            # Procesar Excepciones País (con salto de filas si es necesario)
            if f_exc_pais:
                skip = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
                df_ep = pd.read_excel(f_exc_pais, skiprows=skip, dtype=str) if f_exc_pais.name.endswith('xlsx') else cargar_smart(f_exc_pais)
                bloqueados.update(df_ep.iloc[:, 0].apply(formatear_sku).dropna().tolist())

            df_local = cargar_smart(f_pais, sep=';')

            # Lógica de Cruce de Stock (Modo Espejo)
            def cruce_datos(row):
                sku_amz = str(row['seller-sku'])
                sku_clean = sku_amz[len(prefijo):] if prefijo and sku_amz.startswith(prefijo) else sku_amz
                sku_f = formatear_sku(sku_clean)
                
                # Almacén
                fich = df_local if (prefijo and sku_amz.startswith(prefijo) and df_local is not None) else df_mas
                col = 'StockDisponible' if fich is not None and 'StockDisponible' in fich.columns else 'Stock Operativo'
                
                match = fich[fich['Referencia'].apply(formatear_sku) == sku_f] if fich is not None else pd.DataFrame()
                val = float(match[col].values[0].replace(',','.')) if not match.empty else 0
                return pd.Series([sku_f, val, sku_f.startswith('S')])

            df_list[['sku_f', 'stk_bruto', 'is_rework']] = df_list.apply(cruce_datos, axis=1)

            # Unir Familias
            df_aux_data['SKU_F'] = df_aux_data['SKU'].apply(formatear_sku)
            df_list = df_list.merge(df_aux_data[['SKU_F', 'Familia']], left_on='sku_f', right_on='SKU_F', how='left')
            df_list['Familia'] = df_list['Familia'].fillna('Resto')

            # Cálculo de Quantity Final
            def calc_qty(row):
                if row['seller-sku'] in bloqueados or row['sku_f'] in bloqueados:
                    return 0
                
                fam = str(row['Familia'])
                es_hb = row['seller-sku'] in skus_hb or row['sku_f'] in skus_hb or "HB" in fam
                
                lim = lim_hb if es_hb else (lim_colchones if "Descanso" in fam or "Colchones" in fam else (lim_jardin if "Jardín" in fam else lim_resto))
                
                if row['stk_bruto'] >= lim:
                    factor = 0.20 if row['is_rework'] else 0.80
                    return int(np.ceil(row['stk_bruto'] * factor))
                return 0

            df_list['new_qty'] = df_list.apply(calc_qty, axis=1)

            # Construcción del Fichero Final (Respetando datos de Amazon)
            resultado = pd.DataFrame()
            resultado['sku'] = df_list['seller-sku'].apply(formatear_sku)
            resultado['quantity'] = df_list['new_qty']
            
            # Capturar Plantilla y Handling del archivo original
            resultado['merchant-shipping-group-name'] = df_list['merchant-shipping-group'] if 'merchant-shipping-group' in df_list.columns else "FBM NO HB"
            
            # Buscar columna de tiempo
            col_ht = next((c for c in df_list.columns if 'handling-time' in c or 'leadtime' in c), None)
            resultado['handling-time'] = df_list[col_ht] if col_ht else 2

            st.success("✅ Procesamiento completado.")
            st.dataframe(resultado.head(20))

            csv_txt = resultado.to_csv(sep='\t', index=False)
            st.download_button(f"📥 Descargar STOCK_{tienda}_{pais}.txt", csv_txt, f"STOCK_{tienda}_{pais}.txt")

        except Exception as e:
            st.error(f"Error técnico durante el proceso: {e}")