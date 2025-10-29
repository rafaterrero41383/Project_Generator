import os
import re
import yaml
from openai import OpenAI
from typing import Optional

# Importamos el modelo desde nuestro nuevo archivo centralizado
from models import UnifiedModel

# --- OpenAI Client Setup ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_BASE = "gpt-4o-mini"

PROMPT_UNIFICADO = """
Responde con un ÚNICO YAML válido. Eres un generador de proyectos para cuatro capas:
- Domain (Mule 4)
- Business (Mule 4)
- Proxy (Mule 4, reverse proxy)
- Reception (Apigee)

Objetivo:
A partir de una ESPECIFICACIÓN (OpenAPI/RAML/texto) y la CAPA seleccionada ({capa}), emite un único YAML con toda la metadata necesaria para generar el proyecto final usando un motor de plantillas.

Entrada: Texto de la especificación.
Salida: YAML unificado que se usará como contexto para renderizar las plantillas del arquetipo.

Estructura obligatoria del YAML:

layer: domain | business | proxy | reception
names:
  project_name: string
  artifact_id: string-kebab
  version: "1.0.0"
  group_id: com.company.domain
  api_display_name: string
  api_name: string-kebab
paths:
  base_path: "/v1/resource"
  base_uri: "https://host/v1"
  target_base_url: "https://host/v1"
upstream:
  protocol: HTTP|HTTPS|null
  host: string|null
  path: "/v1" | "/" | null
security:
  auth: none | apikey | oauth2
  cors: true|false
  quota:
    enabled: true|false
    interval: 1
    timeUnit: minute|hour|day
    limit: 60
  spike_arrest:
    enabled: true|false
    rate: "10ps"
transformations:
  - set_mule_pom: true
notes: "supuestos y aclaraciones breves"

Reglas:
- Deriva artifact_id y api_name en kebab-case si faltan.
- No inventes hosts/URLs si no están en la especificación: deja null.
- Responde únicamente con el bloque de código YAML, sin explicaciones.
"""


def _gpt(messages, temperature=0.1, model=MODEL_BASE) -> str:
    """Función base para llamar a la API de OpenAI."""
    try:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error llamando a la API de OpenAI: {e}")
        return ""


def inferir_contexto_unificado(contenido_api: str, layer_choice: str) -> Optional[UnifiedModel]:
    """
    Realiza la ÚNICA llamada al LLM para obtener el contexto y lo valida con Pydantic.
    """
    layer_key = {
        "Domain": "domain", "Business": "business", "Proxy": "proxy", "Reception": "reception"
    }.get(layer_choice, "domain")

    prompt = PROMPT_UNIFICADO.format(capa=layer_key)
    messages = [
        {"role": "system", "content": "Responde solo con un bloque de código YAML válido."},
        {"role": "user", "content": f"{prompt}\n\n=== ESPECIFICACIÓN ===\n{contenido_api}"}
    ]

    raw_yaml = _gpt(messages)

    match = re.search(r"```(?:yaml|yml)?\s*(.*?)```", raw_yaml, re.DOTALL)
    clean_yaml = match.group(1).strip() if match else raw_yaml

    try:
        data = yaml.safe_load(clean_yaml)
        if not data:
            print("Advertencia: El LLM devolvió un YAML vacío.")
            return None

        validated_data = UnifiedModel.model_validate(data)  # .model_validate para Pydantic v2
        return validated_data

    except (yaml.YAMLError, Exception) as e:
        print(f"Error al parsear o validar el YAML del LLM: {e}")
        print(f"--- YAML recibido ---\n{clean_yaml}\n--------------------")
        return None