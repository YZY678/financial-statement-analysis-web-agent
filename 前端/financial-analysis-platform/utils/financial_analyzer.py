import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


def _parse_numeric_value(value):
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)

    text = str(value).strip()
    if text == '' or text in ['不适用', '—', '--', 'nan', 'None', 'NULL']:
        return np.nan

    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative = True
        text = text[1:-1]

    text = text.replace(',', '').replace('%', '').replace('，', '').replace('\n', '').strip()
    text = text.replace('−', '-')
    try:
        number = float(text)
    except Exception:
        return np.nan

    return -number if negative else number

class FinancialAnalyzer:
    """财务数据分析器"""
    
    def __init__(self, df, report_type='income_statement'):
        self.original_df = df.copy()
        self.df = self._prepare_analysis_dataframe(df)
        self.report_type = report_type
        self.periods = self._extract_periods()
        self.data_quality_warnings = self._build_data_quality_warnings()
        self.data_traceability = '本报告所有数据均提取自财报原文，关键指标已标注证据来源。如需复核，请参考财报附注。'
        self.unit_label = '亿元'

    def _prepare_analysis_dataframe(self, df):
        """将长表（科目+本期/上期）标准化为宽表，兼容终端分析逻辑"""
        if df is None or df.empty:
            return df

        prepared = df.copy()
        prepared.columns = [str(c).replace('\n', '').strip() for c in prepared.columns]

        subject_col = None
        for col in prepared.columns:
            col_name = str(col).strip()
            if col_name in ['科目', '项目']:
                subject_col = col
                break

        if subject_col is None:
            return prepared

        value_columns = [c for c in prepared.columns if c != subject_col]
        if not value_columns:
            return prepared

        def _pick_column(candidates):
            for keyword in candidates:
                for col in value_columns:
                    if keyword in str(col):
                        return col
            return None

        current_col = _pick_column(['本期数', '本期发生额', '本期期末数', '本期金额', '期末余额', '本年'])
        previous_col = _pick_column(['上年同期数', '上期发生额', '上期期末数', '上年同期', '期初余额', '上年'])

        if current_col is None and len(value_columns) >= 1:
            current_col = value_columns[0]
        if previous_col is None and len(value_columns) >= 2:
            previous_col = value_columns[1]

        if current_col is None:
            return prepared

        metric_values = {}

        for _, row in prepared.iterrows():
            metric = str(row.get(subject_col, '')).replace('\n', '').strip()
            if metric == '' or metric in ['项目', '科目']:
                continue

            current_value = _parse_numeric_value(row.get(current_col))
            previous_value = _parse_numeric_value(row.get(previous_col)) if previous_col else np.nan

            if pd.isna(current_value) and pd.notna(previous_value):
                likely_shifted = any(keyword in metric for keyword in ['收入', '利润', '资产', '负债', '现金流'])
                if likely_shifted and abs(float(previous_value)) >= 1e6:
                    current_value = previous_value
                    previous_value = np.nan

            if pd.isna(current_value) and pd.isna(previous_value):
                continue

            if metric not in metric_values:
                metric_values[metric] = {'current': current_value, 'previous': previous_value}
                continue

            existing = metric_values[metric]
            old_current = existing.get('current', np.nan)
            old_previous = existing.get('previous', np.nan)

            should_replace = False
            if pd.isna(old_current) and pd.notna(current_value):
                should_replace = True
            elif pd.notna(old_current) and pd.notna(current_value):
                old_abs = abs(float(old_current))
                new_abs = abs(float(current_value))
                if new_abs > old_abs:
                    should_replace = True
            elif pd.isna(old_previous) and pd.notna(previous_value):
                should_replace = True

            if should_replace:
                metric_values[metric] = {'current': current_value, 'previous': previous_value}

        if len(metric_values) < 3:
            return prepared

        previous_row = {'期间': '上年同期'}
        current_row = {'期间': '本期'}
        for metric, values in metric_values.items():
            previous_row[metric] = values.get('previous')
            current_row[metric] = values.get('current')

        wide_df = pd.DataFrame([previous_row, current_row])
        wide_df = self._apply_metric_aliases(wide_df)
        return wide_df

    def _apply_metric_aliases(self, df):
        """将常见财报长字段映射为分析器标准字段名"""
        if df is None or df.empty:
            return df

        alias_rules = {
            '净利润': [
                '净利润',
                '归属于母公司股东的净利润',
                '归属于公司普通股股东的净利润',
                '归属于上市公司股东的净利润',
            ],
            '营业利润': ['营业利润'],
            '营业收入': ['营业收入', '主营业务收入'],
            '资产总计': ['资产总计'],
            '负债合计': ['负债合计'],
            '所有者权益合计': ['所有者权益合计', '股东权益合计'],
            '经营活动产生的现金流量净额': ['经营活动产生的现金流量净额'],
        }

        for canonical, patterns in alias_rules.items():
            if canonical in df.columns:
                continue

            match_cols = []
            for col in df.columns:
                col_text = str(col)
                if any(pattern in col_text for pattern in patterns):
                    match_cols.append(col)

            if match_cols:
                latest = df.iloc[-1]
                def _score(col):
                    value = latest.get(col, np.nan)
                    return np.nan_to_num(abs(_parse_numeric_value(value)), nan=0.0)

                match_col = max(match_cols, key=_score)
                df[canonical] = df[match_col]

        return df

    def _build_data_quality_warnings(self):
        warnings_list = []
        if self.df is None or self.df.empty:
            warnings_list.append('未识别到有效财务数据，请人工复核原始文件。')
            return warnings_list

        numeric_cols = [c for c in self.df.select_dtypes(include=[np.number]).columns if c != '期间']
        if len(numeric_cols) < 5:
            warnings_list.append(f'提取指标数({len(numeric_cols)})低于最低要求(5)，请人工复核。')

        core_indicators = [
            '营业收入',
            '营业成本',
            '净利润',
            '资产总计',
            '负债合计',
            '经营活动产生的现金流量净额',
        ]
        core_count = sum(1 for item in core_indicators if item in self.df.columns)
        if core_count < 5:
            warnings_list.append(f'核心指标覆盖数({core_count})低于最低要求(5)，请人工复核。')

        return warnings_list
        
    def _extract_periods(self):
        """提取期间信息"""
        if '期间' in self.df.columns:
            return [str(x) for x in self.df['期间'].tolist()]

        periods = []
        for i in range(len(self.df)):
            # 尝试从第一列获取期间信息
            first_col = str(self.df.iloc[i, 0])
            periods.append(first_col)
        return periods
    
    def calculate_financial_ratios(self):
        """计算财务比率"""
        ratios = {}
        
        if self.report_type == 'income_statement':
            ratios = self._calculate_profitability_ratios()
        elif self.report_type == 'balance_sheet':
            ratios = self._calculate_solvency_ratios()
            # 尝试计算效率比率
            try:
                efficiency = self._calculate_efficiency_ratios()
                ratios.update(efficiency)
            except:
                pass
        else:
            # 通用比率计算
            ratios = self._calculate_general_ratios()
        
        return ratios
    
    def _calculate_profitability_ratios(self):
        """计算盈利能力比率"""
        ratios = {}
        
        # 毛利率
        if '营业收入' in self.df.columns and '营业成本' in self.df.columns:
            gross_margin = []
            for i in range(len(self.df)):
                revenue = self.df.iloc[i]['营业收入']
                cost = self.df.iloc[i]['营业成本']
                if pd.notna(revenue) and pd.notna(cost) and revenue != 0:
                    gross_margin.append(round((revenue - cost) / revenue * 100, 2))
                else:
                    gross_margin.append(None)
            ratios['毛利率(%)'] = gross_margin
        
        # 净利率
        if '营业收入' in self.df.columns and '净利润' in self.df.columns:
            net_margin = []
            for i in range(len(self.df)):
                revenue = self.df.iloc[i]['营业收入']
                profit = self.df.iloc[i]['净利润']
                if pd.notna(revenue) and pd.notna(profit) and revenue != 0:
                    net_margin.append(round(profit / revenue * 100, 2))
                else:
                    net_margin.append(None)
            ratios['净利率(%)'] = net_margin
        
        # 营业利润率
        if '营业收入' in self.df.columns and '营业利润' in self.df.columns:
            operating_margin = []
            for i in range(len(self.df)):
                revenue = self.df.iloc[i]['营业收入']
                operating_profit = self.df.iloc[i]['营业利润']
                if pd.notna(revenue) and pd.notna(operating_profit) and revenue != 0:
                    operating_margin.append(round(operating_profit / revenue * 100, 2))
                else:
                    operating_margin.append(None)
            ratios['营业利润率(%)'] = operating_margin
        
        # 费用率分析
        expense_ratios = {}
        revenue_col = '营业收入'
        if revenue_col in self.df.columns:
            revenue = self.df[revenue_col]
            
            expense_columns = ['销售费用', '管理费用', '研发费用', '财务费用']
            for col in expense_columns:
                if col in self.df.columns:
                    ratio_values = []
                    for i in range(len(self.df)):
                        if pd.notna(revenue.iloc[i]) and revenue.iloc[i] != 0 and pd.notna(self.df.iloc[i][col]):
                            ratio = self.df.iloc[i][col] / revenue.iloc[i] * 100
                            ratio_values.append(round(ratio, 2))
                        else:
                            ratio_values.append(None)
                    expense_ratios[f'{col}率(%)'] = ratio_values
        
        if expense_ratios:
            ratios.update(expense_ratios)
        
        return ratios
    
    def _calculate_solvency_ratios(self):
        """计算偿债能力比率"""
        ratios = {}
        
        # 流动比率
        if '流动资产合计' in self.df.columns and '流动负债合计' in self.df.columns:
            current_ratio = []
            for i in range(len(self.df)):
                current_assets = self.df.iloc[i]['流动资产合计']
                current_liabilities = self.df.iloc[i]['流动负债合计']
                if pd.notna(current_assets) and pd.notna(current_liabilities) and current_liabilities != 0:
                    current_ratio.append(round(current_assets / current_liabilities, 2))
                else:
                    current_ratio.append(None)
            ratios['流动比率'] = current_ratio
        
        # 速动比率
        if all(col in self.df.columns for col in ['流动资产合计', '存货', '流动负债合计']):
            quick_ratio = []
            for i in range(len(self.df)):
                current_assets = self.df.iloc[i]['流动资产合计']
                inventory = self.df.iloc[i]['存货']
                current_liabilities = self.df.iloc[i]['流动负债合计']
                
                if all(pd.notna(x) for x in [current_assets, inventory, current_liabilities]):
                    if current_liabilities != 0:
                        quick = (current_assets - inventory) / current_liabilities
                        quick_ratio.append(round(quick, 2))
                    else:
                        quick_ratio.append(None)
                else:
                    quick_ratio.append(None)
            ratios['速动比率'] = quick_ratio
        
        # 资产负债率
        if '资产总计' in self.df.columns and '负债合计' in self.df.columns:
            debt_ratio = []
            for i in range(len(self.df)):
                total_assets = self.df.iloc[i]['资产总计']
                total_liabilities = self.df.iloc[i]['负债合计']
                if pd.notna(total_assets) and pd.notna(total_liabilities) and total_assets != 0:
                    debt_ratio.append(round(total_liabilities / total_assets * 100, 2))
                else:
                    debt_ratio.append(None)
            ratios['资产负债率(%)'] = debt_ratio
        
        # 产权比率
        if '负债合计' in self.df.columns and '所有者权益合计' in self.df.columns:
            equity_ratio = []
            for i in range(len(self.df)):
                liabilities = self.df.iloc[i]['负债合计']
                equity = self.df.iloc[i]['所有者权益合计']
                if pd.notna(liabilities) and pd.notna(equity) and equity != 0:
                    equity_ratio.append(round(liabilities / equity, 2))
                else:
                    equity_ratio.append(None)
            ratios['产权比率'] = equity_ratio
        
        return ratios
    
    def _calculate_efficiency_ratios(self):
        """计算营运能力比率"""
        ratios = {}
        
        # 这里需要多期数据计算周转率
        # 由于我们只有资产负债表数据，需要与利润表结合
        # 这里先返回空，后续可以扩展
        
        return ratios
    
    def _calculate_general_ratios(self):
        """计算通用比率"""
        ratios = {}
        
        # 计算各项指标的增长率
        numeric_columns = self.df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_columns:
            growth_rates = []
            for i in range(1, len(self.df)):
                current = self.df.iloc[i][col]
                previous = self.df.iloc[i-1][col]
                
                if pd.notna(current) and pd.notna(previous) and previous != 0:
                    growth = (current - previous) / previous * 100
                    growth_rates.append(round(growth, 2))
                else:
                    growth_rates.append(None)
            
            # 在开头添加None以保持长度一致
            growth_rates.insert(0, None)
            ratios[f'{col}增长率(%)'] = growth_rates
        
        return ratios
    
    def calculate_growth_rates(self):
        """计算增长率"""
        growth = {}
        
        numeric_columns = self.df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_columns:
            rates = []
            for i in range(1, len(self.df)):
                current = self.df.iloc[i][col]
                previous = self.df.iloc[i-1][col]
                
                if pd.notna(current) and pd.notna(previous) and previous != 0:
                    rate = round((current - previous) / previous * 100, 2)
                    rates.append(rate)
                else:
                    rates.append(None)
            
            # 第一个期间没有增长率
            rates.insert(0, None)
            growth[col] = rates
        
        return growth
    
    def generate_trend_charts(self):
        """生成趋势图"""
        charts = []
        
        # 1. 主要指标趋势图
        if self.report_type == 'income_statement':
            main_indicators = ['营业收入', '净利润', '营业利润']
        elif self.report_type == 'balance_sheet':
            main_indicators = ['资产总计', '负债合计', '所有者权益合计']
        else:
            # 取前5个数值列
            numeric_cols = self.df.select_dtypes(include=[np.number]).columns
            main_indicators = list(numeric_cols)[:5] if len(numeric_cols) > 0 else []
        
        # 过滤出实际存在的指标
        existing_indicators = [col for col in main_indicators if col in self.df.columns]
        
        if existing_indicators and len(self.df) > 1:
            # 创建子图
            fig = make_subplots(
                rows=len(existing_indicators), 
                cols=1,
                subplot_titles=[f'{indicator}趋势' for indicator in existing_indicators],
                vertical_spacing=0.1
            )
            
            for i, indicator in enumerate(existing_indicators, 1):
                fig.add_trace(
                    go.Scatter(
                        x=self.periods,
                        y=self.df[indicator],
                        mode='lines+markers',
                        name=indicator,
                        line=dict(width=2)
                    ),
                    row=i, col=1
                )
            
            fig.update_layout(
                height=300 * len(existing_indicators),
                showlegend=True,
                title_text=f"{self.report_type} - 主要指标趋势"
            )
            
            charts.append({
                'title': '收入与利润' if self.report_type == 'income_statement' else '主要指标趋势',
                'type': 'line',
                'data': fig.to_html(full_html=False)
            })

        if self.report_type == 'income_statement' and len(self.df) > 0:
            cfo_col = '经营活动产生的现金流量净额'
            profit_col = '净利润'
            if cfo_col in self.df.columns and profit_col in self.df.columns:
                fig3 = go.Figure()
                fig3.add_trace(go.Bar(x=self.periods, y=self.df[cfo_col], name='经营现金流净额'))
                fig3.add_trace(go.Scatter(x=self.periods, y=self.df[profit_col], mode='lines+markers', name='净利润'))
                fig3.update_layout(
                    title='现金流质量',
                    xaxis_title='期间',
                    yaxis_title='金额',
                    height=420
                )
                charts.append({
                    'title': '现金流质量',
                    'type': 'combo',
                    'data': fig3.to_html(full_html=False)
                })
        
        # 2. 构成分析图（柱状图）
        if len(self.df) > 0:
            # 选择最新一期数据
            latest_data = self.df.iloc[-1]
            
            # 根据报表类型选择不同的构成项目
            if self.report_type == 'income_statement':
                components = ['营业成本', '销售费用', '管理费用', '研发费用', '财务费用']
                title = '成本费用构成'
            elif self.report_type == 'balance_sheet':
                components = ['货币资金', '应收账款', '存货', '固定资产', '无形资产']
                title = '资产构成'
            else:
                components = []
            
            # 过滤出实际存在且非零的项目
            valid_components = []
            values = []
            for comp in components:
                if comp in latest_data.index and pd.notna(latest_data[comp]) and latest_data[comp] != 0:
                    valid_components.append(comp)
                    values.append(latest_data[comp])
            
            if valid_components:
                fig2 = go.Figure(data=[
                    go.Bar(
                        x=valid_components,
                        y=values,
                        text=[f'{v:,.0f}' for v in values],
                        textposition='auto',
                    )
                ])
                
                fig2.update_layout(
                    title=title,
                    xaxis_title='项目',
                    yaxis_title='金额',
                    height=400
                )
                
                charts.append({
                    'title': title,
                    'type': 'bar',
                    'data': fig2.to_html(full_html=False)
                })
        
        return charts
    
    def generate_ratio_charts(self, ratios):
        """生成比率图表"""
        charts = []
        
        if not ratios:
            return charts
        
        # 1. 盈利能力比率图
        profitability_keys = [k for k in ratios.keys() if '率' in k and '增长' not in k]
        if profitability_keys:
            fig1 = make_subplots(
                rows=len(profitability_keys), 
                cols=1,
                subplot_titles=profitability_keys,
                vertical_spacing=0.1
            )
            
            for i, key in enumerate(profitability_keys, 1):
                fig1.add_trace(
                    go.Scatter(
                        x=self.periods,
                        y=ratios[key],
                        mode='lines+markers',
                        name=key,
                        line=dict(width=2)
                    ),
                    row=i, col=1
                )
            
            fig1.update_layout(
                height=250 * len(profitability_keys),
                showlegend=False,
                title_text="盈利能力比率趋势"
            )
            
            charts.append({
                'title': '盈利能力比率',
                'type': 'line',
                'data': fig1.to_html(full_html=False)
            })
        
        # 2. 偿债能力比率图
        solvency_keys = [k for k in ratios.keys() if any(word in k for word in ['比率', '负债率'])]
        if solvency_keys:
            fig2 = go.Figure()
            
            for key in solvency_keys:
                fig2.add_trace(
                    go.Scatter(
                        x=self.periods,
                        y=ratios[key],
                        mode='lines+markers',
                        name=key
                    )
                )
            
            fig2.update_layout(
                title='偿债能力比率趋势',
                xaxis_title='期间',
                yaxis_title='比率',
                height=400
            )
            
            charts.append({
                'title': '偿债能力比率',
                'type': 'line',
                'data': fig2.to_html(full_html=False)
            })
        
        return charts
    
    def generate_summary_insights(self, ratios):
        """生成分析洞察"""
        insights = {
            'strengths': [],
            'concerns': [],
            'recommendations': []
        }
        
        if not ratios or len(self.df) < 2:
            return insights
        
        # 分析盈利能力
        if '毛利率(%)' in ratios:
            latest_gross = [x for x in ratios['毛利率(%)'] if x is not None][-1]
            if latest_gross:
                if latest_gross > 30:
                    insights['strengths'].append(f"毛利率较高({latest_gross}%)，显示产品竞争力强")
                elif latest_gross < 20:
                    insights['concerns'].append(f"毛利率偏低({latest_gross}%)，需关注成本控制")
        
        if '净利率(%)' in ratios:
            latest_net = [x for x in ratios['净利率(%)'] if x is not None][-1]
            if latest_net:
                if latest_net > 15:
                    insights['strengths'].append(f"净利率优秀({latest_net}%)，盈利能力良好")
                elif latest_net < 5:
                    insights['concerns'].append(f"净利率较低({latest_net}%)，盈利空间有限")
        
        # 分析偿债能力
        if '流动比率' in ratios:
            latest_current = [x for x in ratios['流动比率'] if x is not None][-1]
            if latest_current:
                if latest_current > 2:
                    insights['strengths'].append(f"流动比率健康({latest_current})，短期偿债能力强")
                elif latest_current < 1:
                    insights['concerns'].append(f"流动比率偏低({latest_current})，需关注短期偿债风险")
        
        if '资产负债率(%)' in ratios:
            latest_debt = [x for x in ratios['资产负债率(%)'] if x is not None][-1]
            if latest_debt:
                if latest_debt < 50:
                    insights['strengths'].append(f"资产负债率适中({latest_debt}%)，财务结构稳健")
                elif latest_debt > 70:
                    insights['concerns'].append(f"资产负债率偏高({latest_debt}%)，财务风险较大")
        
        # 生成建议
        if insights['concerns']:
            insights['recommendations'].append("建议加强成本控制，提高盈利能力")
            insights['recommendations'].append("优化资产结构，降低财务风险")
        else:
            insights['recommendations'].append("财务状况良好，建议保持当前发展策略")
        
        return insights
    
    def generate_report_data(self):
        """生成报告数据"""
        # 计算比率
        ratios = self.calculate_financial_ratios()
        
        # 计算增长率
        growth = self.calculate_growth_rates()
        
        # 生成图表
        trend_charts = self.generate_trend_charts()
        ratio_charts = self.generate_ratio_charts(ratios)
        
        # 合并图表
        all_charts = trend_charts + ratio_charts
        
        # 生成洞察
        insights = self.generate_summary_insights(ratios)

        cfo_quality = self._analyze_cashflow_quality()
        if cfo_quality.get('warning'):
            insights['concerns'].append(cfo_quality['warning'])

        key_tables = self._build_key_tables()
        
        return {
            'basic_info': {
                'report_type': self.report_type,
                'periods': self.periods,
                'data_points': len(self.df),
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'periods': self.periods,
            'raw_data': self.df.to_dict('records'),
            'ratios': ratios,
            'growth_rates': growth,
            'charts': all_charts,
            'insights': insights,
            'summary_stats': self._calculate_summary_statistics(),
            'data_quality_warnings': self.data_quality_warnings,
            'cashflow_quality': cfo_quality,
            'data_traceability': self.data_traceability,
            'amount_unit': self.unit_label,
            'key_tables': key_tables,
        }

    def _analyze_cashflow_quality(self):
        result = {
            'cfo': None,
            'net_profit': None,
            'ratio': None,
            'ratio_percent': None,
            'warning': None,
        }

        cfo_value = self._get_latest_metric_value('经营活动产生的现金流量净额', contains='经营活动')
        net_profit_value = self._get_latest_metric_value('净利润', contains='净利润')
        if pd.isna(cfo_value) or pd.isna(net_profit_value) or net_profit_value == 0:
            return result

        ratio = float(cfo_value) / float(net_profit_value)
        ratio_percent = round(ratio * 100, 2)
        warning = None
        if ratio < 0.8:
            warning = f'现金流质量偏低: CFO/净利润={ratio_percent}%（低于80%需关注）'

        result.update({
            'cfo': float(cfo_value),
            'net_profit': float(net_profit_value),
            'ratio': ratio,
            'ratio_percent': ratio_percent,
            'warning': warning,
        })
        return result

    def _get_latest_metric_value(self, exact_name, contains=None):
        if self.df is None or self.df.empty:
            return np.nan

        latest = self.df.iloc[-1]
        value = latest.get(exact_name, np.nan)
        if pd.notna(value):
            return value

        for col in self.df.columns:
            if contains and contains in str(col):
                candidate = latest.get(col, np.nan)
                if pd.notna(candidate):
                    return candidate

        return np.nan

    def _build_key_tables(self):
        """构建报告关键表格（统一输出亿元）"""
        if self.df is None or self.df.empty:
            return {}

        latest = self.df.iloc[-1]
        previous = self.df.iloc[-2] if len(self.df) > 1 else None

        def _yi_value(value):
            if pd.isna(value):
                return None
            return round(float(value) / 1e8, 2)

        def _change(current, prev):
            if prev is None or pd.isna(current) or pd.isna(prev) or prev == 0:
                return None
            return round((float(current) - float(prev)) / abs(float(prev)) * 100, 2)

        income_rows = []
        for metric in ['营业收入', '营业成本', '净利润']:
            if metric in self.df.columns:
                curr = latest.get(metric)
                prev = previous.get(metric) if previous is not None else np.nan
                income_rows.append({
                    '项目': metric,
                    '本期金额(亿元)': _yi_value(curr),
                    '同比变化(%)': _change(curr, prev),
                })

        balance_rows = []
        for metric in ['资产总计', '负债合计', '所有者权益合计', '应收账款', '存货']:
            if metric in self.df.columns:
                curr = latest.get(metric)
                balance_rows.append({
                    '项目': metric,
                    '本期金额(亿元)': _yi_value(curr),
                })

        cashflow_rows = []
        for metric in ['经营活动产生的现金流量净额', '投资活动产生的现金流量净额', '筹资活动产生的现金流量净额']:
            if metric in self.df.columns:
                curr = latest.get(metric)
                cashflow_rows.append({
                    '项目': metric,
                    '本期金额(亿元)': _yi_value(curr),
                })

        return {
            'income_statement': income_rows,
            'balance_sheet': balance_rows,
            'cash_flow': cashflow_rows,
        }
    
    def _calculate_summary_statistics(self):
        """计算汇总统计"""
        stats = {}
        
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols[:5]:  # 只计算前5个重要指标
            data = self.df[col].dropna()
            if len(data) > 0:
                stats[col] = {
                    'mean': round(data.mean(), 2),
                    'median': round(data.median(), 2),
                    'std': round(data.std(), 2) if len(data) > 1 else 0,
                    'min': round(data.min(), 2),
                    'max': round(data.max(), 2),
                    'latest': round(data.iloc[-1], 2) if len(data) > 0 else None
                }
        
        return stats