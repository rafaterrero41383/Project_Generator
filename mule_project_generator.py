import tempfile, zipfile, re, os, sys, types, io, json, textwrap
import xml.etree.ElementTree as ET
import yaml
from pathlib import Path

from h11._abnf import method

# --- Parche compatibilidad 3.13 ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    sys.modules['imghdr'] = imghdr
# ----------------------------------

from docx import Document
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import urllib.parse

# ========= CONFIG =========
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("❌ Falta OPENAI_API_KEY en secretos/entorno.")
    st.stop()

client = OpenAI()
MODEL_BASE = "gpt-4o-mini"

st.set_page_config(page_title="🤖 Generador de Proyectos Mulesoft", layout="wide")

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

st.markdown("<h1 style='text-align:center;'>🤖 Generador de Proyectos Mulesoft</h1>", unsafe_allow_html=True)

# ====== Estado ======
if "messages" not in st.session_state: st.session_state.messages = []
if "uploaded_spec" not in st.session_state: st.session_state.uploaded_spec = None
if "generated_zip" not in st.session_state: st.session_state.generated_zip = None
if "observaciones" not in st.session_state: st.session_state.observaciones = []
if "service_type" not in st.session_state: st.session_state.service_type = "UNKNOWN"
if "spec_name" not in st.session_state: st.session_state.spec_name = None
if "spec_kind" not in st.session_state: st.session_state.spec_kind = None   # "RAML" | "OAS" | "TEXT"
if "raml_text" not in st.session_state: st.session_state.raml_text = None  # para evaluación de rúbricas
if "rubrics_result" not in st.session_state: st.session_state.rubrics_result = None

TYPE_LABELS = {
    "REC": "RECEPTION",
    "DOM": "DOMAIN",
    "BUS": "BUSINESS RULES",
    "PROXY": "PROXY",
    "UNKNOWN": "UNKNOWN"
}

col1, col2 = st.columns([1,1])
with col1:
    if st.button("🔄 Reiniciar"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()
with col2:
    st.caption("")

# ========= Utilidades =========

TEXT_EXTS = {".xml",".json",".yaml",".yml",".raml",".properties",".txt",".pom",".md"}

INVALID_WIN = r'[:*?"<>|\\/]'  # caracteres inválidos para nombres de archivo en Windows

def safe_filename(stx: str, fallback: str = "root") -> str:
    s = (stx or "").strip()
    if not s:
        return fallback
    s = re.sub(INVALID_WIN, "-", s)
    s = s.strip("-._ ")
    return s or fallback

def _map_prefix_to_type(filename: str) -> str | None:
    m = re.match(r"^(Rec|DOM|Dom|BUS|Bus|PRO|Pro)_", filename or "")
    if not m: return None
    pref = m.group(1).lower()
    if pref == "rec": return "REC"
    if pref == "dom": return "DOM"
    if pref == "bus": return "BUS"
    if pref == "pro": return "PROXY"
    return None

def leer_especificacion(file) -> str:
    """Lee RAML, OAS (yaml/json) o DTM .docx como texto para el prompt de metadatos."""
    name = file.name.lower()
    file.seek(0)
    if name.endswith(".raml"):
        st.session_state.spec_kind = "RAML"
        txt = file.read().decode("utf-8", errors="ignore")
        st.session_state.raml_text = txt
        return txt
    if name.endswith((".yaml",".yml",".json")):
        st.session_state.spec_kind = "OAS"
        return file.read().decode("utf-8", errors="ignore")
    if name.endswith(".docx"):
        st.session_state.spec_kind = "TEXT"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file.read())
            path = tmp.name
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    st.session_state.spec_kind = None
    return ""

def obtener_arquetipo() -> str|None:
    for f in os.listdir():
        if f.endswith(".zip") and "arquetipo" in f.lower():
            return f
    demo = "/mnt/data/arquetipo-mulesoft.zip"
    if os.path.exists(demo): return demo
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

# ========= Upload =========

spec = st.file_uploader(
    "Adjunta la especificación (RAML, OAS .yaml/.json o DTM .docx)",
    type=["raml","yaml","yml","json","docx"]
)
if spec and st.session_state.uploaded_spec is None:
    st.session_state.uploaded_spec = spec
    st.session_state.spec_name = spec.name

    # Detección SOLO por prefijo de archivo
    stype = _map_prefix_to_type(spec.name)
    st.session_state.service_type = stype if stype else "UNKNOWN"

    # Clasificar tipo de spec por extensión
    leer_especificacion(spec)  # setea spec_kind y raml_text
    st.session_state.messages.append({
        "role":"assistant",
        "content":f"📄 Archivo \"{spec.name}\" cargado. Escribe **crea el proyecto**."
    })

# ========= Helpers PROXY =========

def _parse_base_uri(uri: str):
    if not uri: return ("http","localhost","8081","/")
    p = urllib.parse.urlparse(uri)
    protocol = p.scheme or "http"
    host = p.hostname or "localhost"
    port = str(p.port or (443 if protocol == "https" else 80))
    base_path = p.path or "/"
    if not base_path.startswith("/"): base_path = "/" + base_path
    return (protocol, host, port, base_path)

