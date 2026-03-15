from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Task:
    id: str
    filename: str
    filepath: str
    company_name: str
    report_type: str
    analysis_type: str
    status: str = "pending"
    progress: int = 0
    start_time: str = ""
    end_time: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    user_data: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None
    report_path: Optional[str] = None
    detected_type: Optional[str] = None

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message or "",
            "error": self.error,
        }
