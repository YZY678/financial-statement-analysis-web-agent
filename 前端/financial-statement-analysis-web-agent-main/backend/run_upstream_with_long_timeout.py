import os
from pathlib import Path

import llm_client
from report_generator import generate_financial_report


def patched_call_chat(model, messages, json_mode=False):
    client = llm_client._get_client()
    kwargs = {
        "model": llm_client.LOCAL_MODEL_NAME,
        "messages": messages,
        "timeout": 3600,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def main() -> int:
    pdf_path = "/root/web/1222993920-2.PDF"
    out_path = "/root/web/financial-analysis-platform/reports/upstream_run/generated_report.md"
    output_dir = "/root/web/financial-analysis-platform/reports/upstream_run"

    os.environ["OUTPUT_DIR"] = output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    llm_client._call_chat = patched_call_chat

    article = generate_financial_report(pdf_path)
    Path(out_path).write_text(article, encoding="utf-8")
    print(f"OK: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
