import tempfile, zipfile, re, os, sys, types
import xml.etree.ElementTree as ET
import yaml
from pathlib import Path

# --- Parche compatibilidad 3.13 ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    sys.modules['imghdr'] = imghdr
# ----------------------------------

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
    st.session_state.messages.append({"role":"assistant","content":f"📄 Archivo \"{spec.name}\" cargado. Escribe \"crea el proyecto\"."})

# ========= Utilidades =========

TEXT_EXTS = {".xml",".json",".yaml",".yml",".raml",".properties",".txt",".pom",".md"}

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
upstream_host: host del sistema objetivo (string o null)
upstream_protocol: HTTP/HTTPS (string o null)
upstream_path: path base para http:request (string, ej: "/v1/sistema/endpoint")
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
    data.setdefault("upstream_host", data.get("host_name"))
    data.setdefault("upstream_protocol", data.get("protocol"))
    if not data.get("upstream_path"):
        base_path = (data.get("base_path") or "").lstrip("/")
        data["upstream_path"] = ("/"+base_path) if base_path else "/"

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

# ========= Postprocesos deterministas (flows + TLS) =========

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

# ========= Parsing RAML (recursos/métodos) =========

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
            cur_res = line.strip().split()[0].strip("/").split("/")[0]
            res.setdefault(cur_res, {"methods": set(), "headers_required": {}, "req_types": {}, "res_types": {}})
            cur_method = None
            continue

        token = line.strip().rstrip(":").lower()
        if token in HTTP_METHODS or token in EXTRA_ACTIONS:
            cur_method = token
            res.setdefault(cur_res, {"methods": set(), "headers_required": {}, "req_types": {}, "res_types": {}})
            res[cur_res]["methods"].add(cur_method)
            continue

        if cur_method and line.strip().endswith(":") and "headers" in line.lower():
            for j in range(i+1, min(i+7, len(lines))):
                l2 = lines[j].strip()
                if l2.endswith(":") and not l2.startswith("-"):
                    hdr = l2.rstrip(":")
                    block = "\n".join(lines[j: min(j+6, len(lines))]).lower()
                    if "required: true" in block:
                        res[cur_res]["headers_required"].setdefault(cur_method, []).append(hdr)

        if cur_method and "body:" in line.lower():
            block = "\n".join(lines[i: min(i+10, len(lines))])
            m = re.search(r"type:\s*([A-Za-z0-9_\-\.]+)", block)
            if m: res[cur_res]["req_types"][cur_method] = m.group(1)

        if cur_method and "responses:" in line.lower():
            block = "\n".join(lines[i: min(i+15, len(lines))])
            m = re.search(r"200:\s*(?:\n|\r\n).*?type:\s*([A-Za-z0-9_\-\.]+)", block, re.DOTALL)
            if m: res[cur_res]["res_types"][cur_method] = m.group(1)

    for r, d in res.items():
        if not d["methods"]:
            d["methods"].add("retrieve")
    return res

# ========= Scaffold XML strings (APIkit / no-APIkit) =========

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

def _mk_error_handler_ref():
    return """
    <error-handler>
      <on-error-continue logException="true" type="ANY">
        <flow-ref name="hdl_commonErrorHandler"/>
      </on-error-continue>
    </error-handler>""".rstrip()

def client_file_xml(resource: str, methods: set, general_path: str, use_apikit: bool, raml_cp: str|None):
    gp = general_path or "/api/*"
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

    body = "\n".join(flows)
    content = f"""{header}
  <!-- client consolidado para recurso '{resource}' -->
{apikit_part if apikit_part else ""}
{body}
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
    <logger level="INFO" message="[{resource}] orchestrator {m} start"/>
    <!-- TODO: mapping/externos según contrato RAML -->
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
    <logger level="INFO" message="[{resource}] orchestrator {m} start"/>
    <!-- TODO: mapping/externos según contrato RAML -->
    <logger level="INFO" message="[{resource}] orchestrator {m} end"/>
{_mk_error_handler_ref()}
  </flow>
{_xml_footer()}""".strip()

