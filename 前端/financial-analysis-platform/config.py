import os
from datetime import timedelta

class Config:
    """基础配置"""
    
    # 安全配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'financial-analysis-secret-2024'
    
    # 文件上传配置
    UPLOAD_FOLDER = 'uploads'
    REPORT_FOLDER = 'reports'
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    
    # 允许的文件格式
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'docx', 'pdf'}
    
    # 财务报表模板映射
    FINANCIAL_TEMPLATES = {
        'income_statement': '利润表',
        'balance_sheet': '资产负债表', 
        'cash_flow': '现金流量表',
        'combined': '合并财务报表'
    }
    
    # 分析类型
    ANALYSIS_TYPES = {
        'basic': '基础财务分析',
        'profitability': '盈利能力分析',
        'solvency': '偿债能力分析',
        'growth': '成长能力分析',
        'efficiency': '营运能力分析',
        'agent': 'Agent财务分析',
        'comprehensive': '全面财务分析'
    }
    
    # 财务报表标准列名（用于自动识别）
    INCOME_STATEMENT_COLUMNS = ['营业收入', '营业成本', '毛利润', '销售费用', '管理费用', 
                               '研发费用', '财务费用', '营业利润', '净利润', '每股收益']
    
    BALANCE_SHEET_COLUMNS = ['货币资金', '应收账款', '存货', '流动资产合计', '固定资产', 
                            '无形资产', '非流动资产合计', '资产总计', '短期借款', '应付账款',
                            '流动负债合计', '长期借款', '非流动负债合计', '负债合计', 
                            '股本', '资本公积', '盈余公积', '未分配利润', '所有者权益合计']
    
    # 财务比率计算公式
    FINANCIAL_RATIOS = {
        'profitability': {
            '毛利率': '毛利润 / 营业收入',
            '净利率': '净利润 / 营业收入',
            'ROE': '净利润 / 所有者权益合计',
            'ROA': '净利润 / 资产总计'
        },
        'solvency': {
            '流动比率': '流动资产合计 / 流动负债合计',
            '速动比率': '(流动资产合计 - 存货) / 流动负债合计',
            '资产负债率': '负债合计 / 资产总计',
            '产权比率': '负债合计 / 所有者权益合计'
        },
        'efficiency': {
            '应收账款周转率': '营业收入 / 应收账款',
            '存货周转率': '营业成本 / 存货',
            '总资产周转率': '营业收入 / 资产总计'
        },
        'growth': {
            '营收增长率': '(本期营业收入 - 上期营业收入) / 上期营业收入',
            '净利润增长率': '(本期净利润 - 上期净利润) / 上期净利润',
            '总资产增长率': '(本期资产总计 - 上期资产总计) / 上期资产总计'
        }
    }
    
    # 图表颜色配置
    CHART_COLORS = {
        'primary': '#2E86AB',
        'success': '#A8D5BA',
        'warning': '#F9C784',
        'danger': '#F76C5E',
        'info': '#68C3D4',
        'secondary': '#6C757D'
    }

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    # Keep CSRF functional even when SECRET_KEY is not injected by runtime env.
    SECRET_KEY = os.environ.get('SECRET_KEY') or Config.SECRET_KEY

# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}