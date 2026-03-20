import streamlit as st
import pandas as pd
from io import BytesIO

# Configuración de la interfaz
st.set_page_config(page_title="Convertidor Universal a Excel", page_icon="📈")

st.title("📊 Convertidor Multiformato a Excel")
st.markdown("""
Esta herramienta detecta automáticamente el separador de tus archivos:
* **CSV** (comas, punto y coma)
* **TXT** (Tabulaciones/Listings de Amazon)
* **JSON**
""")

# Ampliamos los tipos de archivos aceptados
uploaded_files = st.file_uploader(
    "Sube o arrastra tus ficheros (.csv, .txt, .json)", 
    type=["csv", "txt", "json"], 
    accept_multiple_files=True
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        try:
            # Lógica de lectura inteligente
            if uploaded_file.name.endswith('.json'):
                df = pd.read_json(uploaded_file)
            else:
                # 'sep=None' hace que Pandas detecte el separador automáticamente
                # 'engine=python' es necesario para que funcione la autodetección
                df = pd.read_csv(uploaded_file, sep=None, engine='python')

            st.success(f"✅ Se han cargado {len(df)} filas de '{uploaded_file.name}'")

            # Conversión a binario para descarga
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            
            excel_data = output.getvalue()
            nombre_descarga = uploaded_file.name.rsplit('.', 1)[0] + ".xlsx"

            st.download_button(
                label=f"📥 Descargar {nombre_descarga}",
                data=excel_data,
                file_name=nombre_descarga,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"❌ Error al procesar {uploaded_file.name}: {e}")