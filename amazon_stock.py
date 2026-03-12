import streamlit as st
import pandas as pd
import numpy as np
import io

# Función para asegurar el formato de 5 dígitos (Excel: =TEXTO(A2;"00000"))
def formatear_sku(sku):
    sku_str = str(sku).strip().replace('"', '').replace("'", "")
    # Si es numérico y corto, rellenamos con ceros.
    if sku_str.isdigit() and len(sku_str) < 5:
        return sku_str.zfill(5)
    return sku_str

# Función de carga ultra-robusta
def cargar_archivo(file, sep=';'):
    if file is None: return None
    if file.name.endswith('.xlsx'):
        return pd.read_excel(file, dtype=str)
    # Probamos varios encodings y separadores para evitar el error utf-8
    for enc in ['ISO-8859-1', 'utf-8', 'latin1', 'cp1252']:
        try:
            file.seek(0)
            df = pd.read_csv(file, sep=sep, dtype=str, encoding=enc)
            # Limpiamos posibles espacios o comillas en los nombres de columnas
            df.columns = [c.strip().replace('"', '') for c in df.columns]
            return df
        except:
            continue
    return None

st.set_page_config(page_title="Amazon Stock Manager", layout="centered")
st.title("📦 Actualizador de Stock Amazon")

# 1. CONFIGURACIÓN
tienda = st.selectbox("Tienda", ["Jabiru", "Turaco", "Marabu"])
pais = st.selectbox("País de Destino", ["ES", "IT", "FR", "DE"])
prefijo = pais if pais != "ES" else ""

# 2. LÍMITES
col_l1, col_l2 = st.columns(2)
with col_l1:
    lim_hb = st.number_input("Heavy & Bulky (HB) >=", value=15)
    lim_colchones = st.number_input("Colchones/Descanso >=", value=10)
with col_l2:
    lim_jardin = st.number_input("Jardín >=", value=10)
    lim_resto = st.number_input("Resto de catálogo >=", value=40)

# 3. CARGA SECUENCIAL (INTERFAZ LIMPIA)
f_listing = st.file_uploader("📄 1. Informe Listings Amazon (.txt)", type=["txt"])
f_massalaves = st.file_uploader("🏢 2. Stock Massalaves (Central ES)", type=["csv", "xlsx"])
f_pais = st.file_uploader(f"🌍 3. Stock Local {pais}", type=["csv", "xlsx"]) if pais != "ES" else None
f_hb = st.file_uploader("🐘 4. Fichero Heavy & Bulky (HB)", type=["xlsx", "csv"])
f_aux = st.file_uploader("🏷️ 5. Auxiliar Plytix (Familias)", type=["xlsx", "csv"])
f_bl_gen = st.file_uploader("🚫 6. Blacklist GLOBAL", type=["xlsx", "csv"])
f_exc_pais = st.file_uploader(f"📍 7. Excepciones {pais}", type=["xlsx", "csv"])

# MAPEO DE HANDLING TIME POR PAÍS (Según tus últimas capturas)
mapa_ht = {
    "ES": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5},
    "DE": {"PRIME SFP": 0, "FBM HB": 2, "FBM NO HB": 3, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5},
    "FR": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5},
    "IT": {"PRIME SFP": 0, "FBM HB": 1, "FBM NO HB": 2, "Sin tarifa": 10, "Lanzamientos": 10, "Descatalogados o bloqueados": 5}
}

