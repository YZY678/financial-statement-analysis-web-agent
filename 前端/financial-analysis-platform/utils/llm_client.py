"""
LLM 客户端：指标提取、分析师风格对话。
重写版V2：解决单位混乱、三张表边界、风险提示问题
重写版V3：扩大表格范围到50000字符，避免年报/季报截断导致指标抽取失败
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

from .config import OPENAI_API_KEY, OPENAI_BASE_URL, LOCAL_MODEL_NAME
# 延迟导入，便于在无 key 时做 mock
_openai_client = None

# 避免提示词过长导致本地模型长时间卡住：默认限制到 80000 字符，可通过环境变量覆盖
EXTRACT_MAX_CHARS = int(os.getenv("EXTRACT_MAX_CHARS", "80000"))

# 单次调用超时（秒），防止请求无限阻塞
CHAT_TIMEOUT_SECONDS = int(os.getenv("CHAT_TIMEOUT_SECONDS", "600"))


def _filter_relevant_tables(tables_json: str, max_chars: int = EXTRACT_MAX_CHARS) -> str:
    """
    关键词过滤表格，只保留包含财务关键词的表格。
    
    Args:
        tables_json: 原始表格JSON字符串
        max_chars: 最大字符数限制
    
    Returns:
        过滤后的表格JSON字符串
    """
    try:
        tables = json.loads(tables_json)
    except json.JSONDecodeError:
        # 解析失败，直接截断返回
        return tables_json[:max_chars]
    
    if not isinstance(tables, list):
        return tables_json[:max_chars]
    
    # 财务关键词（中英文）
    keywords = [
        # 利润表
        "营业收入", "营业总收入", "revenue", "operating revenue",
        "净利润", "归母净利润", "net income", "net profit",
        "毛利", "毛利率", "gross profit", "gross margin",
        "营业成本", "operating cost",
        "销售费用", "管理费用", "研发费用", "财务费用",
        "selling expense", "administrative expense", "r&d expense",
        
        # 资产负债表
        "资产总计", "total assets",
        "负债总计", "total liabilities",
        "所有者权益", "shareholders equity",
        "应收账款", "accounts receivable",
        "存货", "inventory",
        "货币资金", "cash",
        "合同负债", "预收", "contract liability",
        
        # 现金流量表
        "经营活动产生的现金流量净额", "经营现金流",
        "operating cash flow", "cash flow from operating",
        "投资活动产生的现金流量净额",
        "筹资活动产生的现金流量净额",
        "分红", "dividend",
        
        # 其他
        "主要会计数据", "财务指标", "合并", "母公司",
        "本期", "上期", "同比", "year-over-year",
    ]
    
    relevant_tables = []
    
    for table_obj in tables:
        if not isinstance(table_obj, dict):
            continue
        
        table_data = table_obj.get("table", [])
        if not table_data:
            continue
        
        # 将表格转为字符串
        table_str = json.dumps(table_data, ensure_ascii=False)
        
        # 检查是否包含关键词
        has_keyword = any(kw in table_str for kw in keywords)
        
        if has_keyword:
            relevant_tables.append(table_obj)
    
    # 如果过滤后为空，返回原始数据（避免过度过滤）
    if not relevant_tables:
        print("⚠️ 关键词过滤后无表格，使用原始数据")
        return tables_json[:max_chars]
    
    print(f"   关键词过滤: {len(tables)} 个表格 → {len(relevant_tables)} 个相关表格")
    
    # 重新序列化
    filtered_json = json.dumps(relevant_tables, ensure_ascii=False, indent=2)
    
    # 如果还是太长，做头尾拼接
    if len(filtered_json) > max_chars:
        head_size = max_chars * 2 // 3
        tail_size = max_chars // 3
        filtered_json = filtered_json[:head_size] + "\n...(中间省略)...\n" + filtered_json[-tail_size:]
    
    return filtered_json


def _get_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            kwargs = {"api_key": OPENAI_API_KEY}
            if OPENAI_BASE_URL:
                kwargs["base_url"] = OPENAI_BASE_URL
            _openai_client = OpenAI(**kwargs)
        except Exception as e:
            raise RuntimeError(f"初始化 OpenAI 客户端失败: {e}") from e
    return _openai_client


def _call_chat(model: str, messages: List[Dict[str, str]], json_mode: bool = False) -> str:
    client = _get_client()
    target_model = LOCAL_MODEL_NAME
    kwargs = {
        "model": target_model,
        "messages": messages,
        "timeout": CHAT_TIMEOUT_SECONDS,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    r = client.chat.completions.create(**kwargs)
    return r.choices[0].message.content or ""


def extract_metrics(tables_json: str, keys: List[str]) -> Dict[str, Any]:
    """
    从财报表格中提取结构化指标（重写版V3）。
    
    核心改进：
    1. 强制要求：期间、口径、单位三要素
    2. 每个指标必须包含：原始值、单位、换算值、证据来源
    3. 自动校验：分项加总是否等于总数
    4. 返回完整的溯源信息，便于人工复核
    5. 关键词过滤表格，避免截断导致遗漏
    """
    keys_str = ", ".join(keys)
    
    # 调试信息
    print(f"   表格数据长度: {len(tables_json)} 字符")
    
    # 如果表格为空，提前返回
    if tables_json == "[]" or len(tables_json) < 10:
        print("⚠️ 表格数据为空，无法提取指标")
        return {
            "period": "未知期间",
            "scope": "unknown",
            "unit_standard": "亿元",
            "items": {},
            "extraction_failed": True,
            "failure_reason": "表格数据为空"
        }
    
    # 关键词过滤表格（优先级最高的改进）
    tables_subset = _filter_relevant_tables(tables_json)
    
    print(f"   过滤后表格长度: {len(tables_subset)} 字符")
    
    system = """你是专业的财报数据提取专家。严格遵守以下规则：

