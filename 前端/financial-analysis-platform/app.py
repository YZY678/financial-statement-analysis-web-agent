"""
财报分析平台 - 主应用
"""

import os
import uuid
import json
import threading
import time
import csv
import zipfile
import re
import html
import textwrap
import subprocess
import signal
from io import StringIO, BytesIO
from datetime import datetime
from typing import Any, Dict, List
import pandas as pd
import plotly.graph_objects as go
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session, Response
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SubmitField, SelectField, StringField, BooleanField
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# 导入配置和工具
from config import config
from utils.file_processor import FileProcessor
from utils.financial_analyzer import FinancialAnalyzer
from utils.report_alignment import align_report_with_reference
from models.task import Task
from services.task_store import TaskStore
from services.agent_session_store import AgentSessionStore
from services.upstream_agent_runtime import upstream_agent_manager
from services.upstream_report_runtime import upstream_report_runtime
from models.agent_session import AgentSession
from utils.agent_tools import (
    analyze_financial_health,
    build_comparison_table,
    clean_financial_data,
    create_comparison_chart,
    create_multi_metric_comparison_charts,
    create_professional_chart,
    detect_financial_report_type,
    load_financial_data,
    CHART_TYPES,
    DEFAULT_OUTPUT_DIR,
    SUPPORTED_FORMATS,
)
from utils.agent_brain import AgentBrain

# ==================== 初始化应用 ====================

app = Flask(__name__)
env_name = os.environ.get('APP_ENV', 'default')
app.config.from_object(config.get(env_name, config['default']))

# Flask-WTF requires a non-empty secret key for CSRF token generation.
if not app.config.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = 'financial-analysis-secret-2024'

MAX_ANALYSIS_FILE_SIZE_BYTES = app.config.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024)

# Use absolute storage paths so background jobs/subprocesses can always resolve files.
_APP_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
for _path_key in ['UPLOAD_FOLDER', 'REPORT_FOLDER']:
    current_path = app.config.get(_path_key)
    if current_path and not os.path.isabs(current_path):
        app.config[_path_key] = os.path.abspath(os.path.join(_APP_BASE_DIR, current_path))

# 确保目录存在
for folder in [app.config['UPLOAD_FOLDER'], app.config['REPORT_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# ==================== 全局变量 ====================

# 存储任务信息（生产环境用数据库）
task_store = TaskStore()
agent_session_store = AgentSessionStore()

# ==================== 表单定义 ====================

class FinancialUploadForm(FlaskForm):
    """财务报表上传表单"""
    file = FileField('选择财务报表文件', validators=[
        FileRequired(message='请选择财务报表文件'),
        FileAllowed(['csv', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'docx', 'pdf'], 
                   message='只支持CSV、Excel、图片、DOCX和PDF格式')
    ])
    
    report_type = SelectField(
        '报表类型',
        choices=[
            ('auto', '自动检测'),
            ('income_statement', '利润表'),
            ('balance_sheet', '资产负债表'),
            ('cash_flow', '现金流量表'),
            ('combined', '合并财务报表')
        ],
        default='auto'
    )
    
    analysis_type = SelectField(
        '分析类型',
        choices=[
            ('basic', '基础分析'),
            ('profitability', '盈利能力分析'),
            ('solvency', '偿债能力分析'),
            ('growth', '成长性分析'),
            ('agent', 'Agent财务分析'),
            ('comprehensive', '全面分析')
        ],
        default='comprehensive'
    )
    
    company_name = StringField('公司名称')
    include_benchmark = BooleanField('包含行业基准对比')
    
    submit = SubmitField('开始分析', render_kw={"class": "btn-primary btn-lg"})

# ==================== 任务管理 ====================

def create_financial_task(filepath, filename, form_data):
    """创建财务分析任务"""
    task_id = str(uuid.uuid4())

    task = Task(
        id=task_id,
        filename=filename,
        filepath=filepath,
        company_name=form_data.get('company_name', filename),
        report_type=form_data.get('report_type', 'auto'),
        analysis_type=form_data.get('analysis_type', 'comprehensive'),
        status='pending',
        progress=0,
        start_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        end_time=None,
        results=None,
        error=None,
        user_data=form_data
    )
    task_store.create(task)
    
    return task_id


def _get_upload_file_size(file_storage):
    """Return uploaded file size in bytes when available."""
    if not file_storage:
        return 0

    if file_storage.content_length is not None:
        return file_storage.content_length

    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return 0

    try:
        current_pos = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current_pos)
        return size
    except Exception:
        return 0


def _is_file_size_allowed(file_storage):
    """Check whether uploaded file size stays within configured byte limit."""
    return _get_upload_file_size(file_storage) <= MAX_ANALYSIS_FILE_SIZE_BYTES


def _resolve_file_path(path: str) -> str:
    """Resolve legacy relative paths against app root and return absolute path."""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(_APP_BASE_DIR, path))


def _is_task_cancelled(task_id: str) -> bool:
    task = task_store.get(task_id)
    return bool(task and task.status == 'cancelled')


def _terminate_upstream_process_for_task(task_id: str) -> int:
    """Best-effort terminate upstream subprocess launched for a task id."""
    killed = 0
    pattern = f"upstream_{task_id}"
    try:
        completed = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return 0

        for line in (completed.stdout or '').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except Exception:
                continue
    except Exception:
        return 0
    return killed


def _has_upstream_process_for_task(task_id: str) -> bool:
    """Return whether an upstream subprocess for the task id is still alive."""
    pattern = f"upstream_{task_id}"
    try:
        completed = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and bool((completed.stdout or '').strip())
    except Exception:
        return False


def _resolve_upstream_timeout_seconds() -> int:
    raw = os.environ.get("UPSTREAM_REPORT_TIMEOUT_SECONDS", "1200")
    try:
        timeout = int(raw)
    except Exception:
        timeout = 1200
    return min(max(60, timeout), 1200)


def _to_float(value):
    """Best-effort numeric parsing for heterogeneous metric values."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace(',', '').replace('，', '').replace('%', '')
    try:
        return float(text)
    except Exception:
        return None


def _figure_to_chart(title: str, fig) -> Dict[str, Any]:
    return {
        "title": title,
        "data": fig.to_html(full_html=False, include_plotlyjs=False),
    }


def _load_upstream_metric_map(upstream_output_dir: str) -> Dict[str, Any]:
    """Read upstream exported metric CSV into a compact metric map."""
    metric_csv = os.path.join(upstream_output_dir, "financial_metrics.csv")
    if not os.path.exists(metric_csv):
        return {}

    try:
        df = pd.read_csv(metric_csv)
    except Exception:
        return {}

    metric_map: Dict[str, Any] = {}
    for _, row in df.iterrows():
        key = str(row.get("指标英文", "")).strip()
        if not key:
            continue
        raw_value = row.get("数值")
        value = _to_float(raw_value)
        metric_map[key] = value if value is not None else raw_value
    return metric_map


def _build_visual_charts_from_metrics(metric_map: Dict[str, Any], amount_unit: str = "亿元") -> List[Dict[str, Any]]:
    """Build deterministic Plotly charts from normalized metric map."""
    charts: List[Dict[str, Any]] = []

    revenue = _to_float(metric_map.get("revenue"))
    net_income = _to_float(metric_map.get("net_income"))
    operating_cashflow = _to_float(metric_map.get("operating_cashflow"))
    gross_margin = _to_float(metric_map.get("gross_margin"))
    net_margin = _to_float(metric_map.get("net_margin"))
    revenue_yoy = _to_float(metric_map.get("revenue_yoy"))
    net_income_yoy = _to_float(metric_map.get("net_income_yoy"))

    if any(v is not None for v in [revenue, net_income, operating_cashflow]):
        labels = []
        values = []
        for label, val in [
            ("营业收入", revenue),
            ("归母净利润", net_income),
            ("经营现金流", operating_cashflow),
        ]:
            if val is not None:
                labels.append(label)
                values.append(val)
        fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color=['#1f77b4', '#ff7f0e', '#2ca02c'][:len(values)])])
        fig.update_layout(template="plotly_white", yaxis_title=f"金额（{amount_unit}）")
        charts.append(_figure_to_chart("核心金额指标", fig))

    if any(v is not None for v in [gross_margin, net_margin]):
        labels = []
        values = []
        for label, val in [("毛利率", gross_margin), ("净利率", net_margin)]:
            if val is not None:
                labels.append(label)
                values.append(val)
        fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color=['#17becf', '#9467bd'][:len(values)])])
        fig.update_layout(template="plotly_white", yaxis_title="比率（%）")
        charts.append(_figure_to_chart("利润率指标", fig))

    if any(v is not None for v in [revenue_yoy, net_income_yoy]):
        x = ["收入同比", "净利润同比"]
        y = [revenue_yoy or 0.0, net_income_yoy or 0.0]
        fig = go.Figure(data=[go.Scatter(x=x, y=y, mode='lines+markers', line=dict(color='#d62728', width=3))])
        fig.update_layout(template="plotly_white", yaxis_title="同比（%）")
        charts.append(_figure_to_chart("同比变化", fig))

    return charts


def _build_summary_stats_from_metrics(metric_map: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    summary_stats: Dict[str, Dict[str, Any]] = {}
    mapping = {
        "营业收入": "revenue",
        "归母净利润": "net_income",
        "经营现金流": "operating_cashflow",
        "毛利率(%)": "gross_margin",
    }
    for label, key in mapping.items():
        value = _to_float(metric_map.get(key))
        if value is None:
            continue
        summary_stats[label] = {
            "latest": value,
            "mean": value,
            "max": value,
            "min": value,
            "trend": "stable",
        }
    return summary_stats


def _ensure_visualizable_results(results: Dict[str, Any], report_path: str | None = None) -> Dict[str, Any]:
    """Guarantee charts field for frontend rendering across all file types."""
    if not isinstance(results, dict):
        return {"charts": []}

    charts = results.get("charts")
    if isinstance(charts, list) and len(charts) > 0:
        return results

    candidate_metrics: Dict[str, Any] = {}
    for key in [
        "revenue", "net_income", "operating_cashflow", "gross_margin", "net_margin", "revenue_yoy", "net_income_yoy"
    ]:
        if key in results:
            candidate_metrics[key] = results.get(key)

    if not candidate_metrics and isinstance(results.get("summary_stats"), dict):
        stats = results.get("summary_stats") or {}
        candidate_metrics["revenue"] = (stats.get("营业收入") or {}).get("latest")
        candidate_metrics["net_income"] = (stats.get("净利润") or {}).get("latest")
        candidate_metrics["gross_margin"] = (stats.get("毛利率(%)") or {}).get("latest")

    built = _build_visual_charts_from_metrics(candidate_metrics, amount_unit=results.get("amount_unit", "亿元"))
    if built:
        results["charts"] = built
    else:
        results.setdefault("charts", [])

    return results


def _report_content_to_html(report_content: str, report_path: str) -> str:
    """Convert report content to safe display HTML for report page rendering."""
    def _remove_code_like_segments(text: str) -> str:
        if not text:
            return ''
        cleaned = text
        # Remove fenced code blocks from markdown-like content.
        cleaned = re.sub(r"```[\s\S]*?```", "\n", cleaned)
        lines = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                lines.append(raw_line)
                continue
            if re.match(r"^<!DOCTYPE", line, flags=re.IGNORECASE):
                continue
            if re.match(r"^</?html|^</?head|^</?body|^</?style|^</?script", line, flags=re.IGNORECASE):
                continue
            if re.match(r"^[.#]?[A-Za-z_][\w\-\s>*:,\[\]""'=()]+\{\s*$", line):
                continue
            if re.match(r"^[A-Za-z\-]+\s*:\s*[^;]+;\s*$", line):
                continue
            if line == '}':
                continue
            lines.append(raw_line)
        return "\n".join(lines)

    def _drop_code_like_html_nodes(fragment: str) -> str:
        if not fragment:
            return ''
        cleaned = fragment
        node_patterns = [
            r"<(?P<tag>p|li|div|span)[^>]*>\s*[.#]?[A-Za-z_][\w\-\s>*:,\[\]\"'=()]+\{\s*</(?P=tag)>",
            r"<(?P<tag>p|li|div|span)[^>]*>\s*[A-Za-z\-]+\s*:\s*[^;]+;\s*</(?P=tag)>",
            r"<(?P<tag>p|li|div|span)[^>]*>\s*}\s*</(?P=tag)>",
        ]
        for pattern in node_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned

    if report_path.lower().endswith('.html'):
        html_doc = re.sub(r"<script[\s\S]*?</script>", "", report_content or '', flags=re.IGNORECASE)
        html_doc = re.sub(r"<style[\s\S]*?</style>", "", html_doc, flags=re.IGNORECASE)
        body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_doc, flags=re.IGNORECASE)
        body_html = body_match.group(1) if body_match else html_doc
        body_html = re.sub(r"<pre[\s\S]*?</pre>", "", body_html, flags=re.IGNORECASE)
        body_html = re.sub(r"<code[\s\S]*?</code>", "", body_html, flags=re.IGNORECASE)
        body_html = _drop_code_like_html_nodes(body_html)
        return body_html

    cleaned_report = _remove_code_like_segments(report_content)
    try:
        import markdown  # type: ignore
        rendered = markdown.markdown(cleaned_report, extensions=['tables', 'fenced_code'])
        # Hide code blocks in "raw report" area so users only see visualized narrative.
        rendered = re.sub(r"<pre[\s\S]*?</pre>", "", rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"<code[\s\S]*?</code>", "", rendered, flags=re.IGNORECASE)
        rendered = _drop_code_like_html_nodes(rendered)
        return rendered
    except Exception:
        # Fallback keeps content readable even if markdown package is unavailable.
        escaped = html.escape(cleaned_report or '')
        return f"<pre style='white-space: pre-wrap; word-break: break-word;'>{escaped}</pre>"


def _html_fragment_to_text(fragment: str) -> str:
    """Convert HTML fragment to readable plain text while keeping section breaks."""
    if not fragment:
        return ''
    text = fragment
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li\s*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_pdf_text_from_report_view(task: Task, structured: Dict[str, Any], report_content_html: str) -> str:
    """Build PDF export text from the same content sources as the online report page."""
    lines: List[str] = []

    company = task.company_name or task.filename or task.id
    lines.append(f"财务分析报告 - {company}")
    lines.append("")

    def _append_section(title: str, items: List[str]) -> None:
        if not items:
            return
        lines.append(title)
        for item in items:
            normalized = _normalize_report_sentence(item)
            if normalized:
                lines.append(f"- {normalized}")
        lines.append("")

    _append_section('执行摘要', structured.get('executive_points') or [])
    _append_section('关键发现', structured.get('key_findings') or [])
    _append_section('数据质量', structured.get('data_quality') or [])
    _append_section('建议与措施', structured.get('recommendations') or [])
    _append_section('风险提示', structured.get('risks') or [])
    _append_section('结论', structured.get('conclusion') or [])

    ratios = structured.get('ratios') or []
    if ratios:
        lines.append('财务比率分析')
        for row in ratios:
            name = str((row or {}).get('name') or '').strip()
            latest = str((row or {}).get('latest') or '').strip()
            if name:
                lines.append(f"- {name}: {latest}")
        lines.append('')

    raw_text = _html_fragment_to_text(report_content_html)
    if raw_text:
        lines.append('报告正文（后端原始报告，可视化渲染）')
        lines.append(raw_text)

    return "\n".join(lines).strip()


def _report_content_to_plain_text(report_content: str, report_path: str) -> str:
    """Convert markdown/html report content to readable plain text for PDF export."""
    if not report_content:
        return ''

    content = report_content
    if report_path.lower().endswith('.html'):
        content = re.sub(r"<script[\\s\\S]*?</script>", " ", content, flags=re.IGNORECASE)
        content = re.sub(r"<style[\\s\\S]*?</style>", " ", content, flags=re.IGNORECASE)
        content = re.sub(r"<br\\s*/?>", "\n", content, flags=re.IGNORECASE)
        content = re.sub(r"</p\\s*>", "\n", content, flags=re.IGNORECASE)
        content = re.sub(r"</h[1-6]\\s*>", "\n", content, flags=re.IGNORECASE)
        content = re.sub(r"<li\\s*>", "- ", content, flags=re.IGNORECASE)
        content = re.sub(r"</li\\s*>", "\n", content, flags=re.IGNORECASE)
        content = re.sub(r"<[^>]+>", " ", content)

    content = html.unescape(content)
    content = re.sub(r"\r\n?", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = re.sub(r"[ \t]{2,}", " ", content)
    return content.strip()


def _build_report_pdf_bytes(title: str, content: str) -> BytesIO:
    """Build a PDF file buffer for report download."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("缺少 reportlab 依赖，无法导出 PDF") from exc

    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    page_width, page_height = A4
    left_margin = 42
    right_margin = 42
    top_margin = 48
    bottom_margin = 48
    body_font_size = 10.5
    title_font_size = 16
    line_height = 15
    max_chars_per_line = 60
    max_total_chars = 200000

    c = canvas.Canvas(buffer, pagesize=A4)

    def _new_page() -> float:
        c.showPage()
        c.setFont('STSong-Light', body_font_size)
        return page_height - top_margin

    c.setFont('STSong-Light', title_font_size)
    safe_title = (title or '财务分析报告').strip()[:120]
    c.drawCentredString(page_width / 2, page_height - top_margin, safe_title)

    y = page_height - top_margin - 28
    c.setFont('STSong-Light', body_font_size)

    plain = (content or '').replace('\r\n', '\n').replace('\r', '\n')
    if len(plain) > max_total_chars:
        plain = plain[:max_total_chars] + '\n\n[内容过长，已截断导出]'

    for raw_line in plain.split('\n'):
        line = raw_line.strip()
        wrapped_lines = [''] if not line else textwrap.wrap(line, width=max_chars_per_line, break_long_words=True, break_on_hyphens=False)
        for wrapped in wrapped_lines:
            if y < bottom_margin:
                y = _new_page()
            c.drawString(left_margin, y, wrapped)
            y -= line_height

    c.save()
    buffer.seek(0)
    return buffer


