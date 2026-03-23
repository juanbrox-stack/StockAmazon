import streamlit as st
import pandas as pd
import io
import csv
import chardet # Librería para detectar la codificación automáticamente
from io import BytesIO

st.set_page_config(page_title="Conversor Pro (Columnas Limpias)", layout="wide")

def detectar_y_leer(uploaded_file):
    """
    Detecta automáticamente la codificación (UTF-8, Latin-1, etc.)
    para que las tildes y eñes salgan perfectas.
    """
    if uploaded_file is None: return None
    
    # 1. Leer una muestra del archivo para detectar la codificación
    raw_data = uploaded_file.read(10000)
    resultado = chardet.detect(raw_data)
    encoding_detectado = resultado['encoding']
    
    # Si no detecta nada claro, probamos los estándares
    if not encoding_detectado:
        encoding_detectado = 'utf-8'

    try:
        uploaded_file.seek(0)
        content = uploaded_file.read().decode(encoding_detectado, errors='replace')
        
        # Limpiar caracteres nulos
        content = content.replace('\x00', '')
        
        # 2. Leer con Pandas
        # Usamos engine='python' y sep=None para que detecte si es ; o tabulador solo
        df = pd.read_csv(
            io.StringIO(content),
            sep=None,
            engine='python',
            on_bad_lines='skip',
            quoting=csv.QUOTE_NONE
        )
        return df
    except Exception as e:
        # Si falla el detectado, intento de emergencia en latin-1
        try:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep=None, engine='python', encoding='latin-1', on_bad_lines='skip')
        except:
            st.error(f"Error al procesar {uploaded_file.name}")
            return None

def generar_excel(uploaded_file):
    df = detectar_y_leer(uploaded_file)
    if df is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        except Exception as e:
            return None
    return None

# --- INTERFAZ ---
st.title("📂 Conversor de Excel con Columnas Limpias")
st.write("Corrige automáticamente tildes y caracteres extraños (Ã³, Ã¡, etc.)")

archivos = st.file_uploader("Sube tus archivos (Máx 10)", type=['csv', 'txt'], accept_multiple_files=True)

if archivos:
    seleccion = archivos[:10]
    st.divider()
    
    cols = st.columns(2)
    for i, archivo in enumerate(seleccion):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"📄 **{archivo.name}**")
                
                excel_data = generar_excel(archivo)
                
                if excel_data:
                    nombre_out = archivo.name.rsplit('.', 1)[0] + ".xlsx"
                    st.download_button(
                        label="📥 Descargar Excel Limpio",
                        data=excel_data,
                        file_name=nombre_out,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{i}",
                        use_container_width=True
                    )
                else:
                    st.error("No se pudo procesar correctamente")