1. 只能从表格中提取数据，不得推测或计算
2. 必须明确标注：报告期间、合并口径、数值单位
3. 每个数据必须附带证据（表格原文）
4. 发现分项数据时，必须校验加总是否一致
5. 输出纯JSON，不含任何解释文字
6. 【关键】统一单位建议选"亿元"（便于阅读）
7. 【关键】如果某个指标在前面的表格中找不到，继续往后找，不要轻易放弃
8. 【致命错误】必须使用"items"字段包裹所有指标，不要直接在顶层放置指标数据
9. 【致命错误】不要返回"page_XXX"这样的页面级数据，只返回标准化的指标
10. 【强制单位校验】若某指标换算后的 value_unified 超过 10,000（即超过 1 万亿），必须重新核对是否误将原文中的"元"识别成了"亿元"；若原文为"元"则应除以 1 亿后再填入 value_unified（单位仍为亿元）。"""
    
    user = f"""从财报表格中提取以下信息：

**必填元数据**：
- period: 报告期间（如"2024年度"、"2024年1-9月"）
- scope: 合并口径（consolidated=合并报表, parent=母公司, unknown=未知）
- unit_standard: 统一单位（建议"亿元"）

**必填指标**（{keys_str}）：
每个指标包含：
- value_original: 原始数值
- unit_original: 原始单位
- value_unified: 换算为统一单位的数值
- evidence: 表格原文（复制粘贴）
- yoy_change_pct: 同比变化百分比（如有，注意：下降不能超过-100%）

**重要提示**：
- 表格数据可能很长，请仔细搜索整个表格，不要只看前面几行
- 如果某个指标在前面找不到，继续往后找，年报/季报的关键指标通常在利润表、资产负债表、现金流量表中
- 如果某个指标确实找不到，标记为null，但不要放弃其他指标
- 尽可能多地提取指标，即使某些指标缺失也要继续
- 优先提取：revenue（营业收入）、net_income（归母净利润）、gross_margin（毛利率）、operating_cashflow（经营现金流）
- 【强制单位校验】若换算为亿元后某金额超过 10,000（即超过 1 万亿），请重新核对是否误将表格中的"元"识别为"亿元"；若原文单位为"元"，应除以 1 亿再填入 value_unified。

