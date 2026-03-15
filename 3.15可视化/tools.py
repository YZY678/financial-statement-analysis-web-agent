"""
专业财经可视化工具集
功能：文件加载、数据清洗、专业图表生成
版本：v3.1 - 修复图表标注问题
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.cm as cm
matplotlib.use('Agg')
import os
import sys
import warnings
from datetime import datetime
import re
from typing import Tuple, Dict, Any, Optional, List, Union

# 抑制警告
warnings.filterwarnings('ignore')

# ========== 全局配置 ==========
# 1. 中文字体配置
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Microsoft YaHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 2. 专业财经图表样式
_chart_config = {
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.titlesize': 14,
    'figure.figsize': (12, 8),
    'figure.constrained_layout.use': True,
    'figure.constrained_layout.h_pad': 0.1,
    'figure.constrained_layout.w_pad': 0.1,
    'figure.titleweight': 'bold',
    'savefig.bbox': 'tight',
    'savefig.facecolor': 'white',
    'axes.facecolor': 'white',
    'figure.facecolor': 'white',
    'legend.frameon': True,
    'legend.framealpha': 0.9,
}
plt.rcParams.update(_chart_config)

# ============================================================================
# 1. 颜色管理工具
# ============================================================================

class ColorManager:
    """颜色管理工具 - 统一管理所有图表颜色"""

    # 财经配色方案
    FINANCE_COLORS = [
        '#1f77b4',  # 蓝色 - 收入/主色
        '#ff7f0e',  # 橙色 - 成本
        '#2ca02c',  # 绿色 - 利润
        '#d62728',  # 红色 - 警告/负债
        '#9467bd',  # 紫色 - 资产
        '#8c564b',  # 棕色 - 费用
        '#e377c2',  # 粉色 - 权益
        '#7f7f7f',  # 灰色 - 中性
        '#bcbd22',  # 黄色 - 特殊
        '#17becf'   # 青色 - 特殊
    ]

    # 业务指标颜色映射
    BUSINESS_COLORS = {
        'revenue': '#1f77b4',   # 蓝色 - 收入
        'cost': '#ff7f0e',      # 橙色 - 成本
        'expense': '#2ca02c',   # 绿色 - 费用
        'profit': '#d62728',    # 红色 - 利润
        'asset': '#9467bd',     # 紫色 - 资产
        'liability': '#8c564b', # 棕色 - 负债
        'equity': '#e377c2',    # 粉色 - 权益
        'other': '#7f7f7f'      # 灰色 - 其他
    }

    @classmethod
    def get_color_by_index(cls, index: int) -> str:
        """根据索引获取颜色"""
        return cls.FINANCE_COLORS[index % len(cls.FINANCE_COLORS)]

    @classmethod
    def get_color_by_business_type(cls, column_name: str) -> str:
        """根据列名业务类型获取颜色"""
        col_lower = str(column_name).lower()

        if any(keyword in col_lower for keyword in ['收入', 'revenue', 'sales']):
            return cls.BUSINESS_COLORS['revenue']
        elif any(keyword in col_lower for keyword in ['成本', 'cost']):
            return cls.BUSINESS_COLORS['cost']
        elif any(keyword in col_lower for keyword in ['费用', 'expense']):
            return cls.BUSINESS_COLORS['expense']
        elif any(keyword in col_lower for keyword in ['利润', 'profit']):
            return cls.BUSINESS_COLORS['profit']
        elif any(keyword in col_lower for keyword in ['资产', 'asset']):
            return cls.BUSINESS_COLORS['asset']
        elif any(keyword in col_lower for keyword in ['负债', 'liability', 'debt']):
            return cls.BUSINESS_COLORS['liability']
        elif any(keyword in col_lower for keyword in ['权益', 'equity']):
            return cls.BUSINESS_COLORS['equity']
        else:
            return cls.BUSINESS_COLORS['other']

    @classmethod
    def get_colormap_colors(cls, n_colors: int, cmap_name: str = 'Set3') -> list:
        """获取colormap颜色"""
        cmap = cm.get_cmap(cmap_name)
        return [cmap(i) for i in np.linspace(0, 1, n_colors)]


# ============================================================================
# 2. 智能标题生成工具
# ============================================================================

class TitleGenerator:
    """智能标题生成工具 - 统一处理所有图表标题"""

    def __init__(self):
        self.chart_type_names = {
            "income_trend": "趋势分析图",
            "profit_composition": "构成分析图",
            "balance_sheet": "资产负债分析图",
            "revenue_comparison": "对比分析图",
            "expense_breakdown": "费用分析图"
        }

        self.business_keywords = {
            'revenue': ['营业收入', '销售收入', 'revenue', 'sales', 'income', '营收'],
            'cost': ['营业成本', '成本', 'cost'],
            'expense': ['费用', 'expense', '运营费用', '销售费用', '管理费用'],
            'profit': ['利润', 'profit', '毛利', '净利'],
            'asset': ['资产', 'asset', '负债', 'liability', '权益', 'equity']
        }

    def generate_title(self, df: pd.DataFrame, chart_type: str) -> str:
        """
        生成智能图表标题
        返回：处理好的标题（可能包含换行符）
        """
        # 获取图表类型描述
        chart_desc = self.chart_type_names.get(chart_type, "分析图")

        # 分析数据特征
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not numeric_cols:
            return f"财务{chart_desc}"

        # 识别核心业务指标
        indicators = self._analyze_indicators(df, numeric_cols)

        # 构建标题
        if len(indicators['primary']) <= 2:
            # 指标少，直接列出
            indicator_desc = "、".join(indicators['primary'][:2])
            title = f"{indicator_desc}{chart_desc}"
        else:
            # 指标多，概括描述
            first_indicator = indicators['primary'][0] if indicators['primary'] else numeric_cols[0]
            total_count = len(numeric_cols)
            title = f"{first_indicator}等{total_count}项指标{chart_desc}"

        # 智能换行处理
        title = self._apply_smart_wrapping(title)

        return title

    def _analyze_indicators(self, df: pd.DataFrame, numeric_cols: List[str]) -> Dict[str, List[str]]:
        """分析数据中的业务指标"""
        indicators = {
            'primary': [],
            'revenue': [],
            'cost': [],
            'expense': [],
            'profit': [],
            'asset': []
        }

        for col in df.columns:
            col_lower = str(col).lower()
            col_name = str(col)

            # 检查每个分类
            for category, keywords in self.business_keywords.items():
                for keyword in keywords:
                    if keyword in col_lower and col_name not in indicators[category]:
                        indicators[category].append(col_name)
                        if col_name not in indicators['primary']:
                            indicators['primary'].append(col_name)
                        break

        # 如果没有识别到业务指标，使用前几个数值列
        if not indicators['primary'] and numeric_cols:
            indicators['primary'] = numeric_cols[:min(3, len(numeric_cols))]

        return indicators

    def _apply_smart_wrapping(self, title: str, max_length: int = 20) -> str:
        """智能换行处理"""
        # 计算显示长度（中文字符算2个宽度）
        display_length = 0
        for char in title:
            if '\u4e00-\u9fff' in char:
                display_length += 2
            else:
                display_length += 1

        if display_length <= max_length:
            return title

        # 寻找最佳换行点
        break_points = ["、", "与", "和", "及", "等"]

        for break_point in break_points:
            if break_point in title:
                parts = title.split(break_point, 1)
                if len(parts) == 2:
                    part1_len = sum(2 if '\u4e00-\u9fff' in c else 1 for c in parts[0])
                    part2_len = sum(2 if '\u4e00-\u9fff' in c else 1 for c in parts[1])

                    if part1_len < max_length and part2_len < max_length:
                        return f"{parts[0]}{break_point}\n{parts[1]}"

        # 在中间位置寻找合适换行点
        mid_point = len(title) // 2
        for i in range(mid_point, len(title)):
            if title[i] in ["分", "析", "图", "表", "数", "据"]:
                return f"{title[:i]}\n{title[i:]}"

        # 强制在中间换行
        return f"{title[:mid_point]}\n{title[mid_point:]}"


# ============================================================================
# 3. 图表标注工具
# ============================================================================

class ChartAnnotator:
    """图表标注工具 - 统一处理所有图表标注"""

    def __init__(self):
        self.color_manager = ColorManager()

    def add_title_and_labels(self, fig, title: str, ax=None):
        """添加标题和坐标轴标签"""
        if ax is None:
            # 为整个图表添加标题
            fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
        else:
            # 为子图添加标题
            ax.set_title(title, fontsize=12, fontweight='bold')

    def add_axis_labels(self, ax, xlabel: str = None, ylabel: str = None):
        """添加坐标轴标签"""
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=10)

    def add_legend(self, ax, labels: List[str], location: str = 'best'):
        """添加图例"""
        if labels:
            ax.legend(labels=labels, loc=location, fontsize=9, frameon=True, framealpha=0.9)

    def format_axis_ticks(self, ax, rotate_x: bool = False, rotate_y: bool = False):
        """格式化坐标轴刻度"""
        if rotate_x:
            ax.tick_params(axis='x', rotation=45)
        if rotate_y:
            ax.tick_params(axis='y', rotation=45)

    def add_grid(self, ax, alpha: float = 0.3):
        """添加网格"""
        ax.grid(True, alpha=alpha, linestyle='--')


# ============================================================================
# 4. 文件处理工具
# ============================================================================

def load_financial_data(file_path: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    加载财经数据文件
    返回：(DataFrame, 错误信息) 元组
    """
    if not os.path.exists(file_path):
        return None, f"文件不存在: {file_path}"

    file_ext = os.path.splitext(file_path)[1].lower()

    try:
        if file_ext == '.csv':
            return _load_csv_file(file_path)
        elif file_ext in ['.xlsx', '.xls']:
            return _load_excel_file(file_path)
        else:
            return None, f"不支持的文件格式: {file_ext}"

    except FileNotFoundError as file_error:
        return None, f"文件未找到: {str(file_error)}"
    except PermissionError as perm_error:
        return None, f"无权限读取文件: {str(perm_error)}"
    except Exception as general_error:
        return None, f"文件加载失败: {str(general_error)}"


