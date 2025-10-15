import os
import zipfile
import tempfile
import time
import textwrap
from docx import Document
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# === CONFIGURACIÓN INICIAL ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="🤖 Generador Inteligente de Proyectos Mulesoft", layout="wide")

# === CSS VISUAL ===
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

# === ESTADO GLOBAL ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None

assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

st.markdown("<h1 style='text-align:center;'>🤖 Generador Inteligente de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

# === BOTÓN DE REINICIO ===
if st.button("🔄 Reiniciar aplicación"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# === CARGA DE ARCHIVO ===
uploaded = st.file_uploader("📎 Adjunta tu especificación (RAML o DTM .docx)", type=["raml", "docx"])
if uploaded:
    if not st.session_state.uploaded_file or st.session_state.uploaded_file["name"] != uploaded.name:
        st.session_state.uploaded_file = {"name": uploaded.name, "content": uploaded.read()}
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📁 Archivo `{uploaded.name}` cargado correctamente. Describe qué tipo de API deseas generar (System, Process o Experience)."
        })
        st.rerun()

# === CONTENEDOR DEL CHAT ===
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


# === FUNCIÓN: LEER ESPECIFICACIÓN ===
def leer_especificacion(uploaded_file):
    name = uploaded_file["name"].lower()
    if name.endswith(".raml"):
        return uploaded_file["content"].decode("utf-8", errors="ignore")
    elif name.endswith(".docx"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(uploaded_file["content"])
            tmp_path = tmp.name
        doc = Document(tmp_path)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""


# === FUNCIÓN PRINCIPAL ===
def generar_proyecto(prompt_text, user_file):
    archetype_zip = None
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            archetype_zip = f
            break

    if not archetype_zip:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "❌ Error: No se encontró un archivo .zip de arquetipo Mulesoft en la raíz del proyecto."
        })
        st.rerun()
        return

    user_text = leer_especificacion(user_file)

    st.session_state.messages.append({
        "role": "assistant",
        "content": "🧠 Analizando la especificación del archivo para extraer metadatos del proyecto..."
    })
    st.rerun()

    time.sleep(1)

    # === Extraer metadatos del RAML o DTM ===
    base_prompt = textwrap.dedent(
        "Eres un generador de proyectos Mulesoft.\n"
        "Analiza la siguiente especificación (RAML o DTM) y extrae información relevante:\n"
        "- Nombre del proyecto (api_name)\n"
        "- Tipo de API (System, Process, Experience)\n"
        "- Versión\n"
        "- Descripción\n"
        "- Endpoints principales\n"
        "- Dependencias y conectores\n\n"
        "Escribe los valores inferidos en formato YAML.\n"
        "---\n"
    ) + user_text + "\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un experto en arquitectura Mulesoft."},
                {"role": "user", "content": base_prompt}
            ],
            temperature=0.2
        )
        inferred_data = response.choices[0].message.content.strip()
    except Exception as e:
        inferred_data = f"Error al analizar: {e}"

    # === Descomprimir arquetipo ===
    temp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(archetype_zip, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    modified_files = []

    # === Procesar cada archivo ===
    for root, _, files in os.walk(temp_dir):
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            if ext in [".xml", ".json", ".yaml", ".yml", ".txt", ".md", ".raml", ".properties", ".pom"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    original_content = f.read()

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"🧩 Procesando archivo: `{file}` ..."
                })
                st.rerun()
                time.sleep(0.3)

                prompt_file = textwrap.dedent(
                    "Eres un configurador de proyectos Mulesoft.\n"
                    "Usa los siguientes metadatos inferidos del usuario:\n"
                    "---\n"
                ) + inferred_data + textwrap.dedent(
                    "---\n"
                    f"Actualiza el siguiente archivo ({file}) reemplazando valores genéricos "
                    "(nombres, versiones, rutas, descripciones) con la información inferida.\n\n"
                    "Archivo original:\n"
                    "```\n"
                ) + original_content + textwrap.dedent(
                    "```\n"
                    "Archivo actualizado:\n"
                )

                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Eres un configurador experto en Mulesoft."},
                            {"role": "user", "content": prompt_file}
                        ],
                        temperature=0.3
                    )
                    updated_content = resp.choices[0].message.content.strip()
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    modified_files.append(file)

                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"⚠️ Error al modificar `{file}`: {e}"
                    })
                    st.rerun()

    # === Generar ZIP final ===
    output_zip = os.path.join(tempfile.gettempdir(), "proyecto_mulesoft_generado.zip")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, temp_dir)
                zipf.write(full_path, arcname)

    st.session_state.messages.append({
        "role": "assistant",
        "content": f"✅ Proyecto generado exitosamente con {len(modified_files)} archivos modificados."
    })

    with open(output_zip, "rb") as f:
        st.session_state.generated_zip = f.read()


    # === DESCARGA ===
    if "generated_zip" in st.session_state and st.session_state.generated_zip:
        st.download_button(
            "⬇️ Descargar Proyecto Mulesoft (.zip)",
            st.session_state.generated_zip,
            "proyecto_mulesoft_generado.zip",
            "application/zip"
        )
        del st.session_state.generated_zip

    # === CHAT INPUT ===
    user_input = st.chat_input("Describe el tipo de API o los detalles del proyecto...")
    if user_input:
        if not st.session_state.uploaded_file:
            st.toast("⚠️ Primero adjunta un archivo de especificación (RAML o DTM).", icon="⚠️"),
        else:
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.processing = True
            generar_proyecto(user_input, st.session_state.uploaded_file)
            st.rerun()
