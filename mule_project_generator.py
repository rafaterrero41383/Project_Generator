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

    # Limpieza defensiva
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
    data.setdefault("starwars_host", data.get("host_name"))
    data.setdefault("starwars_protocol", data.get("protocol"))
    if not data.get("starwars_path"):
        base_path = (data.get("base_path") or "").lstrip("/")
        data["starwars_path"] = ("/"+base_path) if base_path else "/"

    data = aplicar_perfil_por_capa(data)
    return data

# ========= Perfil por capa =========

def aplicar_perfil_por_capa(ctx: dict) -> dict:
    capa = (ctx.get("tipo_api") or "").strip().lower()
    pref_map = {"experience": "exp", "system": "sys", "process": "prc"}
    if capa in pref_map:
        ctx.setdefault("layer_prefix", pref_map[capa])
        if ctx.get("group_id","").startswith("com.company"):
            ctx["group_id"] = f"com.company.{pref_map[capa]}"
        if ctx.get("general_path") in (None, "", "/api/*"):
            bp = (ctx.get("base_path") or "").strip("/")
            if bp:
                parts = bp.split("/")
                ctx["general_path"] = "/" + ("/".join(parts[:2]) if len(parts)>=2 else bp) + "/*"
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
    artifact = ctx.get("artifact_id", "app")
    layer = ctx.get("layer_prefix")
    prefix = f"{layer}-{artifact}" if layer else artifact

    def repl(m):
        start, old, end = m.group(1), m.group(2), m.group(3)
        if _already_prefixed(old, prefix) or _already_prefixed(old, artifact):
            return f'{start}{old}{end}'
        new = f"{prefix}-{old}"
        new = re.sub(r"--+", "-", new)
        return f'{start}{new}{end}'

    xml_text = _safe_sub(r'(<flow\s+name=")([^"]+)(")', xml_text, repl)
    xml_text = _safe_sub(r'(<sub-flow\s+name=")([^"]+)(")', xml_text, repl)
    return xml_text