def _load_csv_file(file_path: str) -> Tuple[Optional[pd.DataFrame], str]:
    """加载CSV文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin1', 'utf-8-sig']
    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            print(f"✅ 使用编码 {encoding} 成功加载CSV文件")
            return df, ""
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return None, "无法解析CSV文件，请检查文件编码和内容"


def _load_excel_file(file_path: str) -> Tuple[Optional[pd.DataFrame], str]:
    """加载Excel文件"""
    try:
        df = pd.read_excel(file_path)
        return df, ""
    except Exception as excel_error:
        return None, f"Excel文件读取失败: {str(excel_error)}"


def detect_financial_report_type(df: pd.DataFrame) -> Dict[str, Any]:
    """检测财经报表类型"""
    if df is None or df.empty:
        return {
            'type': 'unknown',
            'type_name': '未知数据',
            'has_date_column': False
        }

    columns_lower = [str(col).lower() for col in df.columns]

    # 定义关键词
    income_keywords = ['营业收入', '销售收入', '主营业务收入', 'revenue', 'sales', 'income']
    balance_keywords = ['资产', '负债', '权益', 'asset', 'liability', 'equity']
    cashflow_keywords = ['现金流', '经营', '投资', '融资', 'cash', 'flow']

    scores = {
        'income_statement': 0,
        'balance_sheet': 0,
        'cash_flow': 0
    }

    for col_lower in columns_lower:
        for keyword in income_keywords:
            if keyword in col_lower:
                scores['income_statement'] += 1
                break

        for keyword in balance_keywords:
            if keyword in col_lower:
                scores['balance_sheet'] += 1
                break

        for keyword in cashflow_keywords:
            if keyword in col_lower:
                scores['cash_flow'] += 1
                break

    report_type = max(scores, key=scores.get)

    if scores[report_type] < 2:
        report_type = 'general'

    type_names = {
        'income_statement': '利润表',
        'balance_sheet': '资产负债表',
        'cash_flow': '现金流量表',
        'general': '通用财经数据',
        'unknown': '未知数据'
    }

    return {
        'type': report_type,
        'type_name': type_names.get(report_type, '通用财经数据'),
        'has_date_column': any(keyword in col for col in columns_lower
                              for keyword in ['date', '时间', '日期', 'month', 'year'])
    }


# ============================================================================
# 5. 数据清洗和格式化工具
# ============================================================================

def clean_financial_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """清洗财经数据"""
    if df is None or df.empty:
        return df, {'error': '数据为空'}

    cleaning_report: Dict[str, Any] = {
        'original_shape': df.shape,
        'actions_taken': []
    }

    df_clean = df.copy()

    # 列名标准化
    original_columns = list(df_clean.columns)
    df_clean.columns = [str(col).strip().replace(' ', '_').replace('/', '_')
                       for col in df_clean.columns]
    cleaning_report['column_mapping'] = dict(zip(original_columns, df_clean.columns))

    # 识别和处理日期列
    date_columns = _identify_date_columns(df_clean, cleaning_report)

    # 处理缺失值
    _handle_missing_values(df_clean, date_columns, cleaning_report)

    # 移除重复行
    _remove_duplicates(df_clean, cleaning_report)

    # 重置索引
    df_clean.reset_index(drop=True, inplace=True)
    cleaning_report['cleaned_shape'] = df_clean.shape

    return df_clean, cleaning_report


def _identify_date_columns(df: pd.DataFrame, cleaning_report: Dict[str, Any]) -> List[str]:
    """识别日期列"""
    date_columns: List[str] = []
    for col in df.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ['date', '时间', '日期']):
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                date_columns.append(col)
                cleaning_report['actions_taken'].append(f"将列 '{col}' 转换为日期格式")
            except Exception:
                pass
    return date_columns


def _handle_missing_values(df: pd.DataFrame, date_columns: List[str], cleaning_report: Dict[str, Any]) -> None:
    """处理缺失值"""
    for col in df.columns:
        if col in date_columns:
            continue

        missing_count = df[col].isnull().sum()
        if missing_count > 0:
            if pd.api.types.is_numeric_dtype(df[col]):
                median_val = df[col].median()
                if not pd.isna(median_val):
                    df[col].fillna(median_val, inplace=True)
                    cleaning_report['actions_taken'].append(
                        f"数值列 '{col}' 的 {missing_count} 个缺失值用中位数填充"
                    )
            else:
                df[col].fillna('', inplace=True)


def _remove_duplicates(df: pd.DataFrame, cleaning_report: Dict[str, Any]) -> None:
    """移除重复行"""
    before_dedup = len(df)
    df.drop_duplicates(inplace=True)
    after_dedup = len(df)

    if before_dedup > after_dedup:
        cleaning_report['actions_taken'].append(
            f"移除了 {before_dedup - after_dedup} 个重复行"
        )


# ============================================================================
# 6. 核心绘图工具（只负责绘图）
# ============================================================================

def _create_income_trend_chart(df: pd.DataFrame) -> plt.Figure:
    """创建收入趋势图 - 只负责绘图"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # 获取数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        axes[0, 0].text(0.5, 0.5, '无有效数值数据',
                        ha='center', va='center', fontsize=12)
        return fig

    # 获取颜色管理器
    color_manager = ColorManager()

    # 1. 主趋势图
    ax1 = axes[0, 0]
    date_cols = [col for col in df.columns
                 if '日期' in str(col) or 'date' in str(col).lower()]

    plot_cols = numeric_cols[:3]

    if date_cols and not df.empty and len(df) > 1:
        date_col = date_cols[0]
        for i, col in enumerate(plot_cols):
            color = color_manager.get_color_by_business_type(col)
            data_series = pd.to_numeric(df[col], errors='coerce')
            data = data_series.dropna()
            dates = df[date_col].iloc[:len(data)]

            if len(data) > 0:
                # 为每条线添加标签
                ax1.plot(dates, data.values, marker='o',
                         linewidth=2.5, color=color, label=col, markersize=6)
    else:
        for i, col in enumerate(plot_cols):
            color = color_manager.get_color_by_business_type(col)
            data_series = pd.to_numeric(df[col], errors='coerce')
            data = data_series.dropna()

            if len(data) > 0:
                # 为每条线添加标签
                ax1.plot(range(len(data)), data.values, marker='o',
                         linewidth=2.5, color=color, label=col, markersize=6)

    # 2. 饼图
    ax2 = axes[0, 1]
    if not df.empty and len(plot_cols) > 1:
        last_row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
        sizes = []
        labels = []

        for col in plot_cols:
            if col in last_row:
                val = last_row[col]
                if not pd.isna(val) and val > 0:
                    sizes.append(float(val))
                    labels.append(col)

        if sizes:
            colors = color_manager.get_colormap_colors(len(sizes), 'Set3')
            # 保存饼图的对象用于图例
            wedges, texts, autotexts = ax2.pie(sizes, colors=colors, autopct='%1.1f%%',
                                               startangle=90, pctdistance=0.85)
            # 添加图例标签
            ax2.pie_wedges = wedges
            ax2.pie_labels = labels

    ax2.axis('equal')

    # 3. 增长率分析
    ax3 = axes[1, 0]
    if len(df) > 1 and len(plot_cols) > 0:
        primary_col = plot_cols[0]
        data_series = pd.to_numeric(df[primary_col], errors='coerce')
        data = data_series.dropna()

        if len(data) > 1:
            growth_rates = data.pct_change() * 100
            colors = ['green' if x >= 0 else 'red' for x in growth_rates[1:]]
            x_positions = range(1, len(growth_rates))

            # 为每个柱子添加标签
            bars = ax3.bar(x_positions, growth_rates[1:].values, color=colors, alpha=0.7)
            ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            # 添加数值标签
            for bar, val in zip(bars, growth_rates[1:]):
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height + (1 if height >= 0 else -3),
                         f'{val:.1f}%', ha='center', va='bottom' if height >= 0 else 'top',
                         fontsize=8, rotation=90)

    # 4. 数据统计
    ax4 = axes[1, 1]
    if not df.empty and len(plot_cols) > 0:
        stats_text = ""
        for i, col in enumerate(plot_cols[:2]):
            if col in df.columns:
                data_series = pd.to_numeric(df[col], errors='coerce')
                data = data_series.dropna()
                if len(data) > 0:
                    stats_text += f"{col}:\n"
                    stats_text += f"  样本数: {len(data)}\n"
                    stats_text += f"  平均值: {data.mean():.2f}\n"
                    stats_text += f"  最大值: {data.max():.2f}\n"
                    stats_text += f"  最小值: {data.min():.2f}\n\n"

        ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes,
                 fontsize=9, verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax4.axis('off')
    else:
        ax4.text(0.5, 0.5, '无有效数据统计',
                 ha='center', va='center', fontsize=10)
        ax4.axis('off')

    return fig


