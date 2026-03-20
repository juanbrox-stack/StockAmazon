import streamlit as st
import pandas as pd
import io
import csv
from io import BytesIO

# Configuración inicial
st.set_page_config(page_title="Conversor Inmune a Errores", layout="wide")

def lectura_definitiva(uploaded_file):
    """
    La función de lectura más robusta posible para archivos con errores de formato.
    """
    if uploaded_file is None: return None
    
    # Lista de codificaciones para archivos de Windows/España
    encodings = ['latin-1', 'utf-8', 'cp1252', 'iso-8859-15']
    
    for enc in encodings:
        try:
            # 1. Volver al inicio y leer el contenido bruto para limpiar bytes nulos
            uploaded_file.seek(0)
            content = uploaded_file.read()
            
            # Si es binario, lo decodificamos ignorando errores de caracteres sueltos
            if isinstance(content, bytes):
                text = content.decode(enc, errors='ignore')
            else:
                text = content
            
            # Limpiar caracteres nulos que a veces vienen en exportaciones de SAP/Excel
            text = text.replace('\x00', '')
            
            # 2. Intentar leer usando StringIO para que Pandas no se queje del archivo original
            # on_bad_lines='skip' es la clave para que no falle si una fila está mal
            df = pd.read_csv(
                io.StringIO(text),
                sep=None, 
                engine='python',
                on_bad_lines='skip',
                quoting=csv.QUOTE_NONE # Para que no espere el cierre de comillas "
            )
            
            if df is not None and len(df.columns) > 1:
                return df
        except Exception:
            continue
            
    return None

def generar_excel(uploaded_file):
    df = lectura_definitiva(uploaded_file)
    if df is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        except Exception as e:
            st.error(f"Error al escribir Excel en {uploaded_file.name}: {e}")
    return None

# --- INTERFAZ ---
st.title("📂 Convertidor Multi-Ficheros (Hasta 10)")
st.write("Optimizado para archivos de **Stock Massalaves** y **Listings Amazon**.")

# Subida de archivos (limitamos a 10 por lógica visual)
archivos = st.file_uploader("Arrastra aquí tus archivos (.csv o .txt)", 
                            type=['csv', 'txt'], 
                            accept_multiple_files=True)

if archivos:
    # Seleccionamos solo los primeros 10
    seleccion = archivos[:10]
    if len(archivos) > 10:
        st.warning("⚠️ Solo se muestran los primeros 10 archivos.")

    st.divider()
    
    # Grid de 2 columnas (5 filas x 2 columnas = 10 archivos)
    cols = st.columns(2)
    
    for i, archivo in enumerate(seleccion):
        # El operador % 2 nos ayuda a repartir entre las dos columnas
        with cols[i % 2]:
            with st.container(border=True): # Crea un recuadro para cada archivo
                st.markdown(f"📄 **{archivo.name}**")
                
                excel_data = generar_excel(archivo)
                
                if excel_data:
                    nombre_out = archivo.name.rsplit('.', 1)[0] + ".xlsx"
                    st.download_button(
                        label="📥 Descargar Excel",
                        data=excel_data,
                        file_name=nombre_out,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{i}_{archivo.name}",
                        use_container_width=True
                    )
                else:
                    st.error("❌ Fallo crítico de decodificación")
else:
    st.info("Esperando archivos... Puedes subir hasta 10 a la vez.")