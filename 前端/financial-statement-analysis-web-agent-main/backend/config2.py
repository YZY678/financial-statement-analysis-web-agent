"""
配置文件 - 存储应用程序的配置参数
"""

# 应用程序配置
APP_CONFIG = {
    "name": "财经数据可视化Agent",
    "version": "3.0",
    "developer": "财经数据可视化工作室",
    "contact": "contact@finance-viz.com"
}

# 界面配置
UI_CONFIG = {
    "window_size": "1000x700",
    "theme": "clam",  # 可选: clam, alt, default, classic
    "color_scheme": {
        "primary": "#2c3e50",      # 深蓝色
        "secondary": "#3498db",    # 蓝色
        "accent": "#2ecc71",       # 绿色
        "background": "#ecf0f1",   # 浅灰色
        "text": "#2c3e50",         # 深灰色
        "success": "#27ae60",      # 成功绿
        "warning": "#f39c12",      # 警告橙
        "error": "#e74c3c"         # 错误红
    },
    "font": {
        "title": ("微软雅黑", 16, "bold"),
        "heading": ("微软雅黑", 12, "bold"),
        "normal": ("微软雅黑", 10),
        "monospace": ("Consolas", 10)
    }
}

# 路径配置
PATH_CONFIG = {
    "charts_dir": "./output/charts",
    "reports_dir": "./output/reports",
    "data_dir": "./data",
    "logs_dir": "./logs"
}

# 工具配置
TOOLS_CONFIG = {
    "supported_formats": [".csv", ".xlsx", ".xls"],
    "chart_types": [
        "income_trend",      # 收入趋势图
        "profit_composition", # 利润构成图
        "balance_sheet",     # 资产负债表图表
        "revenue_comparison", # 收入对比图
        "expense_breakdown"  # 费用分解图
    ],
    "chart_defaults": {
        "width": 12,
        "height": 8,
        "dpi": 300,
        "output_dir": "./output/charts"
    }
}

# 大脑配置
BRAIN_CONFIG = {
    "confidence_threshold": 0.3,  # 置信度阈值
    "max_history": 20,            # 最大对话历史
    "auto_clean_data": True       # 自动清洗数据
}

# 导出配置
EXPORT_CONFIG = {
    "image_formats": [".png", ".jpg", ".svg", ".pdf"],
    "report_formats": [".json", ".txt", ".html"],
    "default_format": ".png"
}