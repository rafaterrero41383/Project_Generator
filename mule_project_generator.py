import os
import shutil
import tempfile
import time
import zipfile
import streamlit as st
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI

# --- Configuración inicial --
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="Generador de Proyectos Mulesoft", layout="wide")

# --- CSS visual (simplificado, ya que st.chat_input maneja su propio estilo) ---
st.markdown("""
<style>
body {
    background-color: #f5f6fa !important;
    font-family: 'Inter', sans-serif;
}
h1 {
    text-align: center;
    margin-bottom: 10px;
}
.chat-message {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 16px;
}
.user-message {
    flex-direction: row-reverse;
}
.avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
}
.message-bubble {
    padding: 14px 18px;
    border-radius: 18px;
    max-width: 85%;
    word-wrap: break-word;
    line-height: 1.4;
}
.user-bubble {
    background-color: #e3f2fd;
    border: 1px solid #bbdefb;
}
.assistant-bubble {
    background-color: #f1f0f0;
    border: 1px solid #ddd;
}
</style>
""", unsafe_allow_html=True)

# --- Estado global ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file_details" not in st.session_state:
    st.session_state.uploaded_file_details = None
# Este es el nuevo flag que controlará el flujo
if "processing_triggered" not in st.session_state:
    st.session_state.processing_triggered = False

# --- Avatares ---
assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

# --- Encabezado y Carga de Archivo ---
st.markdown("<h1>🤖 Generador de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "1. Carga tu archivo `.raml` o `.docx`",
    type=["raml", "docx"],
    key="file_uploader"
)

