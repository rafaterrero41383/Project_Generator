import os
import shutil
import tempfile
import time
import zipfile
import streamlit as st
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI
import base64

# --- Configuración inicial (sin cambios) ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="Generador de Proyectos Mulesoft", layout="wide")

# --- CSS Simplificado ---
st.markdown("""
<style>
    /* Ocultar elementos de la UI de Streamlit (opcional, sin cambios) */
    .st-emotion-cache-16txtl3, #MainMenu { display: none; }
    .st-emotion-cache-z5fcl4 { padding-top: 2rem; }

    /* Estilos del chat (burbujas, avatares) - Esto se queda */
    .chat-message { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 16px; }
    .user-message { flex-direction: row-reverse; }
    .avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; }
    .message-bubble { padding: 14px 18px; border-radius: 18px; max-width: 85%; word-wrap: break-word; line-height: 1.4; }
    .user-bubble { background-color: #e3f2fd; border: 1px solid #bbdefb; }
    .assistant-bubble { background-color: #f1f0f0; border: 1px solid #ddd; }

    /* --- CORRECCIÓN CLAVE 1: Asegurar que el contenedor del chat no se desborde --- */
    /* Hacemos que el contenedor principal sea flexible y ocupe el espacio vertical disponible */
    .st-emotion-cache-1jicfl2 {
        flex: 1 1 0%;
        overflow: hidden;
    }

</style>
""", unsafe_allow_html=True)

# --- Estado global (sin cambios) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file_details" not in st.session_state:
    st.session_state.uploaded_file_details = None
if "processing_triggered" not in st.session_state:
    st.session_state.processing_triggered = False

# --- Avatares (sin cambios) ---
assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

# --- Encabezado ---
st.markdown("<h1 style='text-align: center;'>🤖 Generador de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

# --- REORGANIZACIÓN DE LA INTERFAZ ---
uploaded_file = st.file_uploader(
    "1. Adjunta tu archivo de especificaciones (.raml o .docx)",
    type=["raml", "docx"]
)
if uploaded_file:
    if st.session_state.uploaded_file_details is None or st.session_state.uploaded_file_details[
        "name"] != uploaded_file.name:
        st.session_state.uploaded_file_details = {"name": uploaded_file.name, "content": uploaded_file.read()}
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded_file.name}` adjuntado. Ahora, describe qué proyecto quieres crear."
        })
        st.rerun()

# --- Contenedor para el historial de chat ---
# <--- CORRECCIÓN CLAVE 2: Eliminar la altura fija del contenedor.
# Al no especificar una altura, el contenedor crecerá con su contenido,
# pero el CSS que añadimos evitará que se desborde de la pantalla.
chat_container = st.container()
with chat_container:
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

# --- Lógica de procesamiento --
if st.session_state.processing_triggered:
    with st.spinner("Generando el proyecto... por favor, espera."):
        time.sleep(3)  # Simulación
        # Simulación de la creación de un ZIP
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmpfile:
            with zipfile.ZipFile(tmpfile.name, 'w') as zf:
                zf.writestr("info.txt", "Este es un proyecto generado.")
            tmpfile.seek(0)
            st.session_state.generated_zip = tmpfile.read()
        st.session_state.messages.append(
            {"role": "assistant", "content": "¡Proyecto generado! Puedes descargarlo a continuación."})
        st.session_state.processing_triggered = False
        st.rerun()

# Mostrar botón de descarga
if "generated_zip" in st.session_state and st.session_state.generated_zip:
    st.download_button(
        "⬇️ Descargar Proyecto (.zip)",
        st.session_state.generated_zip,
        "proyecto_generado.zip",
        "application/zip"
    )
    del st.session_state.generated_zip

# --- USO DEL WIDGET NATIVO `st.chat_input` (sin cambios) ---
if prompt := st.chat_input("Crea un proyecto basado en el archivo..."):
    if not st.session_state.uploaded_file_details:
        st.toast("⚠️ Por favor, carga un archivo primero.", icon="⚠️")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.processing_triggered = True
        st.rerun()