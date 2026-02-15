"""
财务报告生成主流程（重写版V2）：解决单位混乱、加总校验、三张表边界问题。
重写版V3：
1. 扩大指标抽取表格范围（50000字符）
2. matplotlib可选依赖，优雅降级
3. 图片路径使用正斜杠相对路径，兼容所有Markdown渲染器
"""
import re
from typing import Any, Dict

from code_runner import llm_code_runner
from data_validator import DataValidator, validate_financial_data
from historical_data import fetch_historical_data
from llm_client import llm
from pdf_parser import parse_pdf_with_multimodal_ai


def _generate_profit_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """生成利润表（Markdown表格）"""
    unit = validator.standard_unit
    
    # 提取数据（使用 is not None 判断）
    revenue = data.get("revenue")
    revenue_yoy = data.get("revenue_yoy")
    gross_margin = data.get("gross_margin")
    net_income = data.get("net_income")
    net_income_yoy = data.get("net_income_yoy")
    net_margin = data.get("net_margin")
    sales_ratio = data.get("sales_expense_ratio")
    admin_ratio = data.get("admin_expense_ratio")
    rd_ratio = data.get("rd_expense_ratio")
    
    table = f"""
| 项目 | 本期金额 | 同比变化 | 备注 |
|------|----------|----------|------|
| **营业收入** | {validator.format_value(revenue) if revenue is not None else 'N/A'} | {validator.format_percentage(revenue_yoy) if revenue_yoy is not None else 'N/A'} | |
| **毛利率** | {f'{gross_margin:.2f}%' if gross_margin is not None else 'N/A'} | - | |
| **期间费用率** | | | |
| - 销售费用率 | {f'{sales_ratio:.2f}%' if sales_ratio is not None else 'N/A'} | - | |
| - 管理费用率 | {f'{admin_ratio:.2f}%' if admin_ratio is not None else 'N/A'} | - | |
| - 研发费用率 | {f'{rd_ratio:.2f}%' if rd_ratio is not None else 'N/A'} | - | |
| **归母净利润** | {validator.format_value(net_income) if net_income is not None else 'N/A'} | {validator.format_percentage(net_income_yoy) if net_income_yoy is not None else 'N/A'} | |
| **净利率** | {f'{net_margin:.2f}%' if net_margin is not None else 'N/A'} | - | |

*注：金额单位统一为{unit}*
"""
    return table


def _generate_balance_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """生成资产负债表（Markdown表格）"""
    unit = validator.standard_unit
    
    # 提取数据（使用 is not None 判断）
    revenue = data.get("revenue")  # 用于计算占比
    accounts_receivable = data.get("accounts_receivable")
    inventory = data.get("inventory")
    contract_liability = data.get("contract_liability")
    
    # 计算占比
    ar_ratio = None
    if accounts_receivable is not None and revenue is not None and revenue != 0:
        ar_ratio = (accounts_receivable / revenue * 100)
    
    table = f"""
| 项目 | 本期金额 | 占收入比例 | 备注 |
|------|----------|------------|------|
| **营运资本** | | | |
| - 应收账款 | {validator.format_value(accounts_receivable) if accounts_receivable is not None else 'N/A'} | {f'{ar_ratio:.2f}%' if ar_ratio is not None else 'N/A'} | |
| - 存货 | {validator.format_value(inventory) if inventory is not None else 'N/A'} | - | |
| - 合同负债/预收款 | {validator.format_value(contract_liability) if contract_liability is not None else 'N/A'} | - | 反映渠道打款意愿 |
| **资本结构** | | | |
| - 货币资金 | N/A | - | 待提取 |
| - 资产负债率 | N/A | - | 待提取 |

*注：金额单位统一为{unit}*
"""
    return table


