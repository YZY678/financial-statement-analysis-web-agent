import importlib.util
import os
import sys
from threading import Lock
from typing import Any, Dict, Optional


class UpstreamAgentManager:
    def __init__(self) -> None:
        self._agents: Dict[str, Any] = {}
        self._lock = Lock()
        self._module = None

    def _resolve_base_dir(self) -> str:
        default_dir = "/root/web/upstream_repo/financial-statement-analysis-web-agent-main/可视化"
        return os.environ.get("UPSTREAM_AGENT_DIR", default_dir)

    def _load_module(self):
        if self._module is not None:
            return self._module

        base_dir = self._resolve_base_dir()
        agent_path = os.path.join(base_dir, "agent.py")
        if not os.path.exists(agent_path):
            raise FileNotFoundError(f"上游Agent文件不存在: {agent_path}")

        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)

        spec = importlib.util.spec_from_file_location("upstream_finance_agent", agent_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载上游Agent模块")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module = module
        return module

    def available(self) -> bool:
        try:
            self._load_module()
            return True
        except Exception:
            return False

    def get_or_create(self, session_id: str):
        with self._lock:
            if session_id in self._agents:
                return self._agents[session_id]

            module = self._load_module()
            agent = module.FinanceAgent(f"财经可视化智能体-{session_id[:8]}")
            self._agents[session_id] = agent
            return agent

    def process(self, session_id: str, message: str) -> Dict[str, Any]:
        agent = self.get_or_create(session_id)
        return agent.process(message)

    def execute_tool(self, session_id: str, tool_name: str, tool_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        agent = self.get_or_create(session_id)
        params = tool_params or {}

        mapping = {
            "parse_finance_file": "_execute_load_data",
            "clean_financial_data": "_execute_clean_data",
            "create_professional_chart": "_execute_generate_chart",
            "analyze_financial_health": "_execute_analyze_health",
        }

        if tool_name == "status":
            return {"status": "success", "session_status": agent.get_status()}

        if tool_name == "reset":
            reset_type = str(params.get("reset_type", "soft")).lower()
            return agent.reset(reset_type)

        if tool_name == "export_session_report":
            return agent.export_session_report()

        method_name = mapping.get(tool_name)
        if not method_name:
            return {"status": "error", "response": f"上游不支持该工具: {tool_name}"}

        method = getattr(agent, method_name, None)
        if method is None:
            return {"status": "error", "response": f"上游工具方法不存在: {method_name}"}

        return method(params)


upstream_agent_manager = UpstreamAgentManager()