def _extract_report_indicators(report_content: str) -> List[Dict[str, str]]:
    """Extract key report indicators so result page can reflect report metrics."""
    if not report_content:
        return []

    plain = re.sub(r"<[^>]+>", " ", report_content)
    plain = re.sub(r"\s+", " ", plain)
    patterns = [
        ("营业收入", r"营业收入(?:总计)?[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(亿元|万元|元)"),
        ("净利润", r"(?:归母净利润|净利润)[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(亿元|万元|元)"),
        ("经营活动现金流", r"经营活动现金流(?:量净额)?[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(亿元|万元|元)"),
        ("毛利率", r"毛利率[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
        ("净利率", r"净利率[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
        ("资产负债率", r"资产负债率[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
        ("ROE", r"ROE[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
        ("ROA", r"ROA[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
        ("流动比率", r"流动比率[^\d-]{0,20}(-?\d+(?:\.\d+)?)"),
        ("速动比率", r"速动比率[^\d-]{0,20}(-?\d+(?:\.\d+)?)"),
        ("CFO/净利润", r"(?:CFO/净利润|经营活动现金流/净利润)[^\d-]{0,20}(-?\d+(?:\.\d+)?)\s*(%)"),
    ]

    indicators: List[Dict[str, str]] = []
    seen = set()
    for name, pattern in patterns:
        match = re.search(pattern, plain)
        if not match:
            continue
        value = match.group(1)
        unit = match.group(2) if len(match.groups()) >= 2 else ""
        key = (name, value, unit)
        if key in seen:
            continue
        seen.add(key)
        indicators.append({"name": name, "value": value, "unit": unit})
    return indicators


def _rewrite_report_asset_urls(report_html: str, task_id: str) -> str:
    """Rewrite local report assets (e.g. charts/*.png) to Flask asset route."""
    if not report_html:
        return report_html

    def _replace(match):
        attr = match.group(1)
        quote = match.group(2)
        url = (match.group(3) or '').strip()
        lower = url.lower()
        if not url or lower.startswith(('http://', 'https://', 'data:', 'javascript:', '#', '/')):
            return match.group(0)

        normalized = url
        if normalized.startswith('./'):
            normalized = normalized[2:]
        while normalized.startswith('../'):
            normalized = normalized[3:]
        if normalized.startswith('output/'):
            normalized = normalized[len('output/'):]

        if normalized.startswith('charts/'):
            rewritten = f"/report_asset/{task_id}/{normalized}"
            return f"{attr}={quote}{rewritten}{quote}"
        return match.group(0)

    return re.sub(r'(src|href)\s*=\s*(["\'])([^"\']+)\2', _replace, report_html)


def _parse_float_text(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(',', '').replace('，', '')
    text = text.replace('%', '')
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _normalize_report_sentence(text: str) -> str:
    """Normalize extracted sentence for UI display by removing markdown/control noise."""
    if not text:
        return ''

    cleaned = str(text)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace('**', '').replace('__', '').replace('`', '')
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned)
    cleaned = re.sub(r"^\s*\d+[\.)、]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(' \t\n\r:：-')

    # Drop pure section headers that have little informational value by themselves.
    if cleaned in {'执行摘要', '关键发现', '数据质量', '风险提示', '结论', '建议与措施', '数据溯源'}:
        return ''
    return cleaned


def _sanitize_sentence_list(items: List[str], max_items: int | None = None) -> List[str]:
    sanitized: List[str] = []
    seen = set()
    for item in items:
        normalized = _normalize_report_sentence(item)
        if len(normalized) < 8:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        sanitized.append(normalized)
        if max_items is not None and len(sanitized) >= max_items:
            break
    return sanitized


def _extract_keyword_sentences(report_content: str, keywords: List[str], max_items: int = 4) -> List[str]:
    if not report_content:
        return []
    plain = re.sub(r"<[^>]+>", " ", report_content)
    pieces = re.split(r"[\n。；;]+", plain)
    results: List[str] = []
    for piece in pieces:
        sentence = _normalize_report_sentence(piece)
        if len(sentence) < 8:
            continue
        if any(k in sentence for k in keywords):
            results.append(sentence)
        if len(results) >= max_items:
            break
    return _sanitize_sentence_list(results, max_items=max_items)


def _build_report_derived_charts(indicators: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    charts: List[Dict[str, Any]] = []
    amount_items: List[Dict[str, Any]] = []
    ratio_items: List[Dict[str, Any]] = []

    for item in indicators:
        value = _parse_float_text(item.get('value'))
        if value is None:
            continue
        unit = item.get('unit', '')
        name = item.get('name', '指标')
        if unit == '%' or any(tag in name for tag in ['率', 'ROE', 'ROA', '比率', 'CFO/']):
            ratio_items.append({'name': name, 'value': value})
        else:
            amount_items.append({'name': name, 'value': value})

    if amount_items:
        amount_items = amount_items[:8]
        fig = go.Figure(
            data=[go.Bar(
                x=[x['name'] for x in amount_items],
                y=[x['value'] for x in amount_items],
                marker_color=['#0f5e63', '#158e95', '#2e86ab', '#68c3d4', '#f08a3c', '#f9c784', '#6c757d', '#a8d5ba'][:len(amount_items)]
            )]
        )
        fig.update_layout(template='plotly_white', title='报告提取指标金额对比', yaxis_title='数值')
        charts.append(_figure_to_chart('报告提取指标金额对比', fig))

        pie_items = [x for x in amount_items if x['value'] > 0]
        if pie_items:
            fig = go.Figure(
                data=[go.Pie(labels=[x['name'] for x in pie_items], values=[x['value'] for x in pie_items], hole=0.45)]
            )
            fig.update_layout(template='plotly_white', title='报告提取指标结构占比')
            charts.append(_figure_to_chart('报告提取指标结构占比', fig))

    if ratio_items:
        ratio_items = ratio_items[:8]
        fig = go.Figure(
            data=[go.Bar(
                x=[x['name'] for x in ratio_items],
                y=[x['value'] for x in ratio_items],
                marker_color='#f08a3c'
            )]
        )
        fig.update_layout(template='plotly_white', title='报告提取比率指标', yaxis_title='百分比(%)')
        charts.append(_figure_to_chart('报告提取比率指标', fig))

    return charts


def _build_structured_analysis_from_report(task: Task, report_content: str) -> Dict[str, Any]:
    """Build a rich structured analysis layer based on backend report content."""
    results = task.results if isinstance(task.results, dict) else {}
    indicators = _extract_report_indicators(report_content)

    insights = results.get('insights') or {}
    strengths = _sanitize_sentence_list(list(insights.get('strengths') or []), max_items=6)
    concerns = _sanitize_sentence_list(list(insights.get('concerns') or []), max_items=6)
    recommendations = _sanitize_sentence_list(list(insights.get('recommendations') or []), max_items=6)

    if not strengths:
        strengths = _extract_keyword_sentences(report_content, ['增长', '改善', '提升', '稳健', '充足', '向好'])
    if not concerns:
        concerns = _extract_keyword_sentences(report_content, ['风险', '下降', '下滑', '不足', '压力', '波动'])
    if not recommendations:
        recommendations = _extract_keyword_sentences(report_content, ['建议', '应当', '可以', '需要', '优化'])

    ratio_rows: List[Dict[str, Any]] = []
    ratios = results.get('ratios') if isinstance(results.get('ratios'), dict) else {}
    if ratios:
        for name, values in ratios.items():
            latest = None
            if isinstance(values, list) and values:
                latest = values[-1]
            ratio_rows.append({'name': name, 'latest': latest})
    else:
        for item in indicators:
            name = item.get('name', '指标')
            unit = item.get('unit', '')
            if unit == '%' or any(tag in name for tag in ['率', 'ROE', 'ROA', '比率', 'CFO/']):
                ratio_rows.append({'name': name, 'latest': f"{item.get('value', '-')}{unit}"})

    key_tables = results.get('key_tables') if isinstance(results.get('key_tables'), dict) else {}
    if not key_tables and indicators:
        generic_rows = []
        for item in indicators:
            if item.get('unit') in ['%', '']:
                continue
            generic_rows.append({'项目': item.get('name'), '本期金额(亿元)': item.get('value'), '同比变化(%)': '-'})
        if generic_rows:
            key_tables = {'income_statement': generic_rows[:10]}

    data_quality = list(results.get('data_quality_warnings') or [])
    if not data_quality and len(indicators) < 3:
        data_quality.append('从报告中提取到的结构化指标较少，建议检查原始文件格式与表格清晰度。')

    traceability_text = results.get('data_traceability') or (
        f"数据来源文件: {task.filename}; 报告路径: {task.report_path}; 任务ID: {task.id}; 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    conclusion_lines = _extract_keyword_sentences(report_content, ['结论', '综上', '总体', '总结'], max_items=2)
    if not conclusion_lines:
        conclusion_lines = ['整体来看，公司核心财务指标具备可解释性，建议结合后续期间数据做持续跟踪。']
    conclusion_lines = _sanitize_sentence_list(conclusion_lines, max_items=2)

    existing_charts = results.get('charts') if isinstance(results.get('charts'), list) else []
    derived_charts = _build_report_derived_charts(indicators)
    all_charts = list(existing_charts)
    seen_titles = {c.get('title') for c in all_charts if isinstance(c, dict)}
    for chart in derived_charts:
        title = chart.get('title')
        if title not in seen_titles:
            all_charts.append(chart)
            seen_titles.add(title)

    amount_unit = results.get('amount_unit', '亿元')
    executive_points = [
        f"本次任务文件: {task.filename}",
        f"分析类型: {task.analysis_type}",
        f"已提取关键指标数量: {len(indicators)}",
    ]

    return {
        'executive_points': executive_points,
        'indicators': indicators,
        'key_findings': strengths + concerns[:2],
        'data_quality': data_quality,
        'key_tables_html': generate_key_tables_section(key_tables, amount_unit),
        'charts': all_charts,
        'ratios': ratio_rows,
        'recommendations': recommendations,
        'risks': concerns,
        'conclusion': conclusion_lines,
        'traceability_html': generate_traceability_section(traceability_text),
    }

def update_task_progress(task_id, status, progress, message=None):
    """更新任务进度"""
    if _is_task_cancelled(task_id):
        return
    update_fields = {
        'status': status,
        'progress': progress
    }
    if message is not None:
        update_fields['message'] = message
    task_store.update(task_id, **update_fields)

def process_financial_analysis(task_id):
    """处理财务分析任务（后台线程）"""
    try:
        task = task_store.get(task_id)
        if not task:
            return
        if task.status == 'cancelled':
            return

        task.filepath = _resolve_file_path(task.filepath)
        if not os.path.exists(task.filepath):
            raise FileNotFoundError(f"文件不存在: {task.filepath}")

        file_ext = os.path.splitext((task.filename or "").lower())[1]

        # PDF 任务走上游仓库的原生报告生成逻辑（不修改上游功能）
        if file_ext == '.pdf':
            update_task_progress(task_id, 'processing', 10, '检测到PDF，正在调用上游报告引擎...')
            if _is_task_cancelled(task_id):
                return
            upstream_output_dir = os.path.join(app.config['REPORT_FOLDER'], f"upstream_{task_id}")
            os.makedirs(upstream_output_dir, exist_ok=True)
            upstream_report_runtime.set_output_dir(upstream_output_dir)

            update_task_progress(task_id, 'processing', 50, '上游引擎处理中...')
            md_report = upstream_report_runtime.generate_financial_report(task.filepath)
            if _is_task_cancelled(task_id):
                return

            # 对照关键指标进行后处理对齐（不修改上游后端功能代码）
            reference_path = os.environ.get('REPORT_REFERENCE_PATH', '/root/web/financial_report.md')
            aligned_report, align_changes = align_report_with_reference(md_report, reference_path)

            report_filename = f"financial_report_{task_id}.md"
            report_path = os.path.join(app.config['REPORT_FOLDER'], report_filename)
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(aligned_report)

            metric_map = _load_upstream_metric_map(upstream_output_dir)
            charts = _build_visual_charts_from_metrics(metric_map)
            summary_stats = _build_summary_stats_from_metrics(metric_map)

            task.results = {
                "source": "upstream_report_generator",
                "upstream_output_dir": upstream_output_dir,
                "report_aligned": True,
                "alignment_reference": reference_path,
                "alignment_changes": align_changes,
                "metrics": metric_map,
                "charts": charts,
                "summary_stats": summary_stats,
                "amount_unit": metric_map.get("unit_standard", "亿元"),
                "insights": {
                    "strengths": [],
                    "concerns": [],
                    "recommendations": [],
                },
            }
            task.results = _ensure_visualizable_results(task.results, report_path=report_path)
            task.report_path = report_path
            task.detected_type = 'pdf_financial_report'
            task.status = 'completed'
            task.progress = 100
            task.end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            task.message = '分析完成（上游引擎）！'
            task_store.update(
                task_id,
                results=task.results,
                report_path=task.report_path,
                detected_type=task.detected_type,
                status=task.status,
                progress=task.progress,
                end_time=task.end_time,
                message=task.message,
                error=None,
            )
            return
        
        update_task_progress(task_id, 'processing', 10, '开始读取文件...')
        
        # 1. 读取文件
        df, detected_type = FileProcessor.read_financial_file(
            task.filepath, 
            task.filename
        )
        
        update_task_progress(task_id, 'processing', 30, '数据读取完成，正在分析...')
        if _is_task_cancelled(task_id):
            return
        
        # 确定报表类型
        report_type = task.report_type
        if report_type == 'auto':
            report_type = detected_type
        
        # 验证数据
        FileProcessor.validate_financial_data(df, report_type)
        
        update_task_progress(task_id, 'processing', 50, '数据验证通过，计算财务比率...')
        if _is_task_cancelled(task_id):
            return

        stage_clock_start = time.perf_counter()
        app.logger.info(
            'task=%s analysis_stage=start progress=50 analysis_type=%s report_type=%s rows=%s cols=%s',
            task_id,
            task.analysis_type,
            report_type,
            getattr(df, 'shape', (None, None))[0],
            getattr(df, 'shape', (None, None))[1],
        )
        
        # 2. 财务分析
        analyzer_init_start = time.perf_counter()
        analyzer = FinancialAnalyzer(df, report_type)
        app.logger.info(
            'task=%s analysis_stage=analyzer_initialized elapsed=%.3fs',
            task_id,
            time.perf_counter() - analyzer_init_start,
        )
        
        # 根据分析类型执行不同的分析
        analysis_type = task.analysis_type
        report_data_start = time.perf_counter()
        
        if analysis_type == 'basic':
            results = analyzer.generate_report_data()
            # 只保留基础图表
            results['charts'] = results['charts'][:2] if len(results['charts']) > 2 else results['charts']
        
        elif analysis_type == 'profitability':
            results = analyzer.generate_report_data()
            # 过滤只保留盈利能力相关的图表
            results['charts'] = [c for c in results['charts'] if '盈利' in c['title'] or '利率' in c['title']]
        
        elif analysis_type == 'solvency':
            results = analyzer.generate_report_data()
            # 过滤只保留偿债能力相关的图表
            results['charts'] = [c for c in results['charts'] if '偿债' in c['title'] or '比率' in c['title']]
        
        elif analysis_type == 'agent':
            results = analyzer.generate_report_data()

        else:  # comprehensive
            results = analyzer.generate_report_data()

        app.logger.info(
            'task=%s analysis_stage=report_data_generated elapsed=%.3fs charts=%s',
            task_id,
            time.perf_counter() - report_data_start,
            len(results.get('charts') or []),
        )
        
        update_task_progress(task_id, 'processing', 80, '分析完成，生成报告...')
        if _is_task_cancelled(task_id):
            return
        
        # 3. 生成报告文件
        report_render_start = time.perf_counter()
        report_content = generate_financial_report(task, results)
        app.logger.info(
            'task=%s analysis_stage=report_html_rendered elapsed=%.3fs',
            task_id,
            time.perf_counter() - report_render_start,
        )
        report_filename = f"financial_report_{task_id}.html"
        report_path = os.path.join(app.config['REPORT_FOLDER'], report_filename)
        
        report_write_start = time.perf_counter()
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        app.logger.info(
            'task=%s analysis_stage=report_written elapsed=%.3fs path=%s',
            task_id,
            time.perf_counter() - report_write_start,
            report_path,
        )
        
        # 4. 更新任务结果
        task.results = _ensure_visualizable_results(results)
        task.report_path = report_path
        task.detected_type = detected_type
        task.status = 'completed'
        task.progress = 100
        task.end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        task.message = '分析完成！'
        task_store.update(
            task_id,
            results=task.results,
            report_path=task.report_path,
            detected_type=task.detected_type,
            status=task.status,
            progress=task.progress,
            end_time=task.end_time,
            message=task.message,
            error=None,
        )
        app.logger.info(
            'task=%s analysis_stage=completed total_elapsed=%.3fs',
            task_id,
            time.perf_counter() - stage_clock_start,
        )
        
    except Exception as e:
        task = task_store.get(task_id)
        if task:
            if task.status == 'cancelled':
                task.progress = 0
                task.end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                task.message = '分析已停止'
                task_store.update(
                    task_id,
                    progress=task.progress,
                    end_time=task.end_time,
                    message=task.message,
                )
                return
            task.status = 'failed'
            task.error = str(e)
            task.progress = 0
            task.end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            task.message = '分析失败'
            task_store.update(
                task_id,
                status=task.status,
                error=task.error,
                progress=task.progress,
                end_time=task.end_time,
                message=task.message,
            )

# ==================== 报告生成 ====================

def generate_financial_report(task, results):
    """生成财务分析报告"""
    
    # 基础信息
    company_name = task.company_name or task.filename
    report_type = task.detected_type or task.report_type
    report_type_cn = app.config['FINANCIAL_TEMPLATES'].get(report_type, report_type)
    
    # 构建报告HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>财务分析报告 - {company_name}</title>
    
    <!-- Bootstrap 5 -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <!-- Plotly -->
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f8f9fa;
        }}
        
        .report-container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        
        .report-header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 3px solid #2E86AB;
        }}
        
        .report-header h1 {{
            color: #2E86AB;
            margin-bottom: 10px;
        }}
        
        .report-section {{
            margin-bottom: 40px;
            padding: 20px;
            background: #fff;
            border-radius: 8px;
            border-left: 4px solid #2E86AB;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        
        .section-title {{
            color: #2E86AB;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        
        .chart-container {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        
        .insight-card {{
            background: #f8f9fa;
            border-left: 4px solid;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 4px;
        }}
        
        .strength {{
            border-left-color: #28a745;
            background-color: #d4edda;
        }}
        
        .concern {{
            border-left-color: #dc3545;
            background-color: #f8d7da;
        }}
        
        .recommendation {{
            border-left-color: #ffc107;
            background-color: #fff3cd;
        }}
        
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        
        .data-table th, .data-table td {{
            border: 1px solid #dee2e6;
            padding: 8px;
            text-align: right;
        }}
        
        .data-table th {{
            background-color: #2E86AB;
            color: white;
            text-align: center;
        }}
        
        .data-table tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        
        .ratio-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }}
        
        .good {{
            background-color: #d4edda;
            color: #155724;
        }}
        
        .warning {{
            background-color: #fff3cd;
            color: #856404;
        }}
        
        .danger {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <!-- 报告头部 -->
        <div class="report-header">
            <h1>财务分析报告</h1>
            <h3>{company_name}</h3>
            <p class="text-muted">
                报表类型: {report_type_cn} | 
                分析类型: {app.config['ANALYSIS_TYPES'].get(task.analysis_type)} |
                生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </div>
        
        <!-- 1. 执行摘要 -->
        <div class="report-section">
            <h3 class="section-title">执行摘要</h3>
            <p>本报告对{company_name}的{report_type_cn}进行了详细分析，涵盖{len(results.get('periods', []))}个会计期间。</p>
            
            {generate_executive_summary(results)}
        </div>
        
        <!-- 2. 关键发现 -->
        <div class="report-section">
            <h3 class="section-title">关键发现</h3>
            {generate_key_findings(results.get('insights', {}))}
        </div>

        <!-- 3. 数据质量与现金流质量 -->
        <div class="report-section">
            <h3 class="section-title">数据质量与现金流质量</h3>
            {generate_quality_section(results)}
        </div>

        <!-- 4. 关键财务表（亿元） -->
        <div class="report-section">
            <h3 class="section-title">关键财务表（金额单位：{results.get('amount_unit', '亿元')}）</h3>
            {generate_key_tables_section(results.get('key_tables', {}), results.get('amount_unit', '亿元'))}
        </div>
        
        <!-- 5. 财务图表 -->
        <div class="report-section">
            <h3 class="section-title">财务可视化</h3>
            {generate_charts_section(results.get('charts', []))}
        </div>
        
        <!-- 6. 财务比率分析 -->
        <div class="report-section">
            <h3 class="section-title">财务比率分析</h3>
            {generate_ratios_section(results.get('ratios', {}), results.get('periods', []))}
        </div>
        
        <!-- 7. 原始数据 -->
        <div class="report-section">
            <h3 class="section-title">原始数据</h3>
            {generate_raw_data_section(results.get('raw_data', []))}
        </div>
        
        <!-- 8. 建议 -->
        <div class="report-section">
            <h3 class="section-title">建议与措施</h3>
            {generate_recommendations_section(results.get('insights', {}))}
        </div>

        <!-- 9. 数据溯源 -->
        <div class="report-section">
            <h3 class="section-title">数据溯源</h3>
            {generate_traceability_section(results.get('data_traceability'))}
        </div>
        
        <!-- 页脚 -->
        <div class="footer">
            <p>财务分析报告生成系统</p>
            <p>技术支持: Flask + Pandas + Plotly | 报告编号: {task.id[:8]}</p>
            <p>声明: 本报告基于提供的财务报表数据生成，仅供参考。</p>
        </div>
    </div>
    
    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    """
    
    return html_content

def generate_executive_summary(results):
    """生成执行摘要"""
    if not results:
        return "<p>暂无数据</p>"
    
    summary_html = "<div class='row'>"
    
    # 基本统计
    if 'basic_info' in results:
        info = results['basic_info']
        summary_html += f"""
        <div class="col-md-6">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">基本信息</h5>
                    <ul>
                        <li>分析期间数: {info.get('data_points', 0)}</li>
                        <li>报表类型: {info.get('report_type', '未知')}</li>
                        <li>分析时间: {info.get('analysis_time', '未知')}</li>
                    </ul>
                </div>
            </div>
        </div>
        """
    
    # 关键指标
    if 'summary_stats' in results and results['summary_stats']:
        stats = results['summary_stats']
        first_key = list(stats.keys())[0] if stats else None
        if first_key:
            latest_value = stats[first_key].get('latest', 'N/A')
            if isinstance(latest_value, (int, float)):
                latest_text = f"{latest_value:,.2f}"
            else:
                latest_text = str(latest_value)
            summary_html += f"""
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">关键指标</h5>
                        <p><strong>{first_key}:</strong> {latest_text}</p>
                        <p>详细指标分析见下文</p>
                    </div>
                </div>
            </div>
            """
    
    summary_html += "</div>"
    return summary_html

def generate_key_findings(insights):
    """生成关键发现"""
    if not insights:
        return "<p>暂无关键发现</p>"
    
    findings_html = ""
    
    # 优势
    if insights.get('strengths'):
        findings_html += "<h5>优势</h5>"
        for strength in insights['strengths']:
            findings_html += f'<div class="insight-card strength">{strength}</div>'
    
    # 关注点
    if insights.get('concerns'):
        findings_html += "<h5 class='mt-4'>关注点</h5>"
        for concern in insights['concerns']:
            findings_html += f'<div class="insight-card concern">{concern}</div>'
    
    return findings_html


def generate_quality_section(results):
    """生成数据质量与现金流质量部分"""
    warnings_list = results.get('data_quality_warnings', []) or []
    cashflow_quality = results.get('cashflow_quality', {}) or {}

    if not warnings_list and not cashflow_quality:
        return '<p>暂无数据质量告警</p>'

    html = ''
    if warnings_list:
        html += "<h5>数据质量警告</h5>"
        for item in warnings_list:
            html += f'<div class="insight-card concern">⚠️ {item}</div>'

    ratio_percent = cashflow_quality.get('ratio_percent')
    if ratio_percent is not None:
        warning = cashflow_quality.get('warning')
        html += "<h5 class='mt-3'>现金流质量</h5>"
        html += f'<div class="insight-card {"concern" if warning else "strength"}">CFO/净利润: {ratio_percent}%</div>'
        if warning:
            html += f'<div class="insight-card concern">⚠️ {warning}</div>'

    return html or '<p>暂无数据质量告警</p>'


def _build_simple_table(rows, headers):
    if not rows:
        return '<p>暂无数据</p>'

    table = "<div class='table-responsive'><table class='data-table'><thead><tr>"
    for h in headers:
        table += f"<th>{h}</th>"
    table += "</tr></thead><tbody>"

    for row in rows:
        table += '<tr>'
        for h in headers:
            value = row.get(h)
            if isinstance(value, float):
                table += f"<td>{value:.2f}</td>"
            elif value is None:
                table += '<td>-</td>'
            else:
                table += f"<td>{value}</td>"
        table += '</tr>'
    table += '</tbody></table></div>'
    return table


def generate_key_tables_section(key_tables, amount_unit):
    """生成关键财务表格部分"""
    if not key_tables:
        return '<p>暂无关键表格数据</p>'

    html = ''

    income_rows = key_tables.get('income_statement', [])
    if income_rows:
        html += '<h5>利润表关键项目</h5>'
        html += _build_simple_table(income_rows, ['项目', f'本期金额({amount_unit})', '同比变化(%)'])

    balance_rows = key_tables.get('balance_sheet', [])
    if balance_rows:
        html += '<h5 class="mt-4">资产负债表关键项目</h5>'
        html += _build_simple_table(balance_rows, ['项目', f'本期金额({amount_unit})'])

    cash_rows = key_tables.get('cash_flow', [])
    if cash_rows:
        html += '<h5 class="mt-4">现金流量表关键项目</h5>'
        html += _build_simple_table(cash_rows, ['项目', f'本期金额({amount_unit})'])

    return html or '<p>暂无关键表格数据</p>'


def generate_traceability_section(traceability_text):
    if not traceability_text:
        return '<p>暂无溯源信息</p>'
    return f'<div class="insight-card strength">{traceability_text}</div>'

def generate_charts_section(charts):
    """生成图表部分"""
    if not charts:
        return "<p>暂无图表</p>"
    
    charts_html = "<div class='row'>"
    
    for i, chart in enumerate(charts):
        col_class = "col-md-12" if len(charts) == 1 else "col-md-6"
        charts_html += f"""
        <div class="{col_class}">
            <div class="chart-container">
                <h5>{chart.get('title', '图表')}</h5>
                {chart.get('data', '')}
            </div>
        </div>
        """
        
        # 每行两个图表
        if (i + 1) % 2 == 0:
            charts_html += '</div><div class="row">'
    
    charts_html += "</div>"
    return charts_html

def generate_ratios_section(ratios, periods):
    """生成比率分析部分"""
    if not ratios:
        return "<p>暂无比率数据</p>"
    
    ratios_html = "<div class='table-responsive'><table class='data-table'>"
    
    # 表头
    ratios_html += "<thead><tr><th>财务比率</th>"
    for period in periods:
        ratios_html += f"<th>{period}</th>"
    ratios_html += "</tr></thead><tbody>"
    
    # 数据行
    for ratio_name, values in ratios.items():
        ratios_html += f"<tr><td>{ratio_name}</td>"
        for value in values:
            if value is None:
                ratios_html += "<td>-</td>"
            else:
                # 根据数值添加颜色标识
                badge_class = ""
                if '率' in ratio_name and '%' in ratio_name:
                    if value > 20:
                        badge_class = "good"
                    elif value > 10:
                        badge_class = "warning"
                    else:
                        badge_class = "danger"
                
                value_display = f"{value}"
                if badge_class:
                    value_display += f" <span class='ratio-badge {badge_class}'>{'优良' if badge_class == 'good' else '注意' if badge_class == 'warning' else '关注'}</span>"
                
                ratios_html += f"<td>{value_display}</td>"
        ratios_html += "</tr>"
    
    ratios_html += "</tbody></table></div>"
    return ratios_html

def generate_raw_data_section(raw_data):
    """生成原始数据部分"""
    if not raw_data:
        return "<p>暂无原始数据</p>"
    
    # 获取表头
    if raw_data:
        headers = list(raw_data[0].keys())
    else:
        return "<p>暂无原始数据</p>"
    
    data_html = "<div class='table-responsive'><table class='data-table'>"
    
    # 表头
    data_html += "<thead><tr>"
    for header in headers:
        data_html += f"<th>{header}</th>"
    data_html += "</tr></thead><tbody>"
    
    # 数据行
    for row in raw_data[:10]:  # 只显示前10行
        data_html += "<tr>"
        for header in headers:
            value = row.get(header, '')
            # 格式化数值
            if isinstance(value, (int, float)):
                if abs(value) >= 1000000:
                    value = f"{value/1000000:.2f}M"
                elif abs(value) >= 1000:
                    value = f"{value/1000:.2f}K"
                else:
                    value = f"{value:.2f}"
            data_html += f"<td>{value}</td>"
        data_html += "</tr>"
    
    data_html += "</tbody></table></div>"
    
    if len(raw_data) > 10:
        data_html += f"<p class='text-muted'>仅显示前10行，共{len(raw_data)}行数据</p>"
    
    return data_html

def generate_recommendations_section(insights):
    """生成建议部分"""
    if not insights or not insights.get('recommendations'):
        return "<p>暂无具体建议</p>"
    
    recommendations_html = "<div class='row'>"
    
    for i, rec in enumerate(insights['recommendations'], 1):
        recommendations_html += f"""
        <div class="col-md-6 mb-3">
            <div class="insight-card recommendation">
                <h6>建议{i}</h6>
                <p class="mb-0">{rec}</p>
            </div>
        </div>
        """
    
    recommendations_html += "</div>"
    return recommendations_html

# ==================== 路由定义 ====================

@app.route('/')
def index():
    """首页"""
    # 获取最近的任务
    recent_tasks = task_store.recent(10)
    
    return render_template(
        'index.html',
        recent_tasks=recent_tasks,
        financial_templates=app.config['FINANCIAL_TEMPLATES']
    )

@app.route('/upload', methods=['GET', 'POST'])
def upload_financial():
    """财务报表上传页面"""
    form = FinancialUploadForm()
    
    if form.validate_on_submit():
        try:
            # 保存上传的文件
            file = form.file.data
            filename = secure_filename(file.filename)

            if not _is_file_size_allowed(file):
                flash('文件大小不能超过10MB（10485760字节）', 'error')
                return redirect(url_for('upload_financial'))
            
            # 创建任务ID
            task_id = str(uuid.uuid4())
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_{filename}")
            file.save(filepath)
            
            # 收集表单数据
            form_data = {
                'company_name': form.company_name.data or filename,
                'report_type': form.report_type.data,
                'analysis_type': form.analysis_type.data,
                'include_benchmark': form.include_benchmark.data
            }
            
            # 创建任务
            task_id = create_financial_task(filepath, filename, form_data)
            
            # 启动后台处理线程
            thread = threading.Thread(
                target=process_financial_analysis,
                args=(task_id,),
                daemon=True
            )
            thread.start()
            
            flash('财务报表上传成功！分析任务已开始。', 'success')
            return redirect(url_for('task_status', task_id=task_id))
            
        except Exception as e:
            flash(f'上传失败: {str(e)}', 'error')
    
    return render_template('upload.html', 
                          form=form, 
                          financial_templates=app.config['FINANCIAL_TEMPLATES'],
                          analysis_types=app.config['ANALYSIS_TYPES'])


@app.route('/agent')
def agent_console():
    """Agent 智能体控制台"""
    return render_template('agent.html')

@app.route('/task/<task_id>')
def task_status(task_id):
    """任务状态页面"""
    task = task_store.get(task_id)
    if not task:
        flash('任务不存在', 'error')
        return redirect(url_for('upload_financial'))
    
    return render_template(
        'task_status.html',
        task=task,
        financial_templates=app.config['FINANCIAL_TEMPLATES'],
        analysis_types=app.config['ANALYSIS_TYPES'],
        upstream_timeout_seconds=_resolve_upstream_timeout_seconds(),
    )

@app.route('/api/task/<task_id>/status')
def get_task_status(task_id):
    """获取任务状态API"""
    task = task_store.get(task_id)
    if task:
        # Self-heal stale tasks when worker state is lost but UI keeps polling.
        if task.status == 'processing' and task.progress >= 50 and task.start_time:
            try:
                start_dt = datetime.strptime(task.start_time, '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - start_dt).total_seconds()
                timeout_seconds = _resolve_upstream_timeout_seconds()
                if elapsed > timeout_seconds and not _has_upstream_process_for_task(task_id):
                    task_store.update(
                        task_id,
                        status='failed',
                        progress=0,
                        end_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        message='分析超时，请重试或简化文件',
                        error=f'上游进程已结束且超过超时阈值（{timeout_seconds}s）',
                    )
                    task = task_store.get(task_id)
            except Exception:
                pass
        return jsonify(task.to_public_dict())
    return jsonify({'error': '任务不存在'}), 404


@app.route('/api/task/<task_id>/stop', methods=['POST'])
def stop_task(task_id):
    """停止任务（主要用于长耗时 PDF 上游引擎）。"""
    task = task_store.get(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    if task.status not in ['pending', 'processing']:
        return jsonify({'error': f'当前状态不支持停止: {task.status}'}), 400

    killed = _terminate_upstream_process_for_task(task_id)
    task_store.update(
        task_id,
        status='cancelled',
        progress=0,
        message='分析已停止',
        error=None,
        end_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    return jsonify({'status': 'success', 'task_id': task_id, 'killed_processes': killed})


@app.route('/api/task/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务记录（可用于清理最近任务）。"""
    task = task_store.get(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    if task.status in ['pending', 'processing']:
        return jsonify({'error': '任务正在进行中，请先停止后再删除'}), 409

    ok = task_store.delete(task_id)
    if not ok:
        return jsonify({'error': '删除失败'}), 500
    return jsonify({'status': 'success', 'task_id': task_id})

@app.route('/api/task/<task_id>/raw-data.csv')
def download_raw_data(task_id):
    """下载原始数据CSV"""
    task = task_store.get(task_id)
    if not task or not task.results or not task.results.get('raw_data'):
        return jsonify({'error': '原始数据不可用'}), 404

    raw_data = task.results['raw_data']
    if not raw_data:
        return jsonify({'error': '原始数据为空'}), 404

    output = StringIO()
    fieldnames = list(raw_data[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in raw_data:
        writer.writerow(row)

    safe_name = secure_filename(task.company_name or task.filename or task.id) or f"task_{task.id}"
    filename = f"raw_data_{safe_name}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

# ==================== Agent API ====================

def _log_agent(session: AgentSession, level: str, message: str, extra: Dict[str, Any] | None = None) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    session.logs.append(entry)


def _update_brain_state(session: AgentSession, brain: AgentBrain) -> None:
    brain.update_state(
        data_loaded=session.data_loaded,
        data_cleaned=session.data_cleaned,
        current_file=session.file_name,
        report_type=session.report_type,
    )
    session.brain_state = brain.to_state()


def _build_tools_description() -> List[Dict[str, Any]]:
    return [
        {
            "name": "clean",
            "description": "清洗已加载数据",
            "params": {},
        },
        {
            "name": "chart",
            "description": "生成单文件图表",
            "params": {"chart_type": CHART_TYPES},
        },
        {
            "name": "compare",
            "description": "生成多文件对比图",
            "params": {"metrics": "list"},
        },
        {
            "name": "analyze",
            "description": "财务健康分析",
            "params": {},
        },
        {
            "name": "status",
            "description": "查看会话状态",
            "params": {},
        },
        {
            "name": "reset",
            "description": "重置会话",
            "params": {},
        },
    ]


def _get_brain(session: AgentSession) -> AgentBrain:
    brain = AgentBrain()
    brain.load_state(session.brain_state)
    return brain


def _get_datasets_for_session(session: AgentSession) -> Dict[str, Any]:
    datasets: Dict[str, Any] = {}
    if session.files:
        for item in session.files:
            df = item.get("cleaned_df") if session.data_cleaned else item.get("df")
            if df is not None:
                datasets[item.get("file_name", "data")] = df
    elif session.df is not None:
        datasets[session.file_name or "data"] = session.cleaned_df if session.data_cleaned else session.df
    return datasets


def _is_supported_agent_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename or "")
    return ext.lower() in {item.lower() for item in SUPPORTED_FORMATS}


def _serialize_session_for_export(session: AgentSession) -> Dict[str, Any]:
    return {
        "id": session.id,
        "file_name": session.file_name,
        "report_type": session.report_type,
        "data_loaded": session.data_loaded,
        "data_cleaned": session.data_cleaned,
        "charts": session.charts,
        "compare_charts": session.compare_charts,
        "files": [
            {
                "file_name": item.get("file_name"),
                "report_type": item.get("report_type"),
            }
            for item in session.files
        ],
        "logs": session.logs,
        "workflow_history": session.workflow_history,
        "last_decision": session.last_decision,
        "suggestions": session.suggestions,
        "brain_state": session.brain_state,
    }


def _build_export_html(session: AgentSession) -> str:
    return f"""
<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Agent 会话导出</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #0f172a; }}
    h1 {{ color: #0f5e63; }}
    .section {{ margin-top: 20px; }}
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 12px; background: #e2f3f4; margin-right: 6px; }}
  </style>
</head>
<body>
  <h1>Agent 会话导出</h1>
  <p>会话ID: {session.id}</p>
  <p>文件: {session.file_name or '无'} | 报表类型: {session.report_type or '未知'}</p>
  <p>数据已加载: {session.data_loaded} | 数据已清洗: {session.data_cleaned}</p>
  <div class=\"section\">
    <h2>图表</h2>
    {''.join([f"<div class='tag'>{c.get('title','图表')}</div>" for c in session.charts]) or '<p>暂无图表</p>'}
  </div>
  <div class=\"section\">
    <h2>对比图</h2>
    {''.join([f"<div class='tag'>{c.get('title','对比图')}</div>" for c in session.compare_charts]) or '<p>暂无对比图</p>'}
  </div>
  <div class=\"section\">
    <h2>建议</h2>
    {''.join([f"<div>{s}</div>" for s in session.suggestions]) or '<p>暂无建议</p>'}
  </div>
</body>
</html>
"""


def _build_export_text(session: AgentSession) -> str:
    lines = [
        "财经Agent会话报告",
        f"会话ID: {session.id}",
        f"当前文件: {session.file_name or '无'}",
        f"报表类型: {session.report_type or '未知'}",
        f"数据已加载: {session.data_loaded}",
        f"数据已清洗: {session.data_cleaned}",
        "",
        f"图表数量: {len(session.charts)}",
    ]
    for idx, chart in enumerate(session.charts[-10:], 1):
        lines.append(f"  {idx}. {chart.get('type', 'unknown')} - {chart.get('title', '图表')}")

    lines.append("")
    lines.append(f"对比图数量: {len(session.compare_charts)}")
    for idx, chart in enumerate(session.compare_charts[-10:], 1):
        lines.append(f"  {idx}. {chart.get('metric', 'all')} - {chart.get('title', '对比图')}")

    lines.append("")
    lines.append("最近工作流:")
    for idx, item in enumerate(session.workflow_history[-10:], 1):
        lines.append(f"  {idx}. {item.get('tool', 'unknown')} -> {item.get('result', 'unknown')}")

    if session.logs:
        lines.append("")
        lines.append("最近日志:")
        for idx, item in enumerate(session.logs[-10:], 1):
            lines.append(f"  {idx}. [{item.get('level', 'info')}] {item.get('message', '')}")

    return "\n".join(lines)


def _determine_best_chart_types_for_df(df) -> List[str]:
    chart_types: List[str] = []
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return ["income_trend"]

    num_rows = len(df)
    num_numeric_cols = len(numeric_cols)
    date_cols = [
        col for col in df.columns
        if "日期" in str(col) or "date" in str(col).lower() or "time" in str(col).lower()
    ]
    if date_cols and num_rows > 3:
        chart_types.append("income_trend")

    if num_numeric_cols >= 2:
        chart_types.append("revenue_comparison")

    if num_numeric_cols >= 3 and num_rows == 1:
        chart_types.append("profit_composition")

    asset_keywords = ["资产", "负债", "权益", "asset", "liability", "equity"]
    has_balance_items = any(
        any(keyword in str(col).lower() for keyword in asset_keywords)
        for col in df.columns
    )
    if has_balance_items and num_numeric_cols >= 2:
        chart_types.append("balance_sheet")

    expense_keywords = ["费用", "成本", "expense", "cost"]
    has_expense_items = any(
        any(keyword in str(col).lower() for keyword in expense_keywords)
        for col in df.columns
    )
    if has_expense_items and num_numeric_cols >= 2:
        chart_types.append("expense_breakdown")

    chart_types = list(dict.fromkeys(chart_types))
    if not chart_types:
        if num_numeric_cols >= 3:
            chart_types = ["income_trend", "revenue_comparison"]
        elif num_numeric_cols == 2:
            chart_types = ["revenue_comparison"]
        else:
            chart_types = ["income_trend"]
    return chart_types[:3]


def _generate_charts_for_session(session, chart_types: List[str], title: str, output_dir: str | None = None):
    charts = []
    errors = []
    for chart_type in chart_types:
        chart, error = _generate_chart_for_session(session, chart_type, title, output_dir=output_dir)
        if error:
            errors.append({"chart_type": chart_type, "error": error})
        elif chart:
            charts.append(chart)
    return charts, errors


def _ingest_upstream_chart_info(session: AgentSession, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    chart_info = (result or {}).get("chart_info") or {}
    charts = chart_info.get("charts") or []
    for item in charts:
        chart_path = item.get("path")
        if not chart_path:
            continue
        chart_id = str(uuid.uuid4())
        chart_type = item.get("type", "income_trend")
        chart_title = item.get("title", chart_type)
        session.charts.append(
            {
                "id": chart_id,
                "type": chart_type,
                "title": chart_title,
                "path": chart_path,
            }
        )
        payload.append(
            {
                "id": chart_id,
                "type": chart_type,
                "title": chart_title,
                "download_url": url_for('download_agent_chart', session_id=session.id, chart_id=chart_id),
                "view_url": url_for('view_agent_chart', session_id=session.id, chart_id=chart_id),
                "charts_center_url": url_for('view_agent_chart_center', session_id=session.id),
            }
        )
    if payload:
        session.updated_at = datetime.now().isoformat()
    return payload


def _sync_session_from_upstream(session_id: str, session: AgentSession) -> Dict[str, Any]:
    try:
        upstream_agent = upstream_agent_manager.get_or_create(session_id)
    except Exception:
        return {}

    state = getattr(upstream_agent, "state", {}) or {}
    current_file = state.get("current_file")
    current_data = state.get("current_data")
    cleaned_data = state.get("cleaned_data")

    if current_file:
        session.file_path = current_file
        session.file_name = os.path.basename(current_file)

    if "data_loaded" in state:
        session.data_loaded = bool(state.get("data_loaded"))
    if "data_cleaned" in state:
        session.data_cleaned = bool(state.get("data_cleaned"))
    session.report_type = state.get("report_type") or session.report_type

    if current_data is not None:
        session.df = current_data
    if cleaned_data is not None:
        session.cleaned_df = cleaned_data
    elif not session.data_cleaned:
        session.cleaned_df = None

    session.updated_at = datetime.now().isoformat()
    return state


def _attach_process_meta(resp, elapsed_seconds: float, confidence: float):
    execution_time = f"{elapsed_seconds:.2f}s"

    if isinstance(resp, tuple):
        body = resp[0]
        status_code = resp[1] if len(resp) > 1 else 200
        if isinstance(body, Response):
            payload = body.get_json(silent=True)
            if isinstance(payload, dict):
                payload.setdefault("execution_time", execution_time)
                payload.setdefault("confidence", confidence)
                return jsonify(payload), status_code
            return body, status_code
        if isinstance(body, dict):
            body.setdefault("execution_time", execution_time)
            body.setdefault("confidence", confidence)
            return jsonify(body), status_code
        return resp

    if isinstance(resp, Response):
        payload = resp.get_json(silent=True)
        if isinstance(payload, dict):
            payload.setdefault("execution_time", execution_time)
            payload.setdefault("confidence", confidence)
            return jsonify(payload), resp.status_code
        return resp

    if isinstance(resp, dict):
        resp.setdefault("execution_time", execution_time)
        resp.setdefault("confidence", confidence)
        return jsonify(resp)

    return resp

def _generate_chart_for_session(session, chart_type: str, title: str, output_dir: str | None = None):
    df = session.cleaned_df if session.data_cleaned else session.df
    if df is None or getattr(df, 'empty', False):
        return None, "没有可用的数据"

    chart_path, error = create_professional_chart(
        df,
        chart_type,
        title,
        output_dir=output_dir or DEFAULT_OUTPUT_DIR,
    )
    if error or not chart_path:
        return None, error or "图表生成失败"

    chart_id = str(uuid.uuid4())
    session.charts.append({
        "id": chart_id,
        "type": chart_type,
        "title": title,
        "path": chart_path
    })
    session.updated_at = datetime.now().isoformat()
    return {
        "id": chart_id,
        "type": chart_type,
        "title": title,
        "download_url": url_for('download_agent_chart', session_id=session.id, chart_id=chart_id),
        "view_url": url_for('view_agent_chart', session_id=session.id, chart_id=chart_id),
        "charts_center_url": url_for('view_agent_chart_center', session_id=session.id),
    }, ""


def _generate_compare_chart_for_session(session, metric: str | None, title: str):
    datasets = {}
    for item in session.files:
        df = item.get('cleaned_df') if session.data_cleaned else item.get('df')
        if df is not None:
            datasets[item.get('file_name', 'data')] = df

    chart_path, error = create_comparison_chart(datasets, metric=metric, title=title)
    if error or not chart_path:
        return None, error or "对比图生成失败"

    chart_id = str(uuid.uuid4())
    session.compare_charts.append({
        "id": chart_id,
        "type": "compare",
        "title": title,
        "metric": metric,
        "path": chart_path
    })
    session.updated_at = datetime.now().isoformat()
    return {
        "id": chart_id,
        "type": "compare",
        "title": title,
        "download_url": url_for('download_agent_compare_chart', session_id=session.id, chart_id=chart_id),
        "view_url": url_for('view_agent_compare_chart', session_id=session.id, chart_id=chart_id),
        "charts_center_url": url_for('view_agent_chart_center', session_id=session.id),
    }, ""


def _normalize_agent_tool_name(tool_name: str) -> str:
    aliases = {
        "parse_finance_file": "parse_finance_file",
        "upload_file": "parse_finance_file",
        "upload": "parse_finance_file",
        "load": "parse_finance_file",
        "detect_report_type": "detect_report_type",
        "detect_financial_report_type": "detect_report_type",
        "clean_financial_data": "clean_financial_data",
        "clean": "clean_financial_data",
        "create_professional_chart": "create_professional_chart",
        "chart": "create_professional_chart",
        "analyze_financial_health": "analyze_financial_health",
        "analyze": "analyze_financial_health",
        "status": "status",
        "get_status": "status",
        "reset": "reset",
        "export_session_report": "export_session_report",
        "export": "export_session_report",
        "compare_chart": "compare_chart",
        "compare_table": "compare_table",
    }
    return aliases.get((tool_name or "").strip(), "")


def _load_data_into_session(session: AgentSession, file_path: str) -> tuple[dict | None, str]:
    if not _is_supported_agent_file(file_path):
        return None, f"不支持的文件格式，仅支持: {', '.join(SUPPORTED_FORMATS)}"

    filename = os.path.basename(file_path)
    df, error = load_financial_data(file_path)
    if error or df is None:
        return None, error or "文件加载失败"

    report_info = detect_financial_report_type(df)
    session.file_path = file_path
    session.file_name = os.path.basename(file_path)
    session.report_type = report_info.get('type')
    session.data_loaded = True
    session.data_cleaned = False
    session.df = df
    session.cleaned_df = None
    session.files.append({
        "file_name": filename,
        "file_path": file_path,
        "report_type": session.report_type,
        "df": df,
        "cleaned_df": None,
    })
    session.updated_at = datetime.now().isoformat()
    _log_agent(session, "info", "加载文件", {
        "file": session.file_name,
        "report_type": session.report_type,
    })
    return report_info, ""

@app.route('/api/agent/sessions', methods=['POST'])
def create_agent_session():
    """创建Agent会话"""
    session_id = str(uuid.uuid4())
    session = AgentSession(id=session_id, created_at=datetime.now().isoformat())
    agent_session_store.create(session)
    try:
        upstream_agent_manager.get_or_create(session_id)
    except Exception:
        pass
    return jsonify({"session_id": session_id})


@app.route('/api/agent/sessions/<session_id>/status')
def get_agent_session_status(session_id):
    """获取Agent会话状态"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify(session.to_public_dict())


@app.route('/api/agent/sessions/<session_id>/execute', methods=['POST'])
def execute_agent_tool(session_id):
    """统一工具执行接口（兼容 GitHub 工具命名）"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    payload = request.get_json(silent=True) or {}
    tool_name = _normalize_agent_tool_name(payload.get('tool_name', ''))
    tool_params = payload.get('tool_params') or {}

    if not tool_name:
        return jsonify({"error": "未知工具"}), 400

    if tool_name == 'status':
        upstream_status = None
        try:
            upstream_status = upstream_agent_manager.execute_tool(session_id, 'status', {})
        except Exception:
            upstream_status = None
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "session": session.to_public_dict(),
            "upstream_status": upstream_status,
        })

    if tool_name == 'reset':
        reset_type = str(tool_params.get('reset_type', 'soft')).lower()
        if reset_type not in ['soft', 'hard']:
            return jsonify({"error": "reset_type 仅支持 soft 或 hard"}), 400

        upstream_result = None
        try:
            upstream_result = upstream_agent_manager.execute_tool(session_id, 'reset', {'reset_type': reset_type})
        except Exception:
            upstream_result = None

        reset = agent_session_store.reset(session_id, reset_type=reset_type)
        if not reset:
            return jsonify({"error": "会话不存在"}), 404
        reset.updated_at = datetime.now().isoformat()
        _log_agent(reset, "info", "会话已重置", {"reset_type": reset_type})
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "reset_type": reset_type,
            "session": reset.to_public_dict(),
            "upstream_result": upstream_result,
        })

    if tool_name == 'parse_finance_file':
        file_path = tool_params.get('file_path')
        if not file_path:
            file_path = session.file_path
        if not file_path:
            return jsonify({"error": "未提供文件路径，且会话中无可用文件"}), 400
        file_path = _resolve_file_path(file_path)
        if not os.path.exists(file_path):
            return jsonify({"error": f"文件不存在: {file_path}"}), 400

        report_info, error = _load_data_into_session(session, file_path)
        if error:
            return jsonify({"error": error}), 400

        upstream_result = None
        try:
            upstream_result = upstream_agent_manager.execute_tool(session_id, 'parse_finance_file', {'file_path': file_path})
        except Exception:
            upstream_result = None

        return jsonify({
            "status": "success",
            "tool": tool_name,
            "report_info": report_info,
            "session": session.to_public_dict(),
            "upstream_result": upstream_result,
        })

    if tool_name == 'detect_report_type':
        df = session.cleaned_df if session.data_cleaned else session.df
        if df is None or getattr(df, 'empty', False):
            return jsonify({"error": "没有可用的数据，请先解析或上传文件"}), 400
        report_info = detect_financial_report_type(df)
        session.report_type = report_info.get('type')
        session.updated_at = datetime.now().isoformat()
        _log_agent(session, "info", "识别报表类型", report_info)
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "report_info": report_info,
            "session": session.to_public_dict(),
        })

    if tool_name == 'clean_financial_data':
        upstream_result = None
        try:
            upstream_result = upstream_agent_manager.execute_tool(session_id, 'clean_financial_data', tool_params)
        except Exception:
            upstream_result = None

        result = clean_agent_data(session_id)
        response, status_code = result if isinstance(result, tuple) else (result, 200)
        payload = response.get_json(silent=True) if isinstance(response, Response) else {}
        if not isinstance(payload, dict):
            payload = {}
        payload["tool"] = tool_name
        payload["upstream_result"] = upstream_result
        return jsonify(payload), status_code

    if tool_name == 'create_professional_chart':
        upstream_result = upstream_agent_manager.execute_tool(session_id, 'create_professional_chart', tool_params)
        if upstream_result.get("status") != "success":
            return jsonify({"error": upstream_result.get("response", "图表生成失败")}), 400

        charts = _ingest_upstream_chart_info(session, upstream_result)
        if not charts:
            return jsonify({"error": "上游图表未生成或未返回路径"}), 400

        _log_agent(session, "info", "生成图表", {
            "source": "upstream",
            "count": len(charts),
        })
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "chart": charts[-1],
            "charts": charts,
            "errors": (upstream_result.get("chart_info") or {}).get("errors", []),
            "upstream_result": upstream_result,
        })

    if tool_name == 'analyze_financial_health':
        upstream_result = upstream_agent_manager.execute_tool(session_id, 'analyze_financial_health', tool_params)
        if upstream_result.get("status") != "success":
            return jsonify({"error": upstream_result.get("response", "分析失败")}), 400

        analysis_payload = upstream_result.get("analysis")
        if analysis_payload is None:
            analysis_payload = {"summary": upstream_result.get("response", "分析完成")}

        return jsonify({
            "status": "success",
            "tool": tool_name,
            "response": upstream_result.get("response", "分析完成"),
            "analysis": analysis_payload,
            "upstream_result": upstream_result,
        })

    if tool_name == 'compare_chart':
        metric = tool_params.get('metric')
        metrics = tool_params.get('metrics') or []
        title = tool_params.get('title', '多文件对比')
        datasets = _get_datasets_for_session(session)
        if not datasets:
            return jsonify({"error": "请先上传多个文件"}), 400
        if metrics:
            charts, errors = create_multi_metric_comparison_charts(datasets, metrics=metrics, title=title)
            if not charts:
                return jsonify({"error": "对比图生成失败", "details": errors}), 400
            payload = []
            for chart in charts:
                chart_id = str(uuid.uuid4())
                session.compare_charts.append({
                    "id": chart_id,
                    "type": "compare",
                    "title": chart.get("title"),
                    "metric": chart.get("metric"),
                    "path": chart.get("path"),
                })
                payload.append({
                    "id": chart_id,
                    "type": "compare",
                    "title": chart.get("title"),
                    "download_url": url_for('download_agent_compare_chart', session_id=session.id, chart_id=chart_id),
                    "view_url": url_for('view_agent_compare_chart', session_id=session.id, chart_id=chart_id),
                    "charts_center_url": url_for('view_agent_chart_center', session_id=session.id),
                })
            session.updated_at = datetime.now().isoformat()
            _log_agent(session, "info", "生成多指标对比图", {"metrics": metrics, "count": len(payload)})
            return jsonify({"status": "success", "tool": tool_name, "charts": payload, "errors": errors})

        chart, error = _generate_compare_chart_for_session(session, metric, title)
        if error:
            return jsonify({"error": error}), 400
        _log_agent(session, "info", "生成对比图", {"metric": metric, "title": title})
        return jsonify({"status": "success", "tool": tool_name, "chart": chart})

    if tool_name == 'compare_table':
        metrics = tool_params.get('metrics')
        datasets = _get_datasets_for_session(session)
        if not datasets:
            return jsonify({"error": "请先上传多个文件"}), 400
        table, available_metrics = build_comparison_table(datasets, metrics=metrics)
        if table is None or getattr(table, 'empty', False):
            return jsonify({"error": "无法生成对比表"}), 400
        rows = table.fillna("").to_dict(orient='records')
        _log_agent(session, "info", "生成对比表", {"metrics": metrics, "rows": len(rows)})
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "metrics": available_metrics,
            "table": rows,
        })

    if tool_name == 'export_session_report':
        fmt = str(tool_params.get('format', 'json')).lower()
        if fmt not in ['json', 'html', 'txt', 'zip']:
            return jsonify({"error": "不支持的导出格式"}), 400
        return jsonify({
            "status": "success",
            "tool": tool_name,
            "download_url": url_for('export_agent_session', session_id=session_id, format=fmt),
            "format": fmt,
        })

    return jsonify({"error": "未知工具"}), 400


@app.route('/api/agent/sessions/<session_id>/upload', methods=['POST'])
def upload_agent_file(session_id):
    """上传文件并加载数据"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "未找到文件"}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "文件名为空"}), 400

    if not _is_file_size_allowed(file):
        return jsonify({"error": "文件大小不能超过10MB（10485760字节）"}), 400

    filename = secure_filename(file.filename)
    if not _is_supported_agent_file(filename):
        return jsonify({"error": f"不支持的文件格式，仅支持: {', '.join(SUPPORTED_FORMATS)}"}), 400

    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'agent_sessions')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{session_id}_{filename}")
    file.save(file_path)

    df, error = load_financial_data(file_path)
    if error or df is None:
        session.error = error
        return jsonify({"error": error}), 400

    report_info = detect_financial_report_type(df)
    session.file_path = file_path
    session.file_name = filename
    session.report_type = report_info.get('type')
    session.data_loaded = True
    session.data_cleaned = False
    session.df = df
    session.cleaned_df = None
    session.files.append({
        "file_name": filename,
        "file_path": file_path,
        "report_type": session.report_type,
        "df": df,
        "cleaned_df": None,
    })
    session.updated_at = datetime.now().isoformat()
    _log_agent(session, "info", "文件上传成功", {"file": filename, "report_type": session.report_type})
    try:
        upstream_agent_manager.execute_tool(session_id, "parse_finance_file", {"file_path": file_path})
        _sync_session_from_upstream(session_id, session)
    except Exception:
        pass

    return jsonify({
        "status": "success",
        "report_info": report_info,
        "session": session.to_public_dict()
    })


@app.route('/api/agent/sessions/<session_id>/upload-multiple', methods=['POST'])
def upload_agent_files(session_id):
    """上传多个文件并加载数据"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "未找到文件"}), 400

    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'agent_sessions')
    os.makedirs(upload_dir, exist_ok=True)

    loaded = []
    errors = []
    datasets = {}

    for file in files:
        if not file or file.filename == '':
            continue

        if not _is_file_size_allowed(file):
            errors.append({"file": file.filename or "unknown", "error": "文件大小不能超过10MB（10485760字节）"})
            continue

        filename = secure_filename(file.filename)
        if not _is_supported_agent_file(filename):
            errors.append({"file": filename, "error": f"不支持的文件格式，仅支持: {', '.join(SUPPORTED_FORMATS)}"})
            continue
        file_path = os.path.join(upload_dir, f"{session_id}_{filename}")
        file.save(file_path)

        df, error = load_financial_data(file_path)
        if error or df is None:
            errors.append({"file": filename, "error": error})
            continue

        report_info = detect_financial_report_type(df)
        session.files.append({
            "file_name": filename,
            "file_path": file_path,
            "report_type": report_info.get('type'),
            "df": df,
            "cleaned_df": None
        })
        datasets[filename] = df
        loaded.append({"file": filename, "report_info": report_info})

    session.data_loaded = len(session.files) > 0
    session.updated_at = datetime.now().isoformat()

    if session.data_loaded and not session.file_path:
        first = session.files[0]
        session.file_path = first.get('file_path')
        session.file_name = first.get('file_name')
        session.report_type = first.get('report_type')
        session.df = first.get('df')

    if loaded:
        _log_agent(session, "info", "批量上传完成", {"loaded": len(loaded), "errors": len(errors)})
        try:
            upstream_agent_manager.execute_tool(session_id, "parse_finance_file", {"file_path": session.file_path})
            _sync_session_from_upstream(session_id, session)
        except Exception:
            pass

    return jsonify({
        "status": "success" if loaded else "error",
        "loaded": loaded,
        "errors": errors,
        "session": session.to_public_dict()
    })


