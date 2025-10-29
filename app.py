# app.py
# Interfaz de usuario con Streamlit y orquestación del proceso.

import io
import os
import sys
import types
import socket
import datetime
import time
import json
import requests
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
import tempfile
import shutil
import zipfile
import re

# --- Parche compatibilidad 3.13 (si es necesario) ---
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType("imghdr")
    sys.modules['imghdr'] = imghdr

# --- Importar nuestros módulos ---
from constants import *
from llm_service import inferir_contexto_unificado
from project_generator import procesar_arquetipo

# Asumimos que otras funciones de utilidad (lectura de zip, etc.) están en un archivo utils.py
# Por simplicidad en esta refactorización, las incluimos aquí.

# ========= CONFIG =========
load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    st.error("❌ Falta OPENAI_API_KEY en secretos/entorno.")
    st.stop()

# Datadog (opcional)
DD_API_KEY = os.getenv("DATADOG_API_KEY")
DD_SITE = os.getenv("DATADOG_SITE", "datadoghq.com")
DD_URL = f"https://http-intake.logs.{DD_SITE}/api/v2/logs"
DD_SERVICE = os.getenv("DATADOG_SERVICE", "mule-project-generator")
DD_SOURCE = os.getenv("DATADOG_SOURCE", "mulesoft-gen")
DD_TAGS = os.getenv("DATADOG_TAGS", "app:mule-gen,env:local")

# ========= UI & Estado =========
st.set_page_config(page_title="🤖 Generador de Proyectos", layout="wide")
st.markdown("""
<style>
/* ... (tu CSS aquí) ... */
</style>
""", unsafe_allow_html=True)
st.markdown("<h1 style='text-align:center;'>🤖 Generador de Proyectos</h1>", unsafe_allow_html=True)


