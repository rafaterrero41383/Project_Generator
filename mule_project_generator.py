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
import json
from urllib.parse import urlparse
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
        file.seek(0)
        return file.read().decode("utf-8", errors="ignore")
    elif name.endswith(".docx"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            file.seek(0)
            tmp.write(file.read())
            tmp_path = tmp.name
        doc = Document(tmp_path)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""

def obtener_arquetipo():
    # Busca un ZIP que contenga "arquetipo" en el nombre en la raíz
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            return f
    return None

# === VALIDADORES (para checks puntuales) ===
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
# =============== GENERADOR DETERMINISTA ====================
# ===========================================================

# Directorios/archivos a ignorar
IGNORE_DIRS = {".git", ".hg", ".svn", ".idea", ".DS_Store", "target", ".vscode", "__MACOSX", "docs", "design"}
# Extensiones de guía (no van al ZIP)
GUIDE_EXTS: Iterable[str] = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".ppt", ".pptx", ".key", ".ai", ".psd"
)
# Extensiones de texto para render/reemplazo
TEXT_EXTS: Iterable[str] = (
    ".xml", ".yaml", ".yml", ".json", ".md", ".txt",
    ".properties", ".pom", ".cfg", ".ini", ".raml", ".dwl", ".policy"
)
# Tokens “clásicos”
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
    """Copia/renderiza un archivo del arquetipo aplicando:
       1) Jinja2 en *.j2
       2) Reemplazos de tokens clásicos
       3) Ajustes típicos en YAML/JSON si faltan valores (app.name, api.baseUri, mule-artifact.json name)
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    # 1) Plantillas Jinja2
    if src.name.endswith(".j2"):
        template = env.get_template(str(src.relative_to(env.loader.searchpath[0])).replace("\\", "/"))
        rendered = template.render(**ctx)
        dst = dst.with_name(dst.name[:-3])  # quita .j2
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(rendered)
        return

    # 2) Token replace en archivos de texto
    if is_text_file(src) and token_replace:
        with open(src, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # Reemplazos clásicos
        for token, key in TOKEN_MAP.items():
            if token in content and key in ctx:
                content = content.replace(token, str(ctx[key]))

        # 3) Ajustes comunes por tipo (XML / YAML / JSON)
        ext = src.suffix.lower()
        try:
            if ext in [".yaml", ".yml"]:
                try:
                    y = yaml.safe_load(content) or {}
                    if isinstance(y, dict):
                        # app.name
                        y.setdefault("app", {})
                        if isinstance(y["app"], dict) and not y["app"].get("name"):
                            y["app"]["name"] = ctx.get("project_name")
                        # api.baseUri
                        y.setdefault("api", {})
                        if isinstance(y["api"], dict) and ctx.get("base_uri") and not y["api"].get("baseUri"):
                            y["api"]["baseUri"] = ctx["base_uri"]
                    content = yaml.safe_dump(y, sort_keys=False, allow_unicode=True)
                except Exception:
                    pass
            elif ext == ".json" and src.name == "mule-artifact.json":
                try:
                    j = json.loads(content)
                    if isinstance(j, dict) and not j.get("name"):
                        j["name"] = ctx.get("project_name")
                    content = json.dumps(j, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            # XML/POM: no tocamos nodos por XPath para evitar lxml; validación ligera opcional
            # elif ext in [".xml", ".pom"]:
            #     try:
            #         ET.fromstring(content)
            #     except Exception:
            #         pass
        finally:
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        return

    # 4) Copia binaria tal cual
    import shutil as _shutil
    _shutil.copy2(src, dst)

def unpack_archetype_zip_to_temp(arquetipo_zip: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(arquetipo_zip, "r") as zf:
        zf.extractall(tmp_dir)
    # Detecta carpeta raíz del arquetipo si el ZIP trae contenedor
    candidates = [p for p in tmp_dir.iterdir() if p.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    # Si hay varias, intenta elegir la que tenga src/ o pom.xml
    for c in candidates:
        if (c / "src").exists() or (c / "pom.xml").exists():
            return c
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
            f.write(raml_bytes)
        inject_raml(dst_root, tmp_raml)

    # 6) Empaquetado final
    out_zip = Path(tempfile.gettempdir()) / f"{artifact_id}-{now}.zip"
    zip_dir(dst_root, out_zip)

    return str(out_zip), str(dst_root), len(skipped)

# ===========================================================
# ============== PARSEO Y CONTEXTO (RAML / DTM) =============
# ===========================================================

RAML_HEADER_MARK = "#%RAML"

def parse_raml_text(txt: str) -> dict:
    """Extrae campos básicos de un RAML 1.0 sencillo (heurístico)."""
    data = {
        "title": None,
        "version": None,
        "baseUri": None,
        "protocols": None,
        "mediaType": None,
        "endpoints": [],
    }
    lines = [l.rstrip() for l in txt.splitlines()]

    header_done = False
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if i == 0 and line.startswith(RAML_HEADER_MARK):
            continue
        if line.startswith("types:") or line.startswith("documentation:") or line.startswith("/"):
            header_done = True
        if not header_done:
            m = re.match(r'^([A-Za-z][A-Za-z0-9_-]*):\s*(.+)?$', line.strip())
            if m:
                k, v = m.group(1), m.group(2)
                if v and v.strip().startswith("[") and v.strip().endswith("]"):
                    try:
                        vv = v.strip().strip("[]").replace(" ", "")
                        data[k] = [x for x in vv.split(",") if x]
                    except Exception:
                        data[k] = v
                else:
                    data[k] = v
        else:
            if line.strip().startswith("/"):
                ep = line.strip().split(":")[0].strip()
                if ep:
                    data["endpoints"].append(ep)

    return {
        "title": data.get("title"),
        "version": (data.get("version") or None),
        "baseUri": data.get("baseUri"),
        "protocols": data.get("protocols"),
        "mediaType": data.get("mediaType"),
        "endpoints": data.get("endpoints") or [],
    }

def parse_docx_kv(txt: str) -> dict:
    """Del DTM (DOCX->texto), detecta pares clave: valor y heurísticas básicas."""
    kv = {}
    for line in txt.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k and v:
                kv[k] = v

    title = kv.get("title") or kv.get("nombre api") or kv.get("api name") or kv.get("servicio") or kv.get("microservicio")
    version = kv.get("version") or kv.get("versión") or kv.get("api version") or "1.0.0"
    base_uri = kv.get("baseuri") or kv.get("base uri") or kv.get("base_url") or kv.get("endpoint base")
    group_id = kv.get("group_id") or kv.get("grupo maven") or "com.company.experience"

    return {
        "title": title,
        "version": version,
        "baseUri": base_uri,
        "group_id": group_id,
        "raw": kv
    }

def derive_fields(title: str, version: str, base_uri: str, group_id: str) -> dict:
    project_name = title or "MuleApplication"
    artifact_id = kebab(project_name)
    v = version or "1.0.0"
    base = base_uri or ""
    host_name = None
    base_path = None
    if base:
        try:
            if "{" in base and "}" in base:
                after_host = base.split("}", 1)[-1]
                base_path = after_host if after_host else None
            else:
                u = urlparse(base)
                host_name = u.netloc or None
                base_path = u.path if u.path else None
        except Exception:
            pass
    return {
        "project_name": project_name,
        "artifact_id": artifact_id,
        "version": v,
        "group_id": group_id or "com.company.experience",
        "base_uri": base or None,
        "host_name": host_name,
        "base_path": base_path.lstrip("/") if base_path else None,
    }

def build_context_from_spec(spec_file, raw_text: str) -> dict:
    """Detecta RAML o DTM (docx->texto) y arma el contexto completo."""
    name = spec_file.name.lower()
    if name.endswith(".raml") or raw_text.strip().startswith(RAML_HEADER_MARK):
        r = parse_raml_text(raw_text)
        ctx = derive_fields(
            r.get("title") or "MuleApplication",
            r.get("version") or "1.0.0",
            r.get("baseUri"),
            "com.company.experience",
        )
        ctx.update({
            "media_type": r.get("mediaType"),
            "protocols": ",".join(r.get("protocols")) if isinstance(r.get("protocols"), list) else (r.get("protocols") or None),
            "endpoints": r.get("endpoints") or [],
        })
        return ctx
    else:
        d = parse_docx_kv(raw_text)
        ctx = derive_fields(
            d.get("title") or "MuleApplication",
            d.get("version") or "1.0.0",
            d.get("baseUri"),
            d.get("group_id") or "com.company.experience",
        )
        return ctx

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

        st.session_state.messages.append({"role": "assistant", "content": "🧠 Leyendo especificación y construyendo contexto..."})

        raw_text = leer_especificacion(st.session_state.uploaded_spec)
        ctx = build_context_from_spec(st.session_state.uploaded_spec, raw_text)

        # (Opcional/útil para ver qué se va a inyectar)
        pretty_ctx_yaml = yaml.safe_dump(ctx, sort_keys=False, allow_unicode=True)
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"📘 Contexto derivado de la especificación:\n```yaml\n{pretty_ctx_yaml}\n```"
        })

        st.session_state.messages.append({"role": "assistant", "content": "⚙️ Generando proyecto desde el arquetipo (sin imágenes/guías)..."})

        # Si subiste RAML, lo inyectamos como archivo; si es DOCX, no hay RAML que inyectar
        raml_bytes = None
        if st.session_state.uploaded_spec.name.lower().endswith(".raml"):
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
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"✅ Proyecto generado. Omitidos (imágenes/guías): {omitidos}."
            })
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
