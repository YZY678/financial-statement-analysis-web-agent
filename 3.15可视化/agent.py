"""
专业财经Agent核心调度器 - 适配tools v3.0版
修复：工具调用、模块导入、参数匹配问题
版本：3.2
"""
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# 导入大脑和工具模块
try:
    from brain import Brain
    from tools import (
        load_financial_data,
        clean_financial_data,
        create_professional_chart,
        detect_financial_report_type
    )

    MODULES_AVAILABLE = True
except ImportError as import_error:
    print(f"⚠️ 模块导入失败: {import_error}")
    MODULES_AVAILABLE = False

    # 定义占位符函数
    class Brain:
        def think(self, user_instruction: str, tools_description: List[Dict]) -> Dict[str, Any]:
            return {
                "need_tool": False,
                "reason": "大脑模块不可用",
                "confidence": 0.0
            }

    def load_financial_data(file_path: str) -> Tuple[Optional[pd.DataFrame], str]:
        return None, "工具模块不可用"

    def clean_financial_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        return df, {"error": "工具模块不可用"}

    def create_professional_chart(df: pd.DataFrame, chart_type: str, title: str = None,
                                  output_dir: str = "./charts") -> Tuple[Optional[str], str]:
        return None, "工具模块不可用"

    def detect_financial_report_type(df: pd.DataFrame) -> Dict[str, Any]:
        return {"type": "unknown", "type_name": "未知数据", "has_date_column": False}