# --- Inicialización del Estado ---
def init_session_state():
    defaults = {
        S_MESSAGES: [], S_UPLOADED_SPEC: None, S_GENERATED_ZIP: None,
        S_OBSERVACIONES: [], S_SERVICE_TYPE: "UNKNOWN", S_SPEC_NAME: None,
        S_SPEC_KIND: None, S_IS_GENERATING: False, S_PENDING_ACTION: None,
        S_ARCHETYPE_CHOICE: "Automático", S_RUBRICS_DEFS: [], S_RUBRICS_KIND: "mule",
        S_CTX_TEXT: "", S_EXTRACTED_KIND: None, S_EXTRACTED_NAME: None, S_EXTRACTED_BYTES: None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# ========= Utilidades (movidas de `utils.py` para simplicidad) =========

def _map_prefix_to_type(filename: str) -> str | None:
    if not filename: return None
    fname = filename.lower()
    if "-rec-" in fname or "reception" in fname: return "REC"
    if "-dom-" in fname or "domain" in fname: return "DOM"
    if "-bus-" in fname or "business" in fname: return "BUS"
    if "proxy" in fname: return "PROXY"
    return None


def _best_candidate_from_zip(z: zipfile.ZipFile) -> tuple[str, str, bytes]:
    names = z.namelist()
    candidates = {
        "OAS": [n for n in names if re.search(r'(openapi|swagger)\.(ya?ml|json)$', n, re.I)],
        "RAML": [n for n in names if n.lower().endswith(".raml")],
    }
    for kind, files in candidates.items():
        if files:
            name = files[0]
            return (kind, name, z.read(name))
    return ("RAW", names[0] if names else "", z.read(names[0]) if names else b"")


def leer_especificacion(file):
    name = (file.name or "").lower()
    file.seek(0)
    if name.endswith(".zip"):
        st.session_state[S_SPEC_KIND] = "ZIP"
        data = file.read()
        with zipfile.ZipFile(io.BytesIO(data), "r") as z:
            kind, inner_name, inner_bytes = _best_candidate_from_zip(z)
        st.session_state[S_EXTRACTED_KIND] = kind
        st.session_state[S_EXTRACTED_NAME] = inner_name
        st.session_state[S_EXTRACTED_BYTES] = inner_bytes
        ctx_text = inner_bytes.decode("utf-8", "ignore")
        st.session_state[S_CTX_TEXT] = ctx_text
    # ... (añadir lógica para otros tipos si es necesario)


# --- Lógica de Arquetipos (simplificada) ---
# En una app real, esto estaría en `archetype_manager.py`
def obtener_arquetipo(layer: str) -> str | None:
    # Busca un arquetipo localmente (ej. ./archetypes/reception, ./archetypes/generic-mule)
    archetype_path = Path("archetypes") / layer
    if archetype_path.exists() and archetype_path.is_dir():
        return str(archetype_path.resolve())
    st.error(f"No se encontró el directorio del arquetipo en: {archetype_path}")
    return None


# ========= Lógica Principal de la App =========

def ejecutar_generacion():
    try:
        if not st.session_state[S_UPLOADED_SPEC]:
            st.warning("Primero adjunta el ZIP de diseño.")
            return

        choice = st.session_state[S_ARCHETYPE_CHOICE]
        if choice == "Automático":
            svc_map = {"REC": "Reception", "DOM": "Domain", "BUS": "Business", "PROXY": "Proxy"}
            choice = svc_map.get(st.session_state[S_SERVICE_TYPE], "Domain")

        st.info(f"⚙️ Iniciando generación para la capa: **{choice}**")

        # 1. Obtener el contexto del LLM (una sola llamada)
        with st.spinner("🧠 Analizando especificación con IA..."):
            contexto = inferir_contexto_unificado(
                st.session_state[S_CTX_TEXT],
                choice
            )

        if not contexto:
            st.error("❌ El LLM no pudo generar un contexto válido. Revisa el log o la especificación.")
            return

        st.success("✅ Contexto de generación creado con éxito.")
        with st.expander("Ver YAML de contexto generado"):
            st.code(contexto.json(indent=2), language="json")

        # 2. Encontrar el arquetipo-plantilla correcto
        layer_key = choice.lower()
        arquetipo_path = obtener_arquetipo("reception" if layer_key == "reception" else "generic-mule")

        if not arquetipo_path:
            return  # `obtener_arquetipo` ya muestra un error

        # 3. Renderizar el proyecto
        with st.spinner("🏗️ Construyendo proyecto desde la plantilla..."):
            salida_zip = procesar_arquetipo(
                arquetipo_dir=arquetipo_path,
                context=contexto,
                spec_bytes=st.session_state[S_EXTRACTED_BYTES],
                spec_kind=st.session_state[S_EXTRACTED_KIND]
            )

        st.session_state[S_GENERATED_ZIP] = salida_zip
        st.session_state[S_SERVICE_TYPE] = choice.upper()

        st.success(f"✅ ¡Proyecto '{contexto.names.artifact_id}.zip' generado!")

    except Exception as e:
        st.error(f"💥 Ocurrió un error durante la generación: {e}")
    finally:
        st.session_state[S_IS_GENERATING] = False
        st.session_state[S_PENDING_ACTION] = None


# ========= Renderizado de la UI =========

if st.button("🔄 Reiniciar"):
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()

spec = st.file_uploader(
    "Adjunta el ZIP de diseño (debe contener openapi.yaml o api.raml)", type=["zip"]
)

if spec and st.session_state[S_UPLOADED_SPEC] is None:
    st.session_state[S_UPLOADED_SPEC] = spec
    st.session_state[S_SPEC_NAME] = spec.name
    st.session_state[S_SERVICE_TYPE] = _map_prefix_to_type(spec.name) or "UNKNOWN"
    leer_especificacion(spec)
    st.session_state[S_MESSAGES].append({
        "role": "assistant",
        "content": f"📦 Especificación \"{spec.name}\" cargada. Elige la capa y escribe \"crea el proyecto\"."
    })
    st.rerun()

if st.session_state[S_UPLOADED_SPEC]:
    choices = ["Domain", "Reception", "Business", "Proxy", "Automático"]
    inferred = st.session_state[S_SERVICE_TYPE]
    default_idx = {"DOM": 0, "REC": 1, "BUS": 2, "PROXY": 3}.get(inferred, 4)
    st.session_state[S_ARCHETYPE_CHOICE] = st.radio(
        "Selecciona la capa para generar el proyecto",
        choices, index=default_idx, horizontal=True
    )

# Historial de Chat y entrada de usuario
# ... (la lógica del chat puede permanecer igual, llamando a `ejecutar_generacion`)
if st.session_state.get(S_IS_GENERATING, False):
    st.info("⏳ Generando proyecto… El chat está deshabilitado.")

if st.session_state.is_generating and st.session_state.pending_action == "generate":
    ejecutar_generacion()
    st.rerun()

user_input = st.chat_input("Escribe 'crea el proyecto' para empezar...")
if user_input and not st.session_state[S_IS_GENERATING]:
    st.session_state[S_MESSAGES].append({"role": "user", "content": user_input})
    if "crea el proyecto" in user_input.lower():
        st.session_state[S_IS_GENERATING] = True
        st.session_state[S_PENDING_ACTION] = "generate"
        st.rerun()
    else:
        st.session_state[S_MESSAGES].append(
            {"role": "assistant", "content": "💬 Entendido. Para empezar, escribe \"crea el proyecto\"."})
        st.rerun()

# Botón de descarga
if st.session_state[S_GENERATED_ZIP]:
    zip_path = Path(st.session_state[S_GENERATED_ZIP])
    with open(zip_path, "rb") as f:
        st.download_button(f"⬇️ Descargar {zip_path.name}", f, file_name=zip_path.name)