@app.route('/api/agent/sessions/<session_id>/clean', methods=['POST'])
def clean_agent_data(session_id):
    """清洗数据"""
    session = agent_session_store.get(session_id)
    if not session or session.df is None:
        return jsonify({"error": "会话不存在或未加载数据"}), 400

    upstream_result = upstream_agent_manager.execute_tool(session_id, 'clean_financial_data', {})
    if upstream_result.get("status") != "success":
        return jsonify({"error": upstream_result.get("response", "数据清洗失败")}), 400

    _sync_session_from_upstream(session_id, session)

    if session.cleaned_df is None or getattr(session.cleaned_df, 'empty', False):
        return jsonify({"error": "上游清洗后无可用数据"}), 400

    _, report = clean_financial_data(session.cleaned_df)

    multi_reports = []
    if session.files:
        for item in session.files:
            df = item.get('df')
            cleaned, clean_report = clean_financial_data(df) if df is not None else (None, {})
            if cleaned is not None and not getattr(cleaned, 'empty', False):
                item['cleaned_df'] = cleaned
                multi_reports.append({
                    "file": item.get('file_name'),
                    "report": clean_report
                })

    session.updated_at = datetime.now().isoformat()
    _log_agent(session, "info", "数据清洗完成", {"source": "upstream", "report": report})

    return jsonify({
        "status": "success",
        "cleaning_report": report,
        "multi_reports": multi_reports,
        "session": session.to_public_dict(),
        "upstream_result": upstream_result,
    })


