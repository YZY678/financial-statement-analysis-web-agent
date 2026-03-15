import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .pdf_parser import parse_pdf_with_multimodal_ai

matplotlib.use("Agg")

SUPPORTED_FORMATS = [".csv", ".xlsx", ".xls", ".pdf"]
CHART_TYPES = [
    "income_trend",
    "profit_composition",
    "balance_sheet",
    "revenue_comparison",
    "expense_breakdown",
]
DEFAULT_OUTPUT_DIR = "./reports/agent_charts"


FINANCE_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def load_financial_data(file_path: str) -> Tuple[Optional[pd.DataFrame], str]:
    if not os.path.exists(file_path):
        return None, f"文件不存在: {file_path}"

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    try:
        if ext == ".csv":
            encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin1"]
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    return df, ""
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            return None, "无法解析CSV文件，请检查文件编码和内容"
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
            return df, ""
        if ext == ".pdf":
            # 使用多模态解析获取原始文本和表格 JSON，包装为 DataFrame 供后续流程使用
            raw_text, tables_json = parse_pdf_with_multimodal_ai(file_path)
            df = pd.DataFrame([
                {
                    "raw_text": raw_text,
                    "tables_json": tables_json,
                }
            ])
            return df, ""
        return None, f"不支持的文件格式: {ext}"
    except Exception as exc:
        return None, f"文件加载失败: {str(exc)}"


def detect_financial_report_type(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "type": "unknown",
            "type_name": "未知数据",
            "has_date_column": False,
        }

    columns_lower = [str(col).lower() for col in df.columns]
    income_keywords = ["营业收入", "销售收入", "主营业务收入", "revenue", "sales", "income"]
    balance_keywords = ["资产", "负债", "权益", "asset", "liability", "equity"]
    cashflow_keywords = ["现金流", "经营", "投资", "融资", "cash", "flow"]

    scores = {"income_statement": 0, "balance_sheet": 0, "cash_flow": 0}
    for col_lower in columns_lower:
        if any(keyword in col_lower for keyword in income_keywords):
            scores["income_statement"] += 1
        if any(keyword in col_lower for keyword in balance_keywords):
            scores["balance_sheet"] += 1
        if any(keyword in col_lower for keyword in cashflow_keywords):
            scores["cash_flow"] += 1

    subject_col = next((col for col in df.columns if str(col).strip() in ["科目", "项目"]), None)
    if subject_col is not None:
        subject_values = df[subject_col].astype(str).str.replace(" ", "", regex=False).str.lower()
        for keyword in income_keywords:
            scores["income_statement"] += int(subject_values.str.contains(keyword, na=False).sum())
        for keyword in balance_keywords:
            scores["balance_sheet"] += int(subject_values.str.contains(keyword, na=False).sum())
        for keyword in cashflow_keywords:
            scores["cash_flow"] += int(subject_values.str.contains(keyword, na=False).sum())

    report_type = max(scores, key=scores.get)
    if scores[report_type] < 2:
        report_type = "general"

    type_names = {
        "income_statement": "利润表",
        "balance_sheet": "资产负债表",
        "cash_flow": "现金流量表",
        "general": "通用财经数据",
        "unknown": "未知数据",
    }

    has_date = any(
        keyword in col
        for col in columns_lower
        for keyword in ["date", "时间", "日期", "month", "year"]
    )

    return {
        "type": report_type,
        "type_name": type_names.get(report_type, "通用财经数据"),
        "has_date_column": has_date,
    }


def clean_financial_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if df is None or df.empty:
        return df, {"error": "数据为空"}

    report: Dict[str, Any] = {
        "original_shape": df.shape,
        "actions_taken": [],
    }

    df_clean = df.copy()
    original_columns = list(df_clean.columns)
    df_clean.columns = [
        str(col).strip().replace(" ", "_").replace("/", "_") for col in df_clean.columns
    ]
    report["column_mapping"] = dict(zip(original_columns, df_clean.columns))

    date_columns = []
    for col in df_clean.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ["date", "时间", "日期"]):
            try:
                df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")
                date_columns.append(col)
                report["actions_taken"].append(f"将列 '{col}' 转换为日期格式")
            except Exception:
                continue

    for col in df_clean.columns:
        if col in date_columns:
            continue
        missing_count = df_clean[col].isnull().sum()
        if missing_count > 0:
            if pd.api.types.is_numeric_dtype(df_clean[col]):
                median_val = df_clean[col].median()
                if not pd.isna(median_val):
                    df_clean[col] = df_clean[col].fillna(median_val)
                    report["actions_taken"].append(
                        f"数值列 '{col}' 的 {missing_count} 个缺失值用中位数填充"
                    )
            else:
                df_clean[col] = df_clean[col].fillna("")

    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates().reset_index(drop=True)
    after_dedup = len(df_clean)
    if before_dedup > after_dedup:
        report["actions_taken"].append(
            f"移除了 {before_dedup - after_dedup} 个重复行"
        )

    report["cleaned_shape"] = df_clean.shape
    return df_clean, report


