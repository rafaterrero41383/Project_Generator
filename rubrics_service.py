# rubrics_service.py
# Lógica para cargar y aplicar las rúbricas de calidad a un proyecto generado.

import json
import re
from pathlib import Path
import streamlit as st


# (Estas funciones son adaptadas de tu script original)

def _normalize_rubric_item(item: dict) -> dict:
    return {
        "id": item.get("id") or "",
        "label": item.get("label") or "",
        "category": item.get("category") or "",
        "severity": (item.get("severity") or "WARN").upper(),
        "enabled": item.get("enabled", True),
    }


def cargar_rubricas(rubrics_kind: str) -> list[dict]:
    """Carga las definiciones de rúbricas desde un archivo JSON en la raíz."""
    filename = "Rubrics_Generation_Mule.json" if rubrics_kind == "mule" else "Rubricas_Scaffold_Apigee.json"
    path = Path(filename)
    if not path.exists():
        st.sidebar.warning(f"⚠️ No se encontró el archivo de rúbricas '{filename}'.")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        arr = data.get("rubrics", data)
        if not isinstance(arr, list): arr = [arr]

        rubrics = [_normalize_rubric_item(x) for x in arr if isinstance(x, dict)]
        st.sidebar.success(f"✅ {len(rubrics)} rúbricas ({rubrics_kind}) cargadas desde '{filename}'.")
        return rubrics
    except Exception as e:
        st.sidebar.error(f"❌ Error al cargar rúbricas '{filename}': {e}")
        return []


def _rubric_observaciones_basic_mule(root: Path) -> list[str]:
    """Realiza validaciones básicas de estructura para proyectos Mule."""
    notes = []
    base = root / "src/main/mule"
    if not base.exists():
        notes.append("[Estructura] Falta la carpeta principal `src/main/mule/`.")
        return notes

    for d in ["client", "handler", "orchestrator", "common"]:
        if not (base / d).exists():
            notes.append(f"[Estructura] Falta la carpeta `src/main/mule/{d}/`.")

    if not (root / "pom.xml").exists(): notes.append("[Activos] Falta el archivo `pom.xml`.")
    if not (root / "mule-artifact.json").exists(): notes.append("[Activos] Falta el archivo `mule-artifact.json`.")

    # Aquí puedes añadir más validaciones del script original si lo deseas...
    return notes


def _rubric_observaciones_basic_apigee(root: Path) -> list[str]:
    """Realiza validaciones básicas de estructura para proyectos Apigee."""
    notes = []
    try:
        apiproxy_dir = next(root.glob("**/apiproxy"))
        if not (apiproxy_dir / "proxies/default.xml").exists():
            notes.append("[Apigee] Falta el archivo `proxies/default.xml`.")
        if not (apiproxy_dir / "targets/backend.xml").exists():
            notes.append("[Apigee] Falta el archivo `targets/backend.xml`.")
        if not list((apiproxy_dir / "policies").glob("*.xml")):
            notes.append("[Apigee] No se encontraron políticas en la carpeta `policies/`.")
    except StopIteration:
        notes.append("[Apigee] No se encontró la carpeta `apiproxy` en el proyecto.")
    return notes


def analizar_proyecto_con_rubricas(project_path: Path, rubrics_kind: str, rubrics_defs: list[dict]) -> list[str]:
    """
    Punto de entrada principal para analizar un proyecto y devolver las observaciones.
    """
    if rubrics_kind == "mule":
        base_notes = _rubric_observaciones_basic_mule(project_path)
    else:  # apigee
        base_notes = _rubric_observaciones_basic_apigee(project_path)

    # Si no hay rúbricas cargadas, devolvemos solo las observaciones básicas.
    if not rubrics_defs:
        return [f"<span class='sev-WARN'><b>[WARN]</b></span> {note}" for note in base_notes]

    # Lógica para adornar las notas con la severidad de las rúbricas (simplificada)
    adorned_notes = []
    for note in base_notes:
        matched_rubric = None
        note_l = note.lower()
        for rubric in rubrics_defs:
            if any(kw in note_l for kw in (rubric['id'].lower(), rubric['label'].lower())):
                matched_rubric = rubric
                break

        sev = matched_rubric['severity'] if matched_rubric else "WARN"
        rid = f"({matched_rubric['id']})" if matched_rubric else ""
        adorned_notes.append(f"<span class='sev-{sev}'><b>[{sev}]</b></span> {rid} {note}")

    return adorned_notes