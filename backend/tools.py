"""
专业财经可视化工具集
功能：文件加载、数据清洗、专业图表生成、财务分析
版本：v2.5 - 最终修复版
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
from typing import Tuple, Dict, Any, Optional, List

# 设置中文字体和样式（如果有中文需要）
try:
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass

# 设置图表样式
plt.style.use('seaborn-v0_8-whitegrid')
matplotlib.rcParams['figure.dpi'] = 100
matplotlib.rcParams['savefig.dpi'] = 300

# 抑制警告
warnings.filterwarnings('ignore')

# 设置专业财经图表样式
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
    'figure.figsize': (12, 8)
}
plt.rcParams.update(_chart_config)

# 专业财经配色方案
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
    '#17becf'  # 青色 - 特殊
]


# ============================================================================
# 1. 文件处理工具
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
# 2. 数据清洗和格式化工具
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
# 3. 专业财经图表生成工具
# ============================================================================

def create_professional_chart(df: pd.DataFrame, chart_type: str, title: str,
                              output_dir: str = "./charts") -> Tuple[Optional[str], str]:
    """
    创建专业财经图表 - 修复版
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
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        if not safe_title or len(safe_title) < 2:
            safe_title = "财经图表"

        # 修复：简化文件名生成逻辑
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

        if chart_type not in chart_generators:
            return None, f"不支持的图表类型: {chart_type}"

        # 6. 生成图表
        print(f"📈 正在生成 {chart_type} 图表")
        print(f"   数据形状: {df.shape}")
        print(f"   数值列: {numeric_cols[:3]}")  # 只显示前3个

        fig = chart_generators[chart_type](df, title)

        # 7. 保存图表
        plt.tight_layout()
        plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        print(f"✅ 图表生成成功: {os.path.basename(filepath)}")
        return filepath, ""

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 图表生成失败: {error_msg}")
        return None, f"图表生成失败: {error_msg}"


def _extract_data_info_for_filename(df: pd.DataFrame, numeric_cols: List[str]) -> str:
    """
    从数据中提取信息用于文件名
    """
    info_parts = []

    # 1. 添加数据形状信息
    info_parts.append(f"{len(df)}行{len(df.columns)}列")

    # 2. 添加数值列数量
    if numeric_cols:
        info_parts.append(f"{len(numeric_cols)}个数值列")

    # 3. 尝试识别关键列
    for col in df.columns:
        col_lower = str(col).lower()
        if '收入' in col_lower or 'revenue' in col_lower:
            info_parts.append("收入数据")
            break
        elif '利润' in col_lower or 'profit' in col_lower:
            info_parts.append("利润数据")
            break
        elif '资产' in col_lower or 'asset' in col_lower:
            info_parts.append("资产数据")
            break

    # 4. 如果没有识别到特定类型，使用通用描述
    if not info_parts or info_parts[-1] in ["收入数据", "利润数据", "资产数据"]:
        if len(df) > 12:
            info_parts.append("多期数据")
        elif len(df) > 1:
            info_parts.append(f"{len(df)}期数据")

    return "_".join(info_parts)