@app.errorhandler(RequestEntityTooLarge)
def handle_request_entity_too_large(_error):
    """Return a clear size-limit message when request exceeds configured max bytes."""
    if request.path.startswith('/api/'):
        return jsonify({"error": "文件大小不能超过10MB（10485760字节）"}), 413

    flash('文件大小不能超过10MB（10485760字节）', 'error')
    return redirect(url_for('upload_financial'))


@app.route('/api/agent/sessions/<session_id>/chart', methods=['POST'])
def generate_agent_chart(session_id):
    """生成图表"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    data = request.get_json(silent=True) or {}
    upstream_result = upstream_agent_manager.execute_tool(session_id, 'create_professional_chart', data)
    if upstream_result.get("status") != "success":
        return jsonify({"error": upstream_result.get("response", "图表生成失败")}), 400

    charts = _ingest_upstream_chart_info(session, upstream_result)
    if not charts:
        return jsonify({"error": "上游图表未生成或未返回路径"}), 400

    _log_agent(session, "info", "生成图表", {"source": "upstream", "count": len(charts)})
    chart = charts[-1]

    return jsonify({
        "status": "success",
        "chart": {
            "id": chart["id"],
            "type": chart["type"],
            "title": chart["title"],
            "download_url": chart["download_url"],
            "view_url": chart.get("view_url"),
            "charts_center_url": chart.get("charts_center_url"),
        },
        "charts": charts,
        "upstream_result": upstream_result,
    })


@app.route('/api/agent/sessions/<session_id>/compare/chart', methods=['POST'])
def generate_agent_compare_chart(session_id):
    """生成多文件对比图"""
    session = agent_session_store.get(session_id)
    if not session or not session.files:
        return jsonify({"error": "请先上传多个文件"}), 400

    data = request.get_json(silent=True) or {}
    metric = data.get('metric')
    metrics = data.get('metrics') or []
    title = data.get('title', '多文件对比')
    datasets = _get_datasets_for_session(session)
    if metrics:
        charts, errors = create_multi_metric_comparison_charts(
            datasets,
            metrics=metrics,
            title=title,
        )
        if not charts:
            return jsonify({"error": "对比图生成失败", "details": errors}), 400
        payload = []
        for chart in charts:
            chart_id = str(uuid.uuid4())
            session.compare_charts.append({
                "id": chart_id,
                "type": "compare",
                "title": chart.get("title"),
                "metric": chart.get("metric"),
                "path": chart.get("path"),
            })
            payload.append({
                "id": chart_id,
                "type": "compare",
                "title": chart.get("title"),
                "download_url": url_for('download_agent_compare_chart', session_id=session.id, chart_id=chart_id),
                "view_url": url_for('view_agent_compare_chart', session_id=session.id, chart_id=chart_id),
                "charts_center_url": url_for('view_agent_chart_center', session_id=session.id),
            })
        session.updated_at = datetime.now().isoformat()
        _log_agent(session, "info", "生成多指标对比图", {"metrics": metrics, "count": len(payload)})
        return jsonify({"status": "success", "charts": payload, "errors": errors})

    chart, error = _generate_compare_chart_for_session(session, metric, title)
    if error:
        return jsonify({"error": error}), 400

    _log_agent(session, "info", "生成对比图", {"metric": metric, "title": title})
    return jsonify({
        "status": "success",
        "chart": {
            "id": chart["id"],
            "type": chart["type"],
            "title": chart["title"],
            "download_url": chart["download_url"],
            "view_url": chart.get("view_url"),
            "charts_center_url": chart.get("charts_center_url"),
        }
    })


@app.route('/api/agent/sessions/<session_id>/compare/chart/<chart_id>')
def download_agent_compare_chart(session_id, chart_id):
    """下载对比图表"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    chart = next((c for c in session.compare_charts if c.get('id') == chart_id), None)
    if not chart:
        return jsonify({"error": "图表不存在"}), 404

    chart_path = chart.get('path')
    if not chart_path or not os.path.exists(chart_path):
        return jsonify({"error": "图表文件不存在"}), 404

    return send_file(chart_path, as_attachment=True, download_name=os.path.basename(chart_path))


