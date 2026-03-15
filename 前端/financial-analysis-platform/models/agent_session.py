from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentSession:
    id: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    report_type: Optional[str] = None
    data_loaded: bool = False
    data_cleaned: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None
    df: Optional[Any] = None
    cleaned_df: Optional[Any] = None
    charts: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    compare_charts: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    workflow_history: List[Dict[str, Any]] = field(default_factory=list)
    last_decision: Optional[Dict[str, Any]] = None
    suggestions: List[str] = field(default_factory=list)
    brain_state: Dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "report_type": self.report_type,
            "data_loaded": self.data_loaded,
            "data_cleaned": self.data_cleaned,
            "charts_generated": len(self.charts),
            "files_loaded": len(self.files),
            "files": [
                {
                    "file_name": item.get("file_name"),
                    "report_type": item.get("report_type"),
                }
                for item in self.files
            ],
            "compare_charts": len(self.compare_charts),
            "error": self.error,
            "last_decision": self.last_decision,
            "suggestions": self.suggestions,
            "brain_state": self.brain_state,
        }