**输出JSON格式（严格遵守）**：
{{
  "period": "2024年度",
  "scope": "consolidated",
  "unit_standard": "亿元",
  "ticker": "600519",
  "company_name": "贵州茅台",
  "items": {{
    "revenue": {{
      "value_original": 1706100,
      "unit_original": "万元",
      "value_unified": 170.61,
      "evidence": "营业收入 1,706,100万元",
      "yoy_change_pct": 15.89
    }},
    "net_income": {{
      "value_original": 853000,
      "unit_original": "万元",
      "value_unified": 85.30,
      "evidence": "归母净利润 853,000万元",
      "yoy_change_pct": 16.20
    }},
    "operating_cashflow": {{
      "value_original": 950000,
      "unit_original": "万元",
      "value_unified": 95.00,
      "evidence": "经营活动产生的现金流量净额 950,000万元",
      "yoy_change_pct": 12.50
    }}
  }},
  "validation": {{
    "revenue_breakdown_sum": 170.61,
    "revenue_total": 170.61,
    "is_consistent": true
  }}
}}

**严格禁止的错误格式**：
- ❌ 不要返回 "page_128": {{...}}, "page_129": {{...}} 这样的页面级数据
- ❌ 不要在顶层直接放置 "货币资金": {{...}}, "拆出资金": {{...}}
- ✅ 所有指标必须放在 "items" 字段内
- ✅ 使用英文字段名（revenue, net_income等），不要用中文字段名

**表格数据**：
```json
{tables_subset}
```

只输出JSON，不要解释。"""
    
    content = _call_chat("ignored", [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], json_mode=True)
    
    # 提取并解析JSON
    content = content.strip()
    m = re.search(r"(\{[\s\S]*\})", content)
    if m:
        content = m.group(1)
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 修复一次
        print("⚠️ JSON解析失败，尝试修复...")
        fix = _call_chat("ignored", [
            {"role": "system", "content": system},
            {"role": "user", "content": "修复为合法JSON（只输出JSON）：\n" + content},
        ], json_mode=True)
        m2 = re.search(r"(\{[\s\S]*\})", fix.strip())
        try:
            data = json.loads(m2.group(1) if m2 else fix)
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON修复失败: {e}")
            print(f"   原始输出: {content[:500]}...")
            # 返回空数据结构，避免程序崩溃
            data = {
                "period": "未知期间",
                "scope": "unknown",
                "unit_standard": "亿元",
                "items": {},
                "extraction_failed": True,
                "failure_reason": f"JSON解析失败: {str(e)}"
            }
    
    # 调试：打印提取到的items
    if "items" in data:
        print(f"   成功提取 {len(data.get('items', {}))} 个指标")
        extracted_keys = list(data.get('items', {}).keys())
        print(f"   提取到的指标: {extracted_keys}")
    else:
        print("⚠️ 返回数据中没有'items'字段")
        print(f"   返回的顶层字段: {list(data.keys())}")
        
        # 尝试修复：如果发现页面级数据或中文字段名，尝试重新提取
        has_page_data = any(k.startswith("page_") for k in data.keys())
        has_chinese_fields = any(ord(c) > 127 for k in data.keys() for c in str(k))
        
        if has_page_data or has_chinese_fields:
            print("   检测到错误格式（页面级数据或中文字段名），尝试修复...")
            
            # 构建修复prompt
            fix_prompt = f"""以下JSON格式错误，请修复为正确格式：

错误的JSON：
{json.dumps(data, ensure_ascii=False, indent=2)}

要求：
1. 所有指标必须放在"items"字段内
2. 使用英文字段名（revenue, net_income, operating_cashflow等）
3. 删除所有"page_XXX"字段
4. 删除所有中文字段名
5. 保留period, scope, unit_standard, ticker, company_name这些元数据字段

正确的格式示例：
{{
  "period": "2024年度",
  "scope": "consolidated",
  "unit_standard": "亿元",
  "items": {{
    "revenue": {{"value_unified": 170.61, "evidence": "..."}},
    "net_income": {{"value_unified": 85.30, "evidence": "..."}}
  }}
}}