def insertar_o_actualizar_tls(xml_text: str, ctx: dict) -> str:
    if not ctx.get("tls_enabled"):
        return xml_text
    if "xmlns:tls=" not in xml_text:
        return xml_text

    has_ctx = "<tls:context" in xml_text
    tls_ctx = ['<tls:context name="default-tls">']
    if ctx.get("tls_truststore_path"):
        tls_ctx.append(f'  <tls:trust-store path="{ctx["tls_truststore_path"]}" password="{ctx.get("tls_truststore_password","")}"></tls:trust-store>')
    if ctx.get("tls_keystore_path"):
        tls_ctx.append(f'  <tls:key-store path="{ctx["tls_keystore_path"]}" password="{ctx.get("tls_keystore_password","")}"></tls:key-store>')
    tls_ctx.append('</tls:context>')
    tls_block = "\n".join(tls_ctx)

    if not has_ctx:
        if "</mule>" in xml_text:
            xml_text = xml_text.replace("</mule>", tls_block + "\n</mule>")
        else:
            xml_text = xml_text + "\n" + tls_block

    def add_tls_ref(_rx: str):
        def repl(m):
            tag = m.group(0)
            if 'tlsContext-ref=' in tag:
                return tag
            return tag[:-1] + ' tlsContext-ref="default-tls"'
        return repl

    if (ctx.get("starwars_protocol") or "").upper() == "HTTPS" or 'protocol="HTTPS"' in xml_text:
        xml_text = _safe_sub(r'(<http:request-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)
        xml_text = _safe_sub(r'(<http:listener-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)

    return xml_text

def postprocesar_xml(xml_text: str, fname: str, ctx: dict) -> str:
    name = fname.lower()
    if name.endswith(".xml"):
        xml_text = renombrar_flows(xml_text, ctx)
    xml_text = insertar_o_actualizar_tls(xml_text, ctx)
    return xml_text

# ========= RÚBRICAS y utilidades =========

VALID_ACTIONS = {"retrieve","evaluate","execute","init","create","update","delete"}

def ensure_dirs(root: Path):
    base = root / "src/main/mule"
    for d in ["client", "handler", "orchestrator", "common"]:
        (base / d).mkdir(parents=True, exist_ok=True)

def forbid_loose_xml(root: Path) -> list[str]:
    base = root / "src/main/mule"
    bad = []
    for p in base.glob("*.xml"):
        bad.append(str(p))
    return bad

def parse_resources_from_raml(raml_text: str) -> dict:
    res = {}
    for line in raml_text.splitlines():
        line = line.strip()
        if line.startswith("/"):
            parts = [x for x in line.split("/") if x]
            if not parts:
                continue
            recurso = parts[0]
            action = parts[-1].lower()
            name = recurso[0].lower()+recurso[1:] if recurso else "resource"
            res.setdefault(name, set())
            if action in VALID_ACTIONS:
                res[name].add(action)
    return res

def canonical_names(api_resource: str, actions: set[str]) -> dict:
    pascal = api_resource[0].upper()+api_resource[1:]
    client = f"api{pascal}-client.xml"
    handler = f"api{pascal}-handler.xml"
    orch = [f"{api_resource}-{a}-orchestrator.xml" for a in (actions or {"retrieve"})]
    return {"client": client, "handler": handler, "orchestrators": orch}

def rename_if_needed(path: Path, expected_name: str):
    if path.name != expected_name:
        path.rename(path.with_name(expected_name))

# ========= Helpers RAML → classpath =========

def raml_classpath(root: Path) -> str|None:
    """Devuelve classpath relativo del RAML (p.ej. 'classpath:/api/api.raml') si existe."""
    target = first_raml_target(root)
    try:
        rel = target.relative_to(root / "src/main/resources")
        return "classpath:/" + "/".join(rel.parts)
    except Exception:
        # fallback si el RAML quedó en otro lugar
        candidates = list(root.rglob("*.raml"))
        if candidates:
            try:
                rel = candidates[0].relative_to(root / "src/main/resources")
                return "classpath:/" + "/".join(rel.parts)
            except Exception:
                return None
    return None

# ========= SCAFFOLD: orchestrators, client, handler (con APIkit) =========

def _flow_name(resource: str, suffix: str) -> str:
    return f"{resource}-{suffix}"

def _xml_header(apikit: bool=False):
    if apikit:
        return """<?xml version="1.0" encoding="UTF-8"?>
<mule xmlns:ee="http://www.mulesoft.org/schema/mule/ee/core"
      xmlns:http="http://www.mulesoft.org/schema/mule/http"
      xmlns:apikit="http://www.mulesoft.org/schema/mule/apikit"
      xmlns:tls="http://www.mulesoft.org/schema/mule/tls"
      xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.mulesoft.org/schema/mule/core http://www.mulesoft.org/schema/mule/core/current/mule.xsd
        http://www.mulesoft.org/schema/mule/http http://www.mulesoft.org/schema/mule/http/current/mule-http.xsd
        http://www.mulesoft.org/schema/mule/apikit http://www.mulesoft.org/schema/mule/apikit/current/mule-apikit.xsd
        http://www.mulesoft.org/schema/mule/tls http://www.mulesoft.org/schema/mule/tls/current/mule-tls.xsd
        http://www.mulesoft.org/schema/mule/ee/core http://www.mulesoft.org/schema/mule/ee/core/current/mule-ee.xsd">
""".strip()
    else:
        return """<?xml version="1.0" encoding="UTF-8"?>
<mule xmlns:ee="http://www.mulesoft.org/schema/mule/ee/core"
      xmlns:http="http://www.mulesoft.org/schema/mule/http"
      xmlns:tls="http://www.mulesoft.org/schema/mule/tls"
      xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.mulesoft.org/schema/mule/core http://www.mulesoft.org/schema/mule/core/current/mule.xsd
        http://www.mulesoft.org/schema/mule/http http://www.mulesoft.org/schema/mule/http/current/mule-http.xsd
        http://www.mulesoft.org/schema/mule/tls http://www.mulesoft.org/schema/mule/tls/current/mule-tls.xsd
        http://www.mulesoft.org/schema/mule/ee/core http://www.mulesoft.org/schema/mule/ee/core/current/mule-ee.xsd">
""".strip()

def _xml_footer():
    return "</mule>\n"

def _orchestrator_xml_skeleton(resource: str, action: str) -> str:
    flow_name = _flow_name(resource, f"{action}-orchestrator-main")
    return f"""{_xml_header(False)}
  <!-- Auto-generado: orchestrator base -->
  <flow name="{flow_name}">
    <logger level="INFO" message="[{resource}:{action}] start orchestration"/>
    <!-- TODO: invocar subflows/client aquí -->
    <logger level="INFO" message="[{resource}:{action}] end orchestration"/>
  </flow>
{_xml_footer()}""".strip()

def _client_xml_skeleton(resource_pascal: str, general_path: str, raml_cp: str|None) -> str:
    """
    Si raml_cp está presente, genera client con APIkit (listener + router).
    Si no, genera un client mínimo con logger.
    """
    flow = f"api{resource_pascal}-client-main"
    path = general_path if general_path else "/api/*"
    if raml_cp:
        return f"""{_xml_header(True)}
  <!-- Auto-generado: client con APIkit -->
  <http:listener-config name="api-httpListener">
    <http:listener-connection host="0.0.0.0" port="${{http.port}}"/>
  </http:listener-config>

  <apikit:config name="api-config" raml="{raml_cp}"/>

  <flow name="{flow}">
    <http:listener config-ref="api-httpListener" path="${{general.path}}" />
    <apikit:router config-ref="api-config" />
  </flow>

  <!-- Consola (opcional) -->
  <flow name="api-console">
    <http:listener config-ref="api-httpListener" path="/console/*" />
    <apikit:console config-ref="api-config" />
  </flow>
{_xml_footer()}""".strip()
    else:
        return f"""{_xml_header(False)}
  <!-- Auto-generado: client base -->
  <flow name="{flow}">
    <logger level="INFO" message="[client] request recibido en {path}"/>
  </flow>
{_xml_footer()}""".strip()

def _handler_xml_skeleton(resource_pascal: str) -> str:
    flow = f"api{resource_pascal}-handler-main"
    return f"""{_xml_header(False)}
  <!-- Auto-generado: handler base -->
  <flow name="{flow}">
    <logger level="INFO" message="[handler] inicio manejo"/>
    <!-- TODO: validaciones, mapping, llamadas a orchestrator -->
    <logger level="INFO" message="[handler] fin manejo"/>
  </flow>
{_xml_footer()}""".strip()

def _common_error_handler_xml() -> str:
    return f"""{_xml_header(False)}
  <!-- Auto-generado: common error handler -->
  <sub-flow name="common-error-handler">
    <logger level="ERROR" message="Error en flujo: #[error.description] - #[error.cause]"/>
  </sub-flow>
{_xml_footer()}""".strip()

def scaffold_orchestrators(root: Path, resources: dict) -> list[str]:
    created = []
    base = root / "src/main/mule/orchestrator"
    base.mkdir(parents=True, exist_ok=True)
    for resource, actions in (resources or {}).items():
        planned = sorted(actions or {"retrieve"})
        for action in planned:
            fname = f"{resource}-{action}-orchestrator.xml"
            path = base / fname
            if not path.exists():
                xml = _orchestrator_xml_skeleton(resource, action)
                try:
                    ET.fromstring(xml)
                except ET.ParseError:
                    xml = f"<mule><flow name='{_flow_name(resource, f'{action}-orchestrator-main')}'/></mule>"
                path.write_text(xml, encoding="utf-8")
                created.append(str(path.relative_to(root)))
    return created

def scaffold_client_handler(root: Path, resources: dict, general_path: str, raml_cp: str|None) -> list[str]:
    """
    Crea client/handler y common-error-handler si faltan.
    Si hay RAML → client incluye APIkit (listener + router + console).
    """
    created = []
    base = root / "src/main/mule"
    client_dir = base / "client"
    handler_dir = base / "handler"
    client_dir.mkdir(parents=True, exist_ok=True)
    handler_dir.mkdir(parents=True, exist_ok=True)

    # common-error-handler.xml
    ceh = handler_dir / "common-error-handler.xml"
    if not ceh.exists():
        xml = _common_error_handler_xml()
        try:
            ET.fromstring(xml)
        except ET.ParseError:
            xml = "<mule><sub-flow name='common-error-handler'/></mule>"
        ceh.write_text(xml, encoding="utf-8")
        created.append(str(ceh.relative_to(root)))

    for resource, actions in (resources or {}).items():
        pascal = resource[0].upper()+resource[1:] if resource else "Resource"
        # client
        c_name = f"api{pascal}-client.xml"
        c_path = client_dir / c_name
        if not c_path.exists():
            xml = _client_xml_skeleton(pascal, general_path, raml_cp)
            try:
                ET.fromstring(xml)
            except ET.ParseError:
                xml = f"<mule><flow name='api{pascal}-client-main'/></mule>"
            c_path.write_text(xml, encoding="utf-8")
            created.append(str(c_path.relative_to(root)))
        # handler
        h_name = f"api{pascal}-handler.xml"
        h_path = handler_dir / h_name
        if not h_path.exists():
            xml = _handler_xml_skeleton(pascal)
            try:
                ET.fromstring(xml)
            except ET.ParseError:
                xml = f"<mule><flow name='api{pascal}-handler-main'/></mule>"
            h_path.write_text(xml, encoding="utf-8")
            created.append(str(h_path.relative_to(root)))
    return created

# ========= Rúbricas (aplican después del scaffold) =========

def enforce_rubrics_on_tree(root: Path, raml_bytes: bytes|None) -> list[str]:
    errors = []
    ensure_dirs(root)

    base = root / "src/main/mule"
    client_dir = base / "client"
    handler_dir = base / "handler"
    orch_dir = base / "orchestrator"
    common_dir = base / "common"

    loose = forbid_loose_xml(root)
    if loose:
        errors.append(f"XMLs sueltos en src/main/mule: {', '.join(loose)}")

    resources = {}
    if raml_bytes:
        try:
            raml_text = raml_bytes.decode("utf-8","ignore")
            resources = parse_resources_from_raml(raml_text)
        except Exception:
            resources = {}
    if not resources:
        mf = list(base.rglob("*-mainFlow.xml"))
        stem = "api"
        if mf:
            stem = mf[0].stem.replace("-mainFlow","")
        resources = {stem: set()}

    for recurso, actions in resources.items():
        expected = canonical_names(recurso, actions)

        existing_client = list(client_dir.glob("*.xml"))
        if not existing_client:
            errors.append(f"Falta archivo client para recurso {recurso}")
        else:
            rename_if_needed(existing_client[0], expected["client"])
            if not re.match(r"^api[A-Z][A-Za-z0-9]*-client\.xml$", expected["client"]):
                errors.append(f"Nombre inválido en client: {expected['client']}")

        existing_handler = [p for p in handler_dir.glob("*.xml") if p.name != "common-error-handler.xml"]
        if not existing_handler:
            errors.append(f"Falta archivo handler para recurso {recurso}")
        else:
            rename_if_needed(existing_handler[0], expected["handler"])
            if not re.match(r"^api[A-Z][A-Za-z0-9]*-handler\.xml$", expected["handler"]):
                errors.append(f"Nombre inválido en handler: {expected['handler']}")

        if not (handler_dir / "common-error-handler.xml").exists():
            errors.append("Falta common-error-handler.xml en handler/")

        existing_orch = list(orch_dir.glob("*.xml"))
        if not existing_orch:
            errors.append(f"Faltan orchestrators para recurso {recurso}")
        else:
            if not actions:
                actions = {"retrieve"}
            expected_orch = set(expected["orchestrators"])
            for exp, cur in zip(sorted(expected_orch), existing_orch):
                rename_if_needed(cur, exp)
            bad = [p.name for p in orch_dir.glob("*.xml")
                   if not re.match(r"^[a-z][A-Za-z0-9]*-(retrieve|evaluate|execute|init|create|update|delete)-orchestrator\.xml$", p.name)]
            if bad:
                errors.append(f"Nombres inválidos en orchestrator: {', '.join(bad)}")

    for p in common_dir.glob("*.xml"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if 'http:listener' in text:
                errors.append("common/ no debe contener listeners HTTP")
        except Exception:
            pass

    return errors

def write_validate_script(root: Path):
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    content = """#!/usr/bin/env bash
set -euo pipefail

# 1) Carpetas obligatorias
for d in client handler orchestrator common; do
  test -d "src/main/mule/$d" || { echo "Falta carpeta $d"; exit 1; }
done

# 2) Nada de XMLs sueltos en src/main/mule
if find src/main/mule -maxdepth 1 -type f -name "*.xml" | grep -q .; then
  echo "No debe haber .xml en src/main/mule (mover a client/handler/orchestrator/common)"
  exit 1
fi

# 3) Nombres válidos por capa
if find src/main/mule/client -type f -name "*.xml" | grep -Pv '^.*/api[A-Z][A-Za-z0-9]*-client\\.xml$' | grep -q .; then
  echo "Nombre inválido en client (usar api<Recurso>-client.xml)"; exit 1
fi

if find src/main/mule/handler -type f -name "*.xml" | grep -Pv '^.*/(api[A-Z][A-Za-z0-9]*-handler|common-error-handler)\\.xml$' | grep -q .; then
  echo "Nombre inválido en handler (usar api<Recurso>-handler.xml o common-error-handler.xml)"; exit 1
fi

if find src/main/mule/orchestrator -type f -name "*.xml" | grep -Pv '^.*/[a-z][A-Za-z0-9]*-(retrieve|evaluate|execute|init|create|update|delete)-orchestrator\\.xml$' | grep -q .; then
  echo "Nombre inválido en orchestrator (<recurso>-<action>-orchestrator.xml)"; exit 1
fi

echo "Validación de estructura OK ✅"
"""
    (scripts / "validate-structure.sh").write_text(content, encoding="utf-8")
    os.chmod(scripts / "validate-structure.sh", 0o755)

def write_min_readme(root: Path, resources: dict):
    readme = root / "README.md"
    lines = [
        "# Proyecto MuleSoft",
        "",
        "## Recursos y correlación por capa",
        "",
        "| Recurso | Client | Handler | Orchestrators |",
        "|---|---|---|---|",
    ]
    for r, actions in resources.items():
        pascal = r[0].upper()+r[1:] if r else "Resource"
        client = f"api{pascal}-client.xml"
        handler = f"api{pascal}-handler.xml"
        orchs = ", ".join(sorted([f"{r}-{a}-orchestrator.xml" for a in (actions or {'retrieve'})]))
        lines.append(f"| {r} | {client} | {handler} | {orchs} |")
    readme.write_text("\n".join(lines)+"\n", encoding="utf-8")

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

    roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    root = roots[0] if len(roots)==1 else tmp_dir

    # Progreso UI
    files_to_touch = []
    for r,_,fs in os.walk(root):
        for f in fs:
            p = Path(r)/f
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

                if path.suffix.lower() == ".xml":
                    nuevo = postprocesar_xml(nuevo, path.name, ctx)

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

    # Inyectar RAML y parsear recursos
    resources_for_readme = {}
    raml_cp_value = None
    if spec_bytes and st.session_state.uploaded_spec.name.lower().endswith(".raml"):
        target = first_raml_target(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            f.write(spec_bytes)
        modificados.append(str(target.relative_to(root)))
        try:
            resources_for_readme = parse_resources_from_raml(spec_bytes.decode("utf-8","ignore"))
        except Exception:
            resources_for_readme = {}
        # classpath del RAML para apikit
        raml_cp_value = raml_classpath(root)

    # === SCAFFOLD client/handler (+APIkit si hay RAML) y common-error-handler ===
    if resources_for_readme:
        created_ch = scaffold_client_handler(root, resources_for_readme, ctx.get("general_path"), raml_cp_value)
        if created_ch:
            modificados.extend(created_ch)

    # === SCAFFOLD orchestrators (antes de rúbricas) ===
    if resources_for_readme:
        created_orch = scaffold_orchestrators(root, resources_for_readme)
        if created_orch:
            modificados.extend(created_orch)

    # === RÚBRICAS (estructura y nombres) ===
    rubric_errors = enforce_rubrics_on_tree(root, spec_bytes)

    # Script de validación para CI/CD
    write_validate_script(root)

    # README opcional con tabla de correlación
    if resources_for_readme:
        try:
            write_min_readme(root, resources_for_readme)
        except Exception:
            pass

    if rubric_errors:
        raise RuntimeError("Rúbricas BLOQUEANTES:\n- " + "\n- ".join(rubric_errors))

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

        st.session_state.messages.append({"role":"assistant","content":"⚙️ Reescribiendo archivos del arquetipo con ChatGPT + scaffolds (client/APIkit/handler/orchestrators) + rúbricas..."})
        try:
            salida_zip, modificados, errores = procesar_arquetipo_llm(arquetipo, ctx, spec_bytes)
            st.session_state.generated_zip = salida_zip
            resumen = f"✅ Proyecto generado. Archivos modificados/creados: {len(modificados)}"
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
