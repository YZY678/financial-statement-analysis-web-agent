import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _call_execute(client, session_id: str, tool_name: str, tool_params: Dict[str, Any] | None = None):
    response = client.post(
        f"/api/agent/sessions/{session_id}/execute",
        json={
            "tool_name": tool_name,
            "tool_params": tool_params or {},
        },
    )
    payload = response.get_json(silent=True) or {}
    return response.status_code, payload


def _append_result(results: List[CheckResult], name: str, condition: bool, detail: str):
    results.append(CheckResult(name=name, ok=condition, detail=detail))


def run_selfcheck() -> Tuple[bool, List[CheckResult]]:
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    results: List[CheckResult] = []

    sample_income = os.path.abspath("data/samples/income_statement.csv")
    sample_balance = os.path.abspath("data/samples/balance_sheet.csv")

    if not os.path.exists(sample_income) or not os.path.exists(sample_balance):
        _append_result(
            results,
            "samples_exists",
            False,
            f"示例文件不存在: income={sample_income}, balance={sample_balance}",
        )
        return False, results

    # 1) 创建会话
    create_resp = client.post("/api/agent/sessions")
    create_data = create_resp.get_json(silent=True) or {}
    session_id = create_data.get("session_id")
    _append_result(
        results,
        "create_session",
        create_resp.status_code == 200 and bool(session_id),
        f"status={create_resp.status_code}, session_id={session_id}",
    )
    if not session_id:
        return False, results

    # 2) status
    code, payload = _call_execute(client, session_id, "status")
    _append_result(
        results,
        "execute_status",
        code == 200 and payload.get("status") == "success" and "session" in payload,
        f"status={code}, payload_keys={list(payload.keys())}",
    )

    # 3) upload_file(alias) -> parse_finance_file
    code, payload = _call_execute(client, session_id, "upload_file", {"file_path": sample_income})
    report_info = payload.get("report_info") or {}
    _append_result(
        results,
        "execute_upload_file_alias",
        code == 200 and payload.get("status") == "success" and bool(report_info.get("type")),
        f"status={code}, report_type={report_info.get('type')}",
    )

    # 4) detect_report_type
    code, payload = _call_execute(client, session_id, "detect_report_type")
    _append_result(
        results,
        "execute_detect_report_type",
        code == 200 and payload.get("status") == "success" and bool((payload.get("report_info") or {}).get("type")),
        f"status={code}, report_info={payload.get('report_info')}",
    )

    # 5) clean_financial_data
    code, payload = _call_execute(client, session_id, "clean_financial_data")
    _append_result(
        results,
        "execute_clean_financial_data",
        code == 200 and payload.get("status") == "success" and "cleaning_report" in payload,
        f"status={code}, keys={list(payload.keys())}",
    )

    # 6) create_professional_chart with output_dir
    custom_output_dir = "./reports/agent_charts/selfcheck_custom"
    code, payload = _call_execute(
        client,
        session_id,
        "create_professional_chart",
        {
            "chart_type": "income_trend",
            "title": "接口自检图表",
            "output_dir": custom_output_dir,
        },
    )
    chart = payload.get("chart") or {}
    _append_result(
        results,
        "execute_create_professional_chart",
        code == 200 and payload.get("status") == "success" and bool(chart.get("download_url")),
        f"status={code}, chart={chart}",
    )

    # 7) analyze_financial_health
    code, payload = _call_execute(client, session_id, "analyze_financial_health")
    _append_result(
        results,
        "execute_analyze_financial_health",
        code == 200 and payload.get("status") == "success" and "analysis" in payload,
        f"status={code}, has_analysis={'analysis' in payload}",
    )

    # 8) 比较能力准备：上传多文件
    with open(sample_income, "rb") as f1, open(sample_balance, "rb") as f2:
        multi_resp = client.post(
            f"/api/agent/sessions/{session_id}/upload-multiple",
            data={
                "files": [(f1, os.path.basename(sample_income)), (f2, os.path.basename(sample_balance))],
            },
            content_type="multipart/form-data",
        )
    multi_payload = multi_resp.get_json(silent=True) or {}
    _append_result(
        results,
        "upload_multiple_for_compare",
        multi_resp.status_code == 200 and bool(multi_payload.get("loaded")),
        f"status={multi_resp.status_code}, loaded={len(multi_payload.get('loaded') or [])}",
    )

    # 多文件上传后再次清洗，确保 compare 使用 cleaned_df 路径
    code, payload = _call_execute(client, session_id, "clean_financial_data")
    _append_result(
        results,
        "execute_clean_after_multi_upload",
        code == 200 and payload.get("status") == "success",
        f"status={code}, keys={list(payload.keys())}",
    )

    # 9) compare_table
    code, payload = _call_execute(client, session_id, "compare_table")
    available_metrics = payload.get("metrics") or []
    _append_result(
        results,
        "execute_compare_table",
        code == 200 and payload.get("status") == "success" and isinstance(payload.get("table"), list),
        f"status={code}, rows={len(payload.get('table') or [])}, metrics={available_metrics[:3]}",
    )

    # 10) compare_chart
    compare_params: Dict[str, Any] = {"title": "接口自检对比图"}
    if available_metrics:
        compare_params["metric"] = available_metrics[0]
    code, payload = _call_execute(client, session_id, "compare_chart", compare_params)
    compare_chart = payload.get("chart") or {}
    _append_result(
        results,
        "execute_compare_chart",
        code == 200 and payload.get("status") == "success" and bool(compare_chart.get("download_url")),
        f"status={code}, chart={compare_chart}",
    )

    # 11) export_session_report(json/html/txt/zip)
    for fmt in ["json", "html", "txt", "zip"]:
        code, payload = _call_execute(client, session_id, "export_session_report", {"format": fmt})
        _append_result(
            results,
            f"execute_export_session_report_{fmt}",
            code == 200 and payload.get("status") == "success" and bool(payload.get("download_url")),
            f"status={code}, url={payload.get('download_url')}",
        )

    # 12) reset
    code, payload = _call_execute(client, session_id, "reset")
    _append_result(
        results,
        "execute_reset",
        code == 200 and payload.get("status") == "success" and "session" in payload,
        f"status={code}, keys={list(payload.keys())}",
    )

    success = all(item.ok for item in results)
    return success, results


def main() -> int:
    success, results = run_selfcheck()

    print("=" * 72)
    print("Agent Unified API Interface Selfcheck")
    print("=" * 72)
    for item in results:
        mark = "PASS" if item.ok else "FAIL"
        print(f"[{mark}] {item.name} -> {item.detail}")

    print("-" * 72)
    print(f"TOTAL: {len(results)}, PASS: {sum(1 for r in results if r.ok)}, FAIL: {sum(1 for r in results if not r.ok)}")
    print("RESULT:", "SUCCESS" if success else "FAILED")
    print("=" * 72)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
