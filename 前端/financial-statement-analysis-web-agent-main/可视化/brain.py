"""
专业财经大脑模块 - 修复版
修复静态方法定义错误
"""
import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

# 尝试导入角色设定
try:
    from role import FINANCE_ANALYST_ROLE, get_role_introduction, check_capability
    HAS_ROLE_MODULE = True
except ImportError:
    HAS_ROLE_MODULE = False
    # 默认角色设定
    FINANCE_ANALYST_ROLE = {
        "name": "财经数据可视化专家",
        "capabilities": ["财经数据分析", "图表生成", "财务指标计算"],
        "limitations": ["不提供投资建议", "不处理隐私数据"]
    }

    def get_role_introduction() -> str:
        """获取角色介绍"""
        return "我是财经数据可视化助手，可以帮您处理财经数据和生成专业图表。"

    def check_capability(user_request: str) -> Tuple[bool, str]:
        """检查能力范围"""
        return True, "请求在能力范围内"


class Brain:
    """专业财经大脑 - 智能决策核心"""

    def __init__(self):
        """初始化大脑系统"""
        # 角色身份
        self.role = FINANCE_ANALYST_ROLE

        # 设置日志
        self._setup_logging()
        self.logger = logging.getLogger(__name__)

        # 对话上下文
        self.context = {
            'conversation_history': [],
            'current_state': {
                'data_loaded': False,
                'data_cleaned': False,
                'current_file': None,
                'current_chart_type': None,
                'last_action': None,
                'report_type': None
            },
            'user_preferences': {},
            'workflow_history': []
        }

        # 意图关键词库
        self._setup_intent_keywords()

        # 工具知识库
        self._setup_tool_knowledge()

        self.logger.info("财经大脑初始化完成")

    def _setup_logging(self) -> None:
        """设置日志系统"""
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

    def _setup_intent_keywords(self) -> None:
        """设置意图识别关键词"""
        self.intent_patterns = {
            'greeting': [r'你好', r'您好', r'hello', r'hi', r'在吗'],
            'farewell': [r'再见', r'拜拜', r'退出', r'结束'],
            'help': [r'帮助', r'怎么用', r'功能', r'能做什么'],
            'upload': [r'上传', r'选择文件', r'打开文件', r'加载文件'],
            'parse': [r'解析', r'读取', r'打开', r'加载', r'导入', r'分析.*文件'],
            'clean': [r'清洗', r'清理', r'预处理', r'整理数据'],
            'chart': [r'图表', r'可视化', r'图形', r'画图', r'展示', r'绘图'],
            'trend': [r'趋势', r'变化', r'增长', r'下降', r'走势', r'折线图'],
            'compare': [r'对比', r'比较', r'柱状图', r'条形图', r'对比图'],
            'composition': [r'构成', r'占比', r'比例', r'饼图', r'环形图'],
            'distribution': [r'分布', r'散点图'],
            'analyze': [r'分析', r'统计', r'计算', r'指标', r'比率', r'评估'],
            'income': [r'利润表', r'收入', r'营收', r'利润', r'净利'],
            'balance': [r'资产负债表', r'资产', r'负债', r'权益'],
            'cashflow': [r'现金流量表', r'现金流', r'现金'],
            'health': [r'财务健康', r'财务状况', r'财务指标'],
            'save': [r'保存', r'导出', r'下载', r'存储'],
            'reset': [r'重置', r'清空', r'重新开始'],
            'status': [r'状态', r'进度', r'当前', r'现在']
        }

    def _setup_tool_knowledge(self) -> None:
        """设置工具知识库"""
        self.tool_knowledge = {
            'parse_finance_file': {
                'description': '解析财经数据文件',
                'inputs': ['file_path'],
                'outputs': ['dataframe', 'error_message'],
                'prerequisites': ['file_exists']
            },
            'clean_financial_data': {
                'description': '清洗财经数据',
                'inputs': ['dataframe'],
                'outputs': ['cleaned_dataframe', 'cleaning_report'],
                'prerequisites': ['data_loaded']
            },
            'create_professional_chart': {
                'description': '生成专业财经图表',
                'inputs': ['dataframe', 'chart_type', 'title', 'output_dir'],
                'outputs': ['chart_path', 'error_message'],
                'prerequisites': ['data_available']
            },
            'analyze_financial_health': {
                'description': '分析财务健康状况',
                'inputs': ['dataframe', 'report_type'],
                'outputs': ['analysis_report'],
                'prerequisites': ['data_cleaned']
            }
        }

    def think(self, user_instruction: str, tools_description: List[Dict]) -> Dict[str, Any]:
        """
        核心思考函数 - 分析用户指令并制定决策
        返回: 决策字典
        """
        try:
            # 记录对话历史
            self._record_conversation('user', user_instruction)

            # 检查能力范围
            capability_ok, capability_msg = check_capability(user_instruction)
            if not capability_ok:
                return self._build_response(
                    need_tool=False,
                    reason=capability_msg,
                    confidence=0.9
                )

            # 深度意图分析
            intent_analysis = self._analyze_intent_deeply(user_instruction)

            # 结合上下文优化意图
            intent_analysis = self._apply_context_to_intent(intent_analysis)

            # 制定工具执行计划
            execution_plan = self._plan_execution(intent_analysis, tools_description)

            # 生成专业回复
            response = self._generate_professional_response(intent_analysis, execution_plan)

            # 记录思考过程
            self._record_thought_process(intent_analysis, execution_plan)

            # 返回决策
            return self._build_decision(execution_plan, response, intent_analysis)

        except Exception as e:
            error_msg = f"思考过程出错: {str(e)}"
            self.logger.error(error_msg)
            return self._build_error_response(error_msg)

    def _analyze_intent_deeply(self, user_input: str) -> Dict[str, Any]:
        """深度意图分析"""
        input_lower = user_input.lower()

        # 检测所有可能的意图
        detected_intents = []
        for intent_type, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, input_lower):
                    detected_intents.append(intent_type)
                    break

        # 确定主要意图
        primary_intent = self._determine_primary_intent(detected_intents, user_input)

        # 提取实体信息
        entities = self._extract_entities(user_input, primary_intent)

        # 分析情感
        sentiment = self._analyze_sentiment(user_input)

        # 评估复杂度
        complexity = self._assess_complexity(user_input, detected_intents)

        # 计算置信度
        confidence = self._calculate_confidence(detected_intents, user_input)

        return {
            'primary_intent': primary_intent,
            'secondary_intents': list(set(detected_intents) - {primary_intent}),
            'confidence': confidence,
            'entities': entities,
            'sentiment': sentiment,
            'complexity': complexity,
            'raw_input': user_input
        }

    @staticmethod
    def _determine_primary_intent(intents: List[str], user_input: str) -> str:
        """确定主要意图"""
        if not intents:
            return 'unknown'

        priority_order = [
            'chart', 'trend', 'compare', 'composition', 'distribution',
            'analyze', 'income', 'balance', 'cashflow', 'health',
            'parse', 'clean', 'upload',
            'save', 'reset', 'status',
            'help', 'greeting', 'farewell'
        ]

        for intent in priority_order:
            if intent in intents:
                return intent

        return intents[0]

    def _extract_entities(self, user_input: str, primary_intent: str) -> Dict[str, Any]:
        """从用户输入中提取关键信息"""
        entities = {}

        # 改进的文件路径提取模式
        patterns = [
            r'加载文件[:：]\s*([^\s]+)',  # 加载文件: 路径
            r'解析文件[:：]\s*([^\s]+)',  # 解析文件: 路径
            r'文件[:：]\s*([^\s]+)',  # 文件: 路径
            r'([a-zA-Z]:[\\/][^\\/:\s]+\.[a-zA-Z]{3,4})',  # 绝对文件路径
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                file_path = match.group(1)
                entities['file_path'] = file_path
                break

        # 提取图表类型
        input_lower = user_input.lower()
        chart_mapping = {
            '趋势': 'income_trend',
            '折线': 'income_trend',
            '对比': 'revenue_comparison',
            '柱状': 'revenue_comparison',
            '构成': 'profit_composition',
            '占比': 'profit_composition',
            '饼': 'profit_composition',
            '资产': 'balance_sheet',
            '负债': 'balance_sheet',
            '费用': 'expense_breakdown',
            '成本': 'expense_breakdown',
            '散点': 'distribution'
        }

        for keyword, chart_type in chart_mapping.items():
            if keyword in input_lower:
                entities['chart_type'] = chart_type
                break

        # 提取时间范围
        time_patterns = {
            r'202[0-9]': 'specific_year',
            r'去年': 'last_year',
            r'今年': 'this_year',
            r'季度': 'quarterly',
            r'月度': 'monthly',
            r'年度': 'yearly'
        }

        for pattern, time_type in time_patterns.items():
            if re.search(pattern, input_lower):
                entities['time_period'] = time_type
                break

        # 提取报表类型
        if '利润' in input_lower or '收入' in input_lower:
            entities['report_type'] = 'income_statement'
        elif '资产' in input_lower or '负债' in input_lower:
            entities['report_type'] = 'balance_sheet'
        elif '现金流' in input_lower or '现金' in input_lower:
            entities['report_type'] = 'cash_flow'

        return entities

    @staticmethod
    def _analyze_sentiment(user_input: str) -> str:
        """分析用户情感"""
        positive_words = ['谢谢', '很好', '优秀', '厉害', '不错', '棒']
        negative_words = ['错误', '失败', '不对', '不好', '问题', '糟糕']
        urgent_words = ['尽快', '马上', '立即', '紧急', '快点']

        input_lower = user_input.lower()

        for word in urgent_words:
            if word in input_lower:
                return 'urgent'

        pos_count = sum(1 for word in positive_words if word in input_lower)
        neg_count = sum(1 for word in negative_words if word in input_lower)

        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        else:
            return 'neutral'

    @staticmethod
    def _assess_complexity(user_input: str, intents: List[str]) -> str:
        """评估请求复杂度"""
        # 长文本通常更复杂
        if len(user_input) > 100:
            return 'high'

        # 包含多个意图
        if len(intents) > 2:
            return 'high'

        # 包含特殊要求
        complex_keywords = ['同时', '并且', '还要', '另外', '除了']
        for keyword in complex_keywords:
            if keyword in user_input:
                return 'medium'

        return 'simple'

    def _calculate_confidence(self, detected_intents: List[str], user_input: str) -> float:
        """计算意图识别置信度"""
        if not detected_intents:
            return 0.3

        # 基础置信度
        confidence = min(0.3 + len(detected_intents) * 0.2, 0.8)

        # 输入明确性加分
        if len(user_input) > 20:
            confidence += 0.1

        # 包含具体关键词加分
        specific_terms = ['文件', '图表', '分析', '数据', '利润', '资产', '负债', '收入', '成本']
        for term in specific_terms:
            if term in user_input:
                confidence += 0.05

        # 上下文关联加分
        if '再' in user_input or '重新' in user_input or '还' in user_input or '也' in user_input:
            if self.context['current_state'].get('last_action'):
                confidence += 0.2
            if self.context['current_state'].get('current_chart_type'):
                confidence += 0.1

        # 包含文件路径加分
        file_patterns = [
            r'[a-zA-Z]:[\\/][^\\/:\s]+\.(csv|xlsx|xls)',
            r'/[^/\s]+/[^/\s]+\.(csv|xlsx|xls)',
            r'\.(csv|xlsx|xls)'
        ]

        for pattern in file_patterns:
            if re.search(pattern, user_input):
                confidence += 0.1
                break

        return min(round(confidence, 2), 0.95)

    def _apply_context_to_intent(self, intent_analysis: Dict) -> Dict:
        """结合上下文优化意图理解"""
        input_text = intent_analysis['raw_input']

        # 处理"再"、"重新"等上下文相关词
        if '再' in input_text or '重新' in input_text or '还' in input_text or '也' in input_text:
            last_action = self.context['current_state'].get('last_action')
            last_chart = self.context['current_state'].get('current_chart_type')

            if last_action == 'chart_generation' and last_chart:
                intent_analysis['primary_intent'] = 'chart'
                intent_analysis['entities']['chart_type'] = last_chart
                intent_analysis['confidence'] = 0.85
                intent_analysis['context_note'] = f"根据上下文，重新生成{last_chart}图表"

            intent_analysis['inferred_from_context'] = True

        # 处理"这个"、"当前"等指代
        if '这个' in input_text or '当前' in input_text or '刚刚' in input_text:
            current_file = self.context['current_state'].get('current_file')
            if current_file and current_file != '从上下文获取':
                if 'file_path' not in intent_analysis['entities']:
                    intent_analysis['entities']['file_path'] = current_file

        return intent_analysis

    def _plan_execution(self, intent_analysis: Dict, tools_description: List[Dict]) -> Dict[str, Any]:
        """制定执行计划"""
        primary_intent = intent_analysis['primary_intent']
        entities = intent_analysis['entities']

        # 默认计划
        plan = {
            'need_tool': False,
            'tool_name': None,
            'tool_params': {},
            'workflow': [],
            'estimated_time': 'short',
            'prerequisites_check': True
        }

        # 问候和帮助
        if primary_intent in ['greeting', 'farewell', 'help']:
            return plan

        # 文件操作
        if primary_intent == 'upload':
            plan.update({
                'need_tool': True,
                'tool_name': 'upload_file',
                'workflow': ['upload_file']
            })

        elif primary_intent == 'parse':
            file_path = entities.get('file_path', '从上下文获取')
            plan.update({
                'need_tool': True,
                'tool_name': 'parse_finance_file',
                'tool_params': {'file_path': file_path},
                'workflow': ['parse_finance_file']
            })

        elif primary_intent == 'clean':
            plan.update({
                'need_tool': True,
                'tool_name': 'clean_financial_data',
                'tool_params': {'raw_data': '从上下文获取'},
                'workflow': ['clean_financial_data']
            })

        # 图表生成
        elif primary_intent in ['chart', 'trend', 'compare', 'composition', 'distribution']:
            chart_type = entities.get('chart_type', 'income_trend')
            title = self._generate_chart_title(intent_analysis)

            # 构建完整工作流
            workflow = self._build_chart_workflow()

            plan.update({
                'need_tool': True,
                'tool_name': 'create_professional_chart',
                'tool_params': {
                    'chart_type': chart_type,
                    'title': title,
                    'output_dir': './charts/'
                },
                'workflow': workflow,
                'estimated_time': 'medium'
            })

        # 财务分析
        elif primary_intent in ['analyze', 'income', 'balance', 'cashflow', 'health']:
            report_type = entities.get('report_type', 'general')

            plan.update({
                'need_tool': True,
                'tool_name': 'analyze_financial_health',
                'tool_params': {
                    'df': '从上下文获取',
                    'report_type': report_type
                },
                'workflow': self._build_analysis_workflow(),
                'estimated_time': 'short'
            })

        # 状态查询
        elif primary_intent == 'status':
            plan['need_tool'] = False

        # 检查前提条件
        if plan['need_tool']:
            plan['prerequisites_check'] = self._check_prerequisites(plan['workflow'])

        return plan

    def _build_chart_workflow(self) -> List[str]:
        """构建图表生成工作流"""
        workflow = []
        state = self.context['current_state']

        # 检查数据是否已加载
        if not state.get('data_loaded'):
            workflow.append('parse_finance_file')

        # 检查数据是否已清洗
        if not state.get('data_cleaned'):
            workflow.append('clean_financial_data')

        # 生成图表
        workflow.append('create_professional_chart')

        return workflow

    def _build_analysis_workflow(self) -> List[str]:
        """构建财务分析工作流"""
        workflow = []
        state = self.context['current_state']

        if not state.get('data_loaded'):
            workflow.append('parse_finance_file')

        if not state.get('data_cleaned'):
            workflow.append('clean_financial_data')

        workflow.append('analyze_financial_health')

        return workflow

    def _check_prerequisites(self, workflow: List[str]) -> bool:
        """检查工作流前提条件"""
        state = self.context['current_state']

        for step in workflow:
            if step == 'parse_finance_file':
                if not state.get('current_file'):
                    return False
            elif step == 'clean_financial_data':
                if not state.get('data_loaded'):
                    return False
            elif step == 'create_professional_chart':
                if not state.get('data_cleaned') and not state.get('data_loaded'):
                    return False

        return True

    @staticmethod
    def _generate_chart_title(intent_analysis: Dict) -> str:
        """生成图表标题"""
        input_text = intent_analysis['raw_input']

        # 尝试从用户输入提取有意义的标题
        title_keywords = ['图表', '分析', '趋势', '对比', '构成', '分布']

        for keyword in title_keywords:
            if keyword in input_text:
                start = max(0, input_text.find(keyword) - 20)
                end = min(len(input_text), start + 40)
                candidate = input_text[start:end].strip()

                if len(candidate) > 10:
                    # 清理标题
                    candidate = re.sub(r'[<>:"/\\|?*]', '', candidate)
                    return f"{candidate}分析图表"

        # 使用实体信息生成标题
        if 'chart_type' in intent_analysis.get('entities', {}):
            chart_names = {
                'income_trend': '收入趋势分析图表',
                'profit_composition': '利润构成分析图表',
                'balance_sheet': '资产负债表分析图表',
                'revenue_comparison': '收入对比分析图表',
                'expense_breakdown': '费用构成分析图表'
            }
            chart_type = intent_analysis['entities']['chart_type']
            return chart_names.get(chart_type, '财经数据分析图表')

        return "财经数据分析图表"

    def _generate_professional_response(self, intent_analysis: Dict, execution_plan: Dict) -> str:
        """生成专业财经回复"""
        intent = intent_analysis['primary_intent']

        # 基础回复模板
        templates = {
            'greeting': "您好！我是专业财经数据可视化助手。我可以帮您处理财经数据、生成专业图表、分析财务指标。请告诉我您的需求。",
            'farewell': "感谢使用财经数据可视化助手，再见！",
            'help': f"{get_role_introduction()}\n\n我可以帮您：\n1. 解析财经数据文件\n2. 清洗和预处理数据\n3. 生成专业可视化图表\n4. 分析财务健康指标",
            'upload': "请通过界面选择财经数据文件（支持CSV/Excel格式）。",
            'parse': "正在解析财经数据文件，请稍候...",
            'clean': "正在清洗和预处理财经数据，确保分析准确性...",
            'chart': f"正在生成专业财经图表（{execution_plan.get('tool_params', {}).get('chart_type', '趋势图')}）...",
            'trend': "正在分析数据趋势，生成趋势图表...",
            'compare': "正在准备数据对比分析，生成对比图表...",
            'composition': "正在分析数据构成，生成占比图表...",
            'analyze': "正在分析财务健康指标，计算关键比率...",
            'income': "正在分析利润表数据，计算收入、利润等关键指标...",
            'balance': "正在分析资产负债表，评估资产、负债结构...",
            'cashflow': "正在分析现金流量表，评估现金状况...",
            'health': "正在评估财务健康状况，生成分析报告...",
            'status': self._generate_status_report(),
            'unknown': "我理解您的需求是数据分析。您可以：\n1.上传财经数据文件\n2.要求生成特定图表\n3.进行财务指标分析"
        }

        response = templates.get(intent, templates['unknown'])

        # 添加上下文信息
        if 'context_note' in intent_analysis:
            response = f"{intent_analysis['context_note']}\n{response}"

        return response

    def _generate_status_report(self) -> str:
        """生成状态报告"""
        state = self.context['current_state']
        report_lines = ["📊 当前系统状态:"]

        # 文件信息
        if state.get('current_file') and state['current_file'] != '从上下文获取':
            try:
                file_name = os.path.basename(str(state['current_file']))
                report_lines.append(f"  📁 当前文件: {file_name}")
            except (TypeError, AttributeError):
                report_lines.append("  📁 当前文件: 未知文件")
        else:
            report_lines.append("  📁 当前文件: 无")

        # 数据状态
        data_status = []
        if state.get('data_loaded'):
            data_status.append("✅ 已加载")
        else:
            data_status.append("❌ 未加载")

        if state.get('data_cleaned'):
            data_status.append("✅ 已清洗")
        else:
            data_status.append("❌ 未清洗")

        report_lines.append(f"  📄 数据状态: {' | '.join(data_status)}")

        # 报表类型
        if state.get('report_type'):
            report_type_names = {
                'income_statement': '利润表',
                'balance_sheet': '资产负债表',
                'cash_flow': '现金流量表',
                'general': '通用财经数据',
                'unknown': '未知类型'
            }
            report_name = report_type_names.get(state['report_type'], state['report_type'])
            report_lines.append(f"  📋 报表类型: {report_name}")

        # 图表历史
        if state.get('current_chart_type'):
            chart_names = {
                'income_trend': '收入趋势图',
                'profit_composition': '利润构成图',
                'balance_sheet': '资产负债表图表',
                'revenue_comparison': '收入对比图',
                'expense_breakdown': '费用分解图',
                'distribution': '数据分布图'
            }
            chart_name = chart_names.get(state['current_chart_type'], state['current_chart_type'])
            report_lines.append(f"  📈 上次图表类型: {chart_name}")

        # 操作历史
        if self.context['workflow_history']:
            recent = self.context['workflow_history'][-3:]
            action_names = {
                'parse_finance_file': '解析文件',
                'clean_financial_data': '清洗数据',
                'create_professional_chart': '生成图表',
                'analyze_financial_health': '财务分析',
                'upload_file': '上传文件',
                'detect_report_type': '识别报表类型'
            }
            recent_names = []
            for action in recent:
                action_name = action_names.get(action, action)
                recent_names.append(action_name)

            if recent_names:
                report_lines.append(f"  📝 最近操作: {' → '.join(recent_names)}")

        return "\n".join(report_lines)

    def _generate_suggestions(self, intent_analysis: Dict) -> List[str]:
        """生成后续建议"""
        suggestions = []
        intent = intent_analysis['primary_intent']
        state = self.context['current_state']

        # 状态查询意图
        if intent == 'status':
            if not state.get('data_loaded'):
                suggestions.append("📁 当前状态：未加载数据，请先上传或解析文件")
            else:
                # 获取文件名
                current_file = state.get('current_file', '未知文件')
                if current_file and current_file != '从上下文获取':
                    try:
                        file_name = os.path.basename(str(current_file))
                        suggestions.append(f"📁 当前文件：{file_name}")
                    except (TypeError, AttributeError):
                        suggestions.append("📁 当前文件：未知文件")
                else:
                    suggestions.append("📁 当前文件：无")

                # 数据状态
                if state.get('data_loaded'):
                    suggestions.append("✅ 数据已加载")
                if state.get('data_cleaned'):
                    suggestions.append("🧹 数据已清洗")

                # 下一步建议
                if state.get('data_loaded') and not state.get('data_cleaned'):
                    suggestions.append("💡 下一步建议：进行数据清洗以提高分析质量")
                elif state.get('data_cleaned'):
                    suggestions.append("💡 下一步建议：生成图表或进行财务分析")

            return suggestions[:3]

        # 工具类意图的建议
        if intent in ['parse', 'upload'] and state.get('data_loaded'):
            suggestions.extend([
                "💡 数据已加载，建议：清洗数据以提高分析质量",
                "📈 建议：生成趋势图查看数据变化",
                "📊 建议：创建对比图分析不同项目"
            ])

        elif intent in ['clean'] and state.get('data_cleaned'):
            suggestions.extend([
                "📈 建议：生成收入趋势图分析变化",
                "🥧 建议：创建利润构成图查看结构",
                "⚖️ 建议：分析资产负债率评估风险"
            ])

        elif intent in ['chart', 'trend', 'compare', 'composition']:
            # 检查数据状态
            if not state.get('data_loaded'):
                suggestions.append("📁 请先上传或解析财经数据文件")
            elif not state.get('data_cleaned'):
                suggestions.append("🧹 建议先清洗数据以获得更准确的可视化结果")
            else:
                # 根据意图类型建议
                alt_suggestions = {
                    'trend': ["🔁 也可以：对比不同项目", "🥧 或者：查看构成比例"],
                    'compare': ["📈 或者：分析时间趋势", "🥧 或者：查看详细构成"],
                    'composition': ["📈 或者：对比不同时期", "🔁 或者：分析变化趋势"]
                }

                for intent_key, alt_list in alt_suggestions.items():
                    if intent_key in intent_analysis.get('secondary_intents', []):
                        suggestions.extend(alt_list[:2])
                        break

        # 通用建议
        if not suggestions:
            if not state.get('data_loaded'):
                suggestions.append("📁 首先：上传或解析财经数据文件")
            elif not state.get('data_cleaned'):
                suggestions.append("🧹 然后：清洗数据确保分析准确性")
            else:
                suggestions.append("📈 现在可以：生成图表或进行分析")

        return suggestions[:3]

    def _build_decision(self, execution_plan: Dict, response: str, intent_analysis: Dict) -> Dict[str, Any]:
        """构建决策结果"""
        decision = {
            'need_tool': execution_plan.get('need_tool', False),
            'tool_name': execution_plan.get('tool_name', ''),
            'tool_params': execution_plan.get('tool_params', {}),
            'reason': response,
            'confidence': intent_analysis.get('confidence', 0.5),
            'intent_analysis': intent_analysis,
            'execution_plan': execution_plan,
            'suggestions': self._generate_suggestions(intent_analysis)
        }

        # 记录决策
        self._record_conversation('assistant', response)

        return decision

    @staticmethod
    def _build_error_response(error_msg: str) -> Dict[str, Any]:
        """构建错误响应"""
        return {
            'need_tool': False,
            'tool_name': '',
            'tool_params': {},
            'reason': f"系统思考过程出现错误: {error_msg}",
            'confidence': 0.1
        }

    @staticmethod
    def _build_response(need_tool: bool, reason: str, confidence: float = 0.8, **kwargs) -> Dict[str, Any]:
        """构建标准响应"""
        response = {
            'need_tool': need_tool,
            'reason': reason,
            'confidence': confidence
        }
        response.update(kwargs)
        return response

    def _record_conversation(self, role: str, content: str) -> None:
        """记录对话历史"""
        self.context['conversation_history'].append({
            'timestamp': datetime.now().isoformat(),
            'role': role,
            'content': content[:200]  # 限制长度
        })

        # 保持历史记录长度
        if len(self.context['conversation_history']) > 20:
            self.context['conversation_history'] = self.context['conversation_history'][-20:]

    def _record_thought_process(self, intent_analysis: Dict, execution_plan: Dict) -> None:
        """记录思考过程"""
        # 记录到工作流历史
        if execution_plan.get('tool_name'):
            self.context['workflow_history'].append(execution_plan['tool_name'])

            # 限制历史长度
            if len(self.context['workflow_history']) > 10:
                self.context['workflow_history'] = self.context['workflow_history'][-10:]

        # 记录最后操作
        if intent_analysis.get('primary_intent'):
            intent_map = {
                'chart': 'chart_generation',
                'trend': 'chart_generation',
                'compare': 'chart_generation',
                'composition': 'chart_generation',
                'parse': 'data_parsing',
                'clean': 'data_cleaning',
                'analyze': 'analysis',
                'income': 'analysis',
                'balance': 'analysis',
                'cashflow': 'analysis',
                'health': 'analysis'
            }

            action = intent_map.get(intent_analysis['primary_intent'])
            if action:
                self.context['current_state']['last_action'] = action

    def update_context(self, key: str, value: Any, context_type: str = 'current_state') -> None:
        """更新上下文信息"""
        if context_type in self.context:
            if isinstance(self.context[context_type], dict):
                self.context[context_type][key] = value
            else:
                self.context[context_type] = {key: value}

    def get_context(self) -> Dict[str, Any]:
        """获取当前上下文"""
        return self.context.copy()

    def clear_context(self, context_type: str = None) -> None:
        """清除上下文"""
        if context_type:
            if context_type in self.context:
                if isinstance(self.context[context_type], dict):
                    self.context[context_type] = {}
                elif isinstance(self.context[context_type], list):
                    self.context[context_type] = []
        else:
            self.context = {
                'conversation_history': [],
                'current_state': {
                    'data_loaded': False,
                    'data_cleaned': False,
                    'current_file': None,
                    'current_chart_type': None,
                    'last_action': None,
                    'report_type': None
                },
                'user_preferences': {},
                'workflow_history': []
            }


# 保持原有接口函数
def brain_think(user_instruction: str, tools_description: list) -> Dict[str, Any]:
    """
    原有接口函数 - 保持向后兼容
    参数: user_instruction: 用户指令字符串, tools_description: 工具描述列表
    返回: 决策字典
    """
    brain = Brain()
    result = brain.think(user_instruction, tools_description)

    return {
        'need_tool': result.get('need_tool', False),
        'tool_name': result.get('tool_name', ''),
        'tool_params': result.get('tool_params', {}),
        'reason': result.get('reason', ''),
        'confidence': result.get('confidence', 0.5)
    }


def test_brain() -> None:
    """测试大脑功能"""
    print("=" * 60)
    print("测试修复版财经大脑")
    print("=" * 60)

    # 模拟工具描述
    tools = [
        {"name": "parse_finance_file", "description": "解析财经数据文件"},
        {"name": "clean_financial_data", "description": "清洗财经数据"},
        {"name": "create_professional_chart", "description": "生成专业图表"},
        {"name": "analyze_financial_health", "description": "分析财务健康"}
    ]

    # 创建大脑
    brain = Brain()

    # 测试用例
    test_cases = [
        ("你好，请帮我分析财经数据", "问候"),
        ("上传销售数据文件", "文件上传"),
        ("解析文件: C:/data/sales.csv", "文件解析"),
        ("清洗这份数据", "数据清洗"),
        ("生成销售趋势图", "图表生成"),
        ("分析财务健康状况", "财务分析"),
        ("查看当前状态", "状态查询"),
        ("再生成一个对比图", "上下文相关")
    ]

    for i, (user_input, expected_type) in enumerate(test_cases, 1):
        print(f"\n测试 {i}: '{user_input}'")
        print(f"期望类型: {expected_type}")
        print("-" * 40)

        result = brain.think(user_input, tools)

        print(f"需要工具: {result.get('need_tool')}")
        print(f"工具名称: {result.get('tool_name')}")
        print(f"置信度: {result.get('confidence')}")
        print(f"主要意图: {result.get('intent_analysis', {}).get('primary_intent')}")

        suggestions = result.get('suggestions', [])
        if suggestions:
            print(f"建议: {suggestions}")

    # 显示上下文
    print("\n" + "=" * 60)
    print("大脑上下文:")
    context = brain.get_context()
    print(f"对话历史长度: {len(context.get('conversation_history', []))}")
    print(f"工作流历史: {context.get('workflow_history', [])[-5:]}")

    print("\n" + "=" * 60)
    print("大脑测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    """直接运行此文件进行测试"""
    print("修复版财经大脑系统 v2.2")
    print("-" * 40)

    # 运行测试
    test_brain()