@app.route('/api/agent/sessions/<session_id>/compare/chart/<chart_id>/view')
def view_agent_compare_chart(session_id, chart_id):
    """在线查看对比图表"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    chart = next((c for c in session.compare_charts if c.get('id') == chart_id), None)
    if not chart:
        return jsonify({"error": "图表不存在"}), 404

    chart_path = chart.get('path')
    if not chart_path or not os.path.exists(chart_path):
        return jsonify({"error": "图表文件不存在"}), 404

    return send_file(chart_path, as_attachment=False)


@app.route('/api/agent/sessions/<session_id>/compare/table', methods=['POST'])
def generate_agent_compare_table(session_id):
    """生成多文件对比表"""
    session = agent_session_store.get(session_id)
    if not session or not session.files:
        return jsonify({"error": "请先上传多个文件"}), 400

    data = request.get_json(silent=True) or {}
    metrics = data.get('metrics')
    datasets = _get_datasets_for_session(session)
    table, available_metrics = build_comparison_table(datasets, metrics=metrics)
    if table is None or getattr(table, 'empty', False):
        return jsonify({"error": "无法生成对比表"}), 400

    rows = table.fillna("").to_dict(orient='records')
    _log_agent(session, "info", "生成对比表", {"metrics": metrics, "rows": len(rows)})
    return jsonify({
        "status": "success",
        "metrics": available_metrics,
        "table": rows,
    })


@app.route('/api/agent/sessions/<session_id>/process', methods=['POST'])
def process_agent_message(session_id):
    """自然语言决策入口"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    data = request.get_json(silent=True) or {}
    message = data.get('message', '')
    started_at = time.perf_counter()
    _log_agent(session, "info", "收到指令", {"message": message, "source": "upstream"})

    try:
        upstream_result = upstream_agent_manager.process(session_id, message)
    except Exception as exc:
        return _attach_process_meta((jsonify({"error": f"上游处理失败: {exc}"}), 500), time.perf_counter() - started_at, 0.5)

    confidence = float(upstream_result.get("confidence", 0.5) or 0.5)
    charts = _ingest_upstream_chart_info(session, upstream_result)

    status = upstream_result.get("status", "success")
    message_text = upstream_result.get("response", "已处理")
    suggestions = upstream_result.get("next_suggestions", [])
    session.suggestions = suggestions if isinstance(suggestions, list) else []
    session.updated_at = datetime.now().isoformat()

    payload = {
        "status": status,
        "message": message_text,
        "suggestions": session.suggestions,
        "session": session.to_public_dict(),
        "upstream_result": upstream_result,
    }
    if charts:
        payload["chart"] = charts[-1]
        payload["charts"] = charts

    if status != "success":
        return _attach_process_meta((jsonify(payload), 400), time.perf_counter() - started_at, confidence)
    return _attach_process_meta(jsonify(payload), time.perf_counter() - started_at, confidence)