def _generate_cashflow_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """生成现金流量表（Markdown表格）"""
    unit = validator.standard_unit
    
    # 提取数据（使用 is not None 判断）
    operating_cashflow = data.get("operating_cashflow")
    net_income = data.get("net_income")
    capex = data.get("capex")
    dividend = data.get("dividend")
    
    # 计算CFO/净利润比率
    cfo_to_ni = data.get("cfo_to_ni_ratio")
    if cfo_to_ni is None and operating_cashflow is not None and net_income is not None and net_income != 0:
        cfo_to_ni = (operating_cashflow / net_income) * 100
    
    # 计算分红率
    dividend_ratio = None
    if dividend is not None and net_income is not None and net_income != 0:
        dividend_ratio = (dividend / net_income * 100)
    
    table = f"""
| 项目 | 本期金额 | 质量指标 | 备注 |
|------|----------|----------|------|
| **经营活动现金流** | {validator.format_value(operating_cashflow) if operating_cashflow is not None else 'N/A'} | CFO/净利润: {f'{cfo_to_ni:.1f}%' if cfo_to_ni is not None else 'N/A'} | >100%为优 |
| **投资活动现金流** | | | |
| - 资本开支 | {validator.format_value(capex) if capex is not None else 'N/A'} | - | |
| **筹资活动现金流** | | | |
| - 分红 | {validator.format_value(dividend) if dividend is not None else 'N/A'} | 分红率: {f'{dividend_ratio:.1f}%' if dividend_ratio is not None else 'N/A'} | |

*注：金额单位统一为{unit}*
"""
    return table


def _pick_evidence(raw_text: str) -> str:
    """
    从原文中只抽取和财务相关的证据片段，避免整篇喂进去让模型自由发挥。
    关键：砍掉通稿幻觉，只给模型看真实的财务数据段落。
    """
    patterns = [
        r"经营活动产生的现金流量净额",
        r"投资活动产生的现金流量净额",
        r"筹资活动产生的现金流量净额",
        r"研发费用|研发投入",
        r"销售费用|管理费用|财务费用",
        r"分部|分行业|分产品|分地区",
        r"重大风险|风险提示|风险因素",
        r"营业收入|营业成本|毛利率",
        r"净利润|归属于.*股东",
        r"应收账款|存货|合同负债|预收款",
        r"资产负债率|货币资金",
        r"ROE|净资产收益率|总资产收益率",
    ]
    hits = []
    paras = re.split(r"\n\s*\n", raw_text)
    for p in paras:
        if any(re.search(pt, p) for pt in patterns):
            hits.append(p.strip())
        if len("\n\n".join(hits)) > 8000:
            break
    return "\n\n".join(hits[:50]) or raw_text[:8000]


