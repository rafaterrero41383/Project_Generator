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

# --- Interfaz tipo chat ---
st.set_page_config(page_title="ChatMuleGPT", layout="centered")
st.title("🤖 ChatMuleGPT – Generador de Proyectos Mulesoft")
st.caption("Sube tu archivo `.raml` o `.docx` (DTM) y conversa con el bot mientras genera tu proyecto automáticamente.")

# Inicializar historial del chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar historial de mensajes
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Subida de archivos ---
uploaded_file = st.file_uploader("📂 Adjunta tu archivo (.raml o .docx):", type=["raml", "docx"])

# --- Entrada del usuario ---
if user_input := st.chat_input("Escribe tu mensaje o pide generar el proyecto..."):
    # Mostrar mensaje del usuario en el chat
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Procesar respuesta del asistente
    with st.chat_message("assistant"):
        message_placeholder = st.empty()

        # Si no hay archivo, responder de manera informativa
        if not uploaded_file:
            response_text = "📎 Por favor, adjunta un archivo `.raml` o `.docx` para generar el proyecto."
            message_placeholder.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
        else:
            # Detectar tipo de archivo
            file_extension = uploaded_file.name.split(".")[-1].lower()
            message_placeholder.markdown(f"🔍 Procesando tu archivo `{uploaded_file.name}`...")

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

                # Leer contenido del archivo cargado
                if file_extension == "raml":
                    content = uploaded_file.read().decode("utf-8", errors="ignore")
                elif file_extension == "docx":
                    doc = Document(uploaded_file)
                    content = "\n".join([p.text for p in doc.paragraphs])
                else:
                    message_placeholder.markdown("⚠️ Tipo de archivo no soportado.")
                    st.stop()

                message_placeholder.markdown("✏️ Reescribiendo archivos del arquetipo con la información detectada...")

                result_log = ""
                modified_files = []
                extensiones_permitidas = (".xml", ".raml", ".yaml", ".yml", ".properties", ".md", ".txt")

                archivos_relevantes = [
                    os.path.join(root, file_name)
                    for root, _, files in os.walk(arquetipo_path)
                    for file_name in files
                    if file_name.endswith(extensiones_permitidas)
                ]

                total_archivos = len(archivos_relevantes)
                progreso = st.progress(0)

                for i, file_path in enumerate(archivos_relevantes, start=1):
                    file_name = os.path.basename(file_path)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            original = f.read()

                        file_prompt = f"""
                        Tienes el siguiente archivo de un proyecto Mulesoft llamado `{file_name}`.
                        Reescríbelo de acuerdo al diseño técnico o RAML proporcionado.
                        Mantén el formato original y estructura.
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

                    progreso.progress(i / total_archivos)
                    time.sleep(0.1)

                progreso.progress(1.0)
                message_placeholder.markdown("✅ Archivos procesados correctamente. Generando proyecto...")

                # Crear log
                log_path = os.path.join(arquetipo_path, "log_modificaciones.txt")
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write("🧠 Registro de archivos modificados en el arquetipo Mulesoft\n")
                    log_file.write("==========================================================\n\n")
                    for file_name in modified_files:
                        log_file.write(f"- {file_name}\n")
                    log_file.write("\n\nResumen del proceso:\n")
                    log_file.write(result_log)

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

                response_text = "🎉 Proyecto Mulesoft generado con éxito. Puedes descargar el ZIP con los archivos actualizados."
                message_placeholder.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