if uploaded_file:
    # Guardamos los detalles del archivo en el estado de la sesión para persistencia
    # Verificamos si es un archivo nuevo para no añadir mensajes duplicados
    if st.session_state.uploaded_file_details is None or st.session_state.uploaded_file_details[
        "name"] != uploaded_file.name:
        st.session_state.uploaded_file_details = {
            "name": uploaded_file.name,
            "content": uploaded_file.read()
        }
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded_file.name}` cargado. Ahora, escribe tu instrucción abajo."
        })
        st.rerun()

# --- Mostrar historial del chat ---
for msg in st.session_state.messages:
    avatar = user_avatar if msg["role"] == "user" else assistant_avatar
    bubble_class = "user-bubble" if msg["role"] == "user" else "assistant-bubble"
    message_class = "user-message" if msg["role"] == "user" else "assistant-message"
    st.markdown(f"""
        <div class="chat-message {message_class}">
            <img src="{avatar}" class="avatar">
            <div class="message-bubble {bubble_class}">{msg["content"]}</div>
        </div>
    """, unsafe_allow_html=True)

# --- Lógica principal de procesamiento ---
# Este bloque SÓLO se ejecuta si el flag `processing_triggered` es True
if st.session_state.processing_triggered:
    # Inmediatamente reseteamos el flag para evitar que se ejecute de nuevo en el próximo rerun
    st.session_state.processing_triggered = False

    # Obtenemos la última instrucción del usuario
    user_instruction = st.session_state.messages[-1]['content']
    uploaded_file_details = st.session_state.uploaded_file_details

    # Usamos st.status para mostrar el progreso de forma limpia
    with st.status("Generando proyecto, por favor espera...", expanded=True) as status:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                st.write("🔧 Preparando entorno y arquetipo...")
                arquetipo_path = os.path.join(temp_dir, "arquetipo")
                arquetipo_zip_path = os.path.join(os.getcwd(), "arquetipo-mulesoft.zip")

                if not os.path.exists(arquetipo_zip_path):
                    raise FileNotFoundError(f"No se encontró el archivo del arquetipo: {arquetipo_zip_path}")

                with zipfile.ZipFile(arquetipo_zip_path, "r") as zip_ref:
                    zip_ref.extractall(arquetipo_path)

                file_extension = uploaded_file_details["name"].split(".")[-1].lower()
                content = ""
                if file_extension == "raml":
                    content = uploaded_file_details["content"].decode("utf-8", errors="ignore")
                elif file_extension == "docx":
                    temp_docx_path = os.path.join(temp_dir, uploaded_file_details["name"])
                    with open(temp_docx_path, "wb") as f:
                        f.write(uploaded_file_details["content"])
                    doc = Document(temp_docx_path)
                    content = "\n".join([p.text for p in doc.paragraphs])

                st.write("🧠 Contactando a la IA para procesar los archivos...")
                extensiones_permitidas = (".xml", ".raml", ".yaml", ".yml", ".properties", ".md", ".txt", ".json")
                archivos_relevantes = [os.path.join(root, f) for root, _, files in os.walk(arquetipo_path) for f in
                                       files if f.endswith(extensiones_permitidas)]
                total = len(archivos_relevantes)

                for i, file_path in enumerate(archivos_relevantes, start=1):
                    file_name = os.path.basename(file_path)
                    st.write(f"Procesando archivo {i}/{total}: {file_name}")

                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        original = f.read()

                    prompt = f"""
                    Archivo `{file_name}` de un proyecto Mulesoft. Reescríbelo según el archivo RAML/DTM adjunto y la instrucción del usuario. Mantén formato y estructura. Devuelve solo el nuevo contenido.
                    Instrucción del usuario: "{user_instruction}"
                    Contexto técnico del RAML/DTM:
                    {content[:4000]}
                    Contenido original del archivo a modificar:
                    {original[:2000]}
                    """
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system",
                             "content": "Asistente experto en proyectos Mulesoft. Modificas archivos de un arquetipo basado en un RAML/DTM y una instrucción."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2
                    )
                    new_content = response.choices[0].message.content.strip()

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    time.sleep(0.1)  # Pequeña pausa para UX

                st.write("📦 Empaquetando el proyecto generado...")
                zip_out_path = os.path.join(temp_dir, "proyecto_generado.zip")
                shutil.make_archive(zip_out_path.replace(".zip", ""), 'zip', arquetipo_path)

                with open(zip_out_path, "rb") as f:
                    zip_content = f.read()

                # Guardamos el contenido del zip en el estado para mostrar el botón de descarga en el siguiente rerun
                st.session_state.generated_zip = zip_content
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "¡Proyecto generado exitosamente! Puedes descargarlo ahora."
                })
                status.update(label="✅ ¡Proyecto generado con éxito!", state="complete")

        except Exception as e:
            st.session_state.messages.append({"role": "assistant", "content": f"❌ Ocurrió un error: {e}"})
            status.update(label="❌ Error durante la generación", state="error")

    # Forzamos un rerun final para mostrar el mensaje de éxito/error y el botón de descarga
    st.rerun()

# --- Mostrar botón de descarga si el proyecto fue generado ---
if "generated_zip" in st.session_state and st.session_state.generated_zip:
    st.download_button(
        label="⬇️ Descargar Proyecto Generado (.zip)",
        data=st.session_state.generated_zip,
        file_name="proyecto_generado.zip",
        mime="application/zip"
    )
    # Limpiamos el zip del estado para que el botón no aparezca indefinidamente
    del st.session_state.generated_zip

# --- Input del chat en la parte inferior ---
# `st.chat_input` es la clave aquí. Es un componente que se queda fijo abajo.
if prompt := st.chat_input("Escribe tu instrucción para generar el proyecto..."):
    # Primero, validamos que haya un archivo cargado
    if not st.session_state.uploaded_file_details:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "⚠️ Por favor, carga un archivo antes de dar una instrucción."
        })
        st.rerun()
    else:
        # Añadimos el mensaje del usuario al historial
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Activamos el flag para que el bloque de procesamiento se ejecute en el siguiente rerun
        st.session_state.processing_triggered = True

        # Hacemos rerun para mostrar inmediatamente el mensaje del usuario en el chat
        # y para que el bloque de procesamiento se active
        st.rerun()