def _create_profit_composition_chart(df: pd.DataFrame) -> plt.Figure:
    """创建利润构成图 - 只负责绘图"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        axes[0].text(0.5, 0.5, '无有效数值数据',
                     ha='center', va='center', fontsize=12)
        axes[1].text(0.5, 0.5, '无有效数值数据',
                     ha='center', va='center', fontsize=12)
        return fig

    # 获取颜色管理器
    color_manager = ColorManager()

    # 1. 饼图
    ax1 = axes[0]
    if not df.empty:
        last_row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
        sizes = []
        labels = []

        for col in numeric_cols[:6]:  # 最多显示6个
            if col in last_row:
                val = last_row[col]
                if not pd.isna(val) and val > 0:
                    sizes.append(float(val))
                    labels.append(col)

        if sizes:
            colors = color_manager.get_colormap_colors(len(sizes), 'Set3')
            # 保存饼图的对象用于图例
            wedges, texts, autotexts = ax1.pie(sizes, colors=colors, autopct='%1.1f%%',
                                               startangle=90, pctdistance=0.85)
            # 添加图例标签
            ax1.pie_wedges = wedges
            ax1.pie_labels = labels

    ax1.axis('equal')

    # 2. 条形图
    ax2 = axes[1]
    if not df.empty and len(numeric_cols) > 0:
        data_row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
        values = []
        labels_bar = []

        for col in numeric_cols[:8]:
            if col in data_row:
                val = data_row[col]
                if not pd.isna(val):
                    values.append(float(val))
                    labels_bar.append(col)

        if values:
            y_pos = np.arange(len(values))
            colors_bar = color_manager.get_colormap_colors(len(values), 'viridis')

            bars = ax2.barh(y_pos, values, color=colors_bar, alpha=0.7)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(labels_bar)
            ax2.invert_yaxis()

            # 添加数值标签
            for bar, val in zip(bars, values):
                width = bar.get_width()
                ax2.text(width + 0.01 * max(values), bar.get_y() + bar.get_height()/2.,
                         f'{val:,.0f}', ha='left', va='center', fontsize=9)

    return fig


def _create_revenue_comparison_chart(df: pd.DataFrame) -> plt.Figure:
    """创建收入对比图 - 只负责绘图"""
    fig, ax = plt.subplots(figsize=(14, 9))

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        ax.text(0.5, 0.5, '无有效数值数据，无法生成对比图',
                ha='center', va='center', fontsize=12)
        return fig

    plot_cols = numeric_cols[:6]

    if not df.empty:
        data_row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
        values = []
        labels = []

        for col in plot_cols:
            if col in data_row:
                val = data_row[col]
                if isinstance(val, (int, float, np.integer, np.floating)):
                    if not pd.isna(val):
                        values.append(float(val))
                        labels.append(col)

        if values and len(values) > 0:
            x_pos = np.arange(len(values))
            # 获取颜色管理器
            color_manager = ColorManager()
            colors = [color_manager.get_color_by_business_type(col) for col in plot_cols[:len(values)]]

            bars = ax.bar(x_pos, values, color=colors, alpha=0.85,
                          edgecolor='black', linewidth=1.2)

            # 保存柱状图对象用于图例
            ax.bar_chart_bars = bars
            ax.bar_chart_labels = labels

            # 添加数值标签
            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.01 * max(values),
                         f'{val:,.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    return fig


def _create_expense_breakdown_chart(df: pd.DataFrame) -> plt.Figure:
    """创建费用分解图 - 只负责绘图"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    # 获取颜色管理器
    color_manager = ColorManager()

    expense_cols = []
    for col in df.columns:
        col_lower = str(col).lower()
        if any(keyword in col_lower for keyword in ['cost', 'expense', '费用', '成本', '支出']):
            if pd.api.types.is_numeric_dtype(df[col]):
                expense_cols.append(col)

    # 1. 饼图
    ax1 = axes[0]
    if expense_cols and not df.empty:
        data_row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
        values = []
        labels = []

        for col in expense_cols[:8]:
            if col in data_row:
                val = data_row[col]
                if isinstance(val, (int, float, np.integer, np.floating)):
                    if not pd.isna(val) and val > 0:
                        values.append(float(val))
                        labels.append(col)

        if values and len(values) > 1:
            colors = color_manager.get_colormap_colors(len(values), 'Set3')
            # 保存饼图的对象用于图例
            wedges, texts, autotexts = ax1.pie(values, colors=colors, autopct='%1.1f%%',
                    startangle=90, wedgeprops=dict(edgecolor='w', linewidth=1))
            # 添加图例标签
            ax1.pie_wedges = wedges
            ax1.pie_labels = labels

    ax1.axis('equal')

    # 2. 费用趋势图
    ax2 = axes[1]
    if expense_cols and len(df) > 1:
        plot_cols = expense_cols[:4]

        for i, col in enumerate(plot_cols):
            color = color_manager.get_color_by_business_type(col)
            data_series = pd.to_numeric(df[col], errors='coerce')
            data = data_series.dropna()

            if len(data) > 0:
                # 为每条线添加标签
                ax2.plot(range(len(data)), data.values, marker='o',
                         linewidth=2, color=color, label=col, markersize=5)

    return fig