def _create_income_trend_chart(df: pd.DataFrame, title: str) -> plt.Figure:
    """创建收入趋势图 - 修复版，确保数据正确绘制"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # 获取DataFrame的数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        # 如果没有数值列，尝试转换
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception:
                pass
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # 如果没有数值列，创建示例数据
    if not numeric_cols:
        axes[0, 0].text(0.5, 0.5, '无有效数值数据',
                        ha='center', va='center', fontsize=12)
        return fig

    # 1. 收入趋势 - 主图表
    ax1 = axes[0, 0]

    # 尝试找到日期列
    date_cols = [col for col in df.columns
                 if '日期' in str(col) or 'date' in str(col).lower() or 'time' in str(col).lower()]

    # 获取前3个数值列进行绘制
    plot_cols = numeric_cols[:3]

    if date_cols and not df.empty and len(df) > 1:
        # 有日期列的情况
        date_col = date_cols[0]
        for i, col in enumerate(plot_cols):
            color = FINANCE_COLORS[i % len(FINANCE_COLORS)]

            # 确保数据是数值类型
            data_series = pd.to_numeric(df[col], errors='coerce')
            data = data_series.dropna()  # 修复：使用pandas的dropna
            dates = df[date_col].iloc[:len(data)]  # 确保日期和数据长度匹配

            if len(data) > 0:
                ax1.plot(dates, data.values, marker='o',
                         linewidth=2.5, color=color, label=col, markersize=6)

        ax1.set_xlabel('日期', fontsize=11)
        ax1.set_title('收入趋势分析', fontsize=12, fontweight='bold')

    else:
        # 没有日期列，使用索引
        for i, col in enumerate(plot_cols):
            color = FINANCE_COLORS[i % len(FINANCE_COLORS)]
            data_series = pd.to_numeric(df[col], errors='coerce')
            data = data_series.dropna()  # 修复：使用pandas的dropna

            if len(data) > 0:
                ax1.plot(range(len(data)), data.values, marker='o',
                         linewidth=2.5, color=color, label=col, markersize=6)

        ax1.set_xlabel('数据点', fontsize=11)
        ax1.set_title('数据趋势分析', fontsize=12, fontweight='bold')

    ax1.set_ylabel('金额/数值', fontsize=11)
    ax1.legend(frameon=True, framealpha=0.9, loc='best')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.tick_params(axis='x', rotation=45)

    # 2. 收入构成 - 饼图
    ax2 = axes[0, 1]
    if not df.empty and len(plot_cols) > 1:
        # 使用最后一行的数据
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
            # 修复：正确引用Set3 colormap
            colors = cm.Set3(np.linspace(0, 1, len(sizes)))
            ax2.pie(sizes, labels=labels, colors=colors,
                    autopct='%1.1f%%', startangle=90, pctdistance=0.85)
            ax2.set_title('数据构成分析', fontsize=12, fontweight='bold')
        else:
            ax2.text(0.5, 0.5, '无正数数据\n无法生成饼图',
                     ha='center', va='center', fontsize=10)
    else:
        ax2.text(0.5, 0.5, '数据不足\n无法生成构成图',
                 ha='center', va='center', fontsize=10)

    ax2.axis('equal')

    # 3. 增长率分析
    ax3 = axes[1, 0]
    if len(df) > 1 and len(plot_cols) > 0:
        primary_col = plot_cols[0]
        data_series = pd.to_numeric(df[primary_col], errors='coerce')
        data = data_series.dropna()  # 修复：使用pandas的dropna

        if len(data) > 1:
            growth_rates = data.pct_change() * 100

            # 创建颜色列表：绿色为正增长，红色为负增长
            colors = ['green' if x >= 0 else 'red' for x in growth_rates[1:]]
            x_positions = range(1, len(growth_rates))

            ax3.bar(x_positions, growth_rates[1:].values, color=colors, alpha=0.7)
            ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax3.set_title(f'{primary_col} 增长率 (%)', fontsize=12, fontweight='bold')
            ax3.set_xlabel('期间')
            ax3.set_ylabel('增长率 %')
            ax3.grid(True, alpha=0.2, linestyle='--', axis='y')
        else:
            ax3.text(0.5, 0.5, '数据不足\n无法计算增长率',
                     ha='center', va='center', fontsize=10)
    else:
        ax3.text(0.5, 0.5, '数据不足\n无法进行增长率分析',
                 ha='center', va='center', fontsize=10)

    # 4. 数据统计
    ax4 = axes[1, 1]

    if not df.empty and len(plot_cols) > 0:
        stats_text = "📊 数据统计信息\n\n"

        for i, col in enumerate(plot_cols[:2]):  # 只显示前2列
            if col in df.columns:
                data_series = pd.to_numeric(df[col], errors='coerce')
                data = data_series.dropna()  # 修复：使用pandas的dropna
                if len(data) > 0:
                    stats_text += f"{col}:\n"
                    stats_text += f"  样本数: {len(data)}\n"
                    stats_text += f"  平均值: {data.mean():.2f}\n"
                    stats_text += f"  最大值: {data.max():.2f}\n"
                    stats_text += f"  最小值: {data.min():.2f}\n\n"

        ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes,
                 fontsize=9, verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax4.set_title('数据统计摘要', fontsize=12, fontweight='bold')
        ax4.axis('off')
    else:
        ax4.text(0.5, 0.5, '无有效数据统计',
                 ha='center', va='center', fontsize=10)
        ax4.axis('off')

    return fig


def _create_profit_composition_chart(df: pd.DataFrame, title: str) -> plt.Figure:
    """创建利润构成图 - 修复版"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # 获取数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        axes[0].text(0.5, 0.5, '无有效数值数据',
                     ha='center', va='center', fontsize=12)
        axes[1].text(0.5, 0.5, '无有效数值数据',
                     ha='center', va='center', fontsize=12)
        return fig

    # 1. 饼图
    ax1 = axes[0]

    if not df.empty:  # 修复：使用明确的空值检查
        # 使用最后一行的数据
        if len(df) > 1:
            last_row = df.iloc[-1]
        else:
            last_row = df.iloc[0]

        sizes = []
        labels = []

        for col in numeric_cols:
            if col in last_row:
                val = last_row[col]
                if not pd.isna(val) and val > 0:
                    sizes.append(float(val))
                    labels.append(col)

        if sizes:
            # 修复：正确引用Set3 colormap
            colors = cm.Set3(np.linspace(0, 1, len(sizes)))
            wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=colors,
                                               autopct='%1.1f%%', startangle=90, pctdistance=0.85)

            # 美化百分比文本
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_weight('bold')

            ax1.set_title('数据构成分析', fontsize=12, fontweight='bold')
        else:
            ax1.text(0.5, 0.5, '无正数数据\n无法生成构成图',
                     ha='center', va='center', fontsize=10)
    else:
        ax1.text(0.5, 0.5, '数据为空',
                 ha='center', va='center', fontsize=10)

    ax1.axis('equal')

    # 2. 条形图
    ax2 = axes[1]

    if not df.empty and len(numeric_cols) > 0:  # 修复：使用明确的空值检查
        # 使用最后一行的数据
        if len(df) > 1:
            data_row = df.iloc[-1]
        else:
            data_row = df.iloc[0]

        values = []
        labels_bar = []

        for col in numeric_cols[:8]:  # 最多显示8个
            if col in data_row:
                val = data_row[col]
                if not pd.isna(val):
                    values.append(float(val))
                    labels_bar.append(col)

        if values:
            y_pos = np.arange(len(values))
            colors_bar = cm.viridis(np.linspace(0.2, 0.8, len(values)))

            bars = ax2.barh(y_pos, values, color=colors_bar, alpha=0.7)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(labels_bar)
            ax2.set_xlabel('数值')
            ax2.set_title('数据对比（水平条形图）', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, linestyle='--', axis='x')
            ax2.invert_yaxis()  # 反转y轴，使最大值在顶部

            # 添加数值标签
            for i, (bar, val) in enumerate(zip(bars, values)):
                width = bar.get_width()
                ax2.text(width + 0.01 * max(values), bar.get_y() + bar.get_height() / 2.,
                         f'{val:.0f}', ha='left', va='center', fontsize=9)
        else:
            ax2.text(0.5, 0.5, '无有效数据',
                     ha='center', va='center', fontsize=10)
    else:
        ax2.text(0.5, 0.5, '数据为空或无数值列',
                 ha='center', va='center', fontsize=10)

    return fig