def common_error_handler_xml():
    header = _xml_header(False)
    return f"""{header}
  <!-- common error handler -->
  <sub-flow name="hdl_commonErrorHandler">
    <logger level="ERROR" message="type=#[error.errorType] desc=#[error.description]"/>
  </sub-flow>
{_xml_footer()}""".strip()

def common_global_config_xml(use_apikit: bool):
    header = _xml_header(False)
    listener = "" if use_apikit else """
  <http:listener-config name="global-httpListener">
    <http:listener-connection host="0.0.0.0" port="${http.port}"/>
  </http:listener-config>""".rstrip()
    return f"""{header}
  <configuration-properties file="properties/application.properties"/>
{listener}
{_xml_footer()}""".strip()

# ========= Rúbricas/estructura =========

def ensure_dirs(root: Path):
    base = root / "src/main/mule"
    for d in ["client", "handler", "orchestrator", "common"]:
        (base / d).mkdir(parents=True, exist_ok=True)
    (root / "src/main/resources/api").mkdir(parents=True, exist_ok=True)
    (root / "src/main/resources/properties").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)

def forbid_loose_xml(root: Path) -> list[str]:
    """Antes bloqueaba XMLs sueltos; ahora es solo informativo (no bloquea)."""
    base = root / "src/main/mule"
    return [str(p) for p in base.glob("*.xml")]

def write_minimum_base_files(root: Path):
    props = root / "src/main/resources/properties/application.properties"
    if not props.exists():
        props.write_text("http.port=8081\ngeneral.path=/api/*\n", encoding="utf-8")
    maf = root / "mule-artifact.json"
    if not maf.exists():
        maf.write_text('{"minMuleVersion":"4.6.0","secureProperties":[]}\n', encoding="utf-8")
    pom = root / "pom.xml"
    if not pom.exists():
        pom.write_text("""<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.company.experience</groupId>
  <artifactId>mule-app</artifactId>
  <version>1.0.0</version>
  <packaging>mule-application</packaging>
  <name>mule-app</name>
</project>
""", encoding="utf-8")

def write_validate_script(root: Path):
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    content = r"""#!/usr/bin/env bash
set -euo pipefail

# 1) Carpetas obligatorias
for d in client handler orchestrator common; do
  test -d "src/main/mule/$d" || { echo "Falta carpeta $d"; exit 1; }
done

# 2) (Desactivado) XMLs sueltos permitidos por compatibilidad con arquetipos existentes

# 3) Nombres por capa
if find src/main/mule/client -type f -name "*.xml" | grep -Pv '^.*/[a-z][A-Za-z0-9]*-client\.xml$' | grep -q .; then
  echo "Nombre inválido en client (<recurso>-client.xml)"; exit 1
fi
if find src/main/mule/handler -type f -name "*.xml" | grep -Pv '^.*/([a-z][A-Za-z0-9]*-handler|common-error-handler)\.xml$' | grep -q .; then
  echo "Nombre inválido en handler (<recurso>-handler.xml o common-error-handler.xml)"; exit 1
fi
# orchestrator: acepta <recurso>-orchestrator.xml (1 operación) o <recurso>-<action>-orchestrator.xml (n>1)
if find src/main/mule/orchestrator -type f -name "*.xml" | grep -Pv '^.*/([a-z][A-Za-z0-9]*-(get|post|put|delete|patch|head|options|retrieve|evaluate|execute|init|create|update|delete)-orchestrator|[a-z][A-Za-z0-9]*-orchestrator)\.xml$' | grep -q .; then
  echo "Nombre inválido en orchestrator"; exit 1
fi

# 4) Activos mínimos
test -f "pom.xml" || { echo "Falta pom.xml"; exit 1; }
test -f "mule-artifact.json" || { echo "Falta mule-artifact.json"; exit 1; }
test -f "src/main/resources/properties/application.properties" || { echo "Falta application.properties"; exit 1; }

echo "Validación de estructura OK ✅"
"""
    (scripts / "validate-structure.sh").write_text(content, encoding="utf-8")
    os.chmod(scripts / "validate-structure.sh", 0o755)