@app.route('/api/agent/sessions/<session_id>/chart/<chart_id>')
def download_agent_chart(session_id, chart_id):
    """下载图表"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    chart = next((c for c in session.charts if c.get('id') == chart_id), None)
    if not chart:
        return jsonify({"error": "图表不存在"}), 404

    chart_path = chart.get('path')
    if not chart_path or not os.path.exists(chart_path):
        return jsonify({"error": "图表文件不存在"}), 404

    return send_file(chart_path, as_attachment=True, download_name=os.path.basename(chart_path))


@app.route('/api/agent/sessions/<session_id>/chart/<chart_id>/view')
def view_agent_chart(session_id, chart_id):
    """在线查看图表"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    chart = next((c for c in session.charts if c.get('id') == chart_id), None)
    if not chart:
        return jsonify({"error": "图表不存在"}), 404

    chart_path = chart.get('path')
    if not chart_path or not os.path.exists(chart_path):
        return jsonify({"error": "图表文件不存在"}), 404

    return send_file(chart_path, as_attachment=False)


@app.route('/agent/sessions/<session_id>/charts')
def view_agent_chart_center(session_id):
    """图表中心（替代桌面端打开文件夹）"""
    session = agent_session_store.get(session_id)
    if not session:
        return "会话不存在", 404

    items: List[str] = []
    for chart in session.charts:
        chart_id = chart.get("id")
        title = chart.get("title", "图表")
        view_url = url_for('view_agent_chart', session_id=session_id, chart_id=chart_id)
        download_url = url_for('download_agent_chart', session_id=session_id, chart_id=chart_id)
        items.append(f"<li>{title} - <a href='{view_url}' target='_blank'>查看</a> | <a href='{download_url}' target='_blank'>下载</a></li>")

    for chart in session.compare_charts:
        chart_id = chart.get("id")
        title = chart.get("title", "对比图")
        view_url = url_for('view_agent_compare_chart', session_id=session_id, chart_id=chart_id)
        download_url = url_for('download_agent_compare_chart', session_id=session_id, chart_id=chart_id)
        items.append(f"<li>{title} - <a href='{view_url}' target='_blank'>查看</a> | <a href='{download_url}' target='_blank'>下载</a></li>")

    body = "".join(items) if items else "<li>暂无图表</li>"
    return f"""
    <!DOCTYPE html>
    <html lang='zh-CN'>
    <head><meta charset='utf-8'><title>图表中心</title></head>
    <body style='font-family: Arial, sans-serif; padding: 20px;'>
      <h2>图表中心 - 会话 {session_id}</h2>
      <ul>{body}</ul>
    </body>
    </html>
    """