def _create_balance_sheet_chart(df: pd.DataFrame, title: str) -> plt.Figure:
    """创建资产负债表图表"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # 识别关键列
    asset_cols = [col for col in df.columns
                  if any(keyword in str(col).lower()
                         for keyword in ['asset', '资产'])]
    liability_cols = [col for col in df.columns
                      if any(keyword in str(col).lower()
                             for keyword in ['liability', 'debt', '负债'])]

    # 1. 资产结构
    if asset_cols and not df.empty:  # 修复：使用明确的空值检查
        ax1 = axes[0, 0]
        latest_assets = df[asset_cols].iloc[-1] if len(df) > 1 else df[asset_cols].iloc[0]

        ax1.barh(range(len(latest_assets)), latest_assets.values,
                 edgecolor='black', linewidth=0.5)

        ax1.set_title('资产结构分析', fontsize=12, fontweight='bold')
        ax1.set_yticks(range(len(latest_assets)))
        ax1.set_yticklabels(latest_assets.index)
        ax1.invert_yaxis()
        ax1.set_xlabel('金额')

    # 2. 资产负债率趋势
    if asset_cols and liability_cols and len(df) > 1:
        ax2 = axes[0, 1]
        total_assets = df[asset_cols].sum(axis=1)
        total_liabilities = df[liability_cols].sum(axis=1)

        # 修复：避免Series真值模糊
        if not total_assets.empty and not total_liabilities.empty:
            debt_ratio = (total_liabilities / total_assets) * 100

            ax2.plot(range(len(df)), debt_ratio.values, marker='s', linewidth=2.5,
                     color=FINANCE_COLORS[3])
            ax2.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50%警戒线')

            ax2.set_title('资产负债率趋势 (%)', fontsize=12, fontweight='bold')
            ax2.set_xlabel('期间')
            ax2.set_ylabel('资产负债率 %')
            ax2.legend()
            ax2.grid(True, alpha=0.3, linestyle='--')

    return fig


def _create_revenue_comparison_chart(df: pd.DataFrame, title: str) -> plt.Figure:
    """创建收入对比图 - 修复版，增强标注"""
    fig, ax = plt.subplots(figsize=(14, 9))

    # 获取数值列
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        ax.text(0.5, 0.5, '无有效数值数据，无法生成对比图',
                ha='center', va='center', fontsize=12)
        return fig

    # 只取前6个数值列，避免图表过于拥挤
    plot_cols = numeric_cols[:6]

    if not df.empty:  # 修复：使用明确的空值检查
        # 使用最后一行的数据
        if len(df) > 1:
            data_row = df.iloc[-1]
        else:
            data_row = df.iloc[0]

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
            colors = cm.tab20c(np.arange(len(values)) / len(values))

            bars = ax.bar(x_pos, values, color=colors, alpha=0.85,
                          edgecolor='black', linewidth=1.2)

            # 增强数值标签
            for i, (bar, val) in enumerate(zip(bars, values)):
                height = bar.get_height()
                # 在柱子上方显示数值
                ax.text(bar.get_x() + bar.get_width() / 2., height + 0.01 * max(values),
                        f'{val:,.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

                # 在柱子内部显示百分比
                if sum(values) > 0:
                    percentage = (val / sum(values)) * 100
                    if percentage > 5:  # 只在足够大的柱子上显示
                        ax.text(bar.get_x() + bar.get_width() / 2., height / 2,
                                f'{percentage:.1f}%', ha='center', va='center',
                                fontsize=9, color='white', fontweight='bold')

            ax.set_xticks(x_pos)
            # 优化标签显示
            ax.set_xticklabels([label[:15] + '...' if len(str(label)) > 15 else label
                                for label in labels],
                               rotation=30, ha='right')
            ax.set_ylabel('金额', fontsize=12, fontweight='bold')
            ax.set_xlabel('数据项', fontsize=12, fontweight='bold')

            # 增强标题
            if '对比' in title or 'comparison' in title.lower():
                chart_title = title
            else:
                chart_title = f'{title} - 数据对比分析'

            ax.set_title(chart_title, fontsize=14, fontweight='bold', pad=20)
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')

            # 添加统计信息
            if len(values) > 0:
                stats_text = (f"数据项数: {len(values)}\n"
                              f"总计: {sum(values):,.0f}\n"
                              f"平均: {np.mean(values):,.0f}\n"
                              f"最高: {max(values):,.0f}")

                ax.text(0.98, 0.98, stats_text, transform=ax.transAxes,
                        fontsize=9, verticalalignment='top', horizontalalignment='right',
                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

            # 添加图例
            legend_labels = [f"{label}: {val:,.0f}" for label, val in zip(labels, values)]
            ax.legend(bars, legend_labels, title='数据项详情',
                      loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0.)
        else:
            ax.text(0.5, 0.5, '无有效数值数据',
                    ha='center', va='center', fontsize=12)
    else:
        ax.text(0.5, 0.5, '数据为空，无法生成对比图',
                ha='center', va='center', fontsize=12)

    plt.tight_layout(rect=[0, 0, 0.85, 1])  # 为图例留出空间
    return fig


def _create_expense_breakdown_chart(df: pd.DataFrame, title: str = "费用分析") -> Optional[plt.Figure]:
    """创建优化的费用分解图 - 解决显示问题"""
    try:
        # 检查数据有效性
        if df is None or df.empty or len(df) == 0:
            print("警告: 数据为空，无法生成费用分析图表")
            return None

        # 清理列名：移除空格和特殊字符
        df.columns = df.columns.str.strip()

        # 找出数值列（可能的费用列）
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not numeric_cols:
            # 如果没有数值列，尝试转换可能的数值列
            for col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except:
                    continue
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        if not numeric_cols:
            print(f"警告: 未找到数值列用于费用分析。数据列: {df.columns.tolist()}")
            # 创建简单图表显示错误
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, '未检测到数值数据列\n请检查数据格式',
                    ha='center', va='center', fontsize=12,
                    transform=ax.transAxes, color='red')
            ax.set_title('费用分析 - 数据格式错误', fontsize=14, color='red')
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            return fig

        # 限制显示的列数（避免图表过于拥挤）
        max_cols_to_show = min(6, len(numeric_cols))
        cols_to_use = numeric_cols[:max_cols_to_show]

        # 提取数据
        if len(df) == 1:
            # 单行数据：饼图+条形图
            values = df[cols_to_use].iloc[0].fillna(0).values.tolist()
            labels = cols_to_use

            # 过滤掉零值
            nonzero_idx = [i for i, v in enumerate(values) if v > 0]
            if not nonzero_idx:
                values = [1] * len(values)  # 避免除零错误
                nonzero_idx = list(range(len(values)))

            values = [values[i] for i in nonzero_idx]
            labels = [labels[i] for i in nonzero_idx]

            # 创建复合图表
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))

            # 1. 饼图
            colors = plt.cm.Set3(np.linspace(0, 1, len(values)))
            wedges, texts, autotexts = ax1.pie(
                values, labels=labels, colors=colors,
                autopct=lambda pct: f'{pct:.1f}%\n¥{pct * sum(values) / 100:,.0f}',
                startangle=90, wedgeprops={'edgecolor': 'white', 'linewidth': 2}
            )
            ax1.set_title('费用构成分析', fontsize=14, fontweight='bold', pad=20)

            # 美化饼图文本
            for autotext in autotexts:
                autotext.set_color('darkblue')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(9)
            for text in texts:
                text.set_fontsize(10)

            # 2. 水平条形图
            y_pos = np.arange(len(values))
            bar_colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(values)))

            bars = ax2.barh(y_pos, values, color=bar_colors, alpha=0.8, edgecolor='black')

            # 设置Y轴标签（简化长列名）
            short_labels = [label[:15] + '...' if len(label) > 15 else label for label in labels]
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(short_labels, fontsize=10)
            ax2.set_xlabel('金额 (元)', fontsize=11)
            ax2.set_title('费用金额对比', fontsize=14, fontweight='bold', pad=20)
            ax2.grid(True, alpha=0.3, axis='x')

            # 在条形上显示数值
            for bar, val in zip(bars, values):
                width = bar.get_width()
                ax2.text(width * 1.01, bar.get_y() + bar.get_height() / 2,
                         f'¥{val:,.0f}', va='center', ha='left',
                         fontsize=10, fontweight='bold')

            # 调整布局
            plt.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
            plt.tight_layout()

        else:
            # 多行数据：趋势图
            fig, axes = plt.subplots(2, 1, figsize=(14, 10))

            # 1. 堆叠面积图（显示趋势）
            ax1 = axes[0]

            # 选择最多4个主要费用项
            main_expenses = cols_to_use[:4]

            # 准备数据
            plot_data = df[main_expenses].copy()

            # 确保数据是数值
            for col in main_expenses:
                plot_data[col] = pd.to_numeric(plot_data[col], errors='coerce').fillna(0)

            # 绘制堆叠面积图
            ax1.stackplot(range(len(plot_data)), plot_data.T.values,
                          labels=main_expenses, alpha=0.8)

            ax1.set_title('费用趋势分析', fontsize=14, fontweight='bold', pad=15)
            ax1.set_ylabel('金额 (元)', fontsize=11)
            ax1.legend(loc='upper left', fontsize=10)
            ax1.grid(True, alpha=0.3)

            # 设置X轴标签
            if len(df) <= 12:  # 如果数据点不多，显示所有标签
                x_labels = []
                for i in range(len(df)):
                    if '日期' in df.columns or 'Date' in df.columns:
                        date_col = '日期' if '日期' in df.columns else 'Date'
                        x_labels.append(str(df[date_col].iloc[i])[:10])
                    else:
                        x_labels.append(f'周期 {i + 1}')
                ax1.set_xticks(range(len(df)))
                ax1.set_xticklabels(x_labels, rotation=45, ha='right')

            # 2. 最近一期费用的条形图
            ax2 = axes[1]
            latest_values = df[cols_to_use].iloc[-1].fillna(0).values.tolist()
            latest_values = latest_values[:min(8, len(latest_values))]  # 限制数量

            # 过滤掉零值
            nonzero_latest = [(i, v) for i, v in enumerate(latest_values) if v > 0]
            if nonzero_latest:
                indices, values = zip(*nonzero_latest)
                labels = [cols_to_use[i][:20] + '...' if len(cols_to_use[i]) > 20
                          else cols_to_use[i] for i in indices]
            else:
                values = [1] * len(cols_to_use[:3])
                labels = cols_to_use[:3]

            y_pos = np.arange(len(values))
            bar_colors = plt.cm.coolwarm(np.linspace(0.2, 0.8, len(values)))

            bars = ax2.barh(y_pos, values, color=bar_colors, alpha=0.8, edgecolor='black')
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(labels, fontsize=10)
            ax2.set_xlabel('金额 (元)', fontsize=11)
            ax2.set_title(f'最近一期费用明细 (共{len(df)}期)', fontsize=14, fontweight='bold', pad=15)
            ax2.grid(True, alpha=0.3, axis='x')

            # 在条形上显示数值
            for bar, val in zip(bars, values):
                width = bar.get_width()
                ax2.text(width * 1.01, bar.get_y() + bar.get_height() / 2,
                         f'¥{val:,.0f}', va='center', ha='left',
                         fontsize=10, fontweight='bold')

            # 调整布局
            plt.suptitle(title, fontsize=16, fontweight='bold', y=0.95)
            plt.tight_layout()

        return fig

    except Exception as e:
        print(f"创建费用分析图表时出错: {str(e)}")
        import traceback
        traceback.print_exc()

        # 创建简单的错误显示图表
        fig, ax = plt.subplots(figsize=(10, 6))
        error_msg = f"图表生成错误:\n{str(e)[:100]}..."
        ax.text(0.5, 0.5, error_msg,
                ha='center', va='center', fontsize=12,
                transform=ax.transAxes, color='red')
        ax.set_title('费用分析图表生成失败', fontsize=14, color='red')
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        return fig


# ============================================================================
# 4. 财经分析工具
# ============================================================================

def analyze_financial_health(df: pd.DataFrame, report_type: str) -> Dict[str, Any]:
    """分析财务健康状况"""
    if df is None or df.empty:
        return {
            'report_type': report_type,
            'key_metrics': {},
            'warnings': ['数据为空'],
            'recommendations': ['请提供有效数据']
        }

    analysis: Dict[str, Any] = {
        'report_type': report_type,
        'key_metrics': {},
        'warnings': [],
        'recommendations': []
    }

    if report_type == 'income_statement':
        _analyze_income_statement(df, analysis)
    elif report_type == 'balance_sheet':
        _analyze_balance_sheet(df, analysis)

    return analysis


def _analyze_income_statement(df: pd.DataFrame, analysis: Dict[str, Any]) -> None:
    """分析利润表"""
    revenue_cols = [col for col in df.columns
                    if any(keyword in str(col).lower()
                           for keyword in ['revenue', 'sales', '收入', '营收'])]
    profit_cols = [col for col in df.columns
                   if any(keyword in str(col).lower()
                          for keyword in ['profit', 'net', '利润', '净利'])]

    if revenue_cols and profit_cols and not df.empty:  # 修复：使用明确的空值检查
        latest_revenue = df[revenue_cols[0]].iloc[-1] if len(df) > 1 else df[revenue_cols[0]].iloc[0]
        latest_profit = df[profit_cols[0]].iloc[-1] if len(df) > 1 else df[profit_cols[0]].iloc[0]

        if latest_revenue != 0 and pd.notna(latest_revenue) and pd.notna(latest_profit):
            profit_margin = (latest_profit / latest_revenue) * 100
            analysis['key_metrics']['profit_margin'] = round(profit_margin, 2)

            if profit_margin < 5:
                analysis['warnings'].append('利润率偏低 (<5%)')
            elif profit_margin > 20:
                analysis['recommendations'].append('利润率良好 (>20%)')


def _analyze_balance_sheet(df: pd.DataFrame, analysis: Dict[str, Any]) -> None:
    """分析资产负债表"""
    asset_cols = [col for col in df.columns
                  if any(keyword in str(col).lower()
                         for keyword in ['asset', '资产'])]
    liability_cols = [col for col in df.columns
                      if any(keyword in str(col).lower()
                             for keyword in ['liability', 'debt', '负债'])]

    if asset_cols and liability_cols and not df.empty:  # 修复：使用明确的空值检查
        total_assets = df[asset_cols].sum(axis=1).iloc[-1] if len(df) > 1 else df[asset_cols].sum(axis=1).iloc[0]
        total_liabilities = df[liability_cols].sum(axis=1).iloc[-1] if len(df) > 1 else \
        df[liability_cols].sum(axis=1).iloc[0]

        if total_assets != 0 and pd.notna(total_assets) and pd.notna(total_liabilities):
            debt_ratio = (total_liabilities / total_assets) * 100
            analysis['key_metrics']['debt_ratio'] = round(debt_ratio, 2)

            if debt_ratio > 70:
                analysis['warnings'].append('资产负债率偏高 (>70%)')
            elif debt_ratio < 30:
                analysis['recommendations'].append('资产负债率健康 (<30%)')


# ============================================================================
# 5. 辅助工具
# ============================================================================

def create_sample_dataframe() -> pd.DataFrame:
    """创建示例财经数据"""
    # 修复：将freq='M'改为freq='ME'，兼容新版pandas
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
# 6. 测试工具
# ============================================================================

def test_tools() -> bool:
    """测试所有工具功能"""
    print("=" * 60)
    print("测试专业财经可视化工具集 v2.5")
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
        chart_path, chart_error = create_professional_chart(
            cleaned_df,
            chart_type="income_trend",
            title="测试利润趋势分析",
            output_dir="./test_charts/"
        )

        if chart_error:
            print(f"   ✗ 图表生成失败: {chart_error}")
        else:
            print(f"   ✓ 图表生成成功: {chart_path}")
            if os.path.exists(chart_path):
                file_size = os.path.getsize(chart_path) / 1024
                print(f"   文件大小: {file_size:.1f} KB")

        print("\n5. 测试财务健康分析...")
        health_report = analyze_financial_health(cleaned_df, report_info['type'])
        if health_report['key_metrics']:
            print(f"   关键指标: {health_report['key_metrics']}")

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
    print("专业财经可视化工具集 v2.5")
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
            print("4. create_professional_chart() - 生成专业图表")
            print("5. analyze_financial_health() - 分析财务健康")
        else:
            print("\n❌ 工具集测试失败")
    except Exception as main_error:
        print(f"\n❌ 主程序出错: {str(main_error)}")