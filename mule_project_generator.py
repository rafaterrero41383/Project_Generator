import tempfile, zipfile, re, os, io, json, sys, types
import xml.etree.ElementTree as ET
import yaml
from pathlib import Path
from urllib.parse import urlparse

# --- Parche compatibilidad 3.13 (tuyo) ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    sys.modules['imghdr'] = imghdr
# -----------------------------------------

from docx import Document
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# ========= CONFIG =========
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("❌ Falta OPENAI_API_KEY en secretos/entorno.")
    st.stop()

client = OpenAI()
MODEL_BASE = "gpt-4o-mini"

st.set_page_config(page_title="🤖 Generador Inteligente de Proyectos Mulesoft (LLM)", layout="wide")

# ====== UI base ======
st.markdown("""
<style>
#MainMenu { display:none }
.chat-message { display:flex; align-items:flex-start; gap:12px; margin-bottom:14px; }
.user-message { flex-direction: row-reverse; }
.avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; }
.message-bubble { padding: 12px 14px; border-radius: 14px; max-width: 85%; line-height:1.38; }
.user-bubble { background:#e3f2fd; border:1px solid #bbdefb; }
.assistant-bubble { background:#f1f0f0; border:1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

assistant_avatar = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
user_avatar = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"

st.markdown("<h1 style='text-align:center;'>🤖 Generador Inteligente de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

if "messages" not in st.session_state: st.session_state.messages = []
if "uploaded_spec" not in st.session_state: st.session_state.uploaded_spec = None
if "generated_zip" not in st.session_state: st.session_state.generated_zip = None

if st.button("🔄 Reiniciar"):
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()

spec = st.file_uploader("📎 Adjunta la especificación (RAML o DTM .docx)", type=["raml", "docx"])
if spec and st.session_state.uploaded_spec is None:
    st.session_state.uploaded_spec = spec
    st.session_state.messages.append({"role":"assistant","content":f"📄 Archivo `{spec.name}` cargado. Escribe `crea el proyecto`."})

# ========= Utilidades =========

def leer_especificacion(file) -> str:
    name = file.name.lower()
    file.seek(0)
    if name.endswith(".raml"):
        return file.read().decode("utf-8", errors="ignore")
    if name.endswith(".docx"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            path = tmp.name
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

def obtener_arquetipo() -> str|None:
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            return f
    return None

def validar_xml(txt: str, archivo: str) -> str|None:
    try:
        ET.fromstring(txt)
        return None
    except ET.ParseError as e:
        return f"❌ {archivo}: Error XML → {e}"

def validar_yaml(txt: str, archivo: str) -> str|None:
    try:
        yaml.safe_load(txt)
        return None
    except yaml.YAMLError as e:
        return f"⚠️ {archivo}: Error YAML → {e}"

# ========= Parte 1: Inferir metadatos con ChatGPT =========

PROMPT_CTX = """Eres un ingeniero de integración Mulesoft.
Dado un RAML (o contenido DTM en texto), entrega un YAML válido con estas claves:

project_name: nombre amigable del proyecto (string)
artifact_id: id maven en kebab-case (string)
version: semver (string, ej: 1.0.0)
group_id: maven groupId (string, por defecto com.company.experience)
tipo_api: Experience | System | Process (elige una si hay indicios, si no deja null)
base_uri: URI base del API (string o null)
host_name: host si se puede inferir (string o null)
protocol: HTTP/HTTPS si se infiere (string o null)
base_path: path sin host, sin query, sin protocolo; sin barra inicial (string o null)
general_path: path del listener para ${general.path} (string, ej: "/api/*")
starwars_host: idem host para configuración HTTP (string o null)
starwars_protocol: HTTP/HTTPS (string o null)
starwars_path: path que usarán los http:request (string, ej: "/v1/renapo/evaluate")
media_type: mediaType del RAML si existe (string o null)
protocols: protocolos del RAML (string o null, separados por coma o null)
endpoints: lista de endpoints "raíz" del RAML (array de strings)

Reglas:
- artifact_id = project_name en kebab-case.
- general_path: si hay base_path o primer endpoint, usar "/<path>/*"; si el último segmento es muy específico (p.ej. "/evaluate"), mantén "/<base>/v1/*" si encaja mejor.
- Si base_uri tiene variables {HOST} o similares, host_name = null pero deriva protocol y base_path.
- No incluyas texto fuera del YAML.
"""

def _gpt(messages, temperature=0.2, model=MODEL_BASE) -> str:
    resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    return resp.choices[0].message.content.strip()

def inferir_metadatos(contenido_api: str) -> dict:
    yml = _gpt([
        {"role":"system","content":"Responde solo YAML válido."},
        {"role":"user","content": PROMPT_CTX + "\n\n=== ESPECIFICACIÓN ===\n" + contenido_api}
    ], temperature=0.1)

    # Limpieza defensiva (por si devuelve bloque con ```yaml)
    m = re.search(r"```(?:yaml|yml)?\s*(.*?)```", yml, re.DOTALL)
    if m: yml = m.group(1).strip()
    try:
        data = yaml.safe_load(yml) or {}
    except Exception:
        data = {}

    # defaults mínimos
    data.setdefault("project_name", "MuleApplication")
    if "artifact_id" not in data:
        slug = re.sub(r"[^a-zA-Z0-9]+","-", data["project_name"]).strip("-").lower()
        data["artifact_id"] = re.sub(r"-{2,}","-", slug)
    data.setdefault("version","1.0.0")
    data.setdefault("group_id","com.company.experience")
    data.setdefault("general_path","/api/*")
    # herencia starwars_* por compatibilidad
    data.setdefault("starwars_host", data.get("host_name"))
    data.setdefault("starwars_protocol", data.get("protocol"))
    if not data.get("starwars_path"):
        base_path = (data.get("base_path") or "").lstrip("/")
        data["starwars_path"] = ("/"+base_path) if base_path else "/"

    # Enriquecimiento por capa (perfil)
    data = aplicar_perfil_por_capa(data)
    return data

# ========= Perfil por capa =========

def aplicar_perfil_por_capa(ctx: dict) -> dict:
    capa = (ctx.get("tipo_api") or "").strip().lower()
    # Prefijos y defaults por capa
    pref_map = {"experience": "exp", "system": "sys", "process": "prc"}
    # Si hay capa, exponemos un prefijo para flows y opcionalmente artifact
    if capa in pref_map:
        ctx.setdefault("layer_prefix", pref_map[capa])
        # Ajuste groupId por convención (conservador, sólo si viene default genérico)
        if ctx.get("group_id","").startswith("com.company"):
            ctx["group_id"] = f"com.company.{pref_map[capa]}"
        # Ajuste general_path si quedó muy genérico
        if ctx.get("general_path") in (None, "", "/api/*"):
            # intenta construir desde base_path
            bp = (ctx.get("base_path") or "").strip("/")
            if bp:
                # recorta última hoja muy específica
                parts = bp.split("/")
                if len(parts) >= 2:
                    ctx["general_path"] = "/" + "/".join(parts[:2]) + "/*"
                else:
                    ctx["general_path"] = "/" + bp + "/*"
            else:
                ctx["general_path"] = f"/{pref_map[capa]}/*"
    return ctx

# ========= Parte 2: Reescritura de archivos con ChatGPT =========

PROMPT_FILE = """Eres un configurador experto de proyectos Mule 4.
Objetivo: actualizar el archivo indicado usando los METADATOS (YAML) provistos.

Instrucciones estrictas:
- Mantén el MISMO formato y los mismos saltos de línea.
- No agregues explicaciones, comentarios extra ni bloques ```.
- Sigue los comentarios guía (por ejemplo los marcados con "====") y sustituye valores acordes.
- Sustituye placeholders o literales relevantes (groupId, artifactId, version, name, project.mule.name, http listener path/port, http request host/protocol/path, exchange.json main/assetId/groupId/name/version, propiedades YAML app/general/starwars).
- Si un valor del contexto es null, NO lo inventes; deja el original.
- No elimines secciones no relacionadas.

Responde **solo** con el contenido final del archivo, sin texto extra.

=== METADATOS (YAML) ===
{ctx_yaml}

=== ARCHIVO ({fname}) ORIGINAL ===
{original}
"""

def limpiar_contenido_llm(raw: str) -> str:
    blocks = re.findall(r"```(?:xml|yaml|yml|json|properties|txt)?\s*(.*?)```", raw, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return raw.strip()

def transformar_archivo_con_gpt(fname: str, original: str, ctx: dict) -> str:
    ctx_yaml = yaml.safe_dump(ctx, sort_keys=False, allow_unicode=True)
    raw = _gpt([
        {"role":"system","content":"Actúa como refactorizador determinista de archivos Mule/Java/XML/YAML/JSON."},
        {"role":"user","content": PROMPT_FILE.format(ctx_yaml=ctx_yaml, fname=fname, original=original)}
    ], temperature=0.1)
    contenido = limpiar_contenido_llm(raw)
    if not contenido or len(contenido.splitlines()) < max(3, int(len(original.splitlines())*0.3)):
        return original
    return contenido

# ========= Parte 2.5: Postprocesos deterministas (flows + TLS) =========

def _safe_sub(rx, text, repl_fn, count=0):
    r = re.compile(rx, re.DOTALL)
    return r.sub(lambda m: repl_fn(m), text, count=count)

def _already_prefixed(name: str, prefix: str) -> bool:
    p = prefix.lower()
    return name.lower().startswith(p + "-") or name.lower().startswith(p + ":")

def renombrar_flows(xml_text: str, ctx: dict) -> str:
    """Prefija nombre de flow/sub-flow con artifact_id o layer_prefix-artifact."""
    artifact = ctx.get("artifact_id", "app")
    layer = ctx.get("layer_prefix")
    prefix = f"{layer}-{artifact}" if layer else artifact

    def repl(m):
        start, old, end = m.group(1), m.group(2), m.group(3)
        if _already_prefixed(old, prefix) or _already_prefixed(old, artifact):
            return f'{start}{old}{end}'
        new = f"{prefix}-{old}"
        # normaliza dobles guiones
        new = re.sub(r"--+", "-", new)
        return f'{start}{new}{end}'

    # flow y sub-flow
    xml_text = _safe_sub(r'(<flow\s+name=")([^"]+)(")', xml_text, repl)
    xml_text = _safe_sub(r'(<sub-flow\s+name=")([^"]+)(")', xml_text, repl)
    return xml_text

def insertar_o_actualizar_tls(xml_text: str, ctx: dict) -> str:
    """Inserta <tls:context name="default-tls"> si tls_enabled y xmlns:tls presente; cablea tlsContext-ref."""
    if not ctx.get("tls_enabled"):
        return xml_text
    # Requiere namespace tls en el archivo
    if "xmlns:tls=" not in xml_text:
        # si no tiene el ns tls, no forzamos namespaces para no romper validaciones
        return xml_text

    # 1) Inserta/actualiza contexto TLS por defecto (truststore/keystore si se pasan)
    has_ctx = "<tls:context" in xml_text
    tls_ctx = ['<tls:context name="default-tls">']
    if ctx.get("tls_truststore_path"):
        tls_ctx.append(f'  <tls:trust-store path="{ctx["tls_truststore_path"]}" password="{ctx.get("tls_truststore_password","")}" type="{ctx.get("tls_truststore_type","JKS")}" />')
    if ctx.get("tls_keystore_path"):
        tls_ctx.append(f'  <tls:key-store path="{ctx["tls_keystore_path"]}" password="{ctx.get("tls_keystore_password","")}" type="{ctx.get("tls_keystore_type","JKS")}" />')
    tls_ctx.append('</tls:context>')
    tls_block = "\n".join(tls_ctx)

    if not has_ctx:
        # inserta antes de </mule> si existe
        if "</mule>" in xml_text:
            xml_text = xml_text.replace("</mule>", tls_block + "\n</mule>")
        else:
            xml_text = xml_text + "\n" + tls_block

    # 2) Cablear tlsContext-ref en conexiones HTTP cuando corresponda
    def add_tls_ref(conn_rx: str):
        def repl(m):
            tag = m.group(0)
            if 'tlsContext-ref=' in tag:
                return tag
            return tag[:-1] + ' tlsContext-ref="default-tls"'
        return repl

    # Solo si protocolo es HTTPS o el archivo ya usa HTTPS explícito
    if (ctx.get("starwars_protocol") or "").upper() == "HTTPS" or 'protocol="HTTPS"' in xml_text:
        xml_text = _safe_sub(r'(<http:request-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)
        xml_text = _safe_sub(r'(<http:listener-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)

    return xml_text

def postprocesar_xml(xml_text: str, fname: str, ctx: dict) -> str:
    name = fname.lower()
    # 1) Renombrado de flows/sub-flows
    if name.endswith(".xml"):
        xml_text = renombrar_flows(xml_text, ctx)
    # 2) TLS (global-config, mainFlow, etc.)
    xml_text = insertar_o_actualizar_tls(xml_text, ctx)
    return xml_text

# ========= Parte 3: Proceso del arquetipo =========

TEXT_EXTS = {".xml",".json",".yaml",".yml",".raml",".properties",".txt",".pom",".md"}

def first_raml_target(dst_root: Path) -> Path:
    c = dst_root / "src/main/resources/api/starwars.raml"
    if c.exists() or c.parent.exists(): return c
    c2 = dst_root / "src/main/resources/api/api.raml"
    if c2.parent.exists(): return c2
    existing = list(dst_root.rglob("*.raml"))
    return existing[0] if existing else (dst_root / "src/main/resources/api/api.raml")

def procesar_arquetipo_llm(arquetipo_zip: str, ctx: dict, spec_bytes: bytes|None):
    tmp_dir = Path(tempfile.mkdtemp())
    out_zip = Path(tempfile.gettempdir()) / "proyecto_mulesoft_generado.zip"

    with zipfile.ZipFile(arquetipo_zip, "r") as z:
        z.extractall(tmp_dir)

    # carpeta raíz del arquetipo (si venía anidada)
    roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    root = roots[0] if len(roots)==1 else tmp_dir

    # Progreso UI
    files_to_touch = []
    for r,_,fs in os.walk(root):
        for f in fs:
            p = Path(r)/f
            # excluye imágenes/guias
            if p.suffix.lower() in (".png",".jpg",".jpeg",".gif",".webp",".svg",".pdf",".ppt",".pptx",".key",".ai",".psd"):
                continue
            files_to_touch.append(p)
    total = len(files_to_touch)
    prog = st.progress(0.0)

    modificados, errores = [], []
    for i, path in enumerate(files_to_touch, 1):
        prog.progress(i/total)
        try:
            if path.suffix.lower() in TEXT_EXTS or path.name.lower()=="pom.xml":
                original = path.read_text(encoding="utf-8", errors="ignore")
                nuevo = transformar_archivo_con_gpt(path.name, original, ctx)

                # Post-procesos deterministas (flows + TLS)
                if path.suffix.lower() == ".xml":
                    nuevo = postprocesar_xml(nuevo, path.name, ctx)

                # Validaciones mínimas por tipo
                ext = path.suffix.lower()
                if path.name.lower()=="pom.xml" or ext==".xml":
                    err = validar_xml(nuevo, path.name)
                    if err:
                        errores.append(err + " (revirtiendo)")
                        nuevo = original
                elif ext in (".yaml",".yml"):
                    err = validar_yaml(nuevo, path.name)
                    if err:
                        errores.append(err + " (revirtiendo)")
                        nuevo = original

                path.write_text(nuevo, encoding="utf-8")
                if nuevo != original:
                    modificados.append(str(path.relative_to(root)))
        except Exception as e:
            errores.append(f"⚠️ Error en {path.name}: {e}")

    # Inyectar RAML del usuario si lo subió
    if spec_bytes and st.session_state.uploaded_spec.name.lower().endswith(".raml"):
        target = first_raml_target(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            f.write(spec_bytes)
        modificados.append(str(target.relative_to(root)))

    # Empaquetar
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            z.write(p, p.relative_to(root))

    return str(out_zip), modificados, errores

# ========= Chat/acciones =========

def manejar_mensaje(user_input: str):
    ui = user_input.strip().lower()

    if ui in ("crear proyecto","crea el proyecto","genera el proyecto","crea el proyecto"):
        if not st.session_state.uploaded_spec:
            st.session_state.messages.append({"role":"assistant","content":"⚠️ Primero adjunta un RAML o DTM (.docx)."})
            return

        arquetipo = obtener_arquetipo()
        if not arquetipo:
            st.session_state.messages.append({"role":"assistant","content":"❌ No encontré un ZIP con 'arquetipo' en el directorio."})
            return

        st.session_state.messages.append({"role":"assistant","content":"🧠 Leyendo especificación y construyendo contexto con ChatGPT..."})
        raw = leer_especificacion(st.session_state.uploaded_spec)
        ctx = inferir_metadatos(raw)

        st.session_state.messages.append({"role":"assistant","content":f"🧾 Metadatos:\n```yaml\n{yaml.safe_dump(ctx,sort_keys=False,allow_unicode=True)}\n```"})

        spec_bytes = None
        if st.session_state.uploaded_spec.name.lower().endswith(".raml"):
            st.session_state.uploaded_spec.seek(0)
            spec_bytes = st.session_state.uploaded_spec.read()

        st.session_state.messages.append({"role":"assistant","content":"⚙️ Reescribiendo archivos del arquetipo con ChatGPT + postprocesos (flows/TLS)..."})
        try:
            salida_zip, modificados, errores = procesar_arquetipo_llm(arquetipo, ctx, spec_bytes)
            st.session_state.generated_zip = salida_zip
            resumen = f"✅ Proyecto generado. Archivos modificados: {len(modificados)}"
            if errores:
                resumen += f"\n⚠️ Validaciones/Fallbacks: {len(errores)} (mostrando hasta 5):\n- " + "\n- ".join(errores[:5])
            st.session_state.messages.append({"role":"assistant","content":resumen})
        except Exception as e:
            st.session_state.messages.append({"role":"assistant","content":f"❌ Falló la generación: {e}"})
    else:
        st.session_state.messages.append({"role":"assistant","content":"💬 Escribe `crea el proyecto` para generar el zip a partir de tu RAML/DTM."})

# ====== Render historial ======
with st.container():
    for msg in st.session_state.messages:
        avatar = user_avatar if msg["role"]=="user" else assistant_avatar
        bubble = "user-bubble" if msg["role"]=="user" else "assistant-bubble"
        who = "user-message" if msg["role"]=="user" else "assistant-message"
        st.markdown(
            f'<div class="chat-message {who}"><img src="{avatar}" class="avatar"><div class="message-bubble {bubble}">{msg["content"]}</div></div>',
            unsafe_allow_html=True
        )

# ====== Entrada chat ======
user_input = st.chat_input("Escribe aquí...")
if user_input:
    st.session_state.messages.append({"role":"user","content":user_input})
    manejar_mensaje(user_input)
    st.rerun()

# ====== Descarga ======
if st.session_state.generated_zip:
    with open(st.session_state.generated_zip, "rb") as f:
        st.download_button("⬇️ Descargar Proyecto (.zip)", f, "proyecto_mulesoft_generado.zip", "application/zip")
