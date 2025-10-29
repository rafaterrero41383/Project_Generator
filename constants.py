# --- Claves de Streamlit Session State ---
S_MESSAGES = "messages"
S_UPLOADED_SPEC = "uploaded_spec"
S_GENERATED_ZIP = "generated_zip"
S_OBSERVACIONES = "observaciones"
S_SERVICE_TYPE = "service_type"
S_SPEC_NAME = "spec_name"
S_SPEC_KIND = "spec_kind"
S_IS_GENERATING = "is_generating"
S_PENDING_ACTION = "pending_action"
S_ARCHETYPE_CHOICE = "archetype_choice"
S_RUBRICS_DEFS = "rubrics_defs"
S_RUBRICS_KIND = "rubrics_kind"
S_CTX_TEXT = "ctx_text"
S_EXTRACTED_KIND = "extracted_kind"
S_EXTRACTED_NAME = "extracted_name"
S_EXTRACTED_BYTES = "extracted_bytes"


# --- Tipos de Servicio ---
TYPE_LABELS = {
    "REC": "RECEPTION",
    "DOM": "DOMAIN",
    "BUS": "BUSINESS",
    "PROXY": "PROXY",
    "UNKNOWN": "UNKNOWN"
}

# --- Extensiones de Archivo ---
TEXT_EXTS = {".xml",".json",".yaml",".yml",".raml",".properties",".txt",".pom",".md",".js",".gradle",".groovy"}
INVALID_WIN_CHARS = r'[:*?"<>|\\/]'

# --- Avatares para el Chat ---
ASSISTANT_AVATAR = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png"
USER_AVATAR = "https://cdn-icons-png.flaticon.com/512/1077/1077012.png"