def create_professional_chart(
    df: pd.DataFrame, chart_type: str, title: str, output_dir: str = DEFAULT_OUTPUT_DIR
) -> Tuple[Optional[str], str]:
    if df is None or df.empty:
        return None, "数据为空，无法生成图表"

    os.makedirs(output_dir, exist_ok=True)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return None, "没有有效的数值列，无法生成图表"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(ch for ch in title if ch.isalnum() or ch in ["-", "_"]) or "chart"
    filename = f"{chart_type}_{safe_title}_{timestamp}.png"
    filepath = os.path.join(output_dir, filename)

    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        if chart_type == "income_trend":
            plot_cols = numeric_cols[:3]
            date_cols = [
                col for col in df.columns if "日期" in str(col) or "date" in str(col).lower()
            ]
            x = df[date_cols[0]] if date_cols else range(len(df))
            for idx, col in enumerate(plot_cols):
                ax.plot(x, df[col], label=col, color=FINANCE_COLORS[idx % len(FINANCE_COLORS)])
            ax.set_title(title)
            ax.set_xlabel("日期" if date_cols else "序号")
            ax.set_ylabel("数值")
            ax.legend()
        elif chart_type == "revenue_comparison":
            plot_cols = numeric_cols[:6]
            last_row = df.iloc[-1]
            values = [last_row[col] for col in plot_cols]
            ax.bar(plot_cols, values, color=FINANCE_COLORS[: len(plot_cols)])
            ax.set_title(title)
            ax.set_ylabel("数值")
            ax.tick_params(axis="x", rotation=30)
        elif chart_type == "profit_composition":
            plot_cols = numeric_cols[:6]
            last_row = df.iloc[-1]
            values = [last_row[col] for col in plot_cols]
            ax.pie(values, labels=plot_cols, autopct="%1.1f%%", colors=FINANCE_COLORS)
            ax.set_title(title)
        elif chart_type == "balance_sheet":
            asset_cols = [col for col in df.columns if "资产" in str(col)]
            liability_cols = [col for col in df.columns if "负债" in str(col)]
            if asset_cols and liability_cols:
                assets = df[asset_cols].sum(axis=1)
                liabilities = df[liability_cols].sum(axis=1)
                ax.plot(assets, label="资产", color=FINANCE_COLORS[0])
                ax.plot(liabilities, label="负债", color=FINANCE_COLORS[3])
                ax.set_title(title)
                ax.set_ylabel("数值")
                ax.legend()
            else:
                ax.text(0.5, 0.5, "未找到资产/负债列", ha="center", va="center")
        elif chart_type == "expense_breakdown":
            expense_cols = [col for col in df.columns if "费用" in str(col) or "成本" in str(col)]
            plot_cols = expense_cols[:6] if expense_cols else numeric_cols[:6]
            last_row = df.iloc[-1]
            values = [last_row[col] for col in plot_cols]
            ax.barh(plot_cols, values, color=FINANCE_COLORS[: len(plot_cols)])
            ax.set_title(title)
            ax.set_xlabel("数值")
        else:
            return None, f"不支持的图表类型: {chart_type}"

        plt.tight_layout()
        fig.savefig(filepath, dpi=300, bbox_inches="tight", facecolor="white")
        return filepath, ""
    except Exception as exc:
        return None, f"图表生成失败: {str(exc)}"
    finally:
        plt.close(fig)


def _detect_date_column(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ["date", "时间", "日期", "month", "year"]):
            return col
    return None


