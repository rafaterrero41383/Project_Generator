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
import os
from openai import OpenAI

# ====== NUEVO: imports para el generador determinista ======
from pathlib import Path
from typing import Dict, Optional, Iterable, Tuple, List
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# === CONFIGURACIÓN INICIAL ===
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("❌ No se encontró la variable OPENAI_API_KEY. Configúrala en los secretos de Streamlit.")
    st.stop()

client = OpenAI()

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

# ===========================================================
# ============== FUNCIONES AUXILIARES BASE ==================
# ===========================================================

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
    # Busca un ZIP que contenga "arquetipo" en el nombre (mismo criterio que tenías)
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            return f
    return None

# === VALIDADORES === (los mantenemos para checks puntuales si hace falta)
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

# ===========================================================
# =============== NUEVO: GENERADOR DETERMINISTA =============
# ===========================================================

# Extensiones y reglas
IGNORE_DIRS = {".git", ".hg", ".svn", ".idea", ".DS_Store", "target", ".vscode", "__MACOSX", "docs", "design"}
GUIDE_EXTS: Iterable[str] = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".ppt", ".pptx", ".key", ".ai", ".psd"
)
TEXT_EXTS: Iterable[str] = (
    ".xml", ".yaml", ".yml", ".json", ".md", ".txt",
    ".properties", ".pom", ".cfg", ".ini", ".raml", ".dwl", ".policy"
)

TOKEN_MAP = {
    "__PROJECT_NAME__": "project_name",
    "__ARTIFACT_ID__":  "artifact_id",
    "__GROUP_ID__":     "group_id",
    "__VERSION__":      "version",
    "{project_name}":   "project_name",
    "{artifact_id}":    "artifact_id",
    "{group_id}":       "group_id",
    "{version}":        "version",
}

def kebab(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s).lower()

def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTS or path.name.endswith(".j2"):
        return True
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
        return b"\x00" not in head
    except Exception:
        return False

def jinja_env(root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(root)),
        undefined=StrictUndefined,   # fail-fast si falta un placeholder
        keep_trailing_newline=True,
        autoescape=False,
    )

def first_raml_target(dst_root: Path) -> Path:
    existing = list(dst_root.rglob("*.raml"))
    return existing[0] if existing else (dst_root / "src/main/resources/api/api.raml")

def should_skip(path: Path, include_guides: bool) -> bool:
    if any(part in IGNORE_DIRS for part in path.parts):
        return True
    if not include_guides and path.suffix.lower() in GUIDE_EXTS:
        return True
    return False

def render_or_copy(src: Path, dst: Path, env: Environment, ctx: Dict, token_replace: bool):
    dst.parent.mkdir(parents=True, exist_ok=True)

    if src.name.endswith(".j2"):
        rel = src.as_posix().split("/", 1)[-1]  # ruta relativa sin raíz
        # Construimos correctamente la ruta relativa al root jinja
        # (buscaremos la subruta dentro del árbol a partir del directorio real del loader)
        template = env.get_template(str(src.relative_to(env.loader.searchpath[0])).replace("\\", "/"))
        rendered = template.render(**ctx)
        dst = dst.with_name(dst.name[:-3])  # quita .j2
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(rendered)
        return

    if is_text_file(src) and token_replace:
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for token, key in TOKEN_MAP.items():
            if token in content and key in ctx:
                content = content.replace(token, str(ctx[key]))
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return

    # Copia binaria tal cual (jar, imágenes, etc.)
    import shutil as _shutil
    _shutil.copy2(src, dst)

