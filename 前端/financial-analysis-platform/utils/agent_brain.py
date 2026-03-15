import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Tuple


INTENT_PATTERNS = {
    "greeting": [r"你好", r"您好", r"hello", r"hi"],
    "farewell": [r"再见", r"拜拜", r"退出"],
    "help": [r"帮助", r"怎么用", r"功能"],
    "upload": [r"上传", r"选择文件", r"加载文件", r"导入"],
    "parse": [r"解析", r"读取", r"加载"],
    "clean": [r"清洗", r"预处理", r"整理"],
    "chart": [r"图表", r"可视化", r"画图", r"生成图"],
    "compare": [r"对比", r"比较", r"多文件", r"多个文件"],
    "analyze": [r"分析", r"指标", r"财务健康", r"利润率", r"资产负债"],
    "status": [r"状态", r"进度", r"当前"],
    "reset": [r"重置", r"清空", r"重新开始"],
}

CHART_KEYWORDS = {
    "趋势": "income_trend",
    "折线": "income_trend",
    "对比": "revenue_comparison",
    "柱状": "revenue_comparison",
    "构成": "profit_composition",
    "占比": "profit_composition",
    "资产": "balance_sheet",
    "负债": "balance_sheet",
    "费用": "expense_breakdown",
    "成本": "expense_breakdown",
}


@dataclass
class BrainContext:
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    workflow_history: List[Dict[str, Any]] = field(default_factory=list)
    current_state: Dict[str, Any] = field(default_factory=lambda: {
        "data_loaded": False,
        "data_cleaned": False,
        "current_file": None,
        "current_chart_type": None,
        "last_action": None,
        "report_type": None,
    })


