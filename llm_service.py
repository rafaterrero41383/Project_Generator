import os
import re
import tempfile
import zipfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from constants import TEXT_EXTS
from llm_service import UnifiedModel  # Usamos el modelo validado


def render_template_directory(src_dir: Path, dest_dir: Path, context: UnifiedModel):
    """
    Renderiza un directorio completo de plantillas Jinja2.
    """
    env = Environment(loader=FileSystemLoader(searchpath=str(src_dir)), autoescape=False)

    # Convertimos el objeto Pydantic a un dict para pasarlo a Jinja
    ctx_dict = context.dict()

    for path_plantilla in src_dir.rglob("*"):
        ruta_relativa = path_plantilla.relative_to(src_dir)
        path_destino = dest_dir / ruta_relativa
        path_destino.parent.mkdir(parents=True, exist_ok=True)

        if path_plantilla.is_dir():
            continue

        # Copia archivos binarios directamente
        if path_plantilla.suffix.lower() not in TEXT_EXTS and path_plantilla.name.lower() != "pom.xml":
            shutil.copy(path_plantilla, path_destino)
            continue

        try:
            template = env.get_template(str(ruta_relativa))
            contenido_renderizado = template.render(ctx_dict)
            path_destino.write_text(contenido_renderizado, encoding="utf-8")
        except Exception as e:
            # Si un archivo de texto falla (ej. no es una plantilla), lo copiamos tal cual
            print(f"Info: No se pudo renderizar '{ruta_relativa}' como plantilla. Copiando original. Error: {e}")
            shutil.copy(path_plantilla, path_destino)


def post_process_mule_project(project_root: Path, context: UnifiedModel):
    """
    Aplica lógicas específicas de Mule que son difíciles de manejar solo con plantillas.
    (Ej: generar flujos dinámicamente si fuera necesario, aunque la mayoría se puede hacer con plantillas).
    Por ahora, nos enfocamos en el README y scripts.
    """
    readme_path = project_root / "README.md"
    readme_content = f"""
# {context.names.project_name}

Proyecto generado automáticamente.

- **Capa:** {context.layer.upper()}
- **Artifact ID:** `{context.names.artifact_id}`
- **Group ID:** `{context.names.group_id}`
- **Versión:** `{context.names.version}`
- **Path Base:** `{context.paths.base_path}`
"""
    readme_path.write_text(readme_content, encoding="utf-8")


def procesar_arquetipo(arquetipo_dir: str, context: UnifiedModel, spec_bytes: bytes, spec_kind: str) -> str:
    """
    Función unificada para procesar cualquier arquetipo.
    """
    src_path = Path(arquetipo_dir)
    # Usamos un directorio temporal para el proyecto generado
    dest_path = Path(tempfile.mkdtemp())

    print(f"Generando proyecto en: {dest_path}")

    # 1. Renderizar el arquetipo-plantilla con el contexto del LLM
    render_template_directory(src_path, dest_path, context)

    # 2. Pasos de post-procesamiento específicos de la capa
    if context.layer in ["domain", "business", "proxy"]:
        # Colocar la especificación (RAML/OAS) en el lugar correcto
        api_dir = dest_path / "src/main/resources/api"
        api_dir.mkdir(parents=True, exist_ok=True)
        spec_filename = "api.raml" if spec_kind == "RAML" else "openapi.yaml"
        (api_dir / spec_filename).write_bytes(spec_bytes)

        post_process_mule_project(dest_path, context)

    elif context.layer == "reception":
        # Renombrar el bundle de Apigee si es necesario
        try:
            apiproxy_bundle_dir = next(dest_path.glob("**/apiproxy")).parent
            if apiproxy_bundle_dir.name != context.names.api_name:
                target_dir = apiproxy_bundle_dir.parent / context.names.api_name
                shutil.move(str(apiproxy_bundle_dir), str(target_dir))
        except (StopIteration, Exception) as e:
            print(f"Advertencia: No se pudo renombrar el bundle de Apigee. {e}")

        # Colocar la especificación OAS
        oas_path = dest_path / context.names.api_name / "apiproxy/resources/oas/openapi.json"
        oas_path.parent.mkdir(parents=True, exist_ok=True)
        oas_path.write_bytes(spec_bytes)  # Asumimos que la especificación ya está en el formato correcto

    # 3. Comprimir el resultado en un archivo ZIP
    output_zip_path = Path(tempfile.gettempdir()) / f"{context.names.artifact_id}.zip"
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in dest_path.rglob("*"):
            z.write(p, p.relative_to(dest_path))

    # Limpiar el directorio temporal
    shutil.rmtree(dest_path)

    return str(output_zip_path)