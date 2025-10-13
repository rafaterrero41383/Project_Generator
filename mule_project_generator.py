import streamlit as st
import zipfile
import os
import shutil
import tempfile
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI
import time

# --- Configuración inicial ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Interfaz ---
st.set_page_config(page_title="Generador Optimizado de Proyecto Mulesoft", layout="centered")
st.title("🧠 Generador Optimizado de Proyecto Mulesoft")
st.markdown("""
Sube un archivo `.raml` o `.docx` (DTM) y el sistema reescribirá automáticamente los archivos relevantes del arquetipo Mulesoft  
usando el modelo rápido `gpt-3.5-turbo`, reescritura selectiva y un registro de cambios.
""")

# --- Cargar archivo de entrada ---
uploaded_file = st.file_uploader("📂 Carga tu archivo (.raml o .docx):", type=["raml", "docx"])

if uploaded_file:
    file_extension = uploaded_file.name.split(".")[-1].lower()
    st.write(f"**Archivo detectado:** `{uploaded_file.name}` ({file_extension.upper()})")

    with tempfile.TemporaryDirectory() as temp_dir:
        arquetipo_path = os.path.join(temp_dir, "arquetipo")
        os.makedirs(arquetipo_path, exist_ok=True)

        arquetipo_zip_path = os.path.join(os.getcwd(), "arquetipo-mulesoft.zip")
        if not os.path.exists(arquetipo_zip_path):
            st.error(f"❌ No se encontró el archivo del arquetipo en: {arquetipo_zip_path}")
            st.stop()

        # Descomprimir arquetipo base
        with zipfile.ZipFile(arquetipo_zip_path, "r") as zip_ref:
            zip_ref.extractall(arquetipo_path)
        st.success("✅ Arquetipo base cargado correctamente.")

        # Leer contenido del archivo cargado
        if file_extension == "raml":
            content = uploaded_file.read().decode("utf-8", errors="ignore")
        elif file_extension == "docx":
            doc = Document(uploaded_file)
            content = "\n".join([p.text for p in doc.paragraphs])
        else:
            st.error("Tipo de archivo no soportado.")
            st.stop()

        st.subheader("📘 Vista previa del contenido cargado:")
        st.text_area("Vista previa", content[:2000], height=200)

        if st.button("🚀 Generar Proyecto"):
            st.info("✏️ Reescribiendo archivos relevantes del arquetipo con los datos detectados...")

            result_log = ""
            modified_files = []

            # Extensiones relevantes
            extensiones_permitidas = (".xml", ".raml", ".yaml", ".yml", ".properties", ".md", ".txt")

            # Obtener lista total de archivos relevantes
            archivos_relevantes = [
                os.path.join(root, file_name)
                for root, _, files in os.walk(arquetipo_path)
                for file_name in files
                if file_name.endswith(extensiones_permitidas)
            ]

            total_archivos = len(archivos_relevantes)
            progreso = st.progress(0)
            progreso_texto = st.empty()

            for i, file_path in enumerate(archivos_relevantes, start=1):
                file_name = os.path.basename(file_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        original = f.read()

                    # Prompt optimizado
                    file_prompt = f"""
                    Tienes el siguiente archivo de un proyecto Mulesoft llamado `{file_name}`.
                    Reescríbelo de acuerdo al diseño técnico o RAML proporcionado.
                    Mantén el formato original y la estructura del archivo.
                    No inventes rutas ni endpoints que no existan.
                    Si no se requiere cambio, devuelve el mismo contenido sin alterar.

                    Contenido original:
                    ---
                    {original[:2000]}
                    ---

                    Contexto del microservicio:
                    ---
                    {content[:4000]}
                    ---
                    Devuelve únicamente el nuevo contenido del archivo, sin explicaciones adicionales.
                    """

                    # Llamada al modelo
                    response = client.chat.completions.create(  # type: ignore
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "Asistente experto en proyectos Mulesoft."},
                            {"role": "user", "content": file_prompt}
                        ],
                        temperature=0.3
                    )

                    new_content = response.choices[0].message.content.strip()

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    modified_files.append(file_name)
                    result_log += f"✅ {file_name} modificado correctamente.\n"

                except Exception as e:
                    result_log += f"⚠️ Error modificando {file_name}: {e}\n"

                # Actualizar progreso visual
                progreso.progress(i / total_archivos)
                progreso_texto.text(f"Procesando archivo {i} de {total_archivos}: {file_name}")

                # Pequeña pausa para refrescar la interfaz sin congelar Streamlit
                time.sleep(0.2)

            progreso_texto.text("✅ Procesamiento completo.")
            progreso.progress(1.0)

            # Crear log de modificaciones
            log_path = os.path.join(arquetipo_path, "log_modificaciones.txt")
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write("🧠 Registro de archivos modificados en el arquetipo Mulesoft\n")
                log_file.write("==========================================================\n\n")
                for file_name in modified_files:
                    log_file.write(f"- {file_name}\n")
                log_file.write("\n\nResumen del proceso:\n")
                log_file.write(result_log)

            st.success("🎉 Archivos relevantes reescritos exitosamente.")
            st.text_area("📄 Detalle de modificaciones", result_log, height=300)

            # Comprimir en ZIP
            output_zip_path = os.path.join(temp_dir, "proyecto_generado.zip")
            shutil.make_archive(output_zip_path.replace(".zip", ""), 'zip', arquetipo_path)

            # Descargar resultado
            with open(output_zip_path, "rb") as f:
                st.download_button(
                    label="⬇️ Descargar Proyecto Generado (.zip)",
                    data=f,
                    file_name="proyecto_generado.zip",
                    mime="application/zip"
                )

            st.info("🗒️ Se añadió un archivo `log_modificaciones.txt` dentro del ZIP con el registro detallado de cambios.")