只输出修复后的JSON，不要解释。"""
            
            try:
                fixed_content = _call_chat("ignored", [
                    {"role": "system", "content": system},
                    {"role": "user", "content": fix_prompt},
                ], json_mode=True)
                
                fixed_content = fixed_content.strip()
                m_fix = re.search(r"(\{[\s\S]*\})", fixed_content)
                if m_fix:
                    fixed_content = m_fix.group(1)
                
                data = json.loads(fixed_content)
                print("   ✓ 格式修复成功")
                
                if "items" in data:
                    print(f"   修复后提取 {len(data.get('items', {}))} 个指标")
            except Exception as e:
                print(f"   ✗ 格式修复失败: {e}")
    
    # 数据后处理：提升常用字段到顶层
    if "items" in data:
        for k in keys:
            if k in data["items"]:
                item = data["items"][k]
                if isinstance(item, dict):
                    data[k] = item.get("value_unified") or item.get("value_original")
                else:
                    data[k] = item
    
    # 补充缺失字段
    data.setdefault("period", "未知期间")
    data.setdefault("scope", "unknown")
    data.setdefault("unit_standard", "亿元")
    
    return data


def chat(role: str, task: str, context: str, metadata: Optional[Dict] = None) -> str:
    """
    分析师角色对话（重写版V2）：解决单位混乱、三张表边界、风险提示问题。
    
    task 类型：
    - write_header: 生成报告头部（期间/口径/单位声明）
    - generate_tables: 根据数据生成三张表（JSON，仅含具体数字）
    - analyze_profit: 利润表分析（收入/成本/费用/利润）
    - analyze_balance: 资产负债表分析（应收/存货/负债）
    - analyze_cashflow: 现金流分析（经营/投资/筹资）
    - summarize_risks: 风险提示（可观察、可验证）
    """
    system = """你是专业的卖方分析师，撰写风格：结构清晰、数据为证、结论明确。

【致命错误必须避免】：
1. 单位混用：全文必须统一使用元数据中声明的单位，禁止出现"XX亿元"和"XX万元"混用
2. 数学错误：百分比下降不能超过-100%，增长超过1000%需改为"X倍"表达
3. 三张表边界：利润表只写收入/成本/费用/利润，不要写货币资金/应收/存货等资产负债表项目
4. 风险提示：不要写成"业绩总结"，必须是"如果发生X，会影响Y"的格式

【核心原则】：
1. 每个结论必须有数据支撑
2. 用"百分点"描述比率变化（如"毛利率下降1.2 ppt"）
3. 用"证据→推论"链条，不跳步
4. 风险必须可观察、可验证
5. 不使用"显著"、"大幅"等模糊词，用具体数字"""
    
    task_prompts = {
        "write_header": """根据元数据生成报告头部声明（JSON格式）：
{
  "title": "公司名称 + 期间 + 财报解读",
  "metadata_statement": "本报告基于【期间】【口径】财报，全文金额统一使用【单位】。"
}

注意：必须强调"全文统一使用"，避免读者误解。""",
        
        "generate_tables": """根据【财报数据】生成三张表格，输出纯 JSON，不要任何解释。要求：
1. 只包含有具体数字的行，没有数据的指标不要写。
2. 金额必须带单位（与元数据 unit_standard 一致，如"亿元"）。
3. 百分比用数字+%表示，如 "15.89%"、"+12.5%"。
4. 严格使用以下键名和结构，不要增删键。

输出格式（只输出此 JSON）：
{
  "利润表": [
    {"项目": "营业收入", "本期金额": "170.61亿元", "同比变化": "+15.89%", "备注": ""},
    {"项目": "毛利率", "本期金额": "91.2%", "同比变化": "", "备注": ""},
    {"项目": "归母净利润", "本期金额": "85.30亿元", "同比变化": "+16.20%", "备注": ""}
  ],
  "资产负债表": [
    {"项目": "应收账款", "本期金额": "10.50亿元", "占收入比例": "6.15%", "备注": ""},
    {"项目": "存货", "本期金额": "120.00亿元", "占收入比例": "", "备注": ""}
  ],
  "现金流量表": [
    {"项目": "经营活动现金流", "本期金额": "95.00亿元", "质量指标": "CFO/净利润: 111%", "备注": ">100%为优"},
    {"项目": "分红", "本期金额": "30.00亿元", "质量指标": "分红率: 35%", "备注": ""}
  ]
}

注意：每个数组只包含从财报数据中能得到的、有数字的项；没有的项不要写。""",
        
        "analyze_profit": """分析利润表，输出结构化文本（不要JSON）。

【严格要求】：
1. 只写利润表项目：收入、成本、毛利、费用、净利润
2. 不要写资产负债表项目（货币资金、应收账款、存货、交易性金融资产等）
3. 不要写现金流项目（经营现金流等）
4. 全文使用统一单位（从元数据获取）
5. 百分比变化：用"+15.89%"表示增长，"-2.3%"表示下降（不能超过-100%）
6. 百分点变化：用"+1.2 ppt"表示比率上升，"-0.5 ppt"表示比率下降