class AgentBrain:
    def __init__(self) -> None:
        self.context = BrainContext()

    def think(self, user_input: str, tools_description: List[Dict[str, Any]]) -> Dict[str, Any]:
        intent_analysis = self._analyze_intent(user_input)
        intent_analysis = self._apply_context(intent_analysis)
        execution_plan = self._plan_execution(intent_analysis)
        suggestions = self._generate_suggestions(intent_analysis)

        decision = {
            "need_tool": execution_plan.get("need_tool", False),
            "tool_name": execution_plan.get("tool_name"),
            "tool_params": execution_plan.get("tool_params", {}),
            "reason": execution_plan.get("reason", ""),
            "confidence": intent_analysis.get("confidence", 0.4),
            "intent_analysis": intent_analysis,
            "execution_plan": execution_plan,
            "suggestions": suggestions,
        }

        self._record_conversation("assistant", decision.get("reason", ""))
        self._record_workflow(intent_analysis, execution_plan)
        return decision

    def to_state(self) -> Dict[str, Any]:
        return {
            "conversation_history": self.context.conversation_history,
            "workflow_history": self.context.workflow_history,
            "current_state": self.context.current_state,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        if not state:
            return
        self.context.conversation_history = state.get("conversation_history", [])
        self.context.workflow_history = state.get("workflow_history", [])
        self.context.current_state = state.get("current_state", self.context.current_state)

    def _analyze_intent(self, user_input: str) -> Dict[str, Any]:
        detected = []
        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_input, re.IGNORECASE):
                    detected.append(intent)
                    break

        primary = self._pick_primary_intent(detected)
        entities = self._extract_entities(user_input)
        confidence = self._calculate_confidence(user_input, detected)

        return {
            "primary_intent": primary,
            "secondary_intents": list(set(detected) - {primary}),
            "entities": entities,
            "confidence": confidence,
            "raw_input": user_input,
        }

    @staticmethod
    def _pick_primary_intent(intents: List[str]) -> str:
        if not intents:
            return "unknown"
        priority = [
            "compare",
            "chart",
            "analyze",
            "clean",
            "parse",
            "upload",
            "status",
            "reset",
            "help",
            "greeting",
            "farewell",
        ]
        for intent in priority:
            if intent in intents:
                return intent
        return intents[0]

    @staticmethod
    def _extract_entities(text: str) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        for keyword, chart_type in CHART_KEYWORDS.items():
            if keyword in text:
                entities["chart_type"] = chart_type
                break

        metric_match = re.search(r"(?:对比|比较)\s*([\w\u4e00-\u9fa5、及和\s]{2,30})", text)
        if metric_match:
            raw = metric_match.group(1)
            raw = raw.replace(" ", "")
            parts = re.split(r"[、及和]", raw)
            metrics = [p for p in parts if len(p) >= 2]
            if metrics:
                entities["metrics"] = metrics
                entities["metric"] = metrics[0]

        return entities

    @staticmethod
    def _calculate_confidence(text: str, intents: List[str]) -> float:
        if not intents:
            return 0.3

        confidence = min(0.3 + len(intents) * 0.2, 0.85)
        if len(text) > 20:
            confidence += 0.05
        if re.search(r"\d", text):
            confidence += 0.05
        return round(min(confidence, 0.95), 2)

    def _apply_context(self, intent_analysis: Dict[str, Any]) -> Dict[str, Any]:
        text = intent_analysis.get("raw_input", "")
        state = self.context.current_state

        if any(word in text for word in ["再", "重新", "继续"]):
            last_action = state.get("last_action")
            if last_action == "chart_generation" and state.get("current_chart_type"):
                intent_analysis["primary_intent"] = "chart"
                intent_analysis["entities"]["chart_type"] = state.get("current_chart_type")
                intent_analysis["confidence"] = 0.85

        if any(word in text for word in ["这个", "当前", "刚刚"]):
            if state.get("current_file") and "file_path" not in intent_analysis["entities"]:
                intent_analysis["entities"]["file_path"] = state.get("current_file")

        return intent_analysis

    def _plan_execution(self, intent_analysis: Dict[str, Any]) -> Dict[str, Any]:
        intent = intent_analysis.get("primary_intent")
        entities = intent_analysis.get("entities", {})
        state = self.context.current_state

        plan = {
            "need_tool": False,
            "tool_name": None,
            "tool_params": {},
            "workflow": [],
            "reason": "",
        }

        if intent in ["greeting", "farewell", "help"]:
            plan["reason"] = self._build_response(intent)
            return plan

        if intent == "status":
            plan["reason"] = self._status_report()
            return plan

        if intent == "reset":
            plan["need_tool"] = True
            plan["tool_name"] = "reset"
            plan["reason"] = "正在重置会话"
            return plan

        if intent in ["upload", "parse"]:
            plan["need_tool"] = True
            plan["tool_name"] = "upload"
            plan["reason"] = "请先上传文件"
            return plan

        if intent == "clean":
            plan.update({
                "need_tool": True,
                "tool_name": "clean",
                "reason": "正在清洗数据",
            })
            return plan

        if intent == "analyze":
            plan.update({
                "need_tool": True,
                "tool_name": "analyze",
                "reason": "正在进行财务健康分析",
            })
            return plan

        if intent == "compare":
            plan.update({
                "need_tool": True,
                "tool_name": "compare",
                "tool_params": {
                    "metric": entities.get("metric"),
                    "metrics": entities.get("metrics"),
                    "title": intent_analysis.get("raw_input") or "多文件对比",
                },
                "reason": "正在生成多文件对比图",
            })
            return plan

        if intent == "chart":
            chart_type = entities.get("chart_type", "income_trend")
            title = intent_analysis.get("raw_input") or "财经数据分析"
            plan.update({
                "need_tool": True,
                "tool_name": "chart",
                "tool_params": {
                    "chart_type": chart_type,
                    "title": title,
                },
                "reason": "正在生成图表",
            })
            return plan

        if not state.get("data_loaded"):
            plan["reason"] = "请先上传文件"
        else:
            plan["reason"] = "我可以帮您生成图表或分析财务健康"

        return plan

    def _generate_suggestions(self, intent_analysis: Dict[str, Any]) -> List[str]:
        state = self.context.current_state
        suggestions: List[str] = []

        if not state.get("data_loaded"):
            return ["请先上传或加载数据文件"]

        if not state.get("data_cleaned"):
            suggestions.append("建议先清洗数据以提高分析准确度")

        suggestions.extend([
            "可以尝试：生成趋势图",
            "可以尝试：对比多个文件",
            "可以尝试：财务健康分析",
        ])

        return suggestions[:3]

    @staticmethod
    def _build_response(intent: str) -> str:
        responses = {
            "greeting": "您好，我可以帮您分析财务数据并生成图表。",
            "farewell": "感谢使用，祝您工作顺利。",
            "help": "您可以上传数据、生成图表、进行对比或财务分析。",
        }
        return responses.get(intent, "已收到")

    def _status_report(self) -> str:
        state = self.context.current_state
        return (
            f"数据已加载: {state.get('data_loaded')} | "
            f"数据已清洗: {state.get('data_cleaned')} | "
            f"当前文件: {state.get('current_file') or '无'}"
        )

    def _record_conversation(self, role: str, content: str) -> None:
        self.context.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content[:200],
        })
        if len(self.context.conversation_history) > 20:
            self.context.conversation_history = self.context.conversation_history[-20:]

    def _record_workflow(self, intent_analysis: Dict[str, Any], execution_plan: Dict[str, Any]) -> None:
        intent = intent_analysis.get("primary_intent")
        if intent:
            action_map = {
                "chart": "chart_generation",
                "compare": "compare_generation",
                "clean": "data_cleaning",
                "analyze": "analysis",
            }
            action = action_map.get(intent)
            if action:
                self.context.current_state["last_action"] = action

        if execution_plan.get("tool_name"):
            self.context.workflow_history.append({
                "timestamp": datetime.now().isoformat(),
                "tool": execution_plan.get("tool_name"),
            })

    def update_state(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            self.context.current_state[key] = value
