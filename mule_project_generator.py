import os
import shutil
import tempfile
import time
import zipfile

import streamlit as st
from PIL import Image
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI

# --- Configuración inicial ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Generador de Proyectos Mulesoft", layout="centered")

# --- CSS visual ---
st.markdown("""
<style>
body {
    background-color: #f5f6fa !important;
}

/* Ventana blanca del chat */
.main-window {
    background-color: #fff;
    border-radius: 20px;
    box-shadow: 0 8px 25px rgba(0,0,0,0.08);
    padding: 60px 50px; /* más alto para que la barra quede más abajo */
    margin-top: 40px;
    max-width: 900px;
    margin-left: auto;
    margin-right: auto;
}

/* Contenedor del clip */
.clip-wrapper {
    position: relative;
    width: 42px;  /* reducido para alineación con barra */
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
}

/* Imagen del clip */
.clip-img {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    object-fit: cover;
    transition: transform 0.2s ease-in-out;
    box-shadow: 0 3px 8px rgba(0,0,0,0.1);
    cursor: pointer;
}

/* Hover animado */
.clip-img:hover {
    transform: scale(1.05);
}

/* Check animado */
.checkmark {
    position: absolute;
    top: -5px;
    right: -5px;
    font-size: 18px;
    color: #32CD32;
    opacity: 0;
    animation: popFade 1s ease-in-out forwards;
    z-index: 15;
}

@keyframes popFade {
    0% { opacity: 0; transform: scale(0.5) rotate(-20deg); }
    25% { opacity: 1; transform: scale(1.2) rotate(10deg); }
    60% { opacity: 1; transform: scale(1) rotate(0deg); }
    100% { opacity: 0; transform: scale(0.8) rotate(-10deg); }
}

/* Ocultar uploader nativo */
div[data-testid="stFileUploader"] {
    position: absolute;
    opacity: 0;
    width: 42px;
    height: 42px;
    cursor: pointer;
    z-index: 10;
}

/* Espaciado del input */
[data-testid="stChatInput"] {
    margin-top: 30px;
}
</style>
""", unsafe_allow_html=True)

# --- Encabezado ---
st.markdown("""
<div style="text-align: center; margin-top: -30px;">
    <h1 style="font-size: 40px;">🤖 Generador de Proyectos Mulesoft</h1>
    <p style="color: #666; font-size: 18px; margin-top: 10px;">
        Carga tu archivo <code>.raml</code> o <code>.docx</code> para empezar a generar el proyecto.
    </p>
</div>
""", unsafe_allow_html=True)

# --- Contenedor principal ---
st.markdown('<div class="main-window">', unsafe_allow_html=True)

# --- Estado global seguro ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None
if "show_check" not in st.session_state:
    st.session_state.show_check = False

# --- Mostrar historial del chat ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Layout del chat ---
col1, col2 = st.columns([0.07, 0.93])

with col1:
    st.markdown('<div class="clip-wrapper">', unsafe_allow_html=True)

    # Clip visible (imagen)
    possible_icons = ["clip_icon.png", "clip.jpeg", "clip.jpg"]
    icon_path = next((f for f in possible_icons if os.path.exists(f)), None)

    if icon_path:
        img = Image.open(icon_path)
        st.image(img, use_container_width=True)
    else:
        st.warning("⚠️ No se encontró la imagen del clip. Asegúrate de tener 'clip.jpeg' o 'clip_icon.png' en la raíz del proyecto.")

    # File uploader (funcional al hacer clic en el área del clip)
    uploaded = st.file_uploader("", type=["raml", "docx"], label_visibility="collapsed", key="uploader")

    if uploaded:
        st.session_state.uploaded_file = uploaded
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded.name}` recibido y listo para procesar."
        })
        st.session_state.show_check = True

    if st.session_state.show_check:
        st.markdown('<div class="checkmark">✅</div>', unsafe_allow_html=True)
        st.session_state.show_check = False

    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    user_input = st.chat_input("Escribe tu mensaje o pide generar el proyecto...")

# --- Procesamiento del mensaje ---
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

                # Leer archivo
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

st.markdown("</div>", unsafe_allow_html=True)