**一、营业收入**
- 总收入：XX（统一单位），同比+XX%（绝对增加XX）
- 分产品：产品A XX（占比XX%，同比+XX%）、产品B...
- 驱动因素：量（+XX%）、价（+XX%）、结构（高端占比+XX ppt）

**二、毛利率**
- 综合毛利率：XX%，同比变化XX ppt
- 原因：成本增速XX% vs 收入增速XX%（原材料+XX%，人工+XX%）

**三、期间费用**
- 销售费用率：XX%（同比XX ppt），主要是XX
- 管理费用率：XX%（同比XX ppt）
- 研发费用率：XX%（同比XX ppt）

**四、净利润**
- 归母净利润：XX（统一单位），同比+XX%
- 净利率：XX%，同比XX ppt
- ROE：XX%（如有数据）""",
        
        "analyze_balance": """分析资产负债表要点（不要JSON）。

【严格要求】：
1. 只写资产负债表项目：资产、负债、所有者权益
2. 不要写利润表项目（收入、费用、净利润等）
3. 不要写现金流项目（经营现金流等）
4. 全文使用统一单位

**一、营运资本**
- 应收账款：XX（统一单位），占收入XX%（去年XX%）
- 存货：XX（统一单位），周转天数XX天（去年XX天）
- 合同负债/预收：XX（统一单位），同比+XX%（反映渠道打款意愿）

**二、资本结构**
- 资产负债率：XX%
- 货币资金：XX（统一单位）
- 有息负债：XX（统一单位）""",
        
        "analyze_cashflow": """分析现金流（不要JSON）。

【严格要求】：
1. 只写现金流量表项目：经营/投资/筹资活动现金流
2. 不要写资产负债表项目（货币资金、应收、存货等）
3. 不要写利润表项目（收入、费用等）
4. 全文使用统一单位

**一、经营现金流**
- 经营活动现金流净额：XX（统一单位），同比+XX%
- CFO/净利润：XX%（>100%为优，<80%需关注）
- 差异原因：应收变化+XX、存货变化+XX、预收变化+XX

**二、投资与筹资**
- 投资活动现金流：XX（统一单位），主要投向XX
- 筹资活动现金流：XX（统一单位）
- 分红：XX（统一单位），分红率XX%""",
        
        "summarize_risks": """列出可触发、可验证的风险点（不要JSON）。

【严格要求】：
1. 不要写成"业绩总结"或"公司表现良好"
2. 每个风险必须是"如果发生X，会影响Y"的格式
3. 必须给出可观察的指标（批价、库存、动销、汇率等）
4. 不要重复前面的业绩数据

**风险提示**

1. **量价风险**：若批发价格回落超过X%，将影响经销商打款意愿，导致预收款下降。需跟踪：批价走势、渠道库存天数、终端动销数据。

2. **成本压力**：原材料价格若持续上涨，每上涨X%将压缩毛利率约X ppt。需跟踪：粮食价格指数、人工成本增速。

3. **应收质量**：应收账款占收入比例若继续提升，回款周期延长将增加坏账风险。需跟踪：应收账款周转天数、账龄结构、主要客户资信状况。

4. **政策风险**：（如适用）白酒行业面临反腐、限价等政策不确定性，若政策收紧将影响高端消费。需跟踪：政策动向、公务消费数据、高端餐饮景气度。