class FinanceAgent:
    """专业财经Agent - 适配tools v3.0版"""

    def __init__(self, name: str = "财经数据可视化专家"):
        """初始化Agent"""
        self.name = name
        self.version = "3.2"

        # 检查模块可用性
        if not MODULES_AVAILABLE:
            print("⚠️ 警告: 部分模块导入失败，功能可能受限")

        # 初始化大脑
        if MODULES_AVAILABLE:
            self.brain = Brain()
        else:
            self.brain = None

        # ✅ 更新工具描述，与tools v3.0保持一致
        self.tools_description = [
            {
                "name": "load_financial_data",  # ✅ 修改为正确的工具名
                "description": "加载财经数据文件"
            },
            {
                "name": "clean_financial_data",
                "description": "清洗财经数据"
            },
            {
                "name": "detect_financial_report_type",  # ✅ 添加报表类型检测工具
                "description": "检测财经报表类型"
            },
            {
                "name": "create_professional_chart",
                "description": "生成专业财经图表"
            }
        ]

        # Agent状态
        self.state = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "data_loaded": False,
            "data_cleaned": False,
            "current_file": None,
            "current_data": None,
            "cleaned_data": None,
            "report_type": None,
            "report_type_name": None,
            "last_chart_path": None,
            "last_chart_type": None,
            "charts_generated": [],
            "workflow_history": [],
            "error_history": []
        }

        # 创建输出目录
        self._ensure_directories()

        print(f"✅ {self.name} v{self.version} 初始化完成")
        print(f"   会话ID: {self.state['session_id']}")

    @staticmethod
    def _ensure_directories():
        """确保必要的目录存在"""
        directories = ["./charts", "./data", "./reports"]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def process(self, user_input: str, **kwargs) -> Dict[str, Any]:
        """
        处理用户请求的主要入口
        """
        print(f"\n{'=' * 60}")
        print(f"📥 处理请求: {user_input}")

        start_time = time.time()

        try:
            # 1. 检查大脑可用性
            if not MODULES_AVAILABLE or self.brain is None:
                return {
                    "status": "error",
                    "response": "大脑模块不可用，无法进行智能决策",
                    "execution_time": "0.00s"
                }

            # 2. 大脑思考决策
            print("🤔 大脑思考中...")
            decision = self.brain.think(user_input, self.tools_description)

            # 3. 记录决策
            self._log_decision(decision)

            # 4. 不需要工具，直接返回
            if not decision.get("need_tool", False):
                elapsed = time.time() - start_time
                return {
                    "status": "success",
                    "response": decision.get("reason", "处理完成"),
                    "execution_time": f"{elapsed:.2f}s",
                    "confidence": decision.get("confidence", 0.5)
                }

            # 5. 执行工具
            tool_name = decision.get("tool_name", "")
            tool_params = decision.get("tool_params", {})

            # 更新参数（如果有kwargs传入）
            if kwargs:
                tool_params.update(kwargs)

            result = self._execute_tool(tool_name, tool_params)

            # 6. 添加建议
            if decision.get("suggestions"):
                if "suggestions" not in result:
                    result["suggestions"] = []
                result["suggestions"].extend(decision.get("suggestions", []))

            # 7. 记录执行时间
            elapsed = time.time() - start_time
            result["execution_time"] = f"{elapsed:.2f}s"

            # 8. 记录工作流
            self.state["workflow_history"].append({
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "params": tool_params,
                "result": result.get("status", "unknown")
            })

            return result

        except Exception as process_error:
            error_msg = f"Agent处理失败: {str(process_error)}"
            print(f"❌ {error_msg}")

            # 记录错误
            self.state["error_history"].append({
                "timestamp": datetime.now().isoformat(),
                "user_input": user_input,
                "error": str(process_error)
            })

            elapsed = time.time() - start_time
            return {
                "status": "error",
                "response": error_msg,
                "execution_time": f"{elapsed:.2f}s"
            }

    @staticmethod
    def _log_decision(decision: Dict[str, Any]):
        """记录大脑决策"""
        print(f"   决策: 需要工具={decision.get('need_tool')}")
        print(f"   工具: {decision.get('tool_name', '无')}")
        print(f"   置信度: {decision.get('confidence', 0.0):.2f}")

        intent = decision.get("intent_analysis", {})
        if intent:
            print(f"   意图: {intent.get('primary_intent', 'unknown')}")

    def _execute_tool(self, tool_name: str, tool_params: Dict) -> Dict[str, Any]:
        """
        执行工具函数
        """
        print(f"🔧 执行工具: {tool_name}")

        if not MODULES_AVAILABLE:
            return {
                "status": "error",
                "response": "工具模块不可用，无法执行操作"
            }

        # ✅ 更新工具名映射，与tools v3.0保持一致
        tool_mapping = {
            "load_financial_data": self._execute_load_data,  # ✅ 修改为正确的映射
            "clean_financial_data": self._execute_clean_data,
            "detect_financial_report_type": self._execute_detect_report_type,  # ✅ 添加报表类型检测
            "create_professional_chart": self._execute_generate_chart
        }

        # 检查工具名是否在映射中
        if tool_name in tool_mapping:
            return tool_mapping[tool_name](tool_params)
        else:
            return {
                "status": "error",
                "response": f"未知工具: {tool_name}"
            }

    def _execute_load_data(self, tool_params: Dict) -> Dict[str, Any]:
        """执行数据加载"""
        try:
            # 获取文件路径
            file_path = tool_params.get("file_path", "")

            if not file_path or file_path == "从上下文获取":
                if self.state["current_file"]:
                    file_path = self.state["current_file"]
                else:
                    return {
                        "status": "error",
                        "response": "未指定文件路径，请提供文件路径或上传文件"
                    }

            # 检查文件是否存在
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "response": f"文件不存在: {file_path}"
                }

            # 加载数据
            df, error = load_financial_data(file_path)

            if error or df is None:
                return {
                    "status": "error",
                    "response": f"文件加载失败: {error}"
                }

            # 确保DataFrame有效
            if hasattr(df, 'empty') and df.empty:
                return {
                    "status": "error",
                    "response": "文件内容为空，请检查数据"
                }

            # 检测报表类型
            report_info = detect_financial_report_type(df)

            # 更新状态
            self.state.update({
                "data_loaded": True,
                "current_file": file_path,
                "current_data": df,
                "report_type": report_info.get("type"),
                "report_type_name": report_info.get("type_name"),
                "has_date_column": report_info.get("has_date_column", False),
                "data_cleaned": False
            })

            # 同步到大脑
            if self.brain:
                self.brain.update_context("data_loaded", True, "current_state")
                self.brain.update_context("current_file", file_path, "current_state")
                self.brain.update_context("report_type", report_info.get("type"), "current_state")
                self.brain.update_context("report_type_name", report_info.get("type_name"), "current_state")

            # 文件名
            file_name = os.path.basename(file_path)

            return {
                "status": "success",
                "response": f"✅ 文件加载成功: {file_name}",
                "report_info": report_info
            }

        except Exception as load_error:
            return {
                "status": "error",
                "response": f"数据加载异常: {str(load_error)}"
            }

    def _execute_detect_report_type(self, tool_params: Dict) -> Dict[str, Any]:
        """执行报表类型检测"""
        try:
            # 检查DataFrame而不是布尔值
            if self.state["current_data"] is None or (
                    hasattr(self.state["current_data"], 'empty') and self.state["current_data"].empty):
                return {
                    "status": "error",
                    "response": "没有可用的原始数据，请先加载文件"
                }

            # 检测报表类型
            report_info = detect_financial_report_type(self.state["current_data"])

            # 更新状态
            self.state.update({
                "report_type": report_info.get("type"),
                "report_type_name": report_info.get("type_name"),
                "has_date_column": report_info.get("has_date_column", False)
            })

            # 同步到大脑
            if self.brain:
                self.brain.update_context("report_type", report_info.get("type"), "current_state")
                self.brain.update_context("report_type_name", report_info.get("type_name"), "current_state")

            return {
                "status": "success",
                "response": f"✅ 报表类型检测完成: {report_info.get('type_name')}",
                "report_info": report_info
            }

        except Exception as detect_error:
            return {
                "status": "error",
                "response": f"报表类型检测异常: {str(detect_error)}"
            }

    def _execute_clean_data(self, tool_params: Dict) -> Dict[str, Any]:
        """执行数据清洗"""
        try:
            # 检查DataFrame而不是布尔值
            if self.state["current_data"] is None or (
                    hasattr(self.state["current_data"], 'empty') and self.state["current_data"].empty):
                return {
                    "status": "error",
                    "response": "没有可用的原始数据，请先加载文件"
                }

            # 清洗数据
            cleaned_df, cleaning_report = clean_financial_data(self.state["current_data"])

            # 确保清洗后的DataFrame有效
            if cleaned_df is None or (hasattr(cleaned_df, 'empty') and cleaned_df.empty):
                return {
                    "status": "error",
                    "response": "数据清洗失败，结果为空"
                }

            # 更新状态
            self.state.update({
                "data_cleaned": True,
                "cleaned_data": cleaned_df
            })

            # 同步到大脑
            if self.brain:
                self.brain.update_context("data_cleaned", True, "current_state")

            # 构建响应消息
            response_parts = ["✅ 数据清洗完成"]
            if cleaning_report.get("actions_taken"):
                response_parts.append("执行的操作:")
                for action in cleaning_report["actions_taken"]:
                    response_parts.append(f"  • {action}")

            return {
                "status": "success",
                "response": "\n".join(response_parts),
                "cleaning_report": cleaning_report
            }

        except Exception as clean_error:
            return {
                "status": "error",
                "response": f"数据清洗异常: {str(clean_error)}"
            }

    def _execute_generate_chart(self, tool_params: Dict) -> Dict[str, Any]:
        """执行图表生成"""
        try:
            # 检查数据可用性
            if not self.state["data_loaded"] or self.state["current_data"] is None:
                return {
                    "status": "error",
                    "response": "没有可用的数据，请先加载文件"
                }

            # 如果数据未清洗，尝试自动清洗
            if not self.state["data_cleaned"] and self.state["current_data"] is not None:
                print("⚠️  数据未清洗，自动进行清洗...")
                cleaned_df, _ = clean_financial_data(self.state["current_data"])
                if cleaned_df is not None and not cleaned_df.empty:
                    self.state["data_cleaned"] = True
                    self.state["cleaned_data"] = cleaned_df
                    if self.brain:
                        self.brain.update_context("data_cleaned", True, "current_state")

            # 使用已清洗的数据
            data_to_use = None
            if self.state["data_cleaned"] and self.state["cleaned_data"] is not None:
                data_to_use = self.state["cleaned_data"]
            else:
                data_to_use = self.state["current_data"]

            if data_to_use is None or (hasattr(data_to_use, 'empty') and data_to_use.empty):
                return {
                    "status": "error",
                    "response": "没有可用的数据，无法生成图表"
                }

            # ✅ 获取图表类型，与brain传递的参数匹配
            chart_type = tool_params.get("chart_type", "income_trend")

            # 智能选择图表类型
            chart_types = self._determine_best_chart_types(data_to_use, tool_params)

            if not chart_types:
                return {
                    "status": "error",
                    "response": "无法根据数据特征确定合适的图表类型"
                }

            # 获取图表参数
            base_title = tool_params.get("title", "")
            output_dir = tool_params.get("output_dir", "./charts/")

            # 生成图表
            generated_charts = []
            errors = []

            for chart_type in chart_types:
                # 为每个图表生成有意义的标题
                chart_title = self._generate_chart_title(data_to_use, chart_type, base_title)

                # ✅ 调用tools v3.0的图表生成函数
                chart_path, error = create_professional_chart(
                    df=data_to_use,           # 参数1: df
                    chart_type=chart_type,    # 参数2: chart_type
                    title=chart_title,        # 参数3: title
                    output_dir=output_dir     # 参数4: output_dir
                )

                if error or not chart_path:
                    errors.append(f"{chart_type}: {error}")
                else:
                    generated_charts.append({
                        "path": chart_path,
                        "type": chart_type,
                        "title": chart_title
                    })

            # 更新状态
            if generated_charts:
                last_chart = generated_charts[-1]
                self.state["last_chart_path"] = last_chart["path"]
                self.state["last_chart_type"] = last_chart["type"]
                self.state["charts_generated"].extend(generated_charts)

                # 同步到大脑
                if self.brain:
                    self.brain.update_context("current_chart_type", last_chart["type"], "current_state")

            # 返回结果
            if not generated_charts:
                return {
                    "status": "error",
                    "response": f"图表生成失败: {'; '.join(errors)}"
                }

            # 构建响应消息
            chart_count = len(generated_charts)
            chart_list = "\n".join([f"  📈 {chart['type']}: {os.path.basename(chart['path'])}"
                                    for chart in generated_charts])

            response = f"✅ 成功生成 {chart_count} 个图表:\n{chart_list}"

            if errors:
                response += f"\n\n⚠️  部分图表生成失败:\n" + "\n".join([f"  ❌ {err}" for err in errors])

            return {
                "status": "success",
                "response": response,
                "chart_info": {
                    "charts": generated_charts,
                    "total_generated": chart_count,
                    "errors": errors
                }
            }

        except Exception as chart_error:
            return {
                "status": "error",
                "response": f"图表生成异常: {str(chart_error)}"
            }

    @staticmethod
    def _determine_best_chart_types(df: pd.DataFrame, tool_params: Dict) -> List[str]:
        """
        智能确定最佳图表类型
        基于数据特征自动选择最合适的图表类型
        """
        chart_types = []
        columns_lower = [str(col).lower() for col in df.columns]

        # 🆕 检测是否为完整利润表数据
        has_income = any('营收' in c or 'revenue' in c or 'sales' in c for c in columns_lower)
        has_cost = any('成本' in c or 'cost' in c for c in columns_lower)
        has_expense = any('费用' in c or 'expense' in c for c in columns_lower)
        has_profit = any('利润' in c or 'profit' in c for c in columns_lower)

        # 如果同时包含收入、成本和至少利润或费用中的一项，则非常适合趋势分析
        if has_income and has_cost and (has_expense or has_profit):
            print(f"📊 检测到利润表相关数据，优先使用趋势图展示关系")
            chart_types.append("income_trend")  # 趋势图更能展示派生关系
            # 也可以考虑添加 revenue_comparison 进行对比
            if len(df) == 1:  # 如果只有一期数据，用对比图
                chart_types.append("revenue_comparison")

        # 获取数值列
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not numeric_cols:
            return ["income_trend"]  # 默认类型

        # 检查是否有明确的图表类型请求
        requested_type = tool_params.get("chart_type")
        if requested_type and requested_type != "income_trend":  # income_trend是默认值
            return [requested_type]

        # 分析数据特征
        num_rows = len(df)
        num_numeric_cols = len(numeric_cols)

        # 自动选择图表类型
        # 规则1: 如果有时间序列特征，优先趋势图
        date_cols = [col for col in df.columns
                     if '日期' in str(col) or 'date' in str(col).lower() or 'time' in str(col).lower()]

        if date_cols and num_rows > 3:
            chart_types.append("income_trend")

        # 规则2: 如果有多个数值列，可以生成对比图
        if num_numeric_cols >= 2:
            chart_types.append("revenue_comparison")

        # 规则3: 如果有明显的分类数据，可以生成构成图
        if num_numeric_cols >= 3 and num_rows == 1:
            chart_types.append("profit_composition")

        # 规则4: 如果数据看起来像资产负债表
        asset_keywords = ['资产', '负债', '权益', 'asset', 'liability', 'equity']
        has_balance_items = any(any(keyword in str(col).lower() for keyword in asset_keywords)
                                for col in df.columns)

        if has_balance_items and num_numeric_cols >= 2:
            chart_types.append("balance_sheet")

        # 规则5: 如果数据看起来像费用数据
        expense_keywords = ['费用', '成本', 'expense', 'cost']
        has_expense_items = any(any(keyword in str(col).lower() for keyword in expense_keywords)
                                for col in df.columns)

        if has_expense_items and num_numeric_cols >= 2:
            chart_types.append("expense_breakdown")

        # 去重并确保至少有一种图表类型
        chart_types = list(dict.fromkeys(chart_types))  # 去重保持顺序

        if not chart_types:
            # 默认图表类型
            if num_numeric_cols >= 3:
                chart_types = ["income_trend", "revenue_comparison"]
            elif num_numeric_cols == 2:
                chart_types = ["revenue_comparison"]
            else:
                chart_types = ["income_trend"]

        # 限制至少生成一种图表
        if not chart_types:
            chart_types = ["income_trend"]

        return chart_types

    @staticmethod
    def _generate_chart_title(df: pd.DataFrame, chart_type: str, base_title: str) -> str:
        """
        为图表生成有意义的标题 - 使用智能标题工具
        """
        # ✅ 使用tools v3.0的TitleGenerator
        try:
            from tools import TitleGenerator

            # 创建标题生成器
            title_generator = TitleGenerator()

            # 使用智能标题工具
            title = title_generator.generate_title(df, chart_type)

            # 确保标题不为空
            if not title or title.isspace():
                # 降级方案
                chart_names = {
                    "income_trend": "趋势分析图",
                    "profit_composition": "构成分析图",
                    "balance_sheet": "资产负债分析图",
                    "revenue_comparison": "对比分析图",
                    "expense_breakdown": "费用分析图"
                }
                title = chart_names.get(chart_type, "数据分析图")

            return title

        except Exception as e:
            # 如果智能标题生成失败，使用简单标题
            print(f"⚠️ 智能标题生成失败，使用简单标题: {e}")
            chart_names = {
                "income_trend": "趋势分析图",
                "profit_composition": "构成分析图",
                "balance_sheet": "资产负债分析图",
                "revenue_comparison": "对比分析图",
                "expense_breakdown": "费用分析图"
            }
            return chart_names.get(chart_type, "数据分析图")

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "status": "success",
            "agent_info": {
                "name": self.name,
                "version": self.version,
                "session_id": self.state["session_id"]
            },
            "data_status": {
                "data_loaded": self.state["data_loaded"],
                "data_cleaned": self.state["data_cleaned"],
                "current_file": self.state["current_file"],
                "report_type": self.state["report_type_name"]
            },
            "chart_status": {
                "charts_generated": len(self.state["charts_generated"]),
                "last_chart_type": self.state["last_chart_type"]
            },
            "system_status": {
                "modules_available": MODULES_AVAILABLE,
                "error_count": len(self.state["error_history"])
            }
        }

    def reset(self, reset_type: str = "soft") -> Dict[str, Any]:
        """
        重置Agent状态
        reset_type: soft(软重置) / hard(硬重置)
        """
        try:
            if reset_type == "hard":
                # 硬重置：清空所有状态
                self.state = {
                    "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "data_loaded": False,
                    "data_cleaned": False,
                    "current_file": None,
                    "current_data": None,
                    "cleaned_data": None,
                    "report_type": None,
                    "report_type_name": None,
                    "last_chart_path": None,
                    "last_chart_type": None,
                    "charts_generated": [],
                    "workflow_history": [],
                    "error_history": []
                }

                if self.brain:
                    self.brain.reset()

                return {
                    "status": "success",
                    "response": "✅ Agent已完全重置"
                }
            else:
                # 软重置：只重置数据状态
                self.state.update({
                    "data_loaded": False,
                    "data_cleaned": False,
                    "current_file": None,
                    "current_data": None,
                    "cleaned_data": None,
                    "report_type": None,
                    "report_type_name": None
                })

                if self.brain:
                    self.brain.update_context("data_loaded", False, "current_state")
                    self.brain.update_context("data_cleaned", False, "current_state")
                    self.brain.update_context("current_file", None, "current_state")
                    self.brain.update_context("report_type", None, "current_state")
                    self.brain.update_context("report_type_name", None, "current_state")

                return {
                    "status": "success",
                    "response": "✅ Agent数据状态已重置"
                }

        except Exception as reset_error:
            return {
                "status": "error",
                "response": f"重置失败: {str(reset_error)}"
            }

    def export_session_report(self) -> Dict[str, Any]:
        """导出会话报告"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir = "./reports"
            os.makedirs(report_dir, exist_ok=True)

            report_path = os.path.join(report_dir, f"agent_report_{timestamp}.txt")

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(f"财经Agent会话报告\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"=" * 50 + "\n\n")

                f.write("1. Agent信息:\n")
                f.write(f"   名称: {self.name}\n")
                f.write(f"   版本: {self.version}\n")
                f.write(f"   会话ID: {self.state['session_id']}\n\n")

                f.write("2. 数据状态:\n")
                f.write(f"   数据已加载: {self.state['data_loaded']}\n")
                f.write(f"   数据已清洗: {self.state['data_cleaned']}\n")
                f.write(f"   当前文件: {self.state['current_file'] or '无'}\n")
                f.write(f"   报表类型: {self.state['report_type_name'] or '未知'}\n\n")

                f.write("3. 图表生成记录:\n")
                f.write(f"   已生成图表数: {len(self.state['charts_generated'])}\n")
                for i, chart in enumerate(self.state['charts_generated'][-5:], 1):
                    f.write(f"   {i}. {chart.get('type', '未知')}: {chart.get('path', '未知路径')}\n")
                f.write("\n")

                f.write("4. 工作流历史:\n")
                for i, workflow in enumerate(self.state['workflow_history'][-10:], 1):
                    f.write(f"   {i}. {workflow.get('tool', '未知')} - {workflow.get('result', '未知结果')}\n")
                f.write("\n")

                if self.state['error_history']:
                    f.write("5. 错误记录:\n")
                    for i, error in enumerate(self.state['error_history'][-5:], 1):
                        f.write(f"   {i}. {error.get('user_input', '未知输入')}: {error.get('error', '未知错误')}\n")

            return {
                "status": "success",
                "response": f"会话报告已导出: {report_path}"
            }

        except Exception as e:
            return {
                "status": "error",
                "response": f"导出失败: {str(e)}"
            }


def test_agent() -> None:
    """测试Agent功能"""
    print("=" * 60)
    print("测试适配版财经Agent v3.2")
    print("=" * 60)

    try:
        # 创建Agent
        agent = FinanceAgent("测试财经Agent")

        print("1. 测试Agent初始化...")
        print(f"   Agent名称: {agent.name}")
        print(f"   Agent版本: {agent.version}")

        print("\n2. 测试状态查询...")
        status = agent.get_status()
        print(f"   会话ID: {status['agent_info']['session_id']}")
        print(f"   数据状态: 已加载={status['data_status']['data_loaded']}, "
              f"已清洗={status['data_status']['data_cleaned']}")

        print("\n3. 测试处理功能...")

        # 测试文件加载
        test_file = "sample_data.csv"
        if os.path.exists(test_file):
            result = agent.process(f"加载文件: {test_file}")
            print(f"   文件加载结果: {result.get('status')}")
            if result.get('status') == 'success':
                print(f"   响应: {result.get('response')[:50]}...")
        else:
            print(f"   ⚠️ 测试文件 {test_file} 不存在，跳过加载测试")

        print("\n4. 测试重置功能...")
        reset_result = agent.reset("soft")
        print(f"   重置结果: {reset_result.get('status')}")

        print("\n5. 测试导出功能...")
        export_result = agent.export_session_report()
        print(f"   导出结果: {export_result.get('status')}")
        if export_result.get('status') == 'success':
            print(f"   响应: {export_result.get('response')}")

        print("\n" + "=" * 60)
        print("Agent测试完成!")
        print("=" * 60)

    except Exception as test_error:
        print(f"\n❌ 测试过程中出错: {str(test_error)}")


if __name__ == "__main__":
    """直接运行此文件进行测试"""
    print("适配版财经Agent v3.2")
    print("-" * 40)

    # 运行测试
    test_agent()