def write_min_readme(root: Path, raml_info: dict):
    readme = root / "README.md"
    lines = [
        "# Proyecto MuleSoft",
        "",
        "## Árbol de carpetas",
        "",
        "```\nsrc/main/mule/\n  client/\n  handler/\n  orchestrator/\n  common/\n```",
        "",
        "## Recursos y operaciones",
        "",
        "| Recurso | Operaciones | Headers requeridos (por método) |",
        "|---|---|---|",
    ]
    for r, d in sorted(raml_info.items()):
        ops = ", ".join(sorted(d.get("methods", [])))
        hdrs = {m: d.get("headers_required", {}).get(m, []) for m in d.get("methods", [])}
        hdrs_str = "; ".join([f"{m}: {', '.join(v) if v else '-'}" for m, v in hdrs.items()]) if hdrs else "-"
        lines.append(f"| {r} | {ops} | {hdrs_str} |")
    lines += [
        "",
        "## Cómo ejecutar",
        "- Configura `src/main/resources/properties/application.properties` (puerto y paths).",
        "- Importa en Studio / empaqueta con Maven.",
    ]
    readme.write_text("\n".join(lines)+"\n", encoding="utf-8")

# ========= Helpers RAML/classpath =========

def first_raml_target(dst_root: Path) -> Path:
    preferred = dst_root / "src/main/resources/api/api.raml"
    if preferred.parent.exists():
        return preferred
    existing = list(dst_root.rglob("*.raml"))
    return existing[0] if existing else preferred

def raml_classpath(root: Path) -> str|None:
    target = first_raml_target(root)
    try:
        rel = target.relative_to(root / "src/main/resources")
        return "classpath:/" + "/".join(rel.parts)
    except Exception:
        candidates = list(root.rglob("*.raml"))
        if candidates:
            try:
                rel = candidates[0].relative_to(root / "src/main/resources")
                return "classpath:/" + "/".join(rel.parts)
            except Exception:
                return None
    return None

# ========= Refactor de archivos sueltos con LLM =========

