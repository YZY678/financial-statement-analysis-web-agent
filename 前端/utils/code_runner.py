"""
图表代码运行器（重写版）：多图输出，支持趋势/收入/利润率/费用/现金流/同比等可视化。
- matplotlib 可选依赖，失败时优雅降级
- 图片路径统一使用正斜杠相对路径
- 返回 [(标题, 路径), ...] 供报告嵌入多图
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️ matplotlib未安装，图表生成功能将被禁用")

from .config import CHART_DIR

# 从项目根目录打开 report 时，output/charts/xxx 可正确找到图片
_REL_PREFIX = "output/charts"


def plot_charts(
    current: Dict[str, Any],
    history: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> List[Tuple[str, str]]:
    """
    根据当前财务数据与历史数据绘制多张图表，返回 [(标题, 相对路径), ...]。
    成功时返回多图；失败或无可绘数据时返回空列表；兼容旧调用时取第一项路径。
    """
    out = Path(output_dir or CHART_DIR)
    out.mkdir(parents=True, exist_ok=True)
    charts: List[Tuple[str, str]] = []

    if not MATPLOTLIB_AVAILABLE:
        print("⚠️ matplotlib不可用，跳过图表生成")
        print("   提示：如需图表功能，请运行 pip install matplotlib numpy")
        return charts

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    if history.get("dates") and history.get("close"):
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(history["dates"], history["close"], marker="o", markersize=4, label="收盘价", color="steelblue")
        ax.set_xticks(history["dates"][::max(1, len(history["dates"]) // 8)])
        plt.xticks(rotation=45)
        ax.legend()
        ax.set_title("股价趋势")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        p = out / "chart_trend.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("股价趋势", f"{_REL_PREFIX}/chart_trend.png"))

    revenue = _safe_float(current.get("revenue"))
    net_income = _safe_float(current.get("net_income"))
    gross_margin = _safe_float(current.get("gross_margin"))
    net_margin = _safe_float(current.get("net_margin"))
    sales_ratio = _safe_float(current.get("sales_expense_ratio"))
    admin_ratio = _safe_float(current.get("admin_expense_ratio"))
    rd_ratio = _safe_float(current.get("rd_expense_ratio"))
    cfo = _safe_float(current.get("operating_cashflow"))
    cfo_to_ni = _safe_float(current.get("cfo_to_ni_ratio"))
    revenue_yoy = _safe_float(current.get("revenue_yoy"))
    net_income_yoy = _safe_float(current.get("net_income_yoy"))
    has_data = any([revenue, net_income, gross_margin, net_margin, cfo])

    if not has_data and not charts:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis("off")
        ax.text(0.5, 0.5,
                "未抽取到可绘制的数值指标\n请检查财报表格是否正确解析",
                ha="center", va="center", fontsize=12, color="gray")
        p = out / "financial_chart.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("财务指标", f"{_REL_PREFIX}/financial_chart.png"))
        return charts

    if revenue is not None or net_income is not None:
        fig, ax = plt.subplots(figsize=(8, 5))
        labels, values, colors = [], [], []
        if revenue is not None:
            labels.append("营业收入")
            values.append(revenue / 1e8)
            colors.append("steelblue")
        if net_income is not None:
            labels.append("归母净利润")
            values.append(net_income / 1e8)
            colors.append("coral")
        x_pos = np.arange(len(labels))
        bars = ax.bar(x_pos, values, color=colors, alpha=0.8, width=0.6)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel("金额（亿元）")
        ax.set_title("收入与利润")
        ax.grid(axis="y", alpha=0.3)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{h:.2f}", ha="center", va="bottom", fontsize=10)
        plt.tight_layout()
        p = out / "chart_income_profit.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("收入与利润", f"{_REL_PREFIX}/chart_income_profit.png"))

    if gross_margin is not None or net_margin is not None:
        fig, ax = plt.subplots(figsize=(7, 5))
        labels, values, colors = [], [], []
        if gross_margin is not None:
            labels.append("毛利率")
            values.append(gross_margin)
            colors.append("mediumseagreen")
        if net_margin is not None:
            labels.append("净利率")
            values.append(net_margin)
            colors.append("orange")
        x_pos = np.arange(len(labels))
        bars = ax.bar(x_pos, values, color=colors, alpha=0.8, width=0.6)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel("比率（%）")
        ax.set_title("盈利能力")
        ax.set_ylim(0, max(values) * 1.2 if values else 100)
        ax.grid(axis="y", alpha=0.3)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{h:.2f}%", ha="center", va="bottom", fontsize=10)
        plt.tight_layout()
        p = out / "chart_margins.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("盈利能力", f"{_REL_PREFIX}/chart_margins.png"))

    if sales_ratio is not None or admin_ratio is not None or rd_ratio is not None:
        fig, ax = plt.subplots(figsize=(8, 5))
        labels, values, color_list = [], [], []
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1"]
        for label, val, c in [
            ("销售费用率", sales_ratio, colors[0]),
            ("管理费用率", admin_ratio, colors[1]),
            ("研发费用率", rd_ratio, colors[2]),
        ]:
            if val is not None:
                labels.append(label)
                values.append(val)
                color_list.append(c)
        if labels:
            x_pos = np.arange(len(labels))
            bars = ax.bar(x_pos, values, color=color_list, alpha=0.8, width=0.6)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, rotation=15, ha="right")
            ax.set_ylabel("费用率（%）")
            ax.set_title("期间费用结构")
            ax.grid(axis="y", alpha=0.3)
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{h:.2f}%", ha="center", va="bottom", fontsize=9)
            plt.tight_layout()
            p = out / "chart_expenses.png"
            fig.savefig(p, dpi=150, bbox_inches="tight")
            plt.close(fig)
            charts.append(("期间费用结构", f"{_REL_PREFIX}/chart_expenses.png"))

    if cfo is not None or cfo_to_ni is not None:
        fig, ax = plt.subplots(figsize=(8, 5))
        if cfo is not None:
            bars = ax.bar([0], [cfo / 1e8], color="purple", alpha=0.8, width=0.6)
            ax.set_xticks([0])
            ax.set_xticklabels(["经营现金流"])
            ax.set_ylabel("金额（亿元）")
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{h:.2f}", ha="center", va="bottom", fontsize=10)
        if cfo_to_ni is not None:
            ax2 = ax.twinx()
            ax2.axhline(y=100, color="gray", linestyle="--", alpha=0.5)
            ax2.bar([1], [cfo_to_ni], color="gold", alpha=0.8, width=0.6, label="CFO/净利润")
            ax2.set_ylabel("CFO/净利润（%）")
            ax2.set_ylim(0, max(150, cfo_to_ni * 1.2))
        ax.set_title("现金流质量")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p = out / "chart_cashflow.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("现金流质量", f"{_REL_PREFIX}/chart_cashflow.png"))

    if revenue_yoy is not None or net_income_yoy is not None:
        fig, ax = plt.subplots(figsize=(7, 5))
        labels, values, colors = [], [], []
        if revenue_yoy is not None:
            labels.append("收入同比")
            values.append(revenue_yoy)
            colors.append("steelblue")
        if net_income_yoy is not None:
            labels.append("净利润同比")
            values.append(net_income_yoy)
            colors.append("coral")
        x_pos = np.arange(len(labels))
        bars = ax.bar(x_pos, values, color=colors, alpha=0.8, width=0.6)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_ylabel("同比（%）")
        ax.set_title("同比增速")
        ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.8)
        ax.grid(axis="y", alpha=0.3)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{h:.1f}%", ha="center",
                    va="bottom" if h >= 0 else "top", fontsize=10)
        plt.tight_layout()
        p = out / "chart_yoy.png"
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close(fig)
        charts.append(("同比增速", f"{_REL_PREFIX}/chart_yoy.png"))

    return charts


def _safe_float(value: Any) -> Optional[float]:
    """安全转换为浮点数，失败返回None"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def plot_charts_single_path(current: Dict[str, Any], history: Dict[str, Any]) -> str:
    """兼容旧调用：返回第一张图的路径，无图时返回空字符串。"""
    charts = plot_charts(current, history)
    return charts[0][1] if charts else ""


class LLMCodeRunner:
    def plot_charts(self, current: Dict[str, Any], history: Dict[str, Any]) -> List[Tuple[str, str]]:
        return plot_charts(current, history)


llm_code_runner = LLMCodeRunner()
