from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class IncidentSeverity(str, Enum):
    URGENT = "URGENT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    ALL_GOOD = "ALL_GOOD"

class IncidentType(str, Enum):
    MISSING_FILE = "Missing File"
    DUPLICATED_FILE = "Duplicated File"
    UNEXPECTED_EMPTY = "Unexpected Empty File"
    VOLUME_VARIATION = "Unexpected Volume Variation"
    LATE_UPLOAD = "File Upload After Schedule"
    PREVIOUS_FILE = "Upload of Previous File"

class Incident(BaseModel):
    incident_type: IncidentType
    severity: IncidentSeverity
    description: str
    recommendation: str
    source_id: str
    file_name: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class SourceReport(BaseModel):
    source_id: str
    status: IncidentSeverity
    incidents: List[Incident]
    processed_files_count: int = 0
    total_rows: int = 0

class UsageStats(BaseModel):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost: float
    model: str

class ConsolidatedReport(BaseModel):
    date: str
    generated_at: datetime
    sources: List[SourceReport]
    summary: str
    status: IncidentSeverity
    usage: Optional[UsageStats] = None

class FileMetadata(BaseModel):
    filename: str
    rows: int
    status: str
    is_duplicated: bool
    file_size: Optional[float] = None
    uploaded_at: str
    status_message: Optional[str] = None

class SourceCV(BaseModel):
    source_id: str
    expected_files_by_day: Dict[str, Any] # e.g., {"Mon": {"min": 0, "max": 1}, ...}
    upload_window_by_day: Dict[str, Any] # e.g., {"Mon": {"start": "08:00", "end": "09:00"}, ...}
    filename_patterns: List[str]
    entity_stats: Dict[str, Any] # Stats per entity per day
    empty_file_stats: Dict[str, Any] = Field(default_factory=dict) # Stats about empty files per day