def _ensure_property_line(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:", re.M)
    if pattern.search(text): return text
    return text.rstrip() + f"\n{key}: {value}\n"

def _patch_env_properties(root: Path, protocol: str, host: str, port: str, base_path: str):
    props_dir = root / "src" / "main" / "resources" / "properties"
    wanted = {
        "proxy.protocol": protocol,
        "proxy.host": host,
        "proxy.port": port,
        "proxy.basePath": base_path,
        "proxy.conn.timeout": "10000",
        "proxy.sock.timeout": "10000",
    }
    if not props_dir.exists(): return
    for f in props_dir.glob("*-config.yaml"):
        try:
            txt = f.read_text(encoding="utf-8")
            for k,v in wanted.items():
                txt = _ensure_property_line(txt, k, str(v))
            f.write_text(txt, encoding="utf-8")
        except Exception:
            pass

def _gen_proxy_flows(dst_mule_dir: Path, artifact_id: str):
    dst_mule_dir.mkdir(parents=True, exist_ok=True)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<mule xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:http="http://www.mulesoft.org/schema/mule/http"
      xmlns:ee="http://www.mulesoft.org/schema/mule/ee/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.mulesoft.org/schema/mule/core http://www.mulesoft.org/schema/mule/core/current/mule.xsd
        http://www.mulesoft.org/schema/mule/http http://www.mulesoft.org/schema/mule/http/current/mule-http.xsd
        http://www.mulesoft.org/schema/mule/ee/core http://www.mulesoft.org/schema/mule/ee/core/current/mule-ee.xsd">

  <http:listener-config name="{artifact_id}-http">
    <http:listener-connection host="0.0.0.0" port="8081"/>
  </http:listener-config>

  <http:request-config name="{artifact_id}-upstream">
    <http:request-connection protocol="#[p('proxy.protocol')]" host="#[p('proxy.host')]" port="#[p('proxy.port')]"/>
  </http:request-config>

  <flow name="{artifact_id}-proxy-flow">
    <http:listener config-ref="{artifact_id}-http" path="/{{+proxyPath}}">
      <http:response statusCode="#[attributes.statusCode default 200]"/>
    </http:listener>

    <ee:transform doc:name="Build Target Attributes" xmlns:ee="http://www.mulesoft.org/schema/mule/ee/core">
      <ee:message>
        <ee:set-payload><![CDATA[%dw 2.0
output application/java
---
payload
]]></ee:set-payload>

        <ee:set-attributes><![CDATA[%dw 2.0
output application/java
var qp = (attributes.queryParams default {{}}) as Object
---
{
  method: (attributes.method default "GET") as String,
  targetPath: (p("proxy.basePath") as String) ++ "/" ++ (attributes."listenerPathParams".proxyPath as String),
  queryParams: qp,
  headers: (attributes.headers default {{}}) as Object
}]]></ee:set-attributes>
      </ee:message>
    </ee:transform>

    <http:request method="#[attributes.method]"
                  config-ref="{artifact_id}-upstream"
                  path="#[attributes.targetPath]"
                  queryParams="#[attributes.queryParams]"
                  headers="#[attributes.headers]">
      <http:request-builder>
        <http:header headerName="host" value="#[p('proxy.host')]"/>
      </http:request-builder>
    </http:request>
  </flow>

  <error-handler>
    <on-error-propagate logException="true">
      <set-payload value="#[error.description default error.message]" />
    </on-error-propagate>
  </error-handler>
</mule>
"""
    (dst_mule_dir / f"{artifact_id}-proxy.xml").write_text(xml, encoding="utf-8")

# ========= LLM metadatos =========

PROMPT_CTX = """Eres un ingeniero de integración Mulesoft.
Dado un RAML u OpenAPI (OAS) o contenido DTM en texto, entrega un YAML válido con estas claves:

project_name: nombre amigable del proyecto (string)
artifact_id: id maven en kebab-case (string)
version: semver (string, ej: 1.0.0)
group_id: maven groupId (string, por defecto com.company.experience)
tipo_api: Experience | System | Process (si no aplica, null)
base_uri: URI base del API si se infiere (string o null)
host_name: host si se puede inferir (string o null)
protocol: HTTP/HTTPS si se infiere (string o null)
base_path: path base sin host/protocolo; sin barra inicial (string o null)
general_path: path del listener para ${general.path} (string, ej: "/api/*")
upstream_host: host del sistema objetivo (string o null)
upstream_protocol: HTTP/HTTPS (string o null)
upstream_path: path base (string, ej: "/v1/endpoint")
media_type: mediaType si existe (string o null)
protocols: protocolos si existen (string o null)

Reglas:
- artifact_id = project_name en kebab-case.
- general_path: si hay base_path o primer endpoint, usar "/<path>/*".
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

    m = re.search(r"```(?:yaml|yml)?\s*(.*?)```", yml, re.DOTALL)
    if m: yml = m.group(1).strip()
    try:
        data = yaml.safe_load(yml) or {}
    except Exception:
        data = {}

    data.setdefault("project_name", "MuleApplication")
    if "artifact_id" not in data:
        slug = re.sub(r"[^a-zA-Z0-9]+","-", data["project_name"]).strip("-").lower()
        data["artifact_id"] = re.sub(r"-{2,}","-", slug)
    data.setdefault("version","1.0.0")
    data.setdefault("group_id","com.company.experience")
    data.setdefault("general_path","/api/*")
    data.setdefault("upstream_host", data.get("host_name"))
    data.setdefault("upstream_protocol", data.get("protocol"))
    if not data.get("upstream_path"):
        base_path = (data.get("base_path") or "").lstrip("/")
        data["upstream_path"] = ("/"+base_path) if base_path else "/"

    return aplicar_perfil_por_capa(data)

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
            ctx["general_path"] = ("/"+bp+"/*") if bp else f"/{pref_map[capa]}/*"
    return ctx

# ========= Postprocesos deterministas =========

def _safe_sub(rx, text, repl_fn, count=0):
    r = re.compile(rx, re.DOTALL)
    return r.sub(lambda m: repl_fn(m), text, count=count)

def renombrar_flows_con_prefijo(xml_text: str, ctx: dict) -> str:
    artifact = ctx.get("artifact_id", "app")
    layer = ctx.get("layer_prefix")
    prefix = f"{layer}-{artifact}" if layer else artifact

    def repl(m):
        start, old, end = m.group(1), m.group(2), m.group(3)
        if old.startswith(prefix+"-") or old.startswith(artifact+"-"):
            return f'{start}{old}{end}'
        new = re.sub(r"--+", "-", f"{prefix}-{old}")
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

    if (ctx.get("upstream_protocol") or "").upper() == "HTTPS" or 'protocol="HTTPS"' in xml_text:
        xml_text = _safe_sub(r'(<http:request-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)
        xml_text = _safe_sub(r'(<http:listener-connection\b[^>]*)(/?>)', xml_text, add_tls_ref(r""), count=0)

    return xml_text

def postprocesar_xml(xml_text: str, ctx: dict) -> str:
    xml_text = renombrar_flows_con_prefijo(xml_text, ctx)
    xml_text = insertar_o_actualizar_tls(xml_text, ctx)
    return xml_text

# ========= Parsing RAML (semilight) =========

HTTP_METHODS = {"get","post","put","delete","patch","head","options"}
EXTRA_ACTIONS = {"retrieve","evaluate","execute","init","create","update","delete"}

def parse_raml_semilight(raml_text: str) -> dict:
    lines = raml_text.splitlines()
    res = {}
    cur_res = None
    cur_method = None

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        if line.lstrip().startswith("/"):
            seg = line.strip().split()[0].strip("/").split("/")[0]
            cur_res = safe_filename(seg, "root")
            res.setdefault(cur_res, {"methods": set(), "headers_required": {}, "req_types": {}, "res_types": {}})
            cur_method = None
            continue

        token = line.strip().rstrip(":").lower()
        if token in HTTP_METHODS or token in EXTRA_ACTIONS:
            cur_method = token
            res.setdefault(cur_res or "root", {"methods": set(), "headers_required": {}, "req_types": {}, "res_types": {}})
            res[cur_res or "root"]["methods"].add(cur_method)
            continue

        if cur_method and line.strip().endswith(":") and "headers" in line.lower():
            for j in range(i+1, min(i+7, len(lines))):
                l2 = lines[j].strip()
                if l2.endswith(":") and not l2.startswith("-"):
                    hdr = l2.rstrip(":")
                    block = "\n".join(lines[j: min(j+6, len(lines))]).lower()
                    if "required: true" in block:
                        res[cur_res or "root"]["headers_required"].setdefault(cur_method, []).append(hdr)

        if cur_method and "body:" in line.lower():
            block = "\n".join(lines[i: min(i+10, len(lines))])
            m = re.search(r"type:\s*([A-Za-z0-9_\-\.]+)", block)
            if m: res[cur_res or "root"]["req_types"][cur_method] = m.group(1)

        if cur_method and "responses:" in line.lower():
            block = "\n".join(lines[i: min(i+15, len(lines))])
            m = re.search(r"200:\s*(?:\n|\r\n).*?type:\s*([A-Za-z0-9_\-\.]+)", block, re.DOTALL)
            if m: res[cur_res or "root"]["res_types"][cur_method] = m.group(1)

    for r, d in res.items():
        if not d["methods"]:
            d["methods"].add("retrieve")
    return res

# ========= Generadores XML =========

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
        http://www.mulesoft.org/schema/mule/ee/core http://www.mulesoft.org/schema/mule/ee/core/current/mule-ee.xsd">"""
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
        http://www.mulesoft.org/schema/mule/ee/core http://www.mulesoft.org/schema/mule/ee/core/current/mule-ee.xsd">"""

def _xml_footer():
    return "</mule>\n"

def _mk_error_handler_ref():
    return """
    <error-handler>
      <on-error-continue logException="true" type="ANY">
        <flow-ref name="hdl_commonErrorHandler"/>
      </on-error-continue>
    </error-handler>""".rstrip()

def client_file_xml(resource: str, methods: set, general_path: str, use_apikit: bool, raml_cp: str|None):
    header = _xml_header(apikit=use_apikit)

    flows = []
    for m in sorted(methods):
        fname = f"{resource}_client_{m}"
        flows.append(f'''  <flow name="{fname}">
    <logger level="INFO" message="[{resource}] client {m} start"/>
    <flow-ref name="{resource}_handler_{m}"/>
    <logger level="INFO" message="[{resource}] client {m} end"/>
{_mk_error_handler_ref()}
  </flow>''')

    apikit_part = ""
    if use_apikit and raml_cp:
        apikit_part = f"""
  <http:listener-config name="{resource}-httpListener">
    <http:listener-connection host="0.0.0.0" port="${{http.port}}"/>
  </http:listener-config>

  <apikit:config name="{resource}-api-config" raml="{raml_cp}"/>

  <flow name="{resource}-http-inbound">
    <http:listener config-ref="{resource}-httpListener" path="${{general.path}}"/>
    <apikit:router config-ref="{resource}-api-config"/>
  </flow>

  <flow name="{resource}-api-console">
    <http:listener config-ref="{resource}-httpListener" path="/console/*"/>
    <apikit:console config-ref="{resource}-api-config"/>
  </flow>
""".rstrip()

        impl = []
        for m in sorted(methods):
            apiflow = f"{m}:/"+resource
            impl.append(f'''  <flow name="{apiflow}">
    <flow-ref name="{resource}_client_{m}"/>
{_mk_error_handler_ref()}
  </flow>''')
        apikit_part = apikit_part + "\n" + "\n".join(impl)

    content = f"""{header}
  <!-- client consolidado para recurso '{resource}' -->
{apikit_part if apikit_part else ""}
{chr(10).join(flows)}
{_xml_footer()}"""
    return content.strip()

def handler_file_xml(resource: str, methods: set, raml_info: dict):
    header = _xml_header(False)
    blocks = []
    for m in sorted(methods):
        req_headers = raml_info.get(resource, {}).get("headers_required", {}).get(m, []) if raml_info else []
        hdr_sets = "\n".join([f'    <set-variable variableName="{h.replace("-", "_")}" value="#[attributes.headers.\'{h}\']"/>' for h in req_headers]) if req_headers else "    <!-- no required headers detected -->"
        blocks.append(f'''  <flow name="{resource}_handler_{m}">
{hdr_sets}
    <flow-ref name="{resource}_orchestrator_{m}"/>
{_mk_error_handler_ref()}
  </flow>''')
    return f"""{header}
  <!-- handler consolidado para recurso '{resource}' -->
{chr(10).join(blocks)}
{_xml_footer()}""".strip()

def orchestrator_file_xml(resource: str, methods: set, raml_info: dict, single_file: bool):
    header = _xml_header(False)
    if single_file:
        blocks = []
        for m in sorted(methods):
            blocks.append(f'''  <flow name="{resource}_orchestrator_{m}">
    <logger level="INFO" message="[{resource}] orchestrator {m} start - reqId=#[attributes.headers.'consumerRequestId'] sess=#[attributes.headers.'sessionId']"/>
    <set-payload value='{{"status":"OK","resource":"{resource}","method":"{m}"}}' mimeType="application/json"/>
    <logger level="INFO" message="[{resource}] orchestrator {m} end"/>
{_mk_error_handler_ref()}
  </flow>''')
        return f"""{header}
  <!-- orchestrator consolidado para recurso '{resource}' -->
{chr(10).join(blocks)}
{_xml_footer()}""".strip()
    else:
        m = next(iter(methods))
        return f"""{header}
  <flow name="{resource}_orchestrator_{m}">
    <logger level="INFO" message="[{resource}] orchestrator {m} start - reqId=#[attributes.headers.'consumerRequestId'] sess=#[attributes.headers.'sessionId']"/>
    <set-payload value='{{"status":"OK","resource":"{resource}","method":"{m}"}}' mimeType="application/json"/>
    <logger level="INFO" message="[{resource}] orchestrator {m} end"/>
{_mk_error_handler_ref()}
  </flow>
{_xml_footer()}""".strip()

def common_error_handler_xml_detailed():
    # Cumple rúbrica handler-error.xml / mapeo 4xx/5xx
    header = _xml_header(False)
    return f"""{header}
  <!-- common error handler con mapeo de status -->
  <sub-flow name="hdl_commonErrorHandler">
    <set-variable variableName="httpStatus" value="#[(error.errorType.namespace default '') as String match {{
      case 'HTTP' -> (error.errorType.identifier default '500') as Number
      else -> 500
    }}]"/>
    <set-variable variableName="outboundHeaders" value="#[{{ 'Content-Type': 'application/json' }}]"/>
    <set-payload value='{{"status":"ERROR","message":"#[error.description default error.message]"}}' mimeType="application/json"/>
  </sub-flow>
{_xml_footer()}""".strip()

def validation_headers_xml():
    header = _xml_header(False)
    return f"""{header}
  <!-- Validador de headers obligatorios (plantilla) -->
  <sub-flow name="common_validate_headers">
    <choice>
      <when expression="#[isEmpty(attributes.headers.'consumerRequestId')]">
        <raise-error type="HTTP:BAD_REQUEST" description="Missing consumerRequestId"/>
      </when>
      <otherwise/>
    </choice>
  </sub-flow>
{_xml_footer()}""".strip()

def global_logging_observability_xml():
    header = _xml_header(False)
    return f"""{header}
  <!-- Convención de logging y hooks de métricas -->
  <sub-flow name="common_log_inbound">
    <logger level="INFO" message='{{"event":"inbound","reqId":"#[attributes.headers."consumerRequestId"]","path":"#[attributes.requestPath]","method":"#[attributes.method]"}}'/>
  </sub-flow>

  <sub-flow name="common_log_outbound">
    <logger level="INFO" message='{{"event":"outbound","status":"#[attributes.statusCode default 200]"}}'/>
  </sub-flow>
{_xml_footer()}""".strip()

def healthcheck_xml():
    header = _xml_header(False)
    return f"""{header}
  <flow name="common_healthcheck">
    <set-payload value='{{"status":"UP"}}' mimeType="application/json"/>
  </flow>
{_xml_footer()}""".strip()

def common_error_handler_xml_min():
    header = _xml_header(False)
    return f"""{header}
  <!-- common error handler mínimo -->
  <sub-flow name="hdl_commonErrorHandler">
    <logger level="ERROR" message="type=#[error.errorType] desc=#[error.description]"/>
  </sub-flow>
{_xml_footer()}""".strip()

# ========= Archivos base y helpers =========

def ensure_dirs(root: Path):
    base = root / "src/main/mule"
    for d in ["client", "handler", "orchestrator", "common"]:
        (base / d).mkdir(parents=True, exist_ok=True)
    (root / "src/main/resources/api").mkdir(parents=True, exist_ok=True)
    (root / "src/main/resources/properties").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "src/test/munit").mkdir(parents=True, exist_ok=True)
    (root / "exchange-docs").mkdir(parents=True, exist_ok=True)

def write_minimum_base_files(root: Path):
    props_dir = root / "src/main/resources/properties"
    props = root / "src/main/resources/properties/application.properties"
    if not props.exists():
        props.write_text("http.port=8081\ngeneral.path=/api/*\n", encoding="utf-8")

    # Env properties (cumple rúbrica 23)
    for env in ("dev","qa","prod"):
        f = props_dir / f"{env}-config.yaml"
        if not f.exists():
            f.write_text(
                "upstream:\n  protocol: https\n  host: backend.example.com\n  port: 443\n  basePath: /v1\n# secure-properties: usar para secretos\n",
                encoding="utf-8"
            )

    maf = root / "mule-artifact.json"
    if not maf.exists():
        maf.write_text('{"minMuleVersion":"4.6.0","secureProperties":[],"name":"mule-app"}\n', encoding="utf-8")

    pom = root / "pom.xml"
    if not pom.exists():
        pom.write_text("""<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.company.experience</groupId>
  <artifactId>mule-app</artifactId>
  <version>1.0.0</version>
  <packaging>mule-application</packaging>
  <name>mule-app</name>
  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <mule.runtime.version>4.6.9</mule.runtime.version>
  </properties>
</project>
""", encoding="utf-8")

    # Exchange docs (rúbrica 26)
    ed = root / "exchange-docs" / "home.md"
    if not ed.exists():
        ed.write_text("# Exchange Docs\n\nOwner: TBD\nSLA: TBD\nVersion: 1.0.0\n\nDescripción breve del API.\n", encoding="utf-8")

def first_raml_target(dst_root: Path) -> Path:
    return dst_root / "src/main/resources/api/api.raml"

def oas_target(dst_root: Path) -> Path:
    return dst_root / "src/main/resources/api/openapi.yaml"

def raml_classpath(root: Path) -> str|None:
    target = first_raml_target(root)
    try:
        rel = target.relative_to(root / "src/main/resources")
        return "classpath:/" + "/".join(rel.parts)
    except Exception:
        return None

def transformar_archivo_con_gpt(fname: str, original: str, ctx: dict) -> str:
    PROMPT_FILE = """Eres un configurador experto de proyectos Mule 4.
Actualiza el archivo indicado usando METADATOS (YAML).

Reglas:
- Mantén formato/saltos.
- No agregues explicaciones ni ```.
- Sustituye placeholders (groupId, artifactId, version, project.mule.name,
  http listener path/port, http request host/protocol/path, exchange.json main/assetId/groupId/name/version,
  y propiedades YAML app/general/upstream).
- Si un valor del contexto es null, no lo inventes.
- No borres secciones no relacionadas.

=== METADATOS (YAML) ===
{ctx_yaml}

=== ARCHIVO ({fname}) ORIGINAL ===
{original}
"""
    ctx_yaml = yaml.safe_dump(ctx, sort_keys=False, allow_unicode=True)
    raw = _gpt([
        {"role":"system","content":"Actúa como refactorizador determinista de archivos Mule/Java/XML/YAML/JSON."},
        {"role":"user","content": PROMPT_FILE.format(ctx_yaml=ctx_yaml, fname=fname, original=original)}
    ], temperature=0.1)

    blocks = re.findall(r"```(?:xml|yaml|yml|json|properties|txt)?\s*(.*?)```", raw, re.DOTALL)
    contenido = (blocks[-1].strip() if blocks else raw.strip())
    if not contenido or len(contenido.splitlines()) < max(3, int(len(original.splitlines())*0.3)):
        return original
    return contenido

def enforce_pom_requirements(root_dir: Path, ctx: dict, use_apikit: bool):
    pom_path = root_dir / "pom.xml"
    if not pom_path.exists(): return
    txt = pom_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ET.fromstring(txt)
    except ET.ParseError:
        return
    ns = tree.tag.split("}",1)[0][1:] if tree.tag.startswith("{") else None
    def q(tag): return f"{{{ns}}}{tag}" if ns else tag

    packaging = tree.find(q("packaging"))
    if packaging is None or (packaging.text or "").strip().lower() != "mule-application":
        if packaging is None: packaging = ET.SubElement(tree, q("packaging"))
        packaging.text = "mule-application"

    artifactId = tree.find(q("artifactId"))
    name = tree.find(q("name"))
    groupId = tree.find(q("groupId"))
    artifact = ctx.get("artifact_id") or "mule-app"
    pname = ctx.get("project_name") or artifact
    if artifactId is None:
        artifactId = ET.SubElement(tree, q("artifactId"))
    artifactId.text = artifact
    if name is None:
        name = ET.SubElement(tree, q("name"))
    name.text = pname
    if groupId is None:
        groupId = ET.SubElement(tree, q("groupId"))
    groupId.text = ctx.get("group_id","com.company.experience")

    # properties UTF-8 + mule.runtime.version
    props = tree.find(q("properties")) or ET.SubElement(tree, q("properties"))
    found_enc = props.find(q("project.build.sourceEncoding"))
    if found_enc is None:
        ET.SubElement(props, q("project.build.sourceEncoding")).text = "UTF-8"
    found_rt = props.find(q("mule.runtime.version"))
    if found_rt is None:
        ET.SubElement(props, q("mule.runtime.version")).text = "4.6.9"

    # mule-maven-plugin
    build = tree.find(q("build")) or ET.SubElement(tree, q("build"))
    plugins = build.find(q("plugins")) or ET.SubElement(build, q("plugins"))
    has_plugin = False
    for p in plugins.findall(q("plugin")):
        gid = (p.find(q("groupId")).text if p.find(q("groupId")) is not None else "")
        aid = (p.find(q("artifactId")).text if p.find(q("artifactId")) is not None else "")
        if gid.strip()=="org.mule.tools.maven" and aid.strip()=="mule-maven-plugin":
            has_plugin = True
            ext = p.find(q("extensions")) or ET.SubElement(p, q("extensions"))
            ext.text = "true"
    if not has_plugin:
        p = ET.SubElement(plugins, q("plugin"))
        ET.SubElement(p, q("groupId")).text = "org.mule.tools.maven"
        ET.SubElement(p, q("artifactId")).text = "mule-maven-plugin"
        ET.SubElement(p, q("version")).text = "4.2.0"
        ET.SubElement(p, q("extensions")).text = "true"

    new_txt = ET.tostring(tree, encoding="unicode")
    pom_path.write_text(new_txt, encoding="utf-8")

# ========= README, MUnit, scripts y extras =========

def write_readme(root: Path, raml_info: dict, ctx: dict, service_type: str, spec_kind: str | None, rubrics_result: dict|None):
    readme = root / "README.md"
    lines = [
        "# Proyecto MuleSoft",
        "",
        f"**Service Type detectado:** `{TYPE_LABELS.get(service_type, service_type)}`",
        f"**Especificación:** `{spec_kind or 'N/A'}`",
        "",
        "## Árbol de carpetas",
        "",
        "```\nsrc/main/mule/\n  client/\n  handler/\n  orchestrator/\n  common/\n```",
        "",
        "## Cómo ejecutar",
        "- Importa en Studio o empaqueta con Maven.",
        "- Puerto: `application.properties -> http.port`.",
        "- Path base: `${general.path}`.",
        "",
        "## Recursos y operaciones (si RAML)",
        "",
        "| Recurso | Operaciones | Headers requeridos |",
        "|---|---|---|",
    ]
    for r, d in sorted(raml_info.items()):
        ops = ", ".join(sorted(d.get("methods", [])))
        hdrs = {m: d.get("headers_required", {}).get(m, []) for m in d.get("methods", [])}
        hdrs_str = "; ".join([f"{m}: {', '.join(v) if v else '-'}" for m, v in hdrs.items()]) if hdrs else "-"
        lines.append(f"| {r} | {ops} | {hdrs_str} |")

    if service_type == "PROXY":
        lines += [
            "",
            "## Configuración PROXY",
            "",
            "En `src/main/resources/properties/*-config.yaml`:",
            "```yaml",
            "proxy.protocol: https",
            "proxy.host: api.backend.com",
            "proxy.port: 8443",
            "proxy.basePath: /v1",
            "proxy.conn.timeout: 10000",
            "proxy.sock.timeout: 10000",
            "```",
            "",
            "Flujo generado: `<artifactId>-proxy.xml` (listener 8081 → upstream)."
        ]
    if service_type == "REC":
        lines += [
            "",
            "## Nota REC / OAS",
            "- Se copió el archivo OpenAPI a `src/main/resources/api/openapi.yaml`.",
            "- No se genera APIkit; usa tu estrategia (Router, Custom flows, etc.)."
        ]

    # Checklist de rúbricas
    if rubrics_result:
        lines += [
            "",
            "## Checklist de Rúbricas",
            f"- Score: **{rubrics_result.get('score_percent', 0)}%**",
            f"- Falla por severidad B: **{'Sí' if rubrics_result.get('has_B') else 'No'}**",
            "### Hallazgos",
        ]
        for it in rubrics_result.get("failures", []):
            lines.append(f"- [{it['severity']}] {it['id']}. {it['criterion']}: {it['message']}")

    readme.write_text("\n".join(lines)+"\n", encoding="utf-8")

def write_validate_script(root: Path):
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    content = r"""#!/usr/bin/env bash
set -euo pipefail

YELLOW='\033[1;33m'; NC='\033[0m'
warn() { echo -e "${YELLOW}WARNING:${NC} $*"; }

# Solo avisos, no se corta el pipeline
for d in client handler orchestrator common; do
  test -d "src/main/mule/$d" || warn "Falta carpeta $d (recomendado por rúbricas)"
done

test -f "pom.xml" || warn "Falta pom.xml"
test -f "mule-artifact.json" || warn "Falta mule-artifact.json"
test -f "src/main/resources/properties/application.properties" || warn "Falta application.properties"

warn "Validación de estructura completada (no bloqueante)."
"""
    (scripts / "validate-structure.sh").write_text(content, encoding="utf-8")
    os.chmod(scripts / "validate-structure.sh", 0o755)

def write_munit_min(root: Path, raml_info: dict):
    tests_dir = root / "src/test/munit"
    for recurso, d in sorted(raml_info.items()):
        for m in sorted(d.get("methods", [])):
            name = f"{recurso}-{m}-test.xml"
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<mule xmlns:munit="http://www.mulesoft.org/schema/mule/munit"
      xmlns="http://www.mulesoft.org/schema/mule/core"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.mulesoft.org/schema/mule/core http://www.mulesoft.org/schema/mule/core/current/mule.xsd
        http://www.mulesoft.org/schema/mule/munit http://www.mulesoft.org/schema/mule/munit/current/mule-munit.xsd">

  <munit:test name="{recurso}-{m}-happy">
    <munit:execution>
      <flow-ref name="{recurso}_client_{m}"/>
    </munit:execution>
    <munit:validation>
      <munit-tools:assert-that xmlns:munit-tools="http://www.mulesoft.org/schema/mule/munit-tools"
        expression="#[payload]" is="#[MunitTools::notNullValue()]"/>
    </munit:validation>
  </munit:test>
</mule>
"""
            (tests_dir / name).write_text(xml, encoding="utf-8")

def write_common_extras(root: Path):
    base = root / "src/main/mule/common"
    base.mkdir(parents=True, exist_ok=True)
    # Handler de errores con mapeo
    (root / "src/main/mule/handler" / "handler-error.xml").write_text(common_error_handler_xml_detailed(), encoding="utf-8")
    # Validador de headers
    (base / "validation-headers.xml").write_text(validation_headers_xml(), encoding="utf-8")
    # Logging/observabilidad
    (base / "logging-observability.xml").write_text(global_logging_observability_xml(), encoding="utf-8")
    # Healthcheck
    (base / "healthcheck.xml").write_text(healthcheck_xml(), encoding="utf-8")

# ========= Rúbricas (carga + evaluación) =========

def load_rubrics():
    # Ruta fija según lo subido
    path = "/mnt/data/rubricas_scaffold_rules_v1.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _bool(v): return bool(v)

def _artifact_ok(artifact_id: str) -> bool:
    # kebab-case sin acentos/ñ, ascii básico
    return bool(re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", artifact_id or ""))

def evaluate_rubrics(root: Path, ctx: dict, raml_info: dict, spec_kind: str|None, service_type: str, raml_text: str|None):
    rules = load_rubrics()
    if not rules:
        return {"score_percent": 100, "has_B": False, "failures": [], "threshold": {"min_score_percent": 85, "no_B_failures": True}}

    failures = []
    sev_weight = {"B": 30, "C": 20, "M": 10, "m": 5}

    def fail(id_, criterion, severity, message):
        failures.append({"id": id_, "criterion": criterion, "severity": severity, "message": message})

    # === Chequeos mínimos según rúbrica ===
    # 1 RAML válido
    if spec_kind == "RAML":
        if not (raml_text or "").strip().startswith("#%RAML 1.0"):
            fail(1, "RAML valido y parseable", "B", "Encabezado #%RAML 1.0 ausente o inválido")

    # 2 Metadatos mínimos
    if not ctx.get("project_name") or not ctx.get("version"):
        fail(2, "Metadatos minimos", "B", "project_name/version faltantes")
    # baseUri opcional → si falta, parametrizar por properties: aseguramos application.properties existe
    app_props = (root / "src/main/resources/properties/application.properties").exists()
    if not app_props:
        fail(2, "Metadatos minimos", "B", "application.properties ausente para parametrización")

    # 3 Recursos y métodos
    if spec_kind == "RAML":
        for r, d in raml_info.items():
            if not d.get("methods"):
                fail(3, "Recursos y metodos definidos", "B", f"Recurso {r} sin métodos")

    # 4 Tipos de datos
    if spec_kind == "RAML":
        if "types:" not in (raml_text or ""):
            fail(4, "Tipos de datos", "C", "No se detectaron 'types:' (check semilight)")

    # 5 Responses consistentes (200 mínimo)
    if spec_kind == "RAML":
        for r, d in raml_info.items():
            for m in d.get("methods", []):
                if m in HTTP_METHODS and m not in d.get("res_types", {}):
                    fail(5, "Responses consistentes", "C", f"{r} {m}: sin response 200/type detectado")

    # 10 Compatibilidad versión (pom property)
    pom_ok = (root / "pom.xml").exists() and "mule.runtime.version" in (root / "pom.xml").read_text(encoding="utf-8", errors="ignore")
    if not pom_ok: fail(10, "Compatibilidad de versiones", "M", "mule.runtime.version no definido")

    # 11 Derivación de rutas (no hardcode)
    # Comprobamos que common/global-config.xml existe
    gc_ok = (root / "src/main/mule/common/global-config.xml").exists()
    if not gc_ok: fail(11, "Derivacion de rutas", "B", "global-config.xml ausente")

    # 12 Naming del proyecto
    if not _artifact_ok(ctx.get("artifact_id")):
        fail(12, "Naming del proyecto", "B", "artifactId no cumple kebab-case ascii")

    # 13 Estructura carpetas
    for d in ["client","handler","orchestrator","common"]:
        if not (root / f"src/main/mule/{d}").exists():
            fail(13, "Estructura de carpetas", "B", f"Falta {d}/")

    # 14 pom correcto
    pom_txt = (root/"pom.xml").read_text(encoding="utf-8", errors="ignore") if (root/"pom.xml").exists() else ""
    if "<packaging>mule-application</packaging>" not in pom_txt:
        fail(14, "pom.xml correcto", "B", "Packaging incorrecto")
    if "project.build.sourceEncoding" not in pom_txt:
        fail(14, "pom.xml correcto", "B", "Falta UTF-8 en properties")

    # 15 mule-artifact.json
    maf_ok = (root/"mule-artifact.json").exists() and '"minMuleVersion"' in (root/"mule-artifact.json").read_text(encoding="utf-8", errors="ignore")
    if not maf_ok:
        fail(15, "mule-artifact.json", "C", "minMuleVersion faltante")

    # 16 Listener/APIkit
    # Si hay RAML y no es PROXY/REC, esperamos APIkit router agregado en client si raml_cp existe.
    if spec_kind == "RAML" and service_type not in ("PROXY","REC"):
        # verificación laxa
        any_client = list((root/"src/main/mule/client").glob("*.xml"))
        has_apikit = any("apikit:router" in p.read_text(encoding="utf-8", errors="ignore") for p in any_client) if any_client else False
        if not has_apikit:
            fail(16, "Listener y APIkit", "C", "No se detectó apikit router (laxo)")

    # 17 global-config request-config
    gc_txt = (root / "src/main/mule/common/global-config.xml").read_text(encoding="utf-8", errors="ignore") if gc_ok else ""
    if "http:request-config" not in gc_txt and service_type != "PROXY":
        fail(17, "global-config.xml", "B", "Sin http:request-config en common")

    # 18 handler-error.xml
    if not (root/"src/main/mule/handler/handler-error.xml").exists():
        fail(18, "handler-error.xml", "C", "Archivo no encontrado")

    # 19 validation-headers.xml
    if not (root/"src/main/mule/common/validation-headers.xml").exists():
        fail(19, "validation-headers.xml", "M", "Archivo no encontrado")

    # 20-22 Separación por capas
    if not list((root/"src/main/mule/client").glob("*.xml")):
        fail(20, "Clientes por operacion", "C", "Sin archivos en client/")
    if not list((root/"src/main/mule/handler").glob("*.xml")):
        fail(22, "Handlers por endpoint", "M", "Sin archivos en handler/")
    if not list((root/"src/main/mule/orchestrator").glob("*.xml")):
        fail(21, "Orquestadores por caso de uso", "M", "Sin archivos en orchestrator/")

    # 23 properties por entorno ya creados (dev/qa/prod)
    for env in ("dev","qa","prod"):
        if not (root / f"src/main/resources/properties/{env}-config.yaml").exists():
            fail(23, "Properties por entorno", "C", f"Falta {env}-config.yaml")

    # 24 README/script
    if not (root/"README.md").exists():
        fail(24, "README y scripts", "m", "README ausente")
    if not (root/"scripts/validate-structure.sh").exists():
        fail(24, "README y scripts", "m", "validate-structure.sh ausente")

    # 25 MUnit
    if not list((root/"src/test/munit").glob("*.xml")) and spec_kind == "RAML":
        fail(25, "Pruebas MUnit", "m", "Sin suites generadas")

    # 26 Exchange docs
    if not (root/"exchange-docs/home.md").exists():
        fail(26, "Exchange docs", "m", "home.md ausente")

    # 27 Logging convención
    if not (root/"src/main/mule/common/logging-observability.xml").exists():
        fail(27, "Convenciones de logging", "M", "logging-observability.xml ausente")

    # 30 Healthcheck
    if not (root/"src/main/mule/common/healthcheck.xml").exists():
        fail(30, "Healthcheck", "m", "healthcheck.xml ausente")

    # Scoring
    score = 100
    for f in failures:
        score -= sev_weight.get(f["severity"], 5)
    score = max(0, score)

    has_B = any(f["severity"] == "B" for f in failures)
    return {
        "score_percent": score,
        "has_B": has_B,
        "failures": failures,
        "threshold": rules.get("threshold", {"min_score_percent": 85, "no_B_failures": True})
    }

# ========= Proceso principal =========

def ensure_global_request_config(root: Path, ctx: dict, use_apikit: bool, service_type: str):
    gc = root / "src/main/mule/common/global-config.xml"
    txt = gc.read_text(encoding="utf-8", errors="ignore") if gc.exists() else ""
    # Insertar http:request-config genérico si no es PROXY
    if service_type != "PROXY" and "http:request-config" not in txt:
        block = """
  <http:request-config name="backend-request">
    <http:request-connection protocol="${upstream.protocol}" host="${upstream.host}" port="${upstream.port}"/>
  </http:request-config>
""".rstrip()
        txt = txt.replace("</mule>", f"{block}\n</mule>") if "</mule>" in txt else (txt + "\n" + block + "\n</mule>")
        gc.write_text(txt, encoding="utf-8")

def procesar_arquetipo_llm(arquetipo_zip: str, ctx: dict, spec_bytes: bytes|None):
    tmp_dir = Path(tempfile.mkdtemp())

    with zipfile.ZipFile(arquetipo_zip, "r") as z:
        z.extractall(tmp_dir)

    roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    root = roots[0] if len(roots)==1 else tmp_dir

    ensure_dirs(root)
    write_minimum_base_files(root)

    # Reescritura guiada por LLM de todos los archivos de texto
    files_to_touch = []
    for r,_,fs in os.walk(root):
        for f in fs:
            p = Path(r)/f
            if p.suffix.lower() in (".png",".jpg",".jpeg",".gif",".webp",".svg",".pdf",".ppt",".pptx",".key",".ai",".psd"):
                continue
            files_to_touch.append(p)

    prog = st.progress(0.0)
    total = len(files_to_touch)
    for i, path in enumerate(files_to_touch, 1):
        prog.progress(i/total)
        try:
            if path.suffix.lower() in TEXT_EXTS or path.name.lower()=="pom.xml":
                original = path.read_text(encoding="utf-8", errors="ignore")
                nuevo = transformar_archivo_con_gpt(path.name, original, ctx)

                if path.suffix.lower() == ".xml":
                    nuevo = postprocesar_xml(nuevo, ctx)

                # Validaciones sintácticas
                ext = path.suffix.lower()
                if path.name.lower()=="pom.xml" or ext==".xml":
                    err = validar_xml(nuevo, path.name)
                    if err: nuevo = original
                elif ext in (".yaml",".yml"):
                    err = validar_yaml(nuevo, path.name)
                    if err: nuevo = original

                path.write_text(nuevo, encoding="utf-8")
        except Exception:
            pass

    # Copiar especificación
    raml_info = {}
    raml_cp_value = None
    service_type = st.session_state.get("service_type","UNKNOWN")
    spec_kind = st.session_state.get("spec_kind")
    raml_text = st.session_state.get("raml_text")

    if spec_bytes:
        if spec_kind == "RAML":
            target = first_raml_target(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                f.write(spec_bytes)
            try:
                raml_text = spec_bytes.decode("utf-8","ignore")
                st.session_state.raml_text = raml_text
                raml_info = parse_raml_semilight(raml_text)
            except Exception:
                raml_info = {}
            if service_type not in ("PROXY","REC"):
                raml_cp_value = raml_classpath(root)
        elif spec_kind == "OAS":
            target = oas_target(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                f.write(spec_bytes)
        elif spec_kind == "TEXT":
            pass

    base = root / "src/main/mule"
    client_dir = base / "client"
    handler_dir = base / "handler"
    orch_dir = base / "orchestrator"
    common_dir = base / "common"

    # common/ + error-handler detallado + extras por rúbrica
    ceh = handler_dir / "common-error-handler.xml"
    if not ceh.exists():
        ceh.write_text(common_error_handler_xml_min(), encoding="utf-8")
    # Archivos extra rúbricas (always ensure)
    write_common_extras(root)

    if service_type == "PROXY":
        (common_dir / "global-config.xml").write_text(_xml_header(False) + """
  <configuration-properties file="properties/application.properties"/>
""" + _xml_footer(), encoding="utf-8")
        _gen_proxy_flows(base, ctx.get("artifact_id","mule-app"))
        proto, host, port, bpath = _parse_base_uri((ctx.get("base_uri") or "") or "")
        _patch_env_properties(root, proto, host, port, bpath)
    else:
        use_apikit = bool(raml_cp_value)
        gc = common_dir / "global-config.xml"
        if not gc.exists():
            gc.write_text(_xml_header(False) + """
  <configuration-properties file="properties/application.properties"/>
""" + _xml_footer(), encoding="utf-8")

        # Si hay RAML: generar scaffold
        if raml_info:
            for recurso, data in sorted(raml_info.items()):
                methods = data.get("methods") or {"retrieve"}
                rname = safe_filename(recurso, "root")

                c_path = client_dir / f"{rname}-client.xml"
                if not c_path.exists():
                    xml = client_file_xml(rname, methods, ctx.get("general_path","/api/*"), use_apikit, raml_cp_value)
                    try: ET.fromstring(xml)
                    except ET.ParseError: xml = f"<mule><flow name='{rname}_client_main'/></mule>"
                    c_path.write_text(xml, encoding="utf-8")

                h_path = handler_dir / f"{rname}-handler.xml"
                if not h_path.exists():
                    xml = handler_file_xml(rname, methods, raml_info)
                    try: ET.fromstring(xml)
                    except ET.ParseError: xml = f"<mule><flow name='{rname}_handler_main'/></mule>"
                    h_path.write_text(xml, encoding="utf-8")

                if len(methods) == 1:
                    o_path = orch_dir / f"{rname}-orchestrator.xml"
                    if not o_path.exists():
                        xml = orchestrator_file_xml(rname, methods, raml_info, single_file=True)
                        try: ET.fromstring(xml)
                        except ET.ParseError: xml = f"<mule><flow name='{rname}_orchestrator_main'/></mule>"
                        o_path.write_text(xml, encoding="utf-8")
                else:
                    for m in sorted(methods):
                        o_path = orch_dir / f"{rname}-{m}-orchestrator.xml"
                        if not o_path.exists():
                            xml = orchestrator_file_xml(rname, {m}, raml_info, single_file=False)
                            try: ET.fromstring(xml)
                            except ET.ParseError: xml = f"<mule><flow name='{rname}_orchestrator_{m}'/></mule>"
                            o_path.write_text(xml, encoding="utf-8")

    # POM y dependencias mínimas
    enforce_pom_requirements(root, ctx, use_apikit=False if service_type in ("PROXY","REC") else bool(raml_cp_value))

    # Asegurar request-config genérico si aplica
    ensure_global_request_config(root, ctx, use_apikit=False if service_type in ("PROXY","REC") else bool(raml_cp_value), service_type=service_type)

    # README, script de validación y MUnit
    write_validate_script(root)
    if raml_info and service_type not in ("PROXY","REC"):
        write_munit_min(root, raml_info)

    # Rúbricas → evaluación + observaciones
    rub = evaluate_rubrics(root, ctx, raml_info, spec_kind, service_type, raml_text)
    st.session_state.rubrics_result = rub

    notes = rubric_observaciones(root, use_apikit=False if service_type in ("PROXY","REC") else bool(raml_cp_value), raml_info=raml_info)
    # Añadimos fallas resumidas de rúbrica como observaciones no bloqueantes
    for f in rub.get("failures", []):
        notes.append(f"[Rubrica-{f['severity']}] {f['id']} {f['criterion']}: {f['message']}")
    st.session_state.observaciones = notes

    # README actualizado con rúbricas
    write_readme(root, raml_info, ctx, service_type, spec_kind, rub)

    # ZIP final
    out_name = f"proyecto_mulesoft_generado_{service_type}.zip"
    out_zip = Path(tempfile.gettempdir()) / out_name
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            z.write(p, p.relative_to(root))

    return str(out_zip)

# ========= Observaciones previas (estáticas) =========
def rubric_observaciones(root: Path, use_apikit: bool, raml_info: dict):
    notes = []
    base = root / "src/main/mule"

    required_dirs = ["client","handler","orchestrator","common"]
    for d in required_dirs:
        if not (base/d).exists():
            notes.append(f"[Estructura] Falta carpeta src/main/mule/{d}/")
    loose = [str(p.relative_to(root)) for p in base.glob("*.xml")]
    if loose:
        notes.append("[Estructura] XML sueltos en src/main/mule (mover a subcarpetas): " + ", ".join(loose))

    if not (root/"pom.xml").exists(): notes.append("[Activos] Falta pom.xml")
    if not (root/"mule-artifact.json").exists(): notes.append("[Activos] Falta mule-artifact.json")
    if not (root/"src/main/resources/properties/application.properties").exists(): notes.append("[Activos] Falta application.properties")

    def bad_names(dirpath: Path, pattern: str, extra_ok=None):
        extra_ok = extra_ok or set()
        bad = []
        for p in dirpath.glob("*.xml"):
            if p.name in extra_ok:
                continue
            if not re.match(pattern, p.name):
                bad.append(p.name)
        return bad
    bad_client = bad_names(base/"client", r'^[a-z][A-Za-z0-9]*-client\.xml$')
    if bad_client: notes.append("[Naming] client/: " + ", ".join(bad_client))
    bad_handler = bad_names(base/"handler", r'^[a-z][A-Za-z0-9]*-handler\.xml$', {"common-error-handler.xml"})
    if bad_handler: notes.append("[Naming] handler/: " + ", ".join(bad_handler))
    bad_orch = bad_names(base/"orchestrator", r'^([a-z][A-Za-z0-9]*-(get|post|put|delete|patch|head|options|retrieve|evaluate|execute|init|create|update|delete)-orchestrator|[a-z][A-Za-z0-9]*-orchestrator)\.xml$')
    if bad_orch: notes.append("[Naming] orchestrator/: " + ", ".join(bad_orch))

    for p in (base/"client").glob("*.xml"):
        t = p.read_text("utf-8","ignore")
        if "<flow-ref name=\"" not in t or "_handler_" not in t:
            notes.append(f"[Flujo] {p.name}: client debe delegar a handler con flow-ref")
        if "<http:request " in t:
            notes.append(f"[Flujo] {p.name}: evitar http:request en client")
        if "<error-handler>" not in t:
            notes.append(f"[Errores] {p.name}: agregar error-handler con flow-ref a hdl_commonErrorHandler")

    for p in (base/"handler").glob("*.xml"):
        if p.name == "common-error-handler.xml":
            continue
        t = p.read_text("utf-8","ignore")
        if "_orchestrator_" not in t:
            notes.append(f"[Flujo] {p.name}: handler debe delegar a orchestrator")
        if "<http:request " in t:
            notes.append(f"[Flujo] {p.name}: evitar http:request en handler")
        if "<error-handler>" not in t:
            notes.append(f"[Errores] {p.name}: agregar error-handler con flow-ref a hdl_commonErrorHandler")

    common_txt = (base/"common"/"global-config.xml").read_text("utf-8","ignore") if (base/"common"/"global-config.xml").exists() else ""
    if use_apikit:
        if "http:listener-config" in common_txt:
            notes.append("[APIkit] Con APIkit no se recomienda listener-config en common/global-config.xml")
    else:
        if "http:listener-config" not in common_txt:
            notes.append("[Listener] Sin APIkit, conviene listener-config en common/global-config.xml")
        for folder in ["client","handler","orchestrator"]:
            for p in (base/folder).glob("*.xml"):
                if "http:listener-config" in p.read_text("utf-8","ignore"):
                    notes.append(f"[Listener] {p.name}: listener-config centralizar en common/global-config.xml")

    ceh = base/"handler"/"common-error-handler.xml"
    if not ceh.exists():
        notes.append("[Errores] Falta common-error-handler.xml")
    else:
        if "hdl_commonErrorHandler" not in ceh.read_text("utf-8","ignore"):
            notes.append("[Errores] common-error-handler.xml: definir sub-flow 'hdl_commonErrorHandler'")

    return notes

# ========= Chat/acciones =========

def manejar_mensaje(user_input: str):
    ui = user_input.strip().lower()

    if ui in ("crear proyecto","crea el proyecto","genera el proyecto","crea el proyecto"):
        if not st.session_state.uploaded_spec:
            st.session_state.messages.append({"role":"assistant","content":"⚠️ Primero adjunta un RAML, OAS (.yaml/.json) o DTM (.docx)."})
            return

        arquetipo = obtener_arquetipo()
        if not arquetipo:
            st.session_state.messages.append({"role":"assistant","content":"❌ No encontré un ZIP con 'arquetipo' en el directorio."})
            return

        st.session_state.messages.append({"role":"assistant","content":"🧠 Leyendo especificación y construyendo contexto con ChatGPT..."})
        raw = leer_especificacion(st.session_state.uploaded_spec)
        ctx = inferir_metadatos(raw)

        st.session_state.messages.append({"role":"assistant","content":f"🧾 Metadatos:\n```yaml\n{yaml.safe_dump(ctx,sort_keys=False,allow_unicode=True)}\n```"})

        st.session_state.uploaded_spec.seek(0)
        spec_bytes = st.session_state.uploaded_spec.read()

        st.session_state.messages.append({"role":"assistant","content":"⚙️ Reescribiendo arquetipo / PROXY / OAS + POM + README + MUnit + rúbricas..."})
        try:
            salida_zip = procesar_arquetipo_llm(arquetipo, ctx, spec_bytes)
            st.session_state.generated_zip = salida_zip

            tipo = st.session_state.get("service_type","UNKNOWN")
            label = TYPE_LABELS.get(tipo, tipo)
            rub = st.session_state.get("rubrics_result") or {}
            resumen = f"✅ Proyecto generado. Tipo detectado: **{label}**.\n"
            resumen += f"📊 Score rúbricas: **{rub.get('score_percent',0)}%** | "
            resumen += f"No_B_failures: **{'OK' if not rub.get('has_B') else 'FALLA'}** | "
            thr = rub.get("threshold", {})
            resumen += f"Umbral: **{thr.get('min_score_percent',85)}%**"
            if st.session_state.observaciones:
                resumen += f"\n⚠️ Observaciones: {len(st.session_state.observaciones)} (no bloqueantes)"
            st.session_state.messages.append({"role":"assistant","content":resumen})

            # Mostrar el tipo SOLO tras generar
            st.info(f"🔎 La API es de tipo **{label}**")

        except Exception as e:
            st.session_state.messages.append({"role":"assistant","content":f"⚠️ Generación con advertencias: {e}"})
    else:
        st.session_state.messages.append({"role":"assistant","content":"💬 Escribe `crea el proyecto` para generar el zip a partir de tu especificación."})

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

# ====== Observaciones ======
if st.session_state.get("observaciones"):
    st.markdown("### ⚠️ Observaciones de Rúbricas (no bloqueantes)")
    st.markdown("\n".join(f"- {o}" for o in st.session_state.observaciones))

# ====== Entrada chat ======
user_input = st.chat_input("Escribe aquí...")
if user_input:
    st.session_state.messages.append({"role":"user","content":user_input})
    manejar_mensaje(user_input)
    st.rerun()

# ====== Descarga ======
if st.session_state.generated_zip:
    # Mostrar el tipo solo en esta fase
    tipo = st.session_state.get("service_type","UNKNOWN")
    st.info(f"🔎 La API es de tipo **{TYPE_LABELS.get(tipo, tipo)}**")

    with open(st.session_state.generated_zip, "rb") as f:
        st.download_button("⬇️ Descargar Proyecto (.zip)", f,
                           Path(st.session_state.generated_zip).name,
                           "application/zip")