@app.route('/api/agent/sessions/<session_id>/analyze', methods=['POST'])
def analyze_agent_health(session_id):
    """财务健康分析"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    upstream_result = upstream_agent_manager.execute_tool(
        session_id,
        'analyze_financial_health',
        {'report_type': session.report_type or '从上下文获取'}
    )
    if upstream_result.get("status") != "success":
        return jsonify({"error": upstream_result.get("response", "分析失败")}), 400

    analysis = upstream_result.get("analysis")
    if analysis is None:
        analysis = {"summary": upstream_result.get("response", "分析完成")}

    _log_agent(session, "info", "财务健康分析完成", {"source": "upstream"})
    return jsonify({
        "status": "success",
        "analysis": analysis,
        "response": upstream_result.get("response", "分析完成"),
        "upstream_result": upstream_result,
    })


@app.route('/api/agent/sessions/<session_id>/reset', methods=['POST'])
def reset_agent_session(session_id):
    """重置Agent会话"""
    data = request.get_json(silent=True) or {}
    reset_type = str(data.get('reset_type', 'soft')).lower()
    if reset_type not in ['soft', 'hard']:
        return jsonify({"error": "reset_type 仅支持 soft 或 hard"}), 400

    upstream_result = None
    try:
        upstream_result = upstream_agent_manager.execute_tool(session_id, 'reset', {'reset_type': reset_type})
    except Exception:
        upstream_result = None

    session = agent_session_store.reset(session_id, reset_type=reset_type)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    session.updated_at = datetime.now().isoformat()
    _log_agent(session, "info", "会话已重置", {"reset_type": reset_type})
    return jsonify({
        "status": "success",
        "reset_type": reset_type,
        "session": session.to_public_dict(),
        "upstream_result": upstream_result,
    })


@app.route('/api/agent/config')
def get_agent_config():
    """获取Agent配置"""
    return jsonify({
        "chart_types": CHART_TYPES,
        "supported_formats": SUPPORTED_FORMATS,
        "output_dir": DEFAULT_OUTPUT_DIR,
        "tools": [
            "upload_file",
            "parse_finance_file",
            "detect_report_type",
            "clean_financial_data",
            "create_professional_chart",
            "analyze_financial_health",
            "compare_chart",
            "compare_table",
            "status",
            "reset",
            "export_session_report",
        ],
    })


@app.route('/api/agent/sessions/<session_id>/logs')
def get_agent_logs(session_id):
    """获取Agent日志"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify({
        "status": "success",
        "logs": session.logs,
        "workflow_history": session.workflow_history,
    })


