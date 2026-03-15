"""
财务报告生成主流程（重写版V2）：解决单位混乱、加总校验、三张表边界问题。
重写版V3：
1. 扩大指标抽取表格范围（50000字符）
2. matplotlib可选依赖，优雅降级
3. 图片路径使用正斜杠相对路径，兼容所有Markdown渲染器
4. PDF 抽取数据导出为 CSV/Excel 到 output/
"""
import re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from code_runner import llm_code_runner
from .config import OUTPUT_DIR
from data_validator import DataValidator, validate_financial_data
from historical_data import fetch_historical_data
from llm_client import llm
from pdf_parser import parse_pdf_with_multimodal_ai

# 中文字段名到英文字段名的映射（LLM 有时返回中文 key）
ITEMS_KEY_ALIAS = {
    "营业收入": "revenue", "营收": "revenue", "营业总收入": "revenue",
    "归母净利润": "net_income", "净利润": "net_income", "净利": "net_income",
    "毛利率": "gross_margin", "净利率": "net_margin",
    "销售费用率": "sales_expense_ratio", "管理费用率": "admin_expense_ratio", "研发费用率": "rd_expense_ratio",
    "应收账款": "accounts_receivable", "存货": "inventory", "合同负债": "contract_liability", "预收款": "contract_liability",
    "货币资金": "cash", "资产负债率": "debt_ratio",
    "经营活动产生的现金流量净额": "operating_cashflow", "经营现金流": "operating_cashflow",
    "资本开支": "capex", "分红": "dividend", "现金分红": "dividend",
}