if st.button(f"🚀 GENERAR STOCK {tienda.upper()} {pais}"):
    if not (f_listing and f_massalaves and f_hb and f_aux):
        st.error("Faltan archivos obligatorios.")
    else:
        try:
            # Cargamos listing con tabulador
            df_list = cargar_archivo(f_listing, sep='\t')
            # Cargamos stock con punto y coma
            df_mas = cargar_archivo(f_massalaves, sep=';')
            # Cargamos el resto
            df_hb_data = cargar_archivo(f_hb, sep=';')
            df_aux_data = cargar_archivo(f_aux, sep=',') # Plytix suele ser coma

            # 1. Preparar SKUs de control
            skus_hb = set(df_hb_data.iloc[:, 0].apply(formatear_sku).tolist()) if df_hb_data is not None else set()
            
            # Unificar Blacklists
            bloqueados = set()
            if f_bl_gen:
                df_bg = cargar_archivo(f_bl_gen)
                if df_bg is not None: bloqueados.update(df_bg.iloc[:, 0].apply(formatear_sku).tolist())
            if f_exc_pais:
                skip = 2 if any(n in f_exc_pais.name for n in ["Espan", "Italia"]) else 0
                df_ep = pd.read_excel(f_exc_pais, skiprows=skip, dtype=str) if f_exc_pais.name.endswith('xlsx') else cargar_archivo(f_exc_pais)
                if df_ep is not None: bloqueados.update(df_ep.iloc[:, 0].apply(formatear_sku).tolist())

            df_local = cargar_archivo(f_pais, sep=';')

            # 2. Función de cruce de stock mejorada
            def buscar_stock(row):
                sku_amz = str(row['seller-sku']).strip()
                # Quitar prefijo (IT, FR, DE) si lo tiene para buscar en el stock físico
                sku_limpio = sku_amz[len(prefijo):] if prefijo and sku_amz.startswith(prefijo) else sku_amz
                sku_f = formatear_sku(sku_limpio)
                
                # Decidir origen: Almacén local o Massalaves
                fich = df_local if (prefijo and sku_amz.startswith(prefijo) and df_local is not None) else df_mas
                
                # Identificar columna de stock (G o última)
                col_stk = 'StockDisponible' if 'StockDisponible' in fich.columns else 'Stock Operativo'
                
                # Búsqueda exacta aplicando formato a la columna de referencia del stock
                match = fich[fich['Referencia'].apply(formatear_sku) == sku_f]
                
                if not match.empty:
                    val_str = str(match[col_stk].values[0]).replace(',', '.')
                    return pd.Series([sku_f, float(val_str), sku_f.startswith('S')])
                else:
                    return pd.Series([sku_f, 0.0, sku_f.startswith('S')])

            df_list[['sku_f', 'stk_bruto', 'es_s']] = df_list.apply(buscar_stock, axis=1)

            # 3. Unir Familias (Plytix)
            df_aux_data['SKU_F_AUX'] = df_aux_data.iloc[:, 0].apply(formatear_sku)
            # Buscamos la columna 'Familia' (normalmente la C / índice 2)
            col_familia = df_aux_data.columns[2]
            df_list = df_list.merge(df_aux_data[['SKU_F_AUX', col_familia]], left_on='sku_f', right_on='SKU_F_AUX', how='left')
            df_list['Familia'] = df_list[col_familia].fillna('Resto')

            # 4. Lógica de cálculo y asignación de HT por plantilla
            def calcular_final(row):
                sku_amz = row['seller-sku']
                sku_f = row['sku_f']
                fam = str(row['Familia'])
                es_hb = sku_amz in skus_hb or sku_f in skus_hb or "HB" in fam
                
                # BLOQUEO O STOCK 0
                if sku_amz in bloqueados or sku_f in bloqueados:
                    return 0, "Descatalogados o bloqueados", 5
                
                # Definir límite
                lim = lim_hb if es_hb else (lim_colchones if ("Descanso" in fam or "Colchones" in fam) else (lim_jardin if "Jardín" in fam else lim_resto))
                
                # Cálculo de unidades (80% operativo o 20% rework)
                if row['stk_bruto'] >= lim:
                    factor = 0.20 if row['es_s'] else 0.80
                    qty = int(np.ceil(row['stk_bruto'] * factor))
                    msg = row['merchant-shipping-group'] if 'merchant-shipping-group' in row else "FBM NO HB"
                    ht = mapa_ht[pais].get(msg, 2)
                    return qty, msg, ht
                else:
                    # Si no llega al límite mínimo
                    return 0, "Descatalogados o bloqueados", 5

            df_list[['quantity', 'msg_final', 'ht_final']] = df_list.apply(lambda r: pd.Series(calcular_final(r)), axis=1)

            # 5. Generar Salida
            final = df_list[['seller-sku', 'quantity', 'msg_final', 'ht_final']]
            final.columns = ['sku', 'quantity', 'merchant-shipping-group-name', 'handling-time']
            
            st.success(f"✅ ¡Proceso finalizado! Los SKUs están formateados y el handling-time aplicado por país.")
            st.dataframe(final.head(30))
            
            # Descarga
            txt = final.to_csv(sep='\t', index=False)
            st.download_button(f"📥 Descargar STOCK_{tienda}_{pais}.txt", txt, f"STOCK_{tienda}_{pais}.txt")

        except Exception as e:
            st.error(f"Se produjo un error durante el cálculo: {e}")