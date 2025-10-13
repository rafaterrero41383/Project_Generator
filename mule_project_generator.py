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

# --- Interfaz de chat ---
st.set_page_config(page_title="ChatMuleGPT", layout="centered")
st.title("🤖 ChatMuleGPT – Generador de Proyectos Mulesoft")
st.caption("Sube tu archivo `.raml` o `.docx` con el 📎 y conversa con el asistente mientras genera tu proyecto.")

# --- Estado del chat ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None

# --- Mostrar historial del chat ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Botón de clip (uploader) ---
col1, col2 = st.columns([0.1, 0.9])
with col1:
    uploaded = st.file_uploader("📎", type=["raml", "docx"], label_visibility="collapsed", key="uploader")
    if uploaded:
        st.session_state.uploaded_file = uploaded
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded.name}` recibido y listo para procesar."
        })
        st.rerun()

with col2:
    user_input = st.chat_input("Escribe tu mensaje o pide generar el proyecto...")

# --- Procesar mensaje del usuario ---
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()

        # Validar archivo cargado
        if not st.session_state.uploaded_file:
            placeholder.markdown("📎 Por favor, adjunta primero un archivo `.raml` o `.docx` usando el clip.")
        else:
            uploaded_file = st.session_state.uploaded_file
            file_extension = uploaded_file.name.split(".")[-1].lower()

            with tempfile.TemporaryDirectory() as temp_dir:
                arquetipo_path = os.path.join(temp_dir, "arquetipo")
                os.makedirs(arquetipo_path, exist_ok=True)

                arquetipo_zip_path = os.path.join(os.getcwd(), "arquetipo-mulesoft.zip")
                if not os.path.exists(arquetipo_zip_path):
                    st.error(f"❌ No se encontró el archivo del arquetipo en: {arquetipo_zip_path}")
                    st.stop()

                # Descomprimir arquetipo
                with zipfile.ZipFile(arquetipo_zip_path, "r") as zip_ref:
                    zip_ref.extractall(arquetipo_path)

                # Leer contenido del archivo
                if file_extension == "raml":
                    content = uploaded_file.read().decode("utf-8", errors="ignore")
                elif file_extension == "docx":
                    doc = Document(uploaded_file)
                    content = "\n".join([p.text for p in doc.paragraphs])
                else:
                    placeholder.markdown("⚠️ Tipo de archivo no soportado.")
                    st.stop()

                placeholder.markdown(f"🧩 Procesando `{uploaded_file.name}` y reescribiendo archivos del arquetipo...")

                result_log = ""
                modified_files = []
                extensiones_permitidas = (".xml", ".raml", ".yaml", ".yml", ".properties", ".md", ".txt")

                archivos_relevantes = [
                    os.path.join(root, f)
                    for root, _, files in os.walk(arquetipo_path)
                    for f in files if f.endswith(extensiones_permitidas)
                ]

                total = len(archivos_relevantes)
                progreso = st.progress(0)
                progreso_texto = st.empty()

                for i, file_path in enumerate(archivos_relevantes, start=1):
                    file_name = os.path.basename(file_path)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            original = f.read()

                        prompt = f"""
                        Tienes el siguiente archivo de un proyecto Mulesoft llamado `{file_name}`.
                        Reescríbelo según el archivo RAML/DTM adjunto. Mantén formato y estructura.
                        Si no hay cambios, devuelve el mismo contenido sin modificar.

                        Contenido original:
                        ---
                        {original[:2000]}
                        ---

                        Contexto técnico:
                        ---
                        {content[:4000]}
                        ---
                        Devuelve solo el nuevo contenido, sin explicaciones.
                        """

                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "Asistente experto en proyectos Mulesoft."},
                                {"role": "user", "content": prompt}
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

                    progreso.progress(i / total)
                    progreso_texto.text(f"Procesando archivo {i}/{total}: {file_name}")
                    time.sleep(0.1)

                progreso_texto.text("✅ Todos los archivos procesados.")
                progreso.progress(1.0)

                # Crear log
                log_path = os.path.join(arquetipo_path, "log_modificaciones.txt")
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write("🧠 Archivos modificados en el arquetipo Mulesoft:\n\n")
                    for f in modified_files:
                        log.write(f"- {f}\n")
                    log.write("\n---\n")
                    log.write(result_log)

                # Comprimir
                zip_out = os.path.join(temp_dir, "proyecto_generado.zip")
                shutil.make_archive(zip_out.replace(".zip", ""), 'zip', arquetipo_path)

                with open(zip_out, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Proyecto Generado (.zip)",
                        f,
                        file_name="proyecto_generado.zip",
                        mime="application/zip"
                    )

                response_text = "🎉 Proyecto generado exitosamente. Puedes descargar el ZIP con los archivos actualizados."
                placeholder.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
