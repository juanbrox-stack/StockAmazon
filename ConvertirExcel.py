import streamlit as st
import pandas as pd
import io
import csv
from io import BytesIO

# Configuración de página
st.set_page_config(page_title="Conversor Excel Limpio", layout="wide")

def limpieza_comillas(df):
    """
    Elimina las comillas dobles sobrantes que aparecen al principio 
    y al final de las celdas de texto.
    """
    # Aplicar limpieza a todas las celdas de tipo texto
    return df.applymap(lambda x: x.strip('"') if isinstance(x, str) else x)

def lectura_inteligente(uploaded_file):
    """
    Lee archivos probando UTF-8 y Latin-1, detectando errores de tildes
    y separadores automáticamente.
    """
    if uploaded_file is None: return None
    
    for enc in ['utf-8', 'latin-1', 'cp1252']:
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read().decode(enc)
            
            # Cargamos el DataFrame
            df = pd.read_csv(
                io.StringIO(content),
                sep=None, 
                engine='python',
                on_bad_lines='skip',
                quoting=csv.QUOTE_NONE # Necesario para que no falle la lectura inicial
            )
            
            # Verificación de tildes/eñes (Ã es el síntoma de error en UTF-8)
            columnas_texto = "".join(df.columns.astype(str))
            if 'Ã' in columnas_texto or 'Â' in columnas_texto:
                continue 
            
            # LIMPIEZA DE COMILLAS: Una vez leído, quitamos las " de los datos
            df = limpieza_comillas(df)
            # También limpiamos las comillas de los nombres de las columnas
            df.columns = [col.strip('"') for col in df.columns]
                
            return df
        except:
            continue
    return None

def generar_excel(uploaded_file):
    df = lectura_inteligente(uploaded_file)
    if df is not None:
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
        except:
            return None
    return None

# --- INTERFAZ ---
st.title("📂 Conversor a Excel (Sin Comillas)")
st.write("Limpia automáticamente tildes (Ã³) y elimina las comillas dobles ( \" ) de las filas.")

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
                        key=f"dl_{i}_{archivo.name}",
                        use_container_width=True
                    )
                else:
                    st.error("Error al procesar el archivo")