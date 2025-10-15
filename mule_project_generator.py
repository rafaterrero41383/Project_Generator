import os
import shutil
import tempfile
import time
import zipfile
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# =====================
# CONFIGURACIÓN INICIAL
# =====================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="Generador de Proyectos Mulesoft", layout="wide")

# =====================
# CSS
# =====================
st.markdown("""
<style>
    .st-emotion-cache-16txtl3, #MainMenu { display: none; }
    .st-emotion-cache-z5fcl4 { padding-top: 2rem; }
    .chat-message { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
    .user-message { flex-direction: row-reverse; }
    .avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; }
    .message-bubble { padding: 14px 18px; border-radius: 18px; max-width: 85%; word-wrap: break-word; line-height: 1.4; }
    .user-bubble { background-color: #e3f2fd; border: 1px solid #bbdefb; }
    .assistant-bubble { background-color: #f1f0f0; border: 1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

# =====================
# ESTADO GLOBAL
# =====================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None
if "processing_triggered" not in st.session_state:
    st.session_state.processing_triggered = False

# =====================
# AVATARES
# =====================
assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

# =====================
# ENCABEZADO
# =====================
st.markdown("<h1 style='text-align:center;'>🤖 Generador de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

# =====================
# BOTÓN DE REINICIO
# =====================
if st.button("🔄 Reiniciar aplicación"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# =====================
# CARGA DE ARCHIVO
# =====================
uploaded_file = st.file_uploader("1️⃣ Adjunta tu archivo de especificaciones (.raml o .docx)", type=["raml", "docx"])
if uploaded_file:
    if not st.session_state.uploaded_file or st.session_state.uploaded_file["name"] != uploaded_file.name:
        st.session_state.uploaded_file = {
            "name": uploaded_file.name,
            "content": uploaded_file.read()
        }
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded_file.name}` cargado correctamente. Describe qué tipo de proyecto Mulesoft deseas crear."
        })
        st.rerun()

# =====================
# CHAT CON HISTORIAL
# =====================
with st.container():
    for msg in st.session_state.messages:
        avatar = user_avatar if msg["role"] == "user" else assistant_avatar
        bubble_class = "user-bubble" if msg["role"] == "user" else "assistant-bubble"
        message_class = "user-message" if msg["role"] == "user" else "assistant-message"
        st.markdown(
            f'<div class="chat-message {message_class}">'
            f'<img src="{avatar}" class="avatar">'
            f'<div class="message-bubble {bubble_class}">{msg["content"]}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

# =====================
# FUNCIÓN PARA CREAR EL PROYECTO
# =====================
def generar_proyecto_mulesoft(prompt_text, archivo_usuario):
    arquetipo_path = os.path.join(os.getcwd(), "mulesoft_archetype")

    if not os.path.exists(arquetipo_path):
        raise FileNotFoundError("No se encontró la carpeta 'mulesoft_archetype' en el proyecto.")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_name = prompt_text.strip().replace(" ", "_").lower()
        project_path = os.path.join(tmpdir, project_name)

        shutil.copytree(arquetipo_path, project_path)

        st.session_state.messages.append({"role": "assistant", "content": "📂 Creando estructura base del proyecto..."})
        time.sleep(1)

        # Guardar el archivo del usuario dentro del proyecto
        input_ext = os.path.splitext(archivo_usuario["name"])[1].lower()
        if input_ext == ".raml":
            dest_path = os.path.join(project_path, "src", "main", "resources", "api")
            os.makedirs(dest_path, exist_ok=True)
            with open(os.path.join(dest_path, archivo_usuario["name"]), "wb") as f:
                f.write(archivo_usuario["content"])
        else:
            dest_path = os.path.join(project_path, "docs")
            os.makedirs(dest_path, exist_ok=True)
            with open(os.path.join(dest_path, archivo_usuario["name"]), "wb") as f:
                f.write(archivo_usuario["content"])

        st.session_state.messages.append({"role": "assistant", "content": "🧩 Insertando archivo en la estructura del proyecto..."})
        time.sleep(1)

        # Personalizar el POM.xml (nombre del proyecto)
        pom_path = os.path.join(project_path, "pom.xml")
        if os.path.exists(pom_path):
            with open(pom_path, "r", encoding="utf-8") as f:
                pom_text = f.read()
            pom_text = pom_text.replace("{{project_name}}", project_name)
            with open(pom_path, "w", encoding="utf-8") as f:
                f.write(pom_text)

        st.session_state.messages.append({"role": "assistant", "content": "⚙️ Personalizando archivos del arquetipo..."})
        time.sleep(1)

        # Crear ZIP del proyecto resultante
        zip_path = os.path.join(tmpdir, f"{project_name}.zip")
        shutil.make_archive(zip_path.replace(".zip", ""), "zip", project_path)

        with open(zip_path, "rb") as zf:
            zip_bytes = zf.read()

        st.session_state.messages.append({"role": "assistant", "content": "✅ Proyecto Mulesoft generado correctamente."})
        return zip_bytes

# =====================
# LÓGICA DE PROCESAMIENTO
# =====================
if st.session_state.processing_triggered:
    try:
        zip_data = generar_proyecto_mulesoft(st.session_state.messages[-1]["content"], st.session_state.uploaded_file)
        st.session_state.generated_zip = zip_data
    except Exception as e:
        st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {e}"})
    st.session_state.processing_triggered = False
    st.rerun()

# =====================
# DESCARGA
# =====================
if "generated_zip" in st.session_state and st.session_state.generated_zip:
    st.download_button(
        "⬇️ Descargar Proyecto Mulesoft (.zip)",
        st.session_state.generated_zip,
        "proyecto_mulesoft.zip",
        "application/zip"
    )
    del st.session_state.generated_zip

# =====================
# CHAT INPUT
# =====================
if user_input := st.chat_input("Describe qué tipo de proyecto Mulesoft deseas generar..."):
    if not st.session_state.uploaded_file:
        st.toast("⚠️ Primero adjunta un archivo de especificación (.raml o .docx).", icon="⚠️")
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.processing_triggered = True
        st.rerun()