def generate_financial_report(pdf_path: str) -> str:
    """
    根据财报 PDF 生成一篇完整的分析文章（Markdown）。
    
    重写版V2改进：
    1. 强制单位统一（默认亿元）
    2. 量级sanity check
    3. 加总校验
    4. 严格三张表边界
    5. 风险提示改为可触发格式
    """
    # 1. 解析 PDF
    print("正在解析 PDF...")
    raw_text, tables_json = parse_pdf_with_multimodal_ai(pdf_path)
    
    # 检查表格是否为空
    if tables_json == "[]" or len(tables_json) < 10:
        print("⚠️ 警告：未提取到表格数据或表格数据过少")
        print("   可能原因：")
        print("   1. PDF是扫描件，需要OCR")
        print("   2. 表格格式复杂，pdfplumber无法识别")
        print("   3. PDF损坏或加密")
        print("   建议：检查PDF文件，或使用其他工具（Camelot、Tabula）预处理")
        print(f"   当前tables_json长度: {len(tables_json)}")

    # 2. 提取核心数据（扩充指标列表）
    print("正在提取财务指标...")
    financial_data = llm.extract_metrics(
        tables_json,
        keys=[
            "revenue",              # 营业收入
            "revenue_yoy",          # 收入同比增速
            "net_income",           # 归母净利润
            "net_income_yoy",       # 净利润同比增速
            "gross_margin",         # 毛利率
            "net_margin",           # 净利率
            "sales_expense_ratio",  # 销售费用率
            "admin_expense_ratio",  # 管理费用率
            "rd_expense_ratio",     # 研发费用率
            "accounts_receivable",  # 应收账款
            "inventory",            # 存货
            "contract_liability",   # 合同负债/预收款
            "operating_cashflow",   # 经营现金流
            "capex",                # 资本开支
            "dividend",             # 分红
        ],
    )
    
    # 检查是否提取失败，触发文本回退
    extraction_failed = financial_data.get("extraction_failed", False)
    core_fields = ["revenue", "net_income", "operating_cashflow"]
    core_count = sum(1 for k in core_fields if financial_data.get(k) is not None)
    
    if extraction_failed or core_count < 2:
        print(f"⚠️ 结构化表格提取不足（核心字段: {core_count}/3），尝试从文本提取...")
        
        # 提取证据片段
        evidence = _pick_evidence(raw_text)
        
        # 从文本提取（fallback）
        text_data = llm.extract_metrics_from_text(
            evidence,
            keys=core_fields,  # 只提取核心字段
        )
        
        # 合并数据（文本提取的数据优先级较低，不覆盖已有数据）
        for key, value in text_data.items():
            if key not in ["extraction_failed", "failure_reason", "items"]:
                if financial_data.get(key) is None and value is not None:
                    financial_data[key] = value
                    financial_data[f"{key}_source"] = "text_fallback"
        
        print(f"   文本回退提取完成，补充了 {sum(1 for k in core_fields if financial_data.get(f'{k}_source') == 'text_fallback')} 个核心字段")
    
    # 调试：打印原始抽取结果
    print("=== 原始抽取结果 ===")
    print(financial_data)
    
    # 检查最少指标数（闸门）
    from config import MIN_INDICATORS
    extracted_count = sum(1 for k in financial_data.keys() 
                         if not k.endswith(("_evidence", "_source", "_yoy")) 
                         and k not in ["period", "scope", "unit_standard", "ticker", "company_name", 
                                      "validation_warnings", "extraction_failed", "failure_reason", "items"]
                         and financial_data.get(k) is not None)
    
    print(f"=== 提取指标统计 ===")
    print(f"   有效指标数: {extracted_count}")
    print(f"   最少要求: {MIN_INDICATORS}")
    
    if extracted_count < MIN_INDICATORS:
        print(f"⚠️ 警告：提取指标数({extracted_count})低于最低要求({MIN_INDICATORS})")
        print("   建议：")
        print("   1. 检查PDF是否为扫描件（需要OCR）")
        print("   2. 检查表格格式是否复杂（尝试其他工具）")
        print("   3. 人工复核财报原文")
        financial_data["data_quality_warning"] = f"提取指标数({extracted_count})低于最低要求({MIN_INDICATORS})，请人工复核"
    
    # 3. 数据校验与单位统一
    print("正在校验数据...")
    unit_standard = financial_data.get("unit_standard", "亿元")
    validator = DataValidator(standard_unit=unit_standard)
    
    # 扁平化处理：如果返回了新结构（items嵌套），展开到顶层
    if "items" in financial_data:
        items = financial_data.pop("items")
        for key, val_obj in items.items():
            # 避免覆盖已经存在的顶层值
            if key in financial_data and financial_data[key] is not None:
                continue
            
            if isinstance(val_obj, dict):
                # 优先使用 value_unified（已换算为统一单位）
                unified_val = val_obj.get("value_unified")
                if unified_val is not None:
                    financial_data[key] = unified_val
                else:
                    # 回退到 value_original，手动换算
                    original_val = val_obj.get("value_original")
                    original_unit = val_obj.get("unit_original", unit_standard)
                    if original_val is not None:
                        financial_data[key] = validator.normalize_value(original_val, original_unit)
                    else:
                        financial_data[key] = None
                
                # 保留原始信息用于溯源
                financial_data[f"{key}_evidence"] = val_obj.get("evidence")
                
                # 映射同比变化到独立字段（关键修复）
                yoy = val_obj.get("yoy_change_pct")
                if yoy is not None:
                    # 映射到标准字段名
                    if key == "revenue":
                        financial_data["revenue_yoy"] = yoy
                    elif key == "net_income":
                        financial_data["net_income_yoy"] = yoy
                    elif key == "operating_cashflow":
                        financial_data["operating_cashflow_yoy"] = yoy
                    # 通用映射
                    financial_data[f"{key}_yoy"] = yoy
            else:
                financial_data[key] = val_obj
    
    # 全面校验
    financial_data = validate_financial_data(financial_data, validator)
    
    # 打印校验警告
    warnings = financial_data.get("validation_warnings", [])
    if warnings:
        print("=== 数据校验警告 ===")
        for w in warnings:
            print(w)
    
    print("=== 校验后数据（统一单位）===")
    print({k: v for k, v in financial_data.items() if not k.endswith("_evidence")})

    # 4. 获取历史数据（用于趋势图）
    ticker = financial_data.get("ticker") or "UNKNOWN"
    historical_data = fetch_historical_data(ticker=ticker)

    # 5. 生成图表
    print("正在生成图表...")
    chart_image_path = llm_code_runner.plot_charts(
        current=financial_data,
        history=historical_data,
    )

    # 6. 分段生成文章（按"三张表思维"）
    
    # 提取证据片段
    evidence = _pick_evidence(raw_text)
    
    # Part 1: 报告头部（期间/口径/单位声明）
    print("正在生成报告头部...")
    metadata = {
        "period": financial_data.get("period", "未知期间"),
        "scope": financial_data.get("scope", "unknown"),
        "unit_standard": unit_standard,
        "company_name": financial_data.get("company_name", ""),
        "ticker": ticker,
    }
    header = llm.chat(
        role="analyst",
        task="write_header",
        context=str(financial_data),
        metadata=metadata,
    )
    if isinstance(header, dict):
        title = header.get("title", "财报解读")
        meta_statement = header.get("metadata_statement", f"本报告全文金额统一使用{unit_standard}。")
    else:
        title = "财报解读"
        meta_statement = f"本报告全文金额统一使用{unit_standard}。"

    # Part 2: 利润表分析（严格边界）
    print("正在分析利润表...")
    profit_analysis = llm.chat(
        role="analyst",
        task="analyze_profit",
        context=evidence,
        metadata=metadata,
    )
    if not isinstance(profit_analysis, str):
        profit_analysis = str(profit_analysis)

    # Part 3: 资产负债表分析（严格边界）
    print("正在分析资产负债表...")
    balance_analysis = llm.chat(
        role="analyst",
        task="analyze_balance",
        context=evidence,
        metadata=metadata,
    )
    if not isinstance(balance_analysis, str):
        balance_analysis = str(balance_analysis)

    # Part 4: 现金流分析（严格边界）
    print("正在分析现金流...")
    cashflow_analysis = llm.chat(
        role="analyst",
        task="analyze_cashflow",
        context=evidence,
        metadata=metadata,
    )
    if not isinstance(cashflow_analysis, str):
        cashflow_analysis = str(cashflow_analysis)

    # Part 5: 风险提示（可触发格式）
    print("正在生成风险提示...")
    risks = llm.chat(
        role="analyst",
        task="summarize_risks",
        context=evidence,
        metadata=metadata,
    )
    if not isinstance(risks, str):
        risks = str(risks)

    # 7. 生成三张表格
    print("正在生成三张表格...")
    
    # 利润表
    profit_table = _generate_profit_table(financial_data, validator)
    
    # 资产负债表
    balance_table = _generate_balance_table(financial_data, validator)
    
    # 现金流量表
    cashflow_table = _generate_cashflow_table(financial_data, validator)
    
    # 8. 组装最终文章
    # 添加校验警告（如果有）
    warning_section = ""
    warnings = financial_data.get("validation_warnings", [])
    data_quality_warning = financial_data.get("data_quality_warning")
    
    if warnings or data_quality_warning:
        warning_section = "\n\n**⚠️ 数据质量警告**\n\n"
        
        if data_quality_warning:
            warning_section += f"- **{data_quality_warning}**\n"
        
        for w in warnings:
            warning_section += f"- {w}\n"
        
        warning_section += "\n**重要提示**：由于数据提取不完整，本报告的分析结论可能不准确，请务必人工复核财报原文。\n"
    
    # 图表部分（如果有图表才显示）
    chart_section = ""
    if chart_image_path:
        chart_section = f"""
## 四、核心财务图表

![财务指标可视化]({chart_image_path})

---

"""
    
    final_article = f"""# {title}

{meta_statement}

{warning_section}

---

## 一、利润表

{profit_table}

### 分析

{profit_analysis}

---

## 二、资产负债表

{balance_table}

### 分析

{balance_analysis}

---

## 三、现金流量表

{cashflow_table}

### 分析

{cashflow_analysis}

---

{chart_section}## {'五' if chart_section else '四'}、风险提示

{risks}

---

**数据溯源**：本报告所有数据均提取自财报原文，关键指标已标注证据来源。如需复核，请参考财报附注。

**免责声明**：本报告仅供参考，不构成投资建议。
"""
    return final_article
