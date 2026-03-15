# 配置文件：API Key 等请通过环境变量或 .env 设置
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# OpenAI API（用于 LLM 与多模态 PDF 解析）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)  # 可选，兼容代理

LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "qwen2.5:7b")

# 单位换算/口径控制
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "CNY")
DEFAULT_SCALE = os.getenv("DEFAULT_SCALE", "元")  # 统一单位：元/万元/亿元
STRICT_EVIDENCE = os.getenv("STRICT_EVIDENCE", "1") == "1"  # 是否强制要求证据字段

# 报告质量控制（重写版新增）
REQUIRE_METADATA = os.getenv("REQUIRE_METADATA", "1") == "1"  # 强制要求期间/口径/单位声明
VALIDATE_BREAKDOWN = os.getenv("VALIDATE_BREAKDOWN", "1") == "1"  # 校验分项加总一致性
MIN_INDICATORS = int(os.getenv("MIN_INDICATORS", "5"))  # 最少提取指标数量
ENABLE_EVIDENCE_TRACE = os.getenv("ENABLE_EVIDENCE_TRACE", "1") == "1"  # 启用证据溯源

# 输出目录
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output")).resolve()
CHART_DIR = OUTPUT_DIR / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)
