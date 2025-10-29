import re
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any

class NamesModel(BaseModel):
    project_name: str = "MuleApplication"
    artifact_id: str
    version: str = "1.0.0"
    group_id: str = "com.company.domain"
    api_display_name: Optional[str] = None
    api_name: Optional[str] = None

class PathsModel(BaseModel):
    base_path: str = "/api"
    base_uri: Optional[str] = None
    target_base_url: Optional[str] = None

class UpstreamModel(BaseModel):
    protocol: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None

class QuotaModel(BaseModel):
    enabled: bool = False
    interval: int = 1
    timeUnit: str = "minute"
    limit: int = 60

class SpikeArrestModel(BaseModel):
    enabled: bool = False
    rate: str = "10ps"

class SecurityModel(BaseModel):
    auth: str = "none"
    cors: bool = True
    quota: QuotaModel = Field(default_factory=QuotaModel)
    spike_arrest: SpikeArrestModel = Field(default_factory=SpikeArrestModel)

class UnifiedModel(BaseModel):
    layer: str
    names: NamesModel
    paths: PathsModel
    upstream: UpstreamModel = Field(default_factory=UpstreamModel)
    security: SecurityModel = Field(default_factory=SecurityModel)
    transformations: List[Dict[str, Any]] = []
    notes: str = ""

    @validator('names', pre=True)
    def derive_names(cls, v, values):
        # Derivaciones lógicas para nombres faltantes
        if v.get('project_name') and not v.get('artifact_id'):
            pn = v['project_name']
            v['artifact_id'] = re.sub(r"[^a-zA-Z0-9]+","-", pn).strip("-").lower() or "mule-app"
        if v.get('api_display_name') and not v.get('api_name'):
            adn = v['api_display_name']
            v['api_name'] = re.sub(r"[^a-zA-Z0-9]+","-", adn).strip("-").lower() or "api-proxy"
        return v