def transformar_archivo_con_gpt(fname: str, original: str, ctx: dict) -> str:
    PROMPT_FILE = """Eres un configurador experto de proyectos Mule 4.
Actualiza el archivo indicado usando METADATOS (YAML).

Reglas:
- Mantén formato/saltos.
- No agregues explicaciones ni ``` .
- Sigue comentarios guía; sustituye placeholders (groupId, artifactId, version, project.mule.name,
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

# ========= POM: normalización determinista =========

def _pom_qname(tag: str, ns: str|None):
    return f"{{{ns}}}{tag}" if ns else tag

def _pom_find_or_create(parent, tag, ns):
    q = _pom_qname(tag, ns)
    el = parent.find(q)
    if el is None:
        el = ET.SubElement(parent, q)
    return el

def enforce_pom_requirements(root_dir: Path, ctx: dict, use_apikit: bool) -> list[str]:
    changes = []
    pom_path = root_dir / "pom.xml"
    if not pom_path.exists():
        return changes

    txt = pom_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ET.fromstring(txt)
    except ET.ParseError:
        return changes

    if tree.tag.startswith("{"):
        ns = tree.tag.split("}",1)[0][1:]
    else:
        ns = None

    def q(tag): return _pom_qname(tag, ns)

    packaging = tree.find(q("packaging"))
    if packaging is None or (packaging.text or "").strip().lower() != "mule-application":
        if packaging is None:
            packaging = ET.SubElement(tree, q("packaging"))
        packaging.text = "mule-application"
        changes.append("packaging=mule-application")

    artifactId = tree.find(q("artifactId"))
    name = tree.find(q("name"))
    desired_artifact = ctx.get("artifact_id") or "mule-app"
    desired_name = ctx.get("project_name") or desired_artifact

    if artifactId is None:
        artifactId = ET.SubElement(tree, q("artifactId"))
        artifactId.text = desired_artifact
        changes.append(f"artifactId={desired_artifact}")
    if name is None:
        name = ET.SubElement(tree, q("name"))
        name.text = desired_name
        changes.append(f"name={desired_name}")

    build = tree.find(q("build"))
    if build is None:
        build = ET.SubElement(tree, q("build"))
    plugins = build.find(q("plugins"))
    if plugins is None:
        plugins = ET.SubElement(build, q("plugins"))

    def has_mule_plugin():
        for p in plugins.findall(q("plugin")):
            gid = (p.find(q("groupId")).text if p.find(q("groupId")) is not None else "")
            aid = (p.find(q("artifactId")).text if p.find(q("artifactId")) is not None else "")
            if gid.strip()=="org.mule.tools.maven" and aid.strip()=="mule-maven-plugin":
                return p
        return None

    mule_plugin = has_mule_plugin()
    if mule_plugin is None:
        mule_plugin = ET.SubElement(plugins, q("plugin"))
        ET.SubElement(mule_plugin, q("groupId")).text = "org.mule.tools.maven"
        ET.SubElement(mule_plugin, q("artifactId")).text = "mule-maven-plugin"
        ET.SubElement(mule_plugin, q("version")).text = ctx.get("mule_maven_plugin_version","4.2.0")
        ET.SubElement(mule_plugin, q("extensions")).text = "true"
        changes.append("add: mule-maven-plugin")
    else:
        ext = mule_plugin.find(q("extensions"))
        if ext is None or (ext.text or "").strip().lower() != "true":
            if ext is None:
                ext = ET.SubElement(mule_plugin, q("extensions"))
            ext.text = "true"
            changes.append("mule-maven-plugin.extensions=true")

    if use_apikit:
        deps = tree.find(q("dependencies"))
        if deps is None:
            deps = ET.SubElement(tree, q("dependencies"))

        def has_apikit():
            for d in deps.findall(q("dependency")):
                gid = (d.find(q("groupId")).text if d.find(q("groupId")) is not None else "")
                aid = (d.find(q("artifactId")).text if d.find(q("artifactId")) is not None else "")
                if gid.strip()=="org.mule.modules" and aid.strip()=="mule-apikit-module":
                    return d
            return None

        apikit_dep = has_apikit()
        if apikit_dep is None:
            dep = ET.SubElement(deps, q("dependency"))
            ET.SubElement(dep, q("groupId")).text = "org.mule.modules"
            ET.SubElement(dep, q("artifactId")).text = "mule-apikit-module"
            ET.SubElement(dep, q("version")).text = ctx.get("apikit_version","1.11.0")
            ET.SubElement(dep, q("classifier")).text = "mule-plugin"
            changes.append("add: mule-apikit-module")

    try:
        xml_bytes = ET.tostring(tree, encoding="utf-8")
        pom_path.write_text(xml_bytes.decode("utf-8"), encoding="utf-8")
    except Exception:
        pass

    return changes

# ========= Proceso del arquetipo =========

def procesar_arquetipo_llm(arquetipo_zip: str, ctx: dict, spec_bytes: bytes|None):
    tmp_dir = Path(tempfile.mkdtemp())
    out_zip = Path(tempfile.gettempdir()) / "proyecto_mulesoft_generado.zip"

    with zipfile.ZipFile(arquetipo_zip, "r") as z:
        z.extractall(tmp_dir)

    roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    root = roots[0] if len(roots)==1 else tmp_dir

    ensure_dirs(root)
    write_minimum_base_files(root)

    files_to_touch = []
    for r,_,fs in os.walk(root):
        for f in fs:
            p = Path(r)/f
            if p.suffix.lower() in (".png",".jpg",".jpeg",".gif",".webp",".svg",".pdf",".ppt",".pptx",".key",".ai",".psd"):
                continue
            files_to_touch.append(p)

    prog = st.progress(0.0)
    total = len(files_to_touch)
    modificados, errores = [], []

    for i, path in enumerate(files_to_touch, 1):
        prog.progress(i/total)
        try:
            if path.suffix.lower() in TEXT_EXTS or path.name.lower()=="pom.xml":
                original = path.read_text(encoding="utf-8", errors="ignore")
                nuevo = transformar_archivo_con_gpt(path.name, original, ctx)

                if path.suffix.lower() == ".xml":
                    nuevo = postprocesar_xml(nuevo, ctx)

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
                    try:
                        modificados.append(str(path.relative_to(root)))
                    except Exception:
                        modificados.append(path.name)
        except Exception as e:
            errores.append(f"⚠️ Error en {path.name}: {e}")

    raml_info = {}
    raml_cp_value = None
    if spec_bytes and st.session_state.uploaded_spec.name.lower().endswith(".raml"):
        target = first_raml_target(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            f.write(spec_bytes)
        try:
            raml_text = spec_bytes.decode("utf-8","ignore")
            raml_info = parse_raml_semilight(raml_text)
        except Exception:
            raml_info = {}
        raml_cp_value = raml_classpath(root)

    base = root / "src/main/mule"
    client_dir = base / "client"
    handler_dir = base / "handler"
    orch_dir = base / "orchestrator"
    common_dir = base / "common"

    ceh = handler_dir / "common-error-handler.xml"
    if not ceh.exists():
        xml = common_error_handler_xml()
        try:
            ET.fromstring(xml)
        except ET.ParseError:
            xml = "<mule><sub-flow name='hdl_commonErrorHandler'/></mule>"
        ceh.write_text(xml, encoding="utf-8")
        modificados.append(str(ceh.relative_to(root)))

    use_apikit = bool(raml_cp_value)
    gc = common_dir / "global-config.xml"
    if not gc.exists():
        xml = common_global_config_xml(use_apikit)
        try:
            ET.fromstring(xml)
        except ET.ParseError:
            xml = "<mule/>"
        gc.write_text(xml, encoding="utf-8")
        modificados.append(str(gc.relative_to(root)))

    if raml_info:
        for recurso, data in sorted(raml_info.items()):
            methods = data.get("methods") or {"retrieve"}

            c_path = client_dir / f"{recurso}-client.xml"
            if not c_path.exists():
                xml = client_file_xml(recurso, methods, ctx.get("general_path"), use_apikit, raml_cp_value)
                try: ET.fromstring(xml)
                except ET.ParseError: xml = f"<mule><flow name='{recurso}_client_main'/></mule>"
                c_path.write_text(xml, encoding="utf-8")
                modificados.append(str(c_path.relative_to(root)))

            h_path = handler_dir / f"{recurso}-handler.xml"
            if not h_path.exists():
                xml = handler_file_xml(recurso, methods, raml_info)
                try: ET.fromstring(xml)
                except ET.ParseError: xml = f"<mule><flow name='{recurso}_handler_main'/></mule>"
                h_path.write_text(xml, encoding="utf-8")
                modificados.append(str(h_path.relative_to(root)))

            if len(methods) == 1:
                o_path = orch_dir / f"{recurso}-orchestrator.xml"
                if not o_path.exists():
                    xml = orchestrator_file_xml(recurso, methods, raml_info, single_file=True)
                    try: ET.fromstring(xml)
                    except ET.ParseError: xml = f"<mule><flow name='{recurso}_orchestrator_{next(iter(methods))}'/></mule>"
                    o_path.write_text(xml, encoding="utf-8")
                    modificados.append(str(o_path.relative_to(root)))
            else:
                for m in sorted(methods):
                    o_path = orch_dir / f"{recurso}-{m}-orchestrator.xml"
                    if not o_path.exists():
                        xml = orchestrator_file_xml(recurso, {m}, raml_info, single_file=False)
                        try: ET.fromstring(xml)
                        except ET.ParseError: xml = f"<mule><flow name='{recurso}_orchestrator_{m}'/></mule>"
                        o_path.write_text(xml, encoding="utf-8")
                        modificados.append(str(o_path.relative_to(root)))

    pom_changes = enforce_pom_requirements(root, ctx, use_apikit)
    if pom_changes:
        modificados.append("pom.xml (ajustes: " + ", ".join(pom_changes) + ")")

    rubric_errors = []

    # >>>> RÚBRICA ELIMINADA: XMLs sueltos en src/main/mule (ya no bloquea) <<<<
    # loose = forbid_loose_xml(root)  # lo dejamos como información, no error

    for d in ["client","handler","orchestrator","common"]:
        if not (base / d).exists():
            rubric_errors.append(f"Falta carpeta {d}/ bajo src/main/mule")
    if not (root/"pom.xml").exists(): rubric_errors.append("Falta pom.xml")
    if not (root/"mule-artifact.json").exists(): rubric_errors.append("Falta mule-artifact.json")
    if not (root/"src/main/resources/properties/application.properties").exists(): rubric_errors.append("Falta application.properties")

    bad_client = [p.name for p in (client_dir.glob("*.xml")) if not re.match(r"^[a-z][A-Za-z0-9]*-client\.xml$", p.name)]
    if bad_client: rubric_errors.append("Nombres inválidos en client/: " + ", ".join(bad_client))
    bad_handler = [p.name for p in (handler_dir.glob("*.xml")) if p.name!="common-error-handler.xml" and not re.match(r"^[a-z][A-Za-z0-9]*-handler\.xml$", p.name)]
    if bad_handler: rubric_errors.append("Nombres inválidos en handler/: " + ", ".join(bad_handler))
    bad_orch = [p.name for p in (orch_dir.glob("*.xml")) if not re.match(r"^([a-z][A-Za-z0-9]*-(get|post|put|delete|patch|head|options|retrieve|evaluate|execute|init|create|update|delete)-orchestrator|[a-z][A-Za-z0-9]*-orchestrator)\.xml$", p.name)]
    if bad_orch: rubric_errors.append("Nombres inválidos en orchestrator/: " + ", ".join(bad_orch))

    for p in client_dir.glob("*.xml"):
        t = p.read_text("utf-8","ignore")
        if "<flow-ref name=\"" not in t or "_handler_" not in t:
            rubric_errors.append(f"{p.name}: client debe delegar a handler con flow-ref")
        if "<http:request " in t:
            rubric_errors.append(f"{p.name}: client no debe invocar http:request (externos)")
    for p in handler_dir.glob("*.xml"):
        if p.name == "common-error-handler.xml": continue
        t = p.read_text("utf-8","ignore")
        if "_orchestrator_" not in t:
            rubric_errors.append(f"{p.name}: handler debe delegar a orchestrator con flow-ref")
        if "<http:request " in t:
            rubric_errors.append(f"{p.name}: handler no debe invocar http:request (externos)")

    ceh_txt = (handler_dir / "common-error-handler.xml").read_text("utf-8","ignore") if (handler_dir / "common-error-handler.xml").exists() else ""
    if "hdl_commonErrorHandler" not in ceh_txt:
        rubric_errors.append("common-error-handler.xml debe contener sub-flow 'hdl_commonErrorHandler'")
    for d in [client_dir, handler_dir, orch_dir]:
        for p in d.glob("*.xml"):
            t = p.read_text("utf-8","ignore")
            if "<error-handler>" not in t:
                rubric_errors.append(f"{p.name}: falta error-handler con flow-ref a hdl_commonErrorHandler")

    if bool(raml_cp_value):
        if "http:listener-config" in (common_dir/"global-config.xml").read_text("utf-8","ignore"):
            rubric_errors.append("Con APIkit habilitado no debe haber listener-config en common/global-config.xml")

    write_validate_script(root)

    if rubric_errors:
        raise RuntimeError("Rúbricas BLOQUEANTES:\n- " + "\n- ".join(rubric_errors))

    if raml_info:
        try: write_min_readme(root, raml_info)
        except Exception: pass

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

        st.session_state.messages.append({"role":"assistant","content":"⚙️ Reescribiendo arquetipo + generando scaffold (client/APIkit/handler/orchestrator) + normalizando POM + validando rúbricas..."})
        try:
            salida_zip, modificados, errores = procesar_arquetipo_llm(arquetipo, ctx, spec_bytes)
            st.session_state.generated_zip = salida_zip
            resumen = f"✅ Proyecto generado. Archivos modificados/creados: {len(modificados)}"
            if errores:
                resumen += f"\n⚠️ Validaciones/Fallbacks: {len(errores)} (hasta 5):\n- " + "\n- ".join(errores[:5])
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
