"""
PDF 解析模块：提取原始文本与表格，可选多模态 AI 增强。
"""
import json
import logging
import re
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def _guess_unit(page_text: str) -> str:
    """从页面文本中猜测单位（常见：单位：元/万元/亿元）"""
    if not page_text:
        return "UNKNOWN"
    m = re.search(r"单位[:：]\s*(元|万元|亿元)", page_text)
    return m.group(1) if m else "UNKNOWN"


def _extract_with_pdfplumber(pdf_path: str) -> Tuple[str, str]:
    """使用 pdfplumber 提取文本与表格（按页容错）。"""
    if not pdfplumber:
        raise ImportError("请安装 pdfplumber: pip install pdfplumber")
    raw_parts = []
    tables_all = []
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # 按页容错：单页失败不影响其他页
            try:
                text = page.extract_text()
                if text:
                    raw_parts.append(text)
                
                # 猜测本页单位
                unit = _guess_unit(text or "")
                
                # 尝试多种表格提取策略
                tables = page.extract_tables()
                
                # 如果默认策略失败，尝试调整参数
                if not tables:
                    # 策略1：调整表格设置（适合复杂表格）
                    table_settings = {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 3,
                    }
                    tables = page.extract_tables(table_settings)
                
                if not tables:
                    # 策略2：尝试文本策略（适合无边框表格）
                    table_settings = {
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                    }
                    tables = page.extract_tables(table_settings)
                
                for t in tables:
                    if t and len(t) > 0:  # 确保表格非空
                        # 给每个表格加页码和单位线索
                        tables_all.append({
                            "page": i + 1,
                            "unit_hint": unit,
                            "table": t
                        })
            except Exception as e:
                logger.warning(f"第{i+1}页提取失败: {e}，跳过该页")
                continue
    
    raw_text = "\n\n".join(raw_parts)
    tables_json = json.dumps(tables_all, ensure_ascii=False, indent=2)
    
    # 日志输出
    logger.info(f"PDF解析完成: 共{len(raw_parts)}页，提取到{len(tables_all)}个表格")
    if len(tables_all) == 0:
        logger.warning("⚠️ 未提取到任何表格，可能需要使用OCR或其他工具")
    
    return raw_text, tables_json


def _extract_with_pymupdf(pdf_path: str) -> Tuple[str, str]:
    """使用 PyMuPDF 提取纯文本（无表格结构）。"""
    if not fitz:
        raise ImportError("请安装 PyMuPDF: pip install pymupdf")
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")
    doc = fitz.open(pdf_path)
    raw_parts = [page.get_text() for page in doc]
    doc.close()
    raw_text = "\n\n".join(raw_parts)
    return raw_text, "[]"


def parse_pdf_with_multimodal_ai(pdf_path: str) -> Tuple[str, str]:
    """
    解析 PDF，返回 (原始文本, 表格 JSON)。
    优先使用 pdfplumber 提取文本+表格；只有在完全失败时才回退到 PyMuPDF。
    可在此处扩展：将页面转图片后调用 Vision API 做多模态解析。
    """
    try:
        raw_text, tables_json = _extract_with_pdfplumber(pdf_path)
        # 只有在表格完全为空时才考虑回退
        if tables_json == "[]":
            logger.warning("pdfplumber未提取到表格，尝试pymupdf获取文本")
            # 但保留pdfplumber的文本（通常更好）
            try:
                raw_text_backup, _ = _extract_with_pymupdf(pdf_path)
                if len(raw_text_backup) > len(raw_text):
                    raw_text = raw_text_backup
            except Exception:
                pass
        return raw_text, tables_json
    except Exception as e:
        logger.exception("pdfplumber完全失败，回退到pymupdf: %s", e)
        return _extract_with_pymupdf(pdf_path)
