import streamlit as st
import pandas as pd
import io
import csv
from io import BytesIO

# Configuración de página
st.set_page_config(page_title="Conversor Multi-Ficheros Pro", page_icon="📂", layout="wide")

def lectura_infalible(uploaded_file):
    """
    Intenta leer el archivo con múltiples estrategias y limpieza de caracteres.
    """
    if uploaded_file is None:
        return None
    
    # Prioridad de codificaciones para evitar errores de acentos (Francia, Italia, Massalaves)
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-15']
    
    for enc in encodings:
        try:
            uploaded_file.seek(0)
            # Detección automática de separador (tab, punto y coma, coma)
            return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc)
        except Exception:
            try:
                # Intento ignorando comillas (crucial para Listings de Amazon)
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc, quoting=csv.QUOTE_NONE)
            except Exception:
                continue
    
    return None

def generar_excel(uploaded_file):
    df = lectura_infalible(uploaded_file)
    if df is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        except Exception as e:
            st.error(f"Error técnico en {uploaded_file.name}: {e}")
    return None

# --- INTERFAZ ---
st.title("📂 Convertidor Universal (Hasta 10 archivos)")
st.write("Sube tus reportes de Amazon o Stocks de Massalaves/Países para convertirlos a Excel al instante.")

# Limitamos visualmente y por lógica a 10 archivos
archivos = st.file_uploader(
    "Selecciona hasta 10 archivos (.csv o .txt)", 
    type=['csv', 'txt'], 
    accept_multiple_files=True
)

if archivos:
    # Solo procesamos los primeros 10 si el usuario sube más
    lista_archivos = archivos[:10]
    
    if len(archivos) > 10:
        st.warning("⚠️ Has subido más de 10 archivos. Solo se mostrarán los primeros 10.")

    st.divider()
    
    # Creamos una cuadrícula de 2 columnas para que quepan 5 filas (10 archivos en total)
    cols = st.columns(2)
    
    for i, archivo in enumerate(lista_archivos):
        # Alternamos entre columna 0 y 1
        with cols[i % 2]:
            with st.expander(f"📄 {archivo.name}", expanded=True):
                data_excel = generar_excel(archivo)
                
                if data_excel:
                    nombre_salida = archivo.name.rsplit('.', 1)[0] + ".xlsx"
                    st.download_button(
                        label=f"Descargar Excel",
                        data=data_excel,
                        file_name=nombre_salida,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"btn_{i}_{archivo.name}",
                        use_container_width=True # El botón ocupa todo el ancho de la columna
                    )
                else:
                    st.error("No se pudo decodificar. Revisa el formato.")

else:
    st.info("Estatus: Esperando ficheros... (Puedes arrastrar varios a la vez)")

# Resumen técnico opcional


with st.sidebar:
    st.header("Instrucciones")
    st.write("1. Arrastra tus archivos.")
    st.write("2. Aparecerá un cuadro por cada uno (máx. 10).")
    st.write("3. Haz clic en descargar.")
    st.markdown("---")
    st.caption("Optimizado para archivos con tildes y formatos de Amazon.")