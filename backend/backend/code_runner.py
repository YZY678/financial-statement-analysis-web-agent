"""
图表代码运行器（重写版）：改进数据展示，支持多维度对比。
修复：
1. matplotlib改为可选依赖，失败时优雅降级（返回空字符串）
2. 图片路径统一使用正斜杠相对路径，兼容所有Markdown渲染器
"""
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# matplotlib改为可选依赖
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️ matplotlib未安装，图表生成功能将被禁用")

from config import CHART_DIR


def plot_charts(
    current: Dict[str, Any],
    history: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> str:
    """
    根据当前财务数据与历史数据绘制图表，返回保存的图片路径。
    
    重写版改进：
    1. matplotlib改为可选依赖，失败时返回空字符串（优雅降级）
    2. 多子图布局：收入/利润、毛利率/净利率、现金流质量
    3. 同比增速可视化
    4. 费用率结构对比
    5. 中文字体、无数据提示
    6. 使用正斜杠相对路径，兼容所有Markdown渲染器（避免Windows反斜杠问题）
    
    返回值：
    - 成功：返回相对路径字符串（如 "output/charts/financial_chart.png"）
    - 失败：返回空字符串 ""
    """
    out = output_dir or CHART_DIR
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    save_path = out / "financial_chart.png"
    
    # 如果matplotlib不可用，直接返回空字符串（优雅降级）
    if not MATPLOTLIB_AVAILABLE:
        print("⚠️ matplotlib不可用，跳过图表生成")
        print("   提示：如需图表功能，请运行 pip install matplotlib numpy")
        return ""
    
    # 中文字体（Windows）
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    
    # 如果有历史数据：画趋势线
    if history.get("dates") and history.get("close"):
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(history["dates"], history["close"], marker="o", markersize=4, label="收盘价", color='steelblue')
        ax.set_xticks(history["dates"][::max(1, len(history["dates"]) // 8)])
        plt.xticks(rotation=45)
        handles, labels_ = ax.get_legend_handles_labels()
        if handles:
            ax.legend()
        ax.set_title("股价趋势")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # 返回相对路径（使用正斜杠）
        return "output/charts/financial_chart.png"
    
    # 仅有当前数据：画多维度分析图
    # 提取关键指标
    revenue = _safe_float(current.get("revenue"))
    net_income = _safe_float(current.get("net_income"))
    gross_margin = _safe_float(current.get("gross_margin"))
    net_margin = _safe_float(current.get("net_margin"))
    sales_ratio = _safe_float(current.get("sales_expense_ratio"))
    admin_ratio = _safe_float(current.get("admin_expense_ratio"))
    rd_ratio = _safe_float(current.get("rd_expense_ratio"))
    cfo = _safe_float(current.get("operating_cashflow"))
    cfo_to_ni = _safe_float(current.get("cfo_to_ni_ratio"))
    
    # 检查是否有足够数据
    has_data = any([revenue, net_income, gross_margin, net_margin, cfo])
    
    if not has_data:
        # 无数据：输出提示图
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis("off")
        ax.text(0.5, 0.5, 
                "未抽取到可绘制的数值指标\n请检查财报表格是否正确解析",
                ha="center", va="center", fontsize=12, color="gray")
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        # 返回相对路径（使用正斜杠）
        return "output/charts/financial_chart.png"
    
    # 创建多子图布局（2行2列）
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("核心财务指标分析", fontsize=16, fontweight='bold')
    
    # 子图1：收入与净利润（亿元）
    ax1 = axes[0, 0]
    if revenue is not None or net_income is not None:
        labels = []
        values = []
        colors = []
        if revenue is not None:
            labels.append("营业收入")
            values.append(revenue / 1e8)  # 转亿元
            colors.append('steelblue')
        if net_income is not None:
            labels.append("归母净利润")
            values.append(net_income / 1e8)
            colors.append('coral')
        
        x_pos = np.arange(len(labels))
        bars = ax1.bar(x_pos, values, color=colors, alpha=0.8, width=0.6)
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(labels)
        ax1.set_ylabel("金额（亿元）", fontsize=11)
        ax1.set_title("收入与利润", fontsize=12, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)
        
        # 在柱子上标注数值
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}',
                    ha='center', va='bottom', fontsize=10)
    else:
        ax1.text(0.5, 0.5, "无收入/利润数据", ha='center', va='center', transform=ax1.transAxes)
        ax1.axis('off')
    
    # 子图2：毛利率与净利率（%）
    ax2 = axes[0, 1]
    if gross_margin is not None or net_margin is not None:
        labels = []
        values = []
        colors = []
        if gross_margin is not None:
            labels.append("毛利率")
            values.append(gross_margin)
            colors.append('mediumseagreen')
        if net_margin is not None:
            labels.append("净利率")
            values.append(net_margin)
            colors.append('orange')
        
        x_pos = np.arange(len(labels))
        bars = ax2.bar(x_pos, values, color=colors, alpha=0.8, width=0.6)
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(labels)
        ax2.set_ylabel("比率（%）", fontsize=11)
        ax2.set_title("盈利能力", fontsize=12, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)
        ax2.set_ylim(0, max(values) * 1.2 if values else 100)
        
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}%',
                    ha='center', va='bottom', fontsize=10)
    else:
        ax2.text(0.5, 0.5, "无毛利率/净利率数据", ha='center', va='center', transform=ax2.transAxes)
        ax2.axis('off')
    
    # 子图3：三费率结构（%）
    ax3 = axes[1, 0]
    if sales_ratio is not None or admin_ratio is not None or rd_ratio is not None:
        labels = []
        values = []
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']
        color_list = []
        
        if sales_ratio is not None:
            labels.append("销售费用率")
            values.append(sales_ratio)
            color_list.append(colors[0])
        if admin_ratio is not None:
            labels.append("管理费用率")
            values.append(admin_ratio)
            color_list.append(colors[1])
        if rd_ratio is not None:
            labels.append("研发费用率")
            values.append(rd_ratio)
            color_list.append(colors[2])
        
        x_pos = np.arange(len(labels))
        bars = ax3.bar(x_pos, values, color=color_list, alpha=0.8, width=0.6)
        ax3.set_xticks(x_pos)
        ax3.set_xticklabels(labels, rotation=15, ha='right')
        ax3.set_ylabel("费用率（%）", fontsize=11)
        ax3.set_title("期间费用结构", fontsize=12, fontweight='bold')
        ax3.grid(axis='y', alpha=0.3)
        
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}%',
                    ha='center', va='bottom', fontsize=9)
    else:
        ax3.text(0.5, 0.5, "无费用率数据", ha='center', va='center', transform=ax3.transAxes)
        ax3.axis('off')
    
    # 子图4：现金流质量
    ax4 = axes[1, 1]
    if cfo is not None or cfo_to_ni is not None:
        labels = []
        values = []
        colors = []
        
        if cfo is not None:
            labels.append("经营现金流")
            values.append(cfo / 1e8)  # 转亿元
            colors.append('purple')
        
        if cfo_to_ni is not None:
            # 用双轴显示比率
            ax4_twin = ax4.twinx()
            ax4_twin.axhline(y=100, color='gray', linestyle='--', alpha=0.5, label='基准线(100%)')
            ax4_twin.bar([len(values)], [cfo_to_ni], color='gold', alpha=0.8, width=0.6, label='CFO/净利润')
            ax4_twin.set_ylabel("CFO/净利润（%）", fontsize=11, color='gold')
            ax4_twin.tick_params(axis='y', labelcolor='gold')
            ax4_twin.set_ylim(0, max(150, cfo_to_ni * 1.2))
            labels.append("CFO/净利润")
        
        if cfo is not None:
            x_pos = np.arange(1)
            bars = ax4.bar(x_pos, [cfo / 1e8], color='purple', alpha=0.8, width=0.6)
            ax4.set_xticks(x_pos)
            ax4.set_xticklabels(["经营现金流"])
            ax4.set_ylabel("金额（亿元）", fontsize=11, color='purple')
            ax4.tick_params(axis='y', labelcolor='purple')
            
            for bar in bars:
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.2f}',
                        ha='center', va='bottom', fontsize=10)
        
        ax4.set_title("现金流质量", fontsize=12, fontweight='bold')
        ax4.grid(axis='y', alpha=0.3)
    else:
        ax4.text(0.5, 0.5, "无现金流数据", ha='center', va='center', transform=ax4.transAxes)
        ax4.axis('off')
    
    plt.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    
    # 返回相对路径（使用正斜杠，避免Windows反斜杠问题）
    return "output/charts/financial_chart.png"


def _safe_float(value: Any) -> Optional[float]:
    """安全转换为浮点数，失败返回None"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class LLMCodeRunner:
    """与伪代码中的 llm_code_runner.plot_charts 一致。"""
    def plot_charts(self, current: Dict[str, Any], history: Dict[str, Any]) -> str:
        return plot_charts(current, history)


llm_code_runner = LLMCodeRunner()