def _to_number(v: Any) -> Any:
    """将可解析的字符串转为数字，便于表格显示具体数据。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v if (v == v) else None  # NaN
    try:
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _get_metric(data: Dict[str, Any], *keys: str):
    """按多个键名取第一个非空值，并规范为数字（用于表格与图表）。"""
    for k in keys:
        v = data.get(k)
        if v is not None:
            n = _to_number(v)
            if n is not None:
                return n
            return v
    return None


def _parse_numbers_from_report_text(text: str, unit: str = "亿元") -> Dict[str, Any]:
    """从 LLM 生成的分析文本中解析数字，补全未在表格抽取中得到的指标。仅填充 data 中缺失项。"""
    if not text or not isinstance(text, str):
        return {}
    out = {}
    # 金额类（亿元/万元，统一换算为亿元用于展示）
    amount_patterns = [
        (r"营业收入\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "revenue", 1.0),
        (r"营收\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "revenue", 1.0),
        (r"营业收入\s*[为约]?\s*([\d,]+\.?\d*)\s*万", "revenue", 0.0001),
        (r"归母净利润\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "net_income", 1.0),
        (r"净利润\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "net_income", 1.0),
        (r"经营现金流\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "operating_cashflow", 1.0),
        (r"经营活动.*现金流\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "operating_cashflow", 1.0),
        (r"应收账款\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "accounts_receivable", 1.0),
        (r"存货\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "inventory", 1.0),
        (r"货币资金\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "cash", 1.0),
        (r"合同负债\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "contract_liability", 1.0),
        (r"资本开支\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "capex", 1.0),
        (r"分红\s*[为约]?\s*([\d,]+\.?\d*)\s*亿", "dividend", 1.0),
    ]
    for pattern, key, scale in amount_patterns:
        m = re.search(pattern, text)
        if m:
            try:
                val = float(m.group(1).replace(",", "")) * scale
                out[key] = val
            except (ValueError, TypeError):
                pass
    # 比率类（%）
    ratio_patterns = [
        (r"毛利率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "gross_margin"),
        (r"净利率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "net_margin"),
        (r"销售费用率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "sales_expense_ratio"),
        (r"管理费用率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "admin_expense_ratio"),
        (r"研发费用率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "rd_expense_ratio"),
        (r"资产负债率\s*[为约]?\s*([\d,]+\.?\d*)\s*%", "debt_ratio"),
        (r"收入\s*同比\s*[增涨长]?\s*([+-]?\d+\.?\d*)\s*%", "revenue_yoy"),
        (r"营收\s*同比\s*[增涨长]?\s*([+-]?\d+\.?\d*)\s*%", "revenue_yoy"),
        (r"净利润\s*同比\s*[增涨长]?\s*([+-]?\d+\.?\d*)\s*%", "net_income_yoy"),
        (r"归母净利润\s*同比\s*[增涨长]?\s*([+-]?\d+\.?\d*)\s*%", "net_income_yoy"),
    ]
    for pattern, key in ratio_patterns:
        m = re.search(pattern, text)
        if m:
            try:
                out[key] = float(m.group(1).replace(",", ""))
            except (ValueError, TypeError):
                pass
    return out


def _generate_profit_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """仅输出有具体数据的行；文中未提及的指标不展示，避免空表。"""
    unit = validator.standard_unit
    revenue = _get_metric(data, "revenue", "营业收入", "营收")
    revenue_yoy = _get_metric(data, "revenue_yoy", "营业收入同比")
    gross_margin = _get_metric(data, "gross_margin", "毛利率")
    net_income = _get_metric(data, "net_income", "归母净利润", "净利润")
    net_income_yoy = _get_metric(data, "net_income_yoy", "净利润同比")
    net_margin = _get_metric(data, "net_margin", "净利率")
    sales_ratio = _get_metric(data, "sales_expense_ratio", "销售费用率")
    admin_ratio = _get_metric(data, "admin_expense_ratio", "管理费用率")
    rd_ratio = _get_metric(data, "rd_expense_ratio", "研发费用率")

    def _fmt_val(x):
        return validator.format_value(x) if x is not None else None
    def _fmt_pct(x):
        return validator.format_percentage(x) if x is not None else None
    def _fmt_ratio(x):
        return f"{x:.2f}%" if x is not None else None

    rows = []
    if revenue is not None or revenue_yoy is not None:
        rows.append(("**营业收入**", _fmt_val(revenue) or _fmt_pct(revenue_yoy) or "", _fmt_pct(revenue_yoy) or "", ""))
    if gross_margin is not None:
        rows.append(("**毛利率**", _fmt_ratio(gross_margin), "—", ""))
    if sales_ratio is not None:
        rows.append(("销售费用率", _fmt_ratio(sales_ratio), "—", ""))
    if admin_ratio is not None:
        rows.append(("管理费用率", _fmt_ratio(admin_ratio), "—", ""))
    if rd_ratio is not None:
        rows.append(("研发费用率", _fmt_ratio(rd_ratio), "—", ""))
    if net_income is not None or net_income_yoy is not None:
        rows.append(("**归母净利润**", _fmt_val(net_income) or _fmt_pct(net_income_yoy) or "", _fmt_pct(net_income_yoy) or "", ""))
    if net_margin is not None:
        rows.append(("**净利率**", _fmt_ratio(net_margin), "—", ""))

    if not rows:
        return f"*本表在报告与原文中均未提取到可展示数据，已省略。金额单位：{unit}*"
    header = "| 项目 | 本期金额 | 同比变化 | 备注 |\n|------|----------|----------|------|\n"
    body = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
    return header + body + f"\n\n*金额单位统一为{unit}*"


def _generate_balance_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """仅输出有具体数据的行；文中未提及的指标不展示。"""
    unit = validator.standard_unit
    revenue = _get_metric(data, "revenue", "营业收入", "营收")
    accounts_receivable = _get_metric(data, "accounts_receivable", "应收账款")
    inventory = _get_metric(data, "inventory", "存货")
    contract_liability = _get_metric(data, "contract_liability", "合同负债", "预收款")
    ar_ratio = (accounts_receivable / revenue * 100) if accounts_receivable is not None and revenue and revenue != 0 else None
    debt_ratio = _get_metric(data, "debt_ratio", "资产负债率")
    cash = _get_metric(data, "cash", "货币资金")

    def _fmt_val(x):
        return validator.format_value(x) if x is not None else None

    rows = []
    if accounts_receivable is not None:
        rows.append(("应收账款", _fmt_val(accounts_receivable), f"{ar_ratio:.2f}%" if ar_ratio is not None else "—", ""))
    if inventory is not None:
        rows.append(("存货", _fmt_val(inventory), "—", ""))
    if contract_liability is not None:
        rows.append(("合同负债/预收款", _fmt_val(contract_liability), "—", ""))
    if cash is not None:
        rows.append(("货币资金", _fmt_val(cash), "—", ""))
    if debt_ratio is not None:
        rows.append(("资产负债率", f"{debt_ratio:.2f}%", "—", ""))

    if not rows:
        return f"*本表在报告与原文中均未提取到可展示数据，已省略。金额单位：{unit}*"
    header = "| 项目 | 本期金额 | 占收入比例 | 备注 |\n|------|----------|------------|------|\n"
    body = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
    return header + body + f"\n\n*金额单位统一为{unit}*"


def _generate_cashflow_table(data: Dict[str, Any], validator: DataValidator) -> str:
    """仅输出有具体数据的行；文中未提及的指标不展示。"""
    unit = validator.standard_unit
    operating_cashflow = _get_metric(data, "operating_cashflow", "经营活动产生的现金流量净额", "经营现金流")
    net_income = _get_metric(data, "net_income", "归母净利润", "净利润")
    capex = _get_metric(data, "capex", "资本开支")
    dividend = _get_metric(data, "dividend", "分红", "现金分红")
    cfo_to_ni = data.get("cfo_to_ni_ratio")
    if cfo_to_ni is None and operating_cashflow is not None and net_income and net_income != 0:
        cfo_to_ni = (operating_cashflow / net_income) * 100
    dividend_ratio = (dividend / net_income * 100) if dividend is not None and net_income and net_income != 0 else None

    def _fmt_val(x):
        return validator.format_value(x) if x is not None else None

    rows = []
    if operating_cashflow is not None:
        rows.append(("经营活动现金流", _fmt_val(operating_cashflow), f"CFO/净利润: {cfo_to_ni:.1f}%" if cfo_to_ni is not None else "—", ">100%为优"))
    if capex is not None:
        rows.append(("资本开支", _fmt_val(capex), "—", ""))
    if dividend is not None:
        rows.append(("分红", _fmt_val(dividend), f"分红率: {dividend_ratio:.1f}%" if dividend_ratio is not None else "—", ""))

    if not rows:
        return f"*本表在报告与原文中均未提取到可展示数据，已省略。金额单位：{unit}*"
    header = "| 项目 | 本期金额 | 质量指标 | 备注 |\n|------|----------|----------|------|\n"
    body = "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows)
    return header + body + f"\n\n*金额单位统一为{unit}*"


def _llm_tables_to_markdown(tables_dict: Dict[str, Any], unit: str) -> tuple:
    """将 LLM 返回的三张表（list of dict）转为 Markdown 字符串。返回 (profit_md, balance_md, cashflow_md)。"""
    def _rows_to_md(rows: list, headers: list) -> str:
        if not rows or not isinstance(rows, list):
            return f"*本表在报告与原文中均未提取到可展示数据，已省略。金额单位：{unit}*"
        cols = list(rows[0].keys()) if rows else []
        header_line = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["------"] * len(cols)) + "|"
        body = "\n".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows)
        return header_line + "\n" + sep + "\n" + body + f"\n\n*金额单位统一为{unit}*"

    profit = tables_dict.get("利润表")
    balance = tables_dict.get("资产负债表")
    cashflow = tables_dict.get("现金流量表")
    profit_md = _rows_to_md(profit, ["项目", "本期金额", "同比变化", "备注"]) if profit else f"*本表未生成可展示数据。金额单位：{unit}*"
    balance_md = _rows_to_md(balance, ["项目", "本期金额", "占收入比例", "备注"]) if balance else f"*本表未生成可展示数据。金额单位：{unit}*"
    cashflow_md = _rows_to_md(cashflow, ["项目", "本期金额", "质量指标", "备注"]) if cashflow else f"*本表未生成可展示数据。金额单位：{unit}*"
    return profit_md, balance_md, cashflow_md


# 导出用：指标英文 key -> 中文名
_METRIC_LABELS = {
    "revenue": "营业收入", "revenue_yoy": "收入同比(%)", "net_income": "归母净利润", "net_income_yoy": "净利润同比(%)",
    "gross_margin": "毛利率(%)", "net_margin": "净利率(%)",
    "sales_expense_ratio": "销售费用率(%)", "admin_expense_ratio": "管理费用率(%)", "rd_expense_ratio": "研发费用率(%)",
    "accounts_receivable": "应收账款", "inventory": "存货", "contract_liability": "合同负债/预收款",
    "operating_cashflow": "经营现金流", "capex": "资本开支", "dividend": "分红",
    "cash": "货币资金", "debt_ratio": "资产负债率(%)", "cfo_to_ni_ratio": "CFO/净利润(%)",
    "period": "报告期间", "scope": "口径", "unit_standard": "单位", "company_name": "公司名称", "ticker": "股票代码",
}


def _export_financial_data_to_files(
    data: Dict[str, Any],
    validator: DataValidator,
    output_dir: Path,
    period_suffix: str = "",
    llm_tables: Optional[Dict[str, Any]] = None,
) -> None:
    """将 PDF 抽取的财务数据（或 LLM 生成的三张表）导出为 output 下的 CSV 与 Excel。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    unit = validator.standard_unit
    skip_keys = {"validation_warnings", "data_quality_warning", "extraction_failed", "failure_reason"}
    skip_suffix = ("_evidence", "_source")

    # 若提供了 LLM 生成的三张表，直接导出三张表；指标一览表仍从 data 生成
    if llm_tables and isinstance(llm_tables, dict):
        for name, key in [("利润表", "利润表"), ("资产负债表", "资产负债表"), ("现金流量表", "现金流量表")]:
            rows = llm_tables.get(key)
            if rows and isinstance(rows, list) and len(rows) > 0:
                pd.DataFrame(rows).to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
        try:
            with pd.ExcelWriter(output_dir / "financial_tables.xlsx", engine="openpyxl") as w:
                for name, key in [("利润表", "利润表"), ("资产负债表", "资产负债表"), ("现金流量表", "现金流量表")]:
                    rows = llm_tables.get(key)
                    if rows and isinstance(rows, list) and len(rows) > 0:
                        pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)
            print(f"   已导出: 利润表.csv, 资产负债表.csv, 现金流量表.csv, financial_tables.xlsx（来自 LLM）")
        except Exception as e:
            print(f"   已导出 CSV；Excel 未生成: {e}")
        # 继续写 financial_metrics.csv（从 data）
        rows = []
        for k, v in data.items():
            if k in skip_keys or k.endswith(skip_suffix):
                continue
            if v is None or (isinstance(v, float) and v != v):
                continue
            label = _METRIC_LABELS.get(k, k)
            if isinstance(v, (int, float)):
                rows.append({"指标英文": k, "指标中文": label, "数值": v, "单位": "%" if ("yoy" in k or "ratio" in k or "margin" in k or "expense_ratio" in k or k == "debt_ratio") else unit})
            else:
                rows.append({"指标英文": k, "指标中文": label, "数值": str(v), "单位": ""})
        if rows:
            pd.DataFrame(rows).to_csv(output_dir / "financial_metrics.csv", index=False, encoding="utf-8-sig")
        return

    # 1. 指标一览表 financial_metrics.csv
    rows = []
    for k, v in data.items():
        if k in skip_keys or k.endswith(skip_suffix):
            continue
        if v is None or (isinstance(v, float) and v != v):
            continue
        label = _METRIC_LABELS.get(k, k)
        if isinstance(v, (int, float)):
            if "yoy" in k or "ratio" in k or "margin" in k or "expense_ratio" in k or k == "debt_ratio":
                rows.append({"指标英文": k, "指标中文": label, "数值": v, "单位": "%"})
            else:
                rows.append({"指标英文": k, "指标中文": label, "数值": v, "单位": unit})
        else:
            rows.append({"指标英文": k, "指标中文": label, "数值": str(v), "单位": ""})
    if rows:
        pd.DataFrame(rows).to_csv(output_dir / "financial_metrics.csv", index=False, encoding="utf-8-sig")
        print(f"   已导出: {output_dir / 'financial_metrics.csv'}")

    # 2. 三张表（仅含有数据的行，与报告一致）
    def _v(x):
        return validator.format_value(x) if x is not None else None
    def _p(x):
        return validator.format_percentage(x) if x is not None else None
    def _r(x):
        return f"{x:.2f}%" if x is not None else None

    revenue = _get_metric(data, "revenue", "营业收入", "营收")
    revenue_yoy = _get_metric(data, "revenue_yoy", "营业收入同比")
    gross_margin = _get_metric(data, "gross_margin", "毛利率")
    net_income = _get_metric(data, "net_income", "归母净利润", "净利润")
    net_income_yoy = _get_metric(data, "net_income_yoy", "净利润同比")
    net_margin = _get_metric(data, "net_margin", "净利率")
    sales_ratio = _get_metric(data, "sales_expense_ratio", "销售费用率")
    admin_ratio = _get_metric(data, "admin_expense_ratio", "管理费用率")
    rd_ratio = _get_metric(data, "rd_expense_ratio", "研发费用率")

    profit_rows = []
    if revenue is not None or revenue_yoy is not None:
        profit_rows.append({"项目": "营业收入", "本期金额": _v(revenue) or _p(revenue_yoy), "同比变化": _p(revenue_yoy) or "", "备注": ""})
    if gross_margin is not None:
        profit_rows.append({"项目": "毛利率", "本期金额": _r(gross_margin), "同比变化": "", "备注": ""})
    if sales_ratio is not None:
        profit_rows.append({"项目": "销售费用率", "本期金额": _r(sales_ratio), "同比变化": "", "备注": ""})
    if admin_ratio is not None:
        profit_rows.append({"项目": "管理费用率", "本期金额": _r(admin_ratio), "同比变化": "", "备注": ""})
    if rd_ratio is not None:
        profit_rows.append({"项目": "研发费用率", "本期金额": _r(rd_ratio), "同比变化": "", "备注": ""})
    if net_income is not None or net_income_yoy is not None:
        profit_rows.append({"项目": "归母净利润", "本期金额": _v(net_income) or _p(net_income_yoy), "同比变化": _p(net_income_yoy) or "", "备注": ""})
    if net_margin is not None:
        profit_rows.append({"项目": "净利率", "本期金额": _r(net_margin), "同比变化": "", "备注": ""})
    if profit_rows:
        profit_df = pd.DataFrame(profit_rows)
        profit_df.to_csv(output_dir / "利润表.csv", index=False, encoding="utf-8-sig")

    ar = _get_metric(data, "accounts_receivable", "应收账款")
    inv = _get_metric(data, "inventory", "存货")
    cl = _get_metric(data, "contract_liability", "合同负债", "预收款")
    ar_ratio = (ar / revenue * 100) if ar is not None and revenue and revenue != 0 else None
    cash = _get_metric(data, "cash", "货币资金")
    debt_ratio = _get_metric(data, "debt_ratio", "资产负债率")
    balance_rows = []
    if ar is not None:
        balance_rows.append({"项目": "应收账款", "本期金额": _v(ar), "占收入比例": f"{ar_ratio:.2f}%" if ar_ratio is not None else "", "备注": ""})
    if inv is not None:
        balance_rows.append({"项目": "存货", "本期金额": _v(inv), "占收入比例": "", "备注": ""})
    if cl is not None:
        balance_rows.append({"项目": "合同负债/预收款", "本期金额": _v(cl), "占收入比例": "", "备注": ""})
    if cash is not None:
        balance_rows.append({"项目": "货币资金", "本期金额": _v(cash), "占收入比例": "", "备注": ""})
    if debt_ratio is not None:
        balance_rows.append({"项目": "资产负债率", "本期金额": f"{debt_ratio:.2f}%", "占收入比例": "", "备注": ""})
    if balance_rows:
        balance_df = pd.DataFrame(balance_rows)
        balance_df.to_csv(output_dir / "资产负债表.csv", index=False, encoding="utf-8-sig")

    cfo = _get_metric(data, "operating_cashflow", "经营现金流", "经营活动产生的现金流量净额")
    ni = _get_metric(data, "net_income", "归母净利润", "净利润")
    capex = _get_metric(data, "capex", "资本开支")
    div = _get_metric(data, "dividend", "分红", "现金分红")
    cfo_to_ni = data.get("cfo_to_ni_ratio")
    if cfo_to_ni is None and cfo is not None and ni and ni != 0:
        cfo_to_ni = (cfo / ni) * 100
    div_ratio = (div / ni * 100) if div is not None and ni and ni != 0 else None
    cashflow_rows = []
    if cfo is not None:
        cashflow_rows.append({"项目": "经营活动现金流", "本期金额": _v(cfo), "质量指标": f"CFO/净利润: {cfo_to_ni:.1f}%" if cfo_to_ni is not None else "", "备注": ">100%为优"})
    if capex is not None:
        cashflow_rows.append({"项目": "资本开支", "本期金额": _v(capex), "质量指标": "", "备注": ""})
    if div is not None:
        cashflow_rows.append({"项目": "分红", "本期金额": _v(div), "质量指标": f"分红率: {div_ratio:.1f}%" if div_ratio is not None else "", "备注": ""})
    if cashflow_rows:
        cashflow_df = pd.DataFrame(cashflow_rows)
        cashflow_df.to_csv(output_dir / "现金流量表.csv", index=False, encoding="utf-8-sig")

    exported = [s for s, r in [("利润表", profit_rows), ("资产负债表", balance_rows), ("现金流量表", cashflow_rows)] if r]
    if exported:
        print(f"   已导出: {', '.join(exported)}.csv")

    # 3. 合并为一个 Excel（仅当至少有一张表有数据）
    try:
        if profit_rows or balance_rows or cashflow_rows:
            with pd.ExcelWriter(output_dir / "financial_tables.xlsx", engine="openpyxl") as w:
                if profit_rows:
                    pd.DataFrame(profit_rows).to_excel(w, sheet_name="利润表", index=False)
                if balance_rows:
                    pd.DataFrame(balance_rows).to_excel(w, sheet_name="资产负债表", index=False)
                if cashflow_rows:
                    pd.DataFrame(cashflow_rows).to_excel(w, sheet_name="现金流量表", index=False)
            print(f"   已导出: {output_dir / 'financial_tables.xlsx'}")
    except Exception as e:
        print(f"   未生成 Excel（需安装 openpyxl）: {e}")


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
    from .config import MIN_INDICATORS
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
        if isinstance(items, list):
            # LLM 有时返回 list 而非 dict，统一转为 dict
            _normalized = {}
            for elem in items:
                if isinstance(elem, dict):
                    if len(elem) == 1:
                        k, v = next(iter(elem.items()))
                        _normalized[k] = v
                    elif "key" in elem:
                        _normalized[elem["key"]] = elem
                    elif "name" in elem:
                        _normalized[elem["name"]] = elem
            items = _normalized
        if not isinstance(items, dict):
            items = {}
        for raw_key, val_obj in items.items():
            key = ITEMS_KEY_ALIAS.get(raw_key, raw_key) if isinstance(raw_key, str) else raw_key
            if key in financial_data and financial_data[key] is not None:
                continue
            if isinstance(val_obj, dict):
                unified_val = val_obj.get("value_unified")
                if unified_val is not None:
                    financial_data[key] = _to_number(unified_val) if _to_number(unified_val) is not None else unified_val
                else:
                    original_val = val_obj.get("value_original")
                    original_unit = val_obj.get("unit_original", unit_standard)
                    if original_val is not None:
                        financial_data[key] = validator.normalize_value(original_val, original_unit)
                    else:
                        financial_data[key] = None
                financial_data[f"{key}_evidence"] = val_obj.get("evidence")
                yoy = val_obj.get("yoy_change_pct")
                if yoy is not None:
                    if key == "revenue":
                        financial_data["revenue_yoy"] = _to_number(yoy) or yoy
                    elif key == "net_income":
                        financial_data["net_income_yoy"] = _to_number(yoy) or yoy
                    elif key == "operating_cashflow":
                        financial_data["operating_cashflow_yoy"] = _to_number(yoy) or yoy
                    financial_data[f"{key}_yoy"] = _to_number(yoy) or yoy
            else:
                financial_data[key] = _to_number(val_obj) if _to_number(val_obj) is not None else val_obj
    
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

    # 5. 生成图表（多图：趋势/收入利润/利润率/费用/现金流/同比）
    print("正在生成图表...")
    chart_list = llm_code_runner.plot_charts(
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

    # 6.5 从 LLM 分析文本中解析数字补全数据（仅填充缺失项，避免空表）
    combined_analysis = (profit_analysis or "") + (balance_analysis or "") + (cashflow_analysis or "")
    parsed = _parse_numbers_from_report_text(combined_analysis, unit_standard)
    for k, v in parsed.items():
        if financial_data.get(k) is None and v is not None:
            financial_data[k] = v
    if parsed:
        print(f"   从分析文本补全 {len(parsed)} 个指标")

    # 7. 生成三张表格：优先调用 LLM 生成表格，失败则用本地规则生成
    print("正在生成三张表格...")
    llm_tables = None
    try:
        tables_ctx = {k: v for k, v in financial_data.items() if not k.endswith("_evidence") and k not in ("validation_warnings", "data_quality_warning", "extraction_failed", "failure_reason")}
        llm_tables = llm.chat(
            role="analyst",
            task="generate_tables",
            context=str(tables_ctx)[:12000],
            metadata=metadata,
        )
        if isinstance(llm_tables, dict) and (llm_tables.get("利润表") or llm_tables.get("资产负债表") or llm_tables.get("现金流量表")):
            profit_table, balance_table, cashflow_table = _llm_tables_to_markdown(llm_tables, unit_standard)
            print("   已使用 LLM 生成的三张表")
        else:
            llm_tables = None
    except Exception as e:
        print(f"   LLM 生成表格未使用（将用本地规则）: {e}")
        llm_tables = None

    if llm_tables is None:
        profit_table = _generate_profit_table(financial_data, validator)
        balance_table = _generate_balance_table(financial_data, validator)
        cashflow_table = _generate_cashflow_table(financial_data, validator)

    # 7.5 导出表格数据到 output/（若为 LLM 表则直接导出其内容）
    print("正在导出表格数据到 output/...")
    _export_financial_data_to_files(financial_data, validator, OUTPUT_DIR, llm_tables=llm_tables)
    
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
    
    chart_section = "\n## 四、财务可视化\n\n"
    if chart_list:
        for title, path in chart_list:
            chart_section += f"### {title}\n\n![{title}]({path})\n\n"
        chart_section += "---\n\n"
    else:
        chart_section += "*（未生成图表：请确认已安装 matplotlib 与 numpy，且报告中抽取到有效数值指标；图表文件将保存在 output/charts/ 目录。）*\n\n---\n\n"
    
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
