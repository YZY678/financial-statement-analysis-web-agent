import os
import json
import subprocess
import sys
import tempfile
import time
import uuid
import shutil
from urllib import error, parse, request
from threading import Lock
from typing import Dict, Optional


class UpstreamReportRuntime:
    """Execute upstream backend/main.py in a subprocess without modifying upstream code."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._output_dir: Optional[str] = None
        self._ollama_process: Optional[subprocess.Popen] = None

    def _resolve_backend_dir(self) -> str:
        default_dir = "/root/web/financial-statement-analysis-web-agent-main/backend"
        return os.environ.get("UPSTREAM_REPORT_BACKEND_DIR", default_dir)

    def _resolve_main_py(self) -> str:
        backend_dir = self._resolve_backend_dir()
        main_py = os.path.join(backend_dir, "main.py")
        if not os.path.exists(main_py):
            raise FileNotFoundError(f"上游入口不存在: {main_py}")
        return main_py

    def available(self) -> bool:
        try:
            self._resolve_main_py()
            return True
        except Exception:
            return False

    def _load_upstream_env(self) -> Dict[str, str]:
        """Load key-value pairs from upstream .env without mutating process env."""
        env_map: Dict[str, str] = {}
        env_path = os.path.join(self._resolve_backend_dir(), ".env")
        if not os.path.exists(env_path):
            return env_map

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env_map[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            return {}
        return env_map

    def _resolve_llm_config(self) -> Dict[str, str]:
        upstream_env = self._load_upstream_env()
        base_url = os.environ.get("OPENAI_BASE_URL") or upstream_env.get("OPENAI_BASE_URL", "")
        model = os.environ.get("LOCAL_MODEL_NAME") or upstream_env.get("LOCAL_MODEL_NAME", "")
        return {
            "base_url": base_url,
            "model": model,
        }

    def _normalize_base_url(self, base_url: str) -> str:
        if not base_url:
            return ""
        return base_url[:-3] if base_url.endswith("/v1") else base_url

    def _is_local_ollama_endpoint(self, base_url: str) -> bool:
        if not base_url:
            return False
        normalized = self._normalize_base_url(base_url)
        parsed = parse.urlparse(normalized)
        return parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == 11434

    def _ollama_health_ok(self, ollama_base_url: str) -> bool:
        tags_url = f"{ollama_base_url.rstrip('/')}/api/tags"
        try:
            with request.urlopen(tags_url, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _start_ollama_serve(self) -> None:
        if self._ollama_process and self._ollama_process.poll() is None:
            return
        if shutil.which("ollama") is None:
            raise RuntimeError("未检测到 ollama 命令，无法启动本地模型服务")

        self._ollama_process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _ensure_model_exists(self, model_name: str) -> None:
        if not model_name:
            return
        if shutil.which("ollama") is None:
            return

        completed = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return

        # Exact name or name:latest style match.
        existing = completed.stdout or ""
        if model_name in existing or f"{model_name}:latest" in existing:
            return
        raise RuntimeError(
            f"本地模型缺失: {model_name}。请先执行: ollama pull {model_name}"
        )

    def _ensure_ollama_ready(self, base_url: str, model_name: str) -> None:
        ollama_base = self._normalize_base_url(base_url)
        if self._ollama_health_ok(ollama_base):
            self._ensure_model_exists(model_name)
            return

        self._start_ollama_serve()
        deadline = time.time() + 20
        while time.time() < deadline:
            if self._ollama_health_ok(ollama_base):
                self._ensure_model_exists(model_name)
                return
            time.sleep(0.5)

        raise RuntimeError(
            f"本地 Ollama 服务未就绪: {ollama_base}，请检查 `ollama serve` 是否可启动"
        )

    def _ensure_upstream_dependencies(self) -> None:
        llm_cfg = self._resolve_llm_config()
        base_url = llm_cfg.get("base_url", "")
        model_name = llm_cfg.get("model", "")
        if self._is_local_ollama_endpoint(base_url):
            self._ensure_ollama_ready(base_url, model_name)

    def _resolve_timeout_seconds(self) -> int:
        """Max runtime for one upstream report generation call."""
        raw = os.environ.get("UPSTREAM_REPORT_TIMEOUT_SECONDS", "1200")
        try:
            timeout = int(raw)
        except Exception:
            timeout = 1200
        # Enforce hard cap: one analysis must not exceed 20 minutes.
        return min(max(60, timeout), 1200)

    def generate_financial_report(self, pdf_path: str) -> str:
        main_py = self._resolve_main_py()
        backend_dir = self._resolve_backend_dir()
        self._ensure_upstream_dependencies()
        output_root = self._output_dir or tempfile.gettempdir()
        os.makedirs(output_root, exist_ok=True)
        out_path = os.path.join(output_root, f"financial_report_{uuid.uuid4().hex}.md")

        env = os.environ.copy()
        if self._output_dir:
            env["OUTPUT_DIR"] = self._output_dir

        cmd = [sys.executable, main_py, pdf_path, out_path]
        with self._lock:
            timeout_seconds = self._resolve_timeout_seconds()
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=backend_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"上游报告生成超时（>{timeout_seconds}s），请稍后重试或简化输入文件。"
                ) from exc

        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(err or f"上游运行失败，退出码: {completed.returncode}")

        if not os.path.exists(out_path):
            raise RuntimeError("上游运行完成但未生成报告文件")

        with open(out_path, "r", encoding="utf-8") as f:
            return f.read()

    def set_output_dir(self, output_dir: Optional[str]) -> None:
        self._output_dir = output_dir


upstream_report_runtime = UpstreamReportRuntime()