5. **海外风险**：（如适用）海外收入占比X%，汇率每波动1%影响利润约X。需跟踪：汇率走势、关税政策变化、海外渠道建设进度。"""
    }
    
    prompt_template = task_prompts.get(task, "请根据上下文完成分析任务。")
    
    # 如果有元数据，附加到上下文
    context_full = context[:8000]
    if metadata:
        meta_str = json.dumps(metadata, ensure_ascii=False, indent=2)
        context_full = f"【元数据（必须严格遵守）】：\n{meta_str}\n\n【财报数据】：\n{context_full}"
    
    prompt = f"{prompt_template}\n\n{context_full}"
    
    json_task = task in ("write_header", "generate_tables")
    content = _call_chat("ignored", [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ], json_mode=json_task)
    
    if json_task:
        content = content.strip()
        for pattern in [r"```(?:json)?\s*([\s\S]*?)```", r"(\{[\s\S]*\})"]:
            m = re.search(pattern, content)
            if m:
                content = m.group(1).strip()
                break
        try:
            obj = json.loads(content)
            return obj
        except json.JSONDecodeError:
            if task == "write_header":
                return {"title": "财报解读", "metadata_statement": "本报告基于财报数据，全文金额统一使用亿元。"}
            if task == "generate_tables":
                return {}
            return {"title": "财报解读", "metadata_statement": "本报告基于财报数据，全文金额统一使用亿元。"}
    
    return content


def extract_metrics_from_text(evidence: str, keys: List[str]) -> Dict[str, Any]:
    """
    从原始文本中提取财务指标（fallback方法）。
    
    当表格提取失败时使用，规则依然严格：
    1. 必须复制粘贴证据片段
    2. 找不到就标记为null
    3. 不得推测或计算
    
    Args:
        evidence: 原始文本片段
        keys: 要提取的指标列表
    
    Returns:
        提取结果字典
    """
    keys_str = ", ".join(keys)
    
    system = """你是专业的财报数据提取专家（文本模式）。严格遵守以下规则：

1. 只能从文本中提取明确出现的数据，不得推测或计算
2. 必须复制粘贴证据片段（原文）
3. 找不到的指标标记为null
4. 输出纯JSON，不含任何解释文字
5. 优先提取：营业收入、归母净利润、经营现金流
6. 注意识别单位（元/万元/亿元）
7. 【关键】所有指标必须放在"items"字段内
8. 【关键】使用英文字段名（revenue, net_income, operating_cashflow）"""
    
    user = f"""从以下文本中提取财务指标：{keys_str}

**输出JSON格式（严格遵守）**：
{{
  "period": "2024年度",
  "unit_standard": "亿元",
  "items": {{
    "revenue": {{
      "value_original": 1706100,
      "unit_original": "万元",
      "value_unified": 170.61,
      "evidence": "营业收入1,706,100万元"
    }},
    "net_income": {{
      "value_original": 853000,
      "unit_original": "万元",
      "value_unified": 85.30,
      "evidence": "归属于母公司所有者的净利润853,000万元"
    }},
    "operating_cashflow": {{
      "value_original": 950000,
      "unit_original": "万元",
      "value_unified": 95.00,
      "evidence": "经营活动产生的现金流量净额950,000万元"
    }}
  }}
}}

**重要**：
- 所有指标必须放在"items"字段内
- 使用英文字段名
- 找不到的指标不要包含在items中（不要设为null）

**文本内容**：
{evidence[:15000]}

只输出JSON，不要解释。"""
    
    content = _call_chat("ignored", [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], json_mode=True)
    
    # 提取并解析JSON
    content = content.strip()
    m = re.search(r"(\{[\s\S]*\})", content)
    if m:
        content = m.group(1)
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"⚠️ 文本提取JSON解析失败: {e}")
        return {
            "period": "未知期间",
            "unit_standard": "亿元",
            "items": {},
            "extraction_failed": True,
            "failure_reason": f"文本提取JSON解析失败: {str(e)}"
        }
    
    # 数据后处理：提升常用字段到顶层
    if "items" in data:
        for k in keys:
            if k in data["items"]:
                item = data["items"][k]
                if isinstance(item, dict):
                    data[k] = item.get("value_unified") or item.get("value_original")
                else:
                    data[k] = item
    
    # 补充缺失字段
    data.setdefault("period", "未知期间")
    data.setdefault("unit_standard", "亿元")
    
    print(f"   文本提取到 {len([k for k in keys if data.get(k) is not None])} 个指标")
    
    return data


class LLM:
    """对外暴露的 LLM 接口，与伪代码中的 llm.extract_metrics / llm.chat 一致。"""
    def extract_metrics(self, tables_json: str, keys: List[str]) -> Dict[str, Any]:
        return extract_metrics(tables_json, keys)
    
    def extract_metrics_from_text(self, evidence: str, keys: List[str]) -> Dict[str, Any]:
        return extract_metrics_from_text(evidence, keys)

    def chat(self, role: str, task: str, context: str, metadata: Optional[Dict] = None):
        return chat(role, task, context, metadata)


llm = LLM()
