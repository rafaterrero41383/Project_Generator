import os
import tempfile
import zipfile
import re
# --- Parche para compatibilidad con Python 3.13 ---
import sys, types
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    sys.modules['imghdr'] = imghdr
# ---------------------------------------------------
import xml.etree.ElementTree as ET
import yaml
from docx import Document
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# === CONFIGURACIÓN INICIAL ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="🤖 Generador Inteligente de Proyectos Mulesoft", layout="wide")

# === CSS Y ESTILO DE CHAT ===
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
if "uploaded_spec" not in st.session_state:
    st.session_state.uploaded_spec = None
if "generated_zip" not in st.session_state:
    st.session_state.generated_zip = None

assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

# === TÍTULO CENTRADO ===
st.markdown("<h1 style='text-align:center;'>🤖 Generador Inteligente de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

# === BOTÓN DE REINICIO ===
if st.button("🔄 Reiniciar aplicación"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

# === CARGA DE ESPECIFICACIÓN ===
spec = st.file_uploader("📎 Adjunta la especificación (RAML o DTM .docx)", type=["raml", "docx"])
if spec and st.session_state.uploaded_spec is None:
    st.session_state.uploaded_spec = spec
    st.session_state.messages.append({
        "role": "assistant",
        "content": f"📄 Archivo `{spec.name}` cargado correctamente. Escribe en el chat `Crea el proyecto` para comenzar."
    })

# === FUNCIONES ===

def leer_especificacion(file):
    name = file.name.lower()
    if name.endswith(".raml"):
        return file.read().decode("utf-8", errors="ignore")
    elif name.endswith(".docx"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name
        doc = Document(tmp_path)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""


def obtener_arquetipo():
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            return f
    return None


def inferir_metadatos(contenido_api):
    prompt = f"""Eres un generador de proyectos Mulesoft.
Analiza la siguiente especificación (RAML o DTM) y devuelve metadatos clave en formato YAML:

- api_name
- tipo_api (System, Process, Experience)
- version
- descripcion
- endpoints
- dependencias

Especificación:
---
{contenido_api}
---
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un experto en arquitectura Mulesoft."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error al inferir metadatos: {e}"


def limpiar_contenido_bruto(raw_output):
    code_blocks = re.findall(r"```(?:xml|yaml|yml|json|properties)?(.*?)```", raw_output, re.DOTALL)
    if code_blocks:
        return code_blocks[-1].strip()

    start = raw_output.find("<")
    if start != -1:
        return raw_output[start:].strip()
    return raw_output.strip()


# === VALIDADORES ===

def validar_xml(contenido, archivo):
    try:
        ET.fromstring(contenido)
        return None
    except ET.ParseError as e:
        return f"❌ {archivo}: Error XML → {e}"

def validar_yaml(contenido, archivo):
    try:
        yaml.safe_load(contenido)
        return None
    except yaml.YAMLError as e:
        return f"⚠️ {archivo}: Error YAML → {e}"


def procesar_arquetipo(arquetipo_zip, metadatos_yaml):
    temp_dir = tempfile.mkdtemp()
    output_zip = os.path.join(tempfile.gettempdir(), "proyecto_mulesoft_generado.zip")

    with zipfile.ZipFile(arquetipo_zip, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    archivos_modificados = []
    errores_validacion = []
    archivos_totales = sum(len(files) for _, _, files in os.walk(temp_dir))
    progreso = st.progress(0)
    procesados = 0

    for root, _, files in os.walk(temp_dir):
        for file in files:
            procesados += 1
            progreso.progress(procesados / archivos_totales)
            ruta = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()

            if ext in [".xml", ".json", ".yaml", ".yml", ".raml", ".properties", ".txt", ".pom", ".md"]:
                try:
                    with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
                        original = f.read()

                    prompt_archivo = f"""Eres un configurador de proyectos Mulesoft.
Usa los siguientes metadatos inferidos:
---
{metadatos_yaml}
---
Actualiza el siguiente archivo ({file}) reemplazando placeholders genéricos con valores coherentes según los metadatos.
Responde **solo con el contenido actualizado del archivo**, sin comentarios, sin explicaciones ni texto adicional.
Mantén el formato original.
Archivo original:
{original}
Archivo actualizado:
"""
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Eres un configurador experto en Mulesoft."},
                            {"role": "user", "content": prompt_archivo}
                        ],
                        temperature=0.3
                    )
                    raw_output = response.choices[0].message.content.strip()
                    nuevo_contenido = limpiar_contenido_bruto(raw_output)

                    # === Validación de formato antes de guardar ===
                    if ext in [".xml", ".pom"]:
                        error = validar_xml(nuevo_contenido, file)
                        if error: errores_validacion.append(error)
                    elif ext in [".yaml", ".yml"]:
                        error = validar_yaml(nuevo_contenido, file)
                        if error: errores_validacion.append(error)

                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write(nuevo_contenido)
                    archivos_modificados.append(file)

                except Exception as e:
                    errores_validacion.append(f"⚠️ Error al procesar {file}: {e}")

    # Crear el ZIP final
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, temp_dir)
                zipf.write(full_path, arcname)

    progreso.progress(1.0)
    return output_zip, archivos_modificados, errores_validacion


def manejar_mensaje(user_input):
    user_input = user_input.lower().strip()

    if user_input in ["crear proyecto", "crea el proyecto", "genera el proyecto"]:
        if not st.session_state.uploaded_spec:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "⚠️ Primero carga un archivo RAML o DTM antes de generar el proyecto."
            })
            return

        arquetipo = obtener_arquetipo()
        if not arquetipo:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❌ No se encontró ningún archivo ZIP con 'arquetipo' en la raíz del proyecto."
            })
            return

        st.session_state.messages.append({
            "role": "assistant",
            "content": "🧠 Analizando la especificación..."
        })

        contenido = leer_especificacion(st.session_state.uploaded_spec)
        metadatos = inferir_metadatos(contenido)

        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📘 Metadatos inferidos:\n```\n{metadatos}\n```"
        })

        st.session_state.messages.append({
            "role": "assistant",
            "content": "⚙️ Configurando proyecto con el arquetipo..."
        })

        salida_zip, modificados, errores = procesar_arquetipo(arquetipo, metadatos)
        st.session_state.generated_zip = salida_zip

        msg = f"✅ Proyecto generado correctamente con {len(modificados)} archivos modificados."
        if errores:
            msg += "\n\n⚠️ Se detectaron algunos problemas de validación:\n" + "\n".join(errores[:5])
            if len(errores) > 5:
                msg += f"\n... y {len(errores) - 5} errores más."

        st.session_state.messages.append({
            "role": "assistant",
            "content": msg
        })

    else:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "💬 Entendido. Escribe `Crea el proyecto` para generar tu proyecto Mulesoft."
        })


# === HISTORIAL DEL CHAT ===
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

# === ENTRADA DE CHAT ===
user_input = st.chat_input("Escribe aquí...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    manejar_mensaje(user_input)
    st.rerun()

# === DESCARGA DEL ZIP FINAL ===
if st.session_state.generated_zip:
    with open(st.session_state.generated_zip, "rb") as f:
        st.download_button(
            "⬇️ Descargar Proyecto Mulesoft (.zip)",
            f,
            "proyecto_mulesoft_generado.zip",
            "application/zip"
        )
