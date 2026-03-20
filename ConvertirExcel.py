import streamlit as st
import pandas as pd
import io
import csv
from io import BytesIO

st.set_page_config(page_title="Convertidor Pro a Excel", page_icon="🚀")

def lectura_super_robusta(uploaded_file):
    """
    Intenta todas las estrategias posibles para leer el archivo,
    incluyendo limpieza de líneas corruptas.
    """
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-15']
    
    for enc in encodings:
        try:
            uploaded_file.seek(0)
            # Intento 1: Detección automática de separador
            return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc)
        except Exception:
            try:
                # Intento 2: Ignorando comillas (típico fallo en listings de Amazon)
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc, quoting=csv.QUOTE_NONE)
            except Exception:
                try:
                    # Intento 3: Forzar punto y coma (típico de Massalaves/Excel España)
                    uploaded_file.seek(0)
                    return pd.read_csv(uploaded_file, sep=';', engine='python', encoding=enc, on_bad_lines='skip')
                except Exception:
                    continue
    return None

def generar_excel(uploaded_file):
    df = lectura_super_robusta(uploaded_file)
    if df is not None:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()
    return None

# --- INTERFAZ ---
st.title("🚀 Convertidor de Archivos Críticos")
st.write("Esta versión incluye limpieza de errores para archivos como **StockMassalaves**.")

archivos = st.file_uploader("Sube tus archivos .csv o .txt", type=['csv', 'txt'], accept_multiple_files=True)

if archivos:
    for i, archivo in enumerate(archivos):
        with st.container():
            col_nom, col_btn = st.columns([3, 1])
            with col_nom:
                st.markdown(f"**{archivo.name}**")
            
            with col_btn:
                data = generar_excel(archivo)
                if data:
                    st.download_button(
                        label="📥 Descargar",
                        data=data,
                        file_name=archivo.name.rsplit('.', 1)[0] + ".xlsx",
                        key=f"btn_{i}"
                    )
                else:
                    st.error("Error crítico")

st.divider()
st.info("💡 **Consejo:** Si un archivo sigue fallando, es probable que tenga caracteres 'nulos' o esté bloqueado por otro programa.")