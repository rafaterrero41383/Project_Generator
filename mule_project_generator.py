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

# --- Interfaz principal ---
st.set_page_config(page_title="ChatMuleGPT", layout="centered")

# --- CSS personalizado: reemplaza el uploader por botón circular con clip ---
st.markdown("""
<style>
/* Ocultar texto y bordes del uploader original */
div[data-testid="stFileUploader"] {
    border: none !important;
    background: transparent !important;
}
div[data-testid="stFileUploaderDropzone"] {
    border: none !important;
    background: transparent !important;
    text-align: center !important;
    height: 44px !important;
    width: 44px !important;
    border-radius: 50% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: background-color 0.3s ease, transform 0.15s ease-in-out;
    cursor: pointer !important;
    color: #666 !important;
}
div[data-testid="stFileUploaderDropzone"] div {
    visibility: hidden;
}
div[data-testid="stFileUploaderDropzone"]::before {
    content: "📎";
    font-size: 22px;
    visibility: visible;
    color: inherit;
}
div[data-testid="stFileUploaderDropzone"]:hover {
    transform: scale(1.1);
    background-color: rgba(0, 0, 0, 0.05);
}
div[data-testid="stFileUploaderDropzone"].uploaded {
    background-color: #3adb76 !important; /* Verde suave */
    color: white !important;
    transform: scale(1.05);
}
</style>
""", unsafe_allow_html=True)

# --- Encabezado ---
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

# --- Layout del chat: clip + input ---
col1, col2 = st.columns([0.08, 0.92])

with col1:
    # Clip minimalista
    uploaded = st.file_uploader("", type=["raml", "docx"], label_visibility="collapsed", key="uploader")
    clip_placeholder = st.empty()
    if uploaded:
        # Guardar archivo y marcar éxito visual
        st.session_state.uploaded_file = uploaded
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded.name}` recibido y listo para procesar."
        })
        # Inyectar script que colorea el clip al verde
        st.markdown("""
        <script>
        const dropzones = parent.document.querySelectorAll('div[data-testid="stFileUploaderDropzone"]');
        if (dropzones.length) {
            dropzones[0].classList.add('uploaded');
        }
        </script>
        """, unsafe_allow_html=True)
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

                log_path = os.path.join(arquetipo_path, "log_modificaciones.txt")
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write("🧠 Archivos modificados:\n\n")
                    for f in modified_files:
                        log.write(f"- {f}\n")
                    log.write("\n---\n")
                    log.write(result_log)

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
