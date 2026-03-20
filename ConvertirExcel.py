import streamlit as st
import pandas as pd
import io
import csv
from io import BytesIO

# Configuración de la página
st.set_page_config(page_title="Convertidor Universal a Excel", page_icon="📊")

# --- FUNCIONES DE LECTURA ROBUSTA ---

def robust_read_csv(uploaded_file):
    """
    Intenta leer el archivo probando múltiples codificaciones para evitar 
    errores de 'utf-8' (acentos y caracteres especiales).
    """
    if uploaded_file is None:
        return None
    
    # Lista de codificaciones para archivos de Windows/Excel España/Europa
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-15']
    
    # Si el archivo ya es JSON
    if uploaded_file.name.lower().endswith('.json'):
        try:
            return pd.read_json(uploaded_file)
        except Exception as e:
            st.error(f"Error al leer JSON: {e}")
            return None

    # Para CSV y TXT (Amazon, SAP, etc.)
    for enc in encodings:
        try:
            uploaded_file.seek(0)
            # engine='python' y sep=None detectan automáticamente el separador (tab, punto y coma, coma)
            return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc)
        except Exception:
            try:
                # Segundo intento: Ignorando comillas que suelen venir mal en los listings de Amazon
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc, quoting=csv.QUOTE_NONE)
            except Exception:
                continue # Prueba la siguiente codificación
                
    return None

def convertir_a_excel(uploaded_file):
    """Convierte el DataFrame a un archivo Excel (.xlsx) en memoria"""
    df = robust_read_csv(uploaded_file)
    if df is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        except Exception as e:
            st.error(f"Error al generar el Excel: {e}")
            return None
    return None

# --- INTERFAZ DE USUARIO ---

st.title("📂 Convertidor Universal a Excel")
st.write("Sube cualquier archivo **.csv, .txt (Listing Amazon) o .json** para convertirlo a **.xlsx**.")

# Widget de subida de archivos (admite múltiples a la vez)
archivos_subidos = st.file_uploader(
    "Arrastra o selecciona tus archivos", 
    type=['csv', 'txt', 'json'], 
    accept_multiple_files=True
)

if archivos_subidos:
    st.divider()
    # Crear dos columnas para que los botones de descarga queden ordenados
    cols = st.columns(2)
    
    for i, archivo in enumerate(archivos_subidos):
        with cols[i % 2]:
            st.info(f"📄 {archivo.name}")
            excel_data = convertir_a_excel(archivo)
            
            if excel_data:
                # Generar nombre de salida cambiando la extensión a .xlsx
                nombre_salida = archivo.name.rsplit('.', 1)[0] + ".xlsx"
                
                st.download_button(
                    label=f"📥 Descargar {nombre_salida}",
                    data=excel_data,
                    file_name=nombre_salida,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"btn_{archivo.name}_{i}"
                )
            else:
                st.error(f"No se pudo procesar: {archivo.name}")
    
    st.success(f"¡Procesados {len(archivos_subidos)} archivos!")
else:
    st.info("💡 Esperando archivos para procesar...")

# Pie de página informativo
with st.expander("ℹ️ Información sobre formatos"):
    st.write("""
    - **Listings de Amazon:** Los archivos .txt separados por tabuladores se procesan automáticamente.
    - **Archivos de Stock:** Detecta separadores `;` y `,` habituales en archivos de logística.
    - **Codificación:** Resuelve errores de acentos (Latin-1/UTF-8).
    """)