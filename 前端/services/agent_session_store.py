from typing import Dict, Optional

from models.agent_session import AgentSession


class AgentSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, AgentSession] = {}

    def create(self, session: AgentSession) -> AgentSession:
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def update(self, session_id: str, **kwargs) -> Optional[AgentSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        return session

    def reset(self, session_id: str, reset_type: str = "soft") -> Optional[AgentSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None

        reset_mode = (reset_type or "soft").strip().lower()
        if reset_mode == "hard":
            session.file_path = None
            session.file_name = None
            session.report_type = None
            session.data_loaded = False
            session.data_cleaned = False
            session.error = None
            session.df = None
            session.cleaned_df = None
            session.charts = []
            session.files = []
            session.compare_charts = []
            session.logs = []
            session.workflow_history = []
            session.last_decision = None
            session.suggestions = []
            session.brain_state = {}
            return session

        session.data_loaded = False
        session.data_cleaned = False
        session.error = None
        session.df = None
        session.cleaned_df = None
        return session
