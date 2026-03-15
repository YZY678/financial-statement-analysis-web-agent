## 财报分析平台

一个面向财务报表的分析与可视化平台，支持上传 CSV/Excel/PDF，自动识别报表类型，计算财务比率并生成可视化报告。

### 功能概览
- 多格式财务报表上传与校验
- 自动识别报表类型（利润表/资产负债表/现金流量表）
- 财务比率与趋势图表分析
- 报告导出与在线查看
- Agent 财务分析视图（在结果页展示）
- 支持图片、DOCX 与 PDF 报表解析（OCR/表格提取）

### 目录结构（核心）
```
financial-analysis-platform/
  app.py                  # Flask 主应用
  run.py                  # 启动脚本（支持环境变量）
  config.py               # 配置项
  models/                 # 数据模型
  services/               # 服务层（任务管理）
  utils/                  # 文件解析与分析逻辑
  templates/              # 页面模板
  static/                 # 静态资源
  data/samples/           # 示例文件
  reports/                # 生成报告
  uploads/                # 上传文件
```

### 运行要求
- Python 3.10+
- 依赖见 requirements.txt
- 若使用图片报表：需安装 Tesseract OCR（系统依赖）

### 快速启动
1. 安装依赖：
	- `pip install -r requirements.txt`
2. 启动应用：
	- `python run.py`
3. 访问：
	- http://127.0.0.1:5000

### 环境变量
| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| APP_ENV | 运行环境（development/production） | default |
| APP_HOST | 监听地址 | 0.0.0.0 |
| APP_PORT | 端口 | 5000 |
| APP_DEBUG | 调试模式 | 继承配置 |

### 使用流程
1. 打开首页进入财报分析页面
2. 上传财务报表文件并选择分析类型
3. 等待任务完成，查看结果/报告

### 图片/DOCX/PDF 说明
- 图片报表通过 OCR 识别并解析为表格，建议使用清晰扫描件。
- DOCX 报表需使用表格形式（优先解析第一个表格）。
- PDF 报表优先提取表格，若未识别到表格则回退为文本行解析。

### 说明
- 任务状态与分析结果在内存中维护（生产环境建议替换为数据库）。
- Agent 财务分析为结果页的独立视图，仅在选择 Agent 分析类型时展示。

### Agent 接口对照（GitHub 工具名 ↔ Web API）

为兼容 GitHub 仓库常见工具命名，后端提供统一执行入口：

- `POST /api/agent/sessions/<session_id>/execute`

请求体：

```json
{
  "tool_name": "create_professional_chart",
  "tool_params": {
    "chart_type": "income_trend",
    "title": "收入趋势分析"
  }
}
```

#### 工具映射表

| GitHub 工具名 | 统一执行 tool_name | 关键参数 | 成功返回关键字段 |
| --- | --- | --- | --- |
| upload_file | parse_finance_file | file_path | status, report_info, session |
| parse_finance_file | parse_finance_file | file_path | status, report_info, session |
| detect_report_type | detect_report_type | （可空） | status, report_info, session |
| clean_financial_data | clean_financial_data | （可空） | status, cleaning_report, session |
| create_professional_chart | create_professional_chart | chart_type（可空/auto=自动多图）, title, output_dir（可空） | status, chart/charts |
| analyze_financial_health | analyze_financial_health | （可空） | status, analysis |
| compare_chart | compare_chart | metric 或 metrics, title | status, chart/charts |
| compare_table | compare_table | metrics（可空） | status, metrics, table |
| status / get_status | status | （可空） | status, session |
| reset | reset | reset_type=soft/hard（默认soft） | status, reset_type, session |
| export_session_report | export_session_report | format=json/html/txt/zip | status, download_url |

#### 仍可直接调用的细粒度接口

- 会话：`POST /api/agent/sessions`、`GET /api/agent/sessions/<session_id>/status`
- 上传：`POST /api/agent/sessions/<session_id>/upload`、`POST /api/agent/sessions/<session_id>/upload-multiple`
- 分析：`POST /api/agent/sessions/<session_id>/clean`、`POST /api/agent/sessions/<session_id>/analyze`
- 图表/对比：`POST /api/agent/sessions/<session_id>/chart`、`POST /api/agent/sessions/<session_id>/compare/chart`、`POST /api/agent/sessions/<session_id>/compare/table`
- 其他：`GET /api/agent/config`、`GET /api/agent/sessions/<session_id>/logs`、`GET /api/agent/sessions/<session_id>/export?format=json|html|txt|zip`