def build_comparison_table(
    datasets: Dict[str, pd.DataFrame],
    metrics: Optional[List[str]] = None,
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    if not datasets:
        return None, []

    prepared = []
    available_metrics: List[str] = []

    for name, df in datasets.items():
        if df is None or df.empty:
            continue
        date_col = _detect_date_column(df)
        df_copy = df.copy()
        if date_col:
            df_copy["_date_key"] = pd.to_datetime(df_copy[date_col], errors="coerce")
        else:
            df_copy["_date_key"] = range(len(df_copy))

        numeric_cols = df_copy.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            continue

        if metrics:
            selected_metrics = [m for m in metrics if m in df_copy.columns]
        else:
            selected_metrics = numeric_cols[:3]

        if not selected_metrics:
            continue

        available_metrics.extend([m for m in selected_metrics if m not in available_metrics])
        cols = ["_date_key"] + selected_metrics
        df_subset = df_copy[cols].copy()
        rename_map = {metric: f"{name}:{metric}" for metric in selected_metrics}
        df_subset = df_subset.rename(columns=rename_map)
        prepared.append(df_subset)

    if not prepared:
        return None, []

    merged = prepared[0]
    for df_part in prepared[1:]:
        merged = merged.merge(df_part, on="_date_key", how="outer")

    merged = merged.sort_values("_date_key").reset_index(drop=True)
    if pd.api.types.is_datetime64_any_dtype(merged["_date_key"]):
        merged["date"] = merged["_date_key"].dt.strftime("%Y-%m-%d")
    else:
        merged["date"] = merged["_date_key"].astype(str)

    merged = merged.drop(columns=["_date_key"])
    cols = ["date"] + [col for col in merged.columns if col != "date"]
    merged = merged[cols]
    return merged, available_metrics


def create_comparison_chart(
    datasets: Dict[str, pd.DataFrame],
    metric: Optional[str] = None,
    title: str = "多文件对比",
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Tuple[Optional[str], str]:
    if not datasets:
        return None, "没有可用的数据用于对比"

    os.makedirs(output_dir, exist_ok=True)
    metric_name = metric
    values = []
    labels = []

    for name, df in datasets.items():
        if df is None or df.empty:
            continue
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            continue
        if metric_name is None:
            metric_name = numeric_cols[0]
        if metric_name not in df.columns:
            continue
        value = df[metric_name].iloc[-1]
        if pd.notna(value):
            labels.append(name)
            values.append(float(value))

    if not labels:
        return None, "无法匹配可对比的指标列"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(ch for ch in title if ch.isalnum() or ch in ["-", "_"]) or "compare"
    filename = f"compare_{safe_title}_{timestamp}.png"
    filepath = os.path.join(output_dir, filename)

    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        ax.bar(labels, values, color=FINANCE_COLORS[: len(labels)])
        ax.set_title(f"{title} ({metric_name})")
        ax.set_ylabel("数值")
        ax.tick_params(axis="x", rotation=30)
        plt.tight_layout()
        fig.savefig(filepath, dpi=300, bbox_inches="tight", facecolor="white")
        return filepath, ""
    except Exception as exc:
        return None, f"对比图表生成失败: {str(exc)}"
    finally:
        plt.close(fig)


def create_multi_metric_comparison_charts(
    datasets: Dict[str, pd.DataFrame],
    metrics: List[str],
    title: str = "多指标对比",
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    charts = []
    errors: List[str] = []
    for metric in metrics:
        chart_path, error = create_comparison_chart(
            datasets,
            metric=metric,
            title=f"{title} - {metric}",
            output_dir=output_dir,
        )
        if error or not chart_path:
            errors.append(f"{metric}: {error}")
            continue
        charts.append({
            "metric": metric,
            "path": chart_path,
            "title": f"{title} - {metric}",
        })
    return charts, errors


def analyze_financial_health(df: pd.DataFrame, report_type: str) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "report_type": report_type,
            "key_metrics": {},
            "warnings": ["数据为空"],
            "recommendations": ["请提供有效数据"],
        }

    analysis: Dict[str, Any] = {
        "report_type": report_type,
        "key_metrics": {},
        "warnings": [],
        "recommendations": [],
    }

    if report_type == "income_statement":
        revenue_cols = [col for col in df.columns if "收入" in str(col) or "revenue" in str(col).lower()]
        profit_cols = [col for col in df.columns if "利润" in str(col) or "profit" in str(col).lower()]
        if revenue_cols and profit_cols:
            revenue = df[revenue_cols[0]].iloc[-1]
            profit = df[profit_cols[0]].iloc[-1]
            if pd.notna(revenue) and pd.notna(profit) and revenue != 0:
                margin = round((profit / revenue) * 100, 2)
                analysis["key_metrics"]["profit_margin"] = margin
                if margin < 5:
                    analysis["warnings"].append("利润率偏低 (<5%)")
                elif margin > 20:
                    analysis["recommendations"].append("利润率良好 (>20%)")

    if report_type == "balance_sheet":
        asset_cols = [col for col in df.columns if "资产" in str(col)]
        liability_cols = [col for col in df.columns if "负债" in str(col)]
        if asset_cols and liability_cols:
            assets = df[asset_cols].sum(axis=1).iloc[-1]
            liabilities = df[liability_cols].sum(axis=1).iloc[-1]
            if pd.notna(assets) and pd.notna(liabilities) and assets != 0:
                ratio = round((liabilities / assets) * 100, 2)
                analysis["key_metrics"]["debt_ratio"] = ratio
                if ratio > 70:
                    analysis["warnings"].append("资产负债率偏高 (>70%)")
                elif ratio < 30:
                    analysis["recommendations"].append("资产负债率健康 (<30%)")

    if not analysis["warnings"] and not analysis["recommendations"]:
        analysis["recommendations"].append("数据质量良好，可继续生成图表")

    return analysis