def unpack_archetype_zip_to_temp(arquetipo_zip: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(arquetipo_zip, "r") as zf:
        zf.extractall(tmp_dir)
    # Detecta la carpeta raíz del arquetipo (si el zip trae un directorio contenedor)
    # Tomamos la primera carpeta con 'mule' o 'src' adentro como root
    candidates = [p for p in tmp_dir.iterdir() if p.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    # fallback: el propio tmp_dir
    return tmp_dir

def render_tree_from_root(archetype_root: Path, dst_root: Path, ctx: Dict, include_guides: bool, token_replace: bool = True) -> List[Path]:
    env = jinja_env(archetype_root)
    skipped: List[Path] = []
    for root, _, files in os.walk(archetype_root):
        r = Path(root)
        if any(part in IGNORE_DIRS for part in r.parts):
            continue
        for fname in files:
            src = r / fname
            if should_skip(src, include_guides):
                skipped.append(src)
                continue
            rel = src.relative_to(archetype_root)
            dst = dst_root / rel
            render_or_copy(src, dst, env, ctx, token_replace)
    return skipped

def inject_raml(dst_root: Path, raml_path: Optional[Path]):
    if not raml_path:
        return
    target = first_raml_target(dst_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    import shutil as _shutil
    _shutil.copy2(raml_path, target)

def zip_dir(src: Path, out_zip: Path):
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in src.rglob("*"):
            z.write(p, p.relative_to(src))

def generate_from_archetype_zip(arquetipo_zip: str, ctx: Dict, raml_bytes: Optional[bytes], include_guides: bool = False) -> Tuple[str, str, int]:
    if not os.path.exists(arquetipo_zip):
        raise FileNotFoundError(f"No se encontró el arquetipo: {arquetipo_zip}")

    # 1) Descomprime arquetipo a temp y define su raíz real
    archetype_root = unpack_archetype_zip_to_temp(arquetipo_zip)

    # 2) Normaliza contexto
    artifact_id = ctx.get("artifact_id") or kebab(ctx["project_name"])
    from datetime import datetime
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    ctx = {**ctx, "artifact_id": artifact_id, "created_at": datetime.now().isoformat(timespec="seconds")}

    # 3) Directorio de salida intermedio
    dst_root = Path(tempfile.mkdtemp()) / f"{artifact_id}-{now}"
    dst_root.mkdir(parents=True, exist_ok=True)

    # 4) Render/copiar árbol (sin imágenes/guías por defecto)
    skipped = render_tree_from_root(archetype_root, dst_root, ctx, include_guides=include_guides, token_replace=True)

    # 5) Inyección RAML (si se subió)
    if raml_bytes:
        tmp_raml = Path(tempfile.mkdtemp()) / "api.raml"
        with open(tmp_raml, "wb") as f:
            f.write(rl := raml_bytes)
        inject_raml(dst_root, tmp_raml)

    # 6) Empaquetado final
    out_zip = Path(tempfile.gettempdir()) / f"{artifact_id}-{now}.zip"
    zip_dir(dst_root, out_zip)

    return str(out_zip), str(dst_root), len(skipped)

# ===========================================================
# ============== INFERENCIA LIGERA DE METADATOS =============
# ===========================================================

def inferir_metadatos(contenido_api):
    prompt = f"""Eres un generador de proyectos Mulesoft.
Analiza la siguiente especificación (RAML o DTM) y devuelve metadatos clave en formato YAML:

- api_name
- group_id (si puedes inferirlo, si no deja com.company.experience)
- version
- descripcion

Especificación:
---
{contenido_api}
---
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un arquitecto Mulesoft conservador y estricto con estándares."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
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

def yaml_to_ctx(metadatos_yaml: str) -> Dict:
    """
    Convierte YAML de metadatos a contexto del generador.
    Aplica defaults conservadores cuando falten campos.
    """
    try:
        data = yaml.safe_load(metadatos_yaml) or {}
    except Exception:
        data = {}
    api_name = data.get("api_name") or "MuleApplication"
    group_id = data.get("group_id") or "com.company.experience"
    version = data.get("version") or "1.0.0"
    # Campos adicionales opcionales
    return {
        "project_name": api_name,
        "group_id": group_id,
        "version": version,
        # Puedes mapear más claves de tu arquetipo aquí:
        # "host_name": data.get("host_name"),
        # "sdName": data.get("sdName"),
        # "bqName": data.get("bqName"),
    }

# ===========================================================
# =================== FLUJO DE MENSAJES =====================
# ===========================================================

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

        st.session_state.messages.append({"role": "assistant", "content": "🧠 Analizando la especificación..."})

        contenido = leer_especificacion(st.session_state.uploaded_spec)
        metadatos = inferir_metadatos(contenido)
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📘 Metadatos inferidos:\n```\n{metadatos}\n```"
        })

        ctx = yaml_to_ctx(limpiar_contenido_bruto(metadatos))

        st.session_state.messages.append({"role": "assistant", "content": "⚙️ Generando proyecto desde el arquetipo (sin imágenes/guías)..."})

        # Si subiste RAML, úsalo. Si subiste DOCX, no hay RAML para inyectar.
        raml_bytes = None
        if st.session_state.uploaded_spec.name.lower().endswith(".raml"):
            # Ya leímos el texto arriba; necesitamos bytes crudos para escribir.
            # Recuperamos el buffer original:
            st.session_state.uploaded_spec.seek(0)
            raml_bytes = st.session_state.uploaded_spec.read()

        try:
            salida_zip, _carpeta, omitidos = generate_from_archetype_zip(
                arquetipo_zip=arquetipo,
                ctx=ctx,
                raml_bytes=raml_bytes,
                include_guides=False
            )
            st.session_state.generated_zip = salida_zip

            msg = f"✅ Proyecto generado correctamente. Omitidos (imágenes/guías): {omitidos}."
            st.session_state.messages.append({"role": "assistant", "content": msg})

        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ Falló la generación: {e}"
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
