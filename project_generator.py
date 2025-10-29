import os
import tempfile
import zipfile
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from constants import TEXT_EXTS
from models import UnifiedModel

def render_template_directory(src_dir: Path, dest_dir: Path, context: UnifiedModel):
    """
    Renderiza un directorio completo de plantillas Jinja2.
    """
    env = Environment(loader=FileSystemLoader(searchpath=str(src_dir)), autoescape=False)

    # Usamos .model_dump() para Pydantic v2+ para pasarlo a Jinja
    ctx_dict = context.model_dump()

    for path_plantilla in src_dir.rglob("*"):
        ruta_relativa = path_plantilla.relative_to(src_dir)
        path_destino = dest_dir / ruta_relativa
        path_destino.parent.mkdir(parents=True, exist_ok=True)

        if path_plantilla.is_dir():
            continue

        if path_plantilla.suffix.lower() not in TEXT_EXTS and path_plantilla.name.lower() != "pom.xml":
            shutil.copy(path_plantilla, path_destino)
            continue

        try:
            template_name = str(ruta_relativa).replace(os.path.sep, '/')  # Jinja prefiere slashes
            template = env.get_template(template_name)
            contenido_renderizado = template.render(ctx_dict)
            path_destino.write_text(contenido_renderizado, encoding="utf-8")
        except Exception as e:
            print(f"Info: No se pudo renderizar '{ruta_relativa}' como plantilla. Copiando original. Error: {e}")
            shutil.copy(path_plantilla, path_destino)


def post_process_mule_project(project_root: Path, context: UnifiedModel):
    """
    Aplica lógicas específicas de Mule que son difíciles de manejar solo con plantillas.
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
    dest_path = Path(tempfile.mkdtemp())

    print(f"Generando proyecto en: {dest_path}")

    render_template_directory(src_path, dest_path, context)

    if context.layer in ["domain", "business", "proxy"]:
        api_dir = dest_path / "src/main/resources/api"
        api_dir.mkdir(parents=True, exist_ok=True)
        spec_filename = "api.raml" if spec_kind == "RAML" else "openapi.yaml"
        (api_dir / spec_filename).write_bytes(spec_bytes)
        post_process_mule_project(dest_path, context)

    elif context.layer == "reception":
        try:
            bundle_parent = next(dest_path.glob("*/apiproxy")).parent
            if bundle_parent.name != context.names.api_name:
                target_dir = bundle_parent.parent / context.names.api_name
                shutil.move(str(bundle_parent), str(target_dir))
                oas_dir = target_dir / "apiproxy/resources/oas"
            else:
                oas_dir = bundle_parent / "apiproxy/resources/oas"

            oas_dir.mkdir(parents=True, exist_ok=True)
            (oas_dir / "openapi.json").write_bytes(spec_bytes)
        except (StopIteration, Exception) as e:
            print(f"Advertencia: No se pudo procesar el bundle de Apigee. {e}")

    output_zip_path = Path(tempfile.gettempdir()) / f"{context.names.artifact_id}.zip"
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in dest_path.rglob("*"):
            z.write(p, p.relative_to(dest_path))

    shutil.rmtree(dest_path)
    return str(output_zip_path)