@app.route('/api/agent/sessions/<session_id>/export')
def export_agent_session(session_id):
    """导出会话报告"""
    session = agent_session_store.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    fmt = request.args.get('format', 'json').lower()
    if fmt not in ['json', 'html', 'txt', 'zip']:
        return jsonify({"error": "不支持的导出格式"}), 400

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_id = session.id.replace('-', '')

    if fmt == 'json':
        payload = _serialize_session_for_export(session)
        response = jsonify(payload)
        response.headers['Content-Disposition'] = f'attachment; filename="agent_session_{safe_id}_{timestamp}.json"'
        return response

    if fmt == 'html':
        html = _build_export_html(session)
        return Response(
            html,
            mimetype='text/html',
            headers={'Content-Disposition': f'attachment; filename="agent_session_{safe_id}_{timestamp}.html"'}
        )

    if fmt == 'txt':
        text = _build_export_text(session)
        return Response(
            text,
            mimetype='text/plain; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="agent_session_{safe_id}_{timestamp}.txt"'}
        )

    json_payload = json.dumps(_serialize_session_for_export(session), ensure_ascii=False, indent=2)
    html_payload = _build_export_html(session)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr('session.json', json_payload)
        zipf.writestr('session.html', html_payload)
        for chart in session.charts + session.compare_charts:
            chart_path = chart.get('path')
            if chart_path and os.path.exists(chart_path):
                zipf.write(chart_path, arcname=os.path.basename(chart_path))
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"agent_session_{safe_id}_{timestamp}.zip",
        mimetype='application/zip'
    )

@app.route('/results/<task_id>')
def show_results(task_id):
    """显示分析结果"""
    task = task_store.get(task_id)
    if not task or task.status != 'completed':
        flash('任务未完成或不存在', 'error')
        return redirect(url_for('upload_financial'))
    
    report_indicators = []
    report_structured = {}
    if task.report_path and os.path.exists(task.report_path):
        try:
            with open(task.report_path, 'r', encoding='utf-8', errors='ignore') as f:
                report_content = f.read()
            report_indicators = _extract_report_indicators(report_content)
            report_structured = _build_structured_analysis_from_report(task, report_content)
        except Exception:
            report_indicators = []
            report_structured = {}

    return render_template(
        'results.html',
        task=task,
        analysis_types=app.config['ANALYSIS_TYPES'],
        financial_templates=app.config['FINANCIAL_TEMPLATES'],
        report_indicators=report_indicators,
        report_structured=report_structured,
    )

@app.route('/report/<task_id>')
def show_report(task_id):
    """显示分析报告"""
    task = task_store.get(task_id)
    if not task or not task.report_path:
        flash('报告未生成', 'error')
        return redirect(url_for('show_results', task_id=task_id))
    
    # 读取并显示报告
    with open(task.report_path, 'r', encoding='utf-8') as f:
        report_content = f.read()

    charts = []
    if task.results and isinstance(task.results, dict):
        charts = task.results.get('charts') or []

    report_content_html = _report_content_to_html(report_content, task.report_path)
    report_content_html = _rewrite_report_asset_urls(report_content_html, task_id)
    structured = _build_structured_analysis_from_report(task, report_content)
    return render_template(
        'report.html',
        task=task,
        charts=charts,
        report_content_html=report_content_html,
        structured=structured,
    )


@app.route('/report_asset/<task_id>/<path:asset_path>')
def report_asset(task_id, asset_path):
    """Serve local chart/image assets referenced by report body."""
    task = task_store.get(task_id)
    if not task or not task.report_path:
        return jsonify({'error': '报告不存在'}), 404

    report_dir = os.path.dirname(task.report_path)
    normalized = os.path.normpath(asset_path).lstrip('/\\')
    candidates = [os.path.join(report_dir, normalized)]

    if task.results and isinstance(task.results, dict):
        upstream_output_dir = task.results.get('upstream_output_dir')
        if upstream_output_dir:
            candidates.append(os.path.join(upstream_output_dir, normalized))

    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            return send_file(abs_path)

    return jsonify({'error': '报告资源不存在'}), 404

@app.route('/download/<task_id>')
def download_report(task_id):
    """下载报告"""
    task = task_store.get(task_id)
    if task and task.report_path:
        company = (task.company_name or task.id).strip()
        company = re.sub(r'\.(pdf|html|md|csv|xlsx|xls|docx|png|jpg|jpeg)$', '', company, flags=re.IGNORECASE)
        filename = f"财务分析报告_{company}.pdf"
        try:
            with open(task.report_path, 'r', encoding='utf-8', errors='ignore') as f:
                report_content = f.read()
            report_content_html = _report_content_to_html(report_content, task.report_path)
            report_content_html = _rewrite_report_asset_urls(report_content_html, task_id)
            structured = _build_structured_analysis_from_report(task, report_content)
            pdf_text = _build_pdf_text_from_report_view(task, structured, report_content_html)
            pdf_bytes = _build_report_pdf_bytes(f"财务分析报告 - {company}", pdf_text)
            return send_file(
                pdf_bytes,
                as_attachment=True,
                download_name=filename,
                mimetype='application/pdf'
            )
        except Exception:
            app.logger.exception('导出 PDF 失败 task_id=%s report_path=%s', task_id, task.report_path)
            flash('PDF 导出失败，请联系管理员检查 reportlab 依赖', 'error')
            return redirect(url_for('show_results', task_id=task_id))
    flash('报告不存在', 'error')
    return redirect(url_for('index'))

@app.route('/sample/<sample_type>')
def download_sample(sample_type):
    """下载示例文件"""
    sample_files = {
        'income': 'data/samples/income_statement.csv',
        'balance': 'data/samples/balance_sheet.csv'
    }
    
    if sample_type in sample_files and os.path.exists(sample_files[sample_type]):
        filename = f'示例财务报表_{sample_type}.csv'
        return send_file(
            sample_files[sample_type],
            as_attachment=True,
            download_name=filename
        )
    
    flash('示例文件不存在', 'error')
    return redirect(url_for('upload_financial'))

# ==================== 错误处理 ====================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# ==================== 启动应用 ====================

if __name__ == '__main__':
    host = os.environ.get('APP_HOST', '0.0.0.0')
    port = int(os.environ.get('APP_PORT', '5000'))
    debug_env = os.environ.get('APP_DEBUG')
    debug = True if debug_env is None else debug_env.lower() in ['1', 'true', 'yes']

    print("=" * 60)
    print("财报分析平台启动中...")
    print(f"访问地址: http://127.0.0.1:{port}")
    print(f"服务监听: {host}:{port}")
    print(f"上传目录: {app.config['UPLOAD_FOLDER']}")
    print(f"报告目录: {app.config['REPORT_FOLDER']}")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=debug)