def _create_balance_sheet_chart(df: pd.DataFrame) -> plt.Figure:
    """创建资产负债表图表 - 只负责绘图"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # 识别关键列
    asset_cols = [col for col in df.columns
                  if any(keyword in str(col).lower()
                         for keyword in ['asset', '资产'])]
    liability_cols = [col for col in df.columns
                      if any(keyword in str(col).lower()
                             for keyword in ['liability', 'debt', '负债'])]

    # 1. 资产结构
    if asset_cols and not df.empty:
        ax1 = axes[0, 0]
        latest_assets = df[asset_cols].iloc[-1] if len(df) > 1 else df[asset_cols].iloc[0]

        # 获取颜色管理器
        color_manager = ColorManager()
        colors = [color_manager.get_color_by_business_type(col) for col in latest_assets.index]

        bars = ax1.barh(range(len(latest_assets)), latest_assets.values,
                 color=colors, edgecolor='black', linewidth=0.5)
        ax1.set_yticks(range(len(latest_assets)))
        ax1.set_yticklabels(latest_assets.index)
        ax1.invert_yaxis()

        # 添加数值标签
        for bar, val in zip(bars, latest_assets.values):
            width = bar.get_width()
            ax1.text(width, bar.get_y() + bar.get_height()/2.,
                     f'{val:,.0f}', ha='left', va='center', fontsize=9)

    # 2. 资产负债率趋势
    if asset_cols and liability_cols and len(df) > 1:
        ax2 = axes[0, 1]
        total_assets = df[asset_cols].sum(axis=1)
        total_liabilities = df[liability_cols].sum(axis=1)

        if not total_assets.empty and not total_liabilities.empty:
            debt_ratio = (total_liabilities / total_assets) * 100

            color_manager = ColorManager()
            line, = ax2.plot(range(len(df)), debt_ratio.values, marker='s', linewidth=2.5,
                     color=color_manager.BUSINESS_COLORS['liability'])
            ax2.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50%警戒线')

            # 添加标签
            ax2.legend(handles=[line], labels=['资产负债率'])

            # 添加数值标签
            for i, val in enumerate(debt_ratio.values):
                ax2.text(i, val + 1, f'{val:.1f}%', ha='center', va='bottom', fontsize=8)

    return fig


# ============================================================================
# 7. 图表装饰器（统一处理标注）
# ============================================================================

def decorate_income_trend_chart(fig: plt.Figure, df: pd.DataFrame) -> plt.Figure:
    """装饰收入趋势图"""
    annotator = ChartAnnotator()
    axes = fig.axes

    if len(axes) >= 4:
        # 1. 主趋势图
        ax1 = axes[0]
        # 检查是否有日期列
        date_cols = [col for col in df.columns
                     if '日期' in str(col) or 'date' in str(col).lower()]

        if date_cols and not df.empty and len(df) > 1:
            annotator.add_axis_labels(ax1, '日期', '金额/数值')
        else:
            annotator.add_axis_labels(ax1, '时间序列 (期)', '金额/数值')

        annotator.add_grid(ax1)
        annotator.format_axis_ticks(ax1, rotate_x=True)

        # 添加图例
        lines = ax1.get_lines()
        if lines:
            labels = [line.get_label() for line in lines if line.get_label()]
            if labels:
                ax1.legend(labels=labels, title='指标', fontsize=9, frameon=True, framealpha=0.9)

        # 2. 饼图
        ax2 = axes[1]
        annotator.add_title_and_labels(None, '数据构成分析', ax2)

        # 添加饼图图例
        if hasattr(ax2, 'pie_wedges') and hasattr(ax2, 'pie_labels'):
            ax2.legend(ax2.pie_wedges, ax2.pie_labels, title='构成指标',
                      loc='center left', bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)

        # 3. 增长率分析
        ax3 = axes[2]
        annotator.add_title_and_labels(None, '增长率分析 (%)', ax3)
        annotator.add_axis_labels(ax3, '时间序列 (期)', '增长率 %')
        annotator.add_grid(ax3, alpha=0.2)

        # 4. 数据统计
        ax4 = axes[3]
        annotator.add_title_and_labels(None, '数据统计摘要', ax4)
        ax4.axis('off')  # 确保坐标轴关闭，只显示文本框

    return fig


def decorate_profit_composition_chart(fig: plt.Figure, df: pd.DataFrame) -> plt.Figure:
    """装饰利润构成图"""
    annotator = ChartAnnotator()
    axes = fig.axes

    if len(axes) >= 2:
        # 1. 饼图
        ax1 = axes[0]
        annotator.add_title_and_labels(None, '数据构成分析', ax1)

        # 添加饼图图例
        if hasattr(ax1, 'pie_wedges') and hasattr(ax1, 'pie_labels'):
            ax1.legend(ax1.pie_wedges, ax1.pie_labels, title='构成指标',
                      loc='center left', bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)

        # 2. 条形图
        ax2 = axes[1]
        annotator.add_title_and_labels(None, '数据对比（水平条形图）', ax2)
        annotator.add_axis_labels(ax2, '金额', None)
        annotator.add_grid(ax2)

        # 添加Y轴刻度标签（已由绘图函数设置）
        # 添加数值标签（已由绘图函数设置）

    return fig


def decorate_revenue_comparison_chart(fig: plt.Figure, df: pd.DataFrame) -> plt.Figure:
    """装饰收入对比图"""
    annotator = ChartAnnotator()
    ax = fig.axes[0]

    annotator.add_axis_labels(ax, '数据项', '金额')
    annotator.add_grid(ax)

    # 设置X轴刻度标签
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()[:6]
    if numeric_cols:
        x_pos = range(len(numeric_cols))
        ax.set_xticks(x_pos)
        ax.set_xticklabels(numeric_cols, rotation=30, ha='right')

    # 添加图例
    if hasattr(ax, 'bar_chart_bars') and hasattr(ax, 'bar_chart_labels'):
        # 创建图例句柄
        handles = []
        for bar, label in zip(ax.bar_chart_bars, ax.bar_chart_labels):
            # 为每个柱子创建一个图例句柄
            handles.append(plt.Rectangle((0,0),1,1, color=bar.get_facecolor(), label=label))

        if handles:
            ax.legend(handles=handles, title='数据项',
                     bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)

    return fig


def decorate_expense_breakdown_chart(fig: plt.Figure, df: pd.DataFrame) -> plt.Figure:
    """装饰费用分解图"""
    annotator = ChartAnnotator()
    axes = fig.axes

    if len(axes) >= 2:
        # 1. 饼图
        ax1 = axes[0]
        annotator.add_title_and_labels(None, '费用构成分析', ax1)

        # 添加饼图图例
        if hasattr(ax1, 'pie_wedges') and hasattr(ax1, 'pie_labels'):
            ax1.legend(ax1.pie_wedges, ax1.pie_labels, title='费用项目',
                      loc='center left', bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)

        # 2. 趋势图
        ax2 = axes[1]
        annotator.add_title_and_labels(None, '费用趋势分析', ax2)
        annotator.add_axis_labels(ax2, '时间序列 (期)', '金额')
        annotator.add_grid(ax2)

        # 添加图例
        lines = ax2.get_lines()
        if lines:
            labels = [line.get_label() for line in lines if line.get_label()]
            if labels:
                ax2.legend(labels=labels, title='费用项目', fontsize=9, frameon=True, framealpha=0.9)

    return fig


def decorate_balance_sheet_chart(fig: plt.Figure, df: pd.DataFrame) -> plt.Figure:
    """装饰资产负债表图表"""
    annotator = ChartAnnotator()
    axes = fig.axes

    if len(axes) >= 2:
        # 1. 资产结构
        ax1 = axes[0]
        annotator.add_title_and_labels(None, '资产结构分析', ax1)
        annotator.add_axis_labels(ax1, '金额', None)

        # 2. 资产负债率趋势
        ax2 = axes[1]
        annotator.add_title_and_labels(None, '资产负债率趋势 (%)', ax2)
        annotator.add_axis_labels(ax2, '时间序列 (期)', '资产负债率 %')
        annotator.add_grid(ax2)

    return fig


# ============================================================================
# 8. 主图表生成函数
# ============================================================================

def create_professional_chart(df: pd.DataFrame, chart_type: str, title: str = None,
                             output_dir: str = "./charts") -> Tuple[Optional[str], str]:
    """
    创建专业财经图表 - 统一入口
    """
    try:
        # 1. 数据验证
        if df is None or df.empty:
            return None, "数据为空，无法生成图表"

        # 2. 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        output_dir_abs = os.path.abspath(output_dir)

        # 3. 检查数值列
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        # 如果没有数值列，尝试转换
        if not numeric_cols:
            for col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception:
                    pass
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not numeric_cols:
            return None, "没有有效的数值列，无法生成图表"

        # 4. 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title) if title else "财经图表"
        if not safe_title or len(safe_title) < 2:
            safe_title = "财经图表"

        filename = f"{chart_type}_{safe_title}_{timestamp}.png"
        filepath = os.path.join(output_dir_abs, filename)

        # 5. 图表类型映射
        chart_generators = {
            "income_trend": _create_income_trend_chart,
            "profit_composition": _create_profit_composition_chart,
            "balance_sheet": _create_balance_sheet_chart,
            "revenue_comparison": _create_revenue_comparison_chart,
            "expense_breakdown": _create_expense_breakdown_chart
        }

        chart_decorators = {
            "income_trend": decorate_income_trend_chart,
            "profit_composition": decorate_profit_composition_chart,
            "balance_sheet": decorate_balance_sheet_chart,
            "revenue_comparison": decorate_revenue_comparison_chart,
            "expense_breakdown": decorate_expense_breakdown_chart
        }

        if chart_type not in chart_generators:
            return None, f"不支持的图表类型: {chart_type}"

        # 6. 生成图表
        print(f"📈 正在生成 {chart_type} 图表")
        print(f"   数据形状: {df.shape}")
        print(f"   数值列: {numeric_cols[:3]}")

        # 6.1 生成图表（只绘图）
        fig = chart_generators[chart_type](df)

        # 6.2 使用智能标题生成工具
        title_generator = TitleGenerator()
        chart_title = title if title else title_generator.generate_title(df, chart_type)

        # 6.3 添加主标题
        annotator = ChartAnnotator()
        annotator.add_title_and_labels(fig, chart_title)

        # 6.4 装饰图表（添加标注）
        if chart_type in chart_decorators:
            fig = chart_decorators[chart_type](fig, df)

        # 6.5 调整布局
        plt.tight_layout(rect=[0, 0.03, 1, 0.97])  # 增加顶部空间，防止标题重叠

        # 7. 保存图表
        plt.savefig(
            filepath,
            dpi=300,
            bbox_inches='tight',
            facecolor='white',
            pad_inches=0.5,
            edgecolor='none'
        )

        plt.close(fig)

        # 8. 记录成功信息
        print(f"✅ 图表生成成功: {os.path.basename(filepath)}")
        return filepath, ""

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 图表生成失败: {error_msg}")
        return None, f"图表生成失败: {error_msg}"


# ============================================================================
# 9. 辅助工具
# ============================================================================

def create_sample_dataframe() -> pd.DataFrame:
    """创建示例财经数据"""
    dates = pd.date_range(start='2023-01-01', periods=12, freq='ME')

    data = {
        '日期': dates,
        '营业收入': np.random.randint(1000, 5000, 12) * 1000,
        '营业成本': np.random.randint(500, 3000, 12) * 1000,
        '销售费用': np.random.randint(100, 500, 12) * 1000,
        '管理费用': np.random.randint(50, 300, 12) * 1000,
        '净利润': np.random.randint(200, 1500, 12) * 1000,
        '总资产': np.random.randint(5000, 20000, 12) * 1000,
        '总负债': np.random.randint(2000, 10000, 12) * 1000,
        '股东权益': np.random.randint(3000, 12000, 12) * 1000
    }

    return pd.DataFrame(data)


# ============================================================================
# 10. 测试工具
# ============================================================================

def test_tools() -> bool:
    """测试所有工具功能"""
    print("=" * 60)
    print("测试专业财经可视化工具集 v3.1")
    print("=" * 60)

    try:
        # 创建测试数据
        df = create_sample_dataframe()

        print("1. 测试数据加载功能...")
        test_file = "./test_finance_data.csv"
        df.to_csv(test_file, index=False, encoding='utf-8')

        loaded_df, error = load_financial_data(test_file)
        if error:
            print(f"   ✗ 数据加载失败: {error}")
            return False

        print(f"   ✓ 数据加载成功，形状: {loaded_df.shape}")

        print("\n2. 测试报表类型检测...")
        report_info = detect_financial_report_type(df)
        print(f"   报表类型: {report_info['type_name']}")

        print("\n3. 测试数据清洗...")
        cleaned_df, cleaning_report = clean_financial_data(df)
        print(f"   原始形状: {cleaning_report['original_shape']}")
        print(f"   清洗后形状: {cleaning_report['cleaned_shape']}")

        print("\n4. 测试专业图表生成...")

        # 测试所有图表类型
        chart_types = ["income_trend", "profit_composition", "revenue_comparison",
                      "expense_breakdown", "balance_sheet"]

        for chart_type in chart_types:
            print(f"   生成 {chart_type} 图表...")
            chart_path, chart_error = create_professional_chart(
                cleaned_df,
                chart_type=chart_type,
                output_dir="./test_charts/"
            )

            if chart_error:
                print(f"   ✗ {chart_type} 生成失败: {chart_error}")
            else:
                print(f"   ✓ {chart_type} 生成成功")
                if os.path.exists(chart_path):
                    file_size = os.path.getsize(chart_path) / 1024
                    print(f"     文件大小: {file_size:.1f} KB")

        # 清理测试文件
        if os.path.exists(test_file):
            os.remove(test_file)

        print("\n" + "=" * 60)
        print("工具集测试完成!")
        print("=" * 60)

        return True

    except Exception as test_error:
        print(f"\n❌ 测试过程中出错: {str(test_error)}")
        return False


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    """直接运行此文件进行测试"""
    print("专业财经可视化工具集 v3.1")
    print("-" * 40)

    # 检查依赖
    try:
        import pandas
        import matplotlib.pyplot

        print("✓ 依赖检查通过")
    except ImportError as import_error:
        print(f"✗ 缺少依赖: {import_error}")
        print("请安装: pip install pandas matplotlib")
        sys.exit(1)

    # 运行测试
    try:
        success = test_tools()

        if success:
            print("\n✅ 工具集测试成功！")
            print("\n主要功能:")
            print("1. load_financial_data() - 加载财经文件")
            print("2. detect_financial_report_type() - 识别报表类型")
            print("3. clean_financial_data() - 清洗财经数据")
            print("4. ColorManager - 颜色管理工具")
            print("5. TitleGenerator - 智能标题生成工具")
            print("6. ChartAnnotator - 图表标注工具")
            print("7. create_professional_chart() - 生成专业图表")
        else:
            print("\n❌ 工具集测试失败")
    except Exception as main_error:
        print(f"\n❌ 主程序出错: {str(main_error)}")