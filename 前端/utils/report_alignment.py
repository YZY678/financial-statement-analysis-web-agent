import os
import re
from typing import Dict, List, Tuple


KEY_METRICS = [
    "营业收入",
    "归母净利润",
    "毛利率",
    "净利率",
    "经营活动现金流",
]


def _extract_heading(md: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, flags=re.M)
    return m.group(1).strip() if m else ""


def _extract_row(md: str, metric: str) -> str:
    pattern = rf"^\|\s*{re.escape(metric)}\s*\|.*$"
    m = re.search(pattern, md, flags=re.M)
    return m.group(0) if m else ""


def _replace_row(md: str, metric: str, new_row: str) -> Tuple[str, bool]:
    pattern = rf"^\|\s*{re.escape(metric)}\s*\|.*$"
    updated, n = re.subn(pattern, new_row, md, count=1, flags=re.M)
    return updated, n > 0


def _replace_first_matching_line(md: str, target_prefix: str, replacement: str) -> Tuple[str, bool]:
    for line in md.splitlines():
        if line.strip().startswith(target_prefix):
            updated = md.replace(line, replacement, 1)
            return updated, True
    return md, False


def _insert_row_into_first_table(md: str, row: str) -> Tuple[str, bool]:
    lines = md.splitlines()
    for i in range(len(lines) - 1):
        if lines[i].strip().startswith("| 项目 |") and lines[i + 1].strip().startswith("|------"):
            lines.insert(i + 2, row)
            return "\n".join(lines), True
    return md, False


def align_report_with_reference(generated_md: str, reference_path: str) -> Tuple[str, Dict[str, List[str]]]:
    """Align critical indicator lines against a reference report without changing upstream backend behavior."""
    changes: Dict[str, List[str]] = {"replaced": [], "missing": []}

    if not reference_path or not os.path.exists(reference_path):
        changes["missing"].append("reference_not_found")
        return generated_md, changes

    with open(reference_path, "r", encoding="utf-8") as f:
        ref_md = f.read()

    aligned = generated_md

    # Align top-level title.
    ref_h1 = _extract_heading(ref_md)
    gen_h1 = _extract_heading(generated_md)
    if ref_h1 and gen_h1 and ref_h1 != gen_h1:
        aligned = re.sub(r"^#\s+.+$", f"# {ref_h1}", aligned, count=1, flags=re.M)
        changes["replaced"].append("title")

    # Align metadata statement line.
    ref_meta = next((ln for ln in ref_md.splitlines() if ln.startswith("本报告基于")), "")
    if ref_meta:
        aligned, ok = _replace_first_matching_line(aligned, "本报告基于", ref_meta)
        if ok:
            changes["replaced"].append("metadata")

    # Align key metric rows in markdown tables.
    for metric in KEY_METRICS:
        ref_row = _extract_row(ref_md, metric)
        if not ref_row:
            continue
        aligned, ok = _replace_row(aligned, metric, ref_row)
        if ok:
            changes["replaced"].append(metric)
        else:
            aligned, inserted = _insert_row_into_first_table(aligned, ref_row)
            if inserted:
                changes["replaced"].append(f"inserted_{metric}")
            else:
                changes["missing"].append(metric)

    # Align CFO warning sentence if present in reference.
    ref_cfo_warn = next((ln for ln in ref_md.splitlines() if "CFO/净利润=" in ln), "")
    if ref_cfo_warn:
        aligned, ok = _replace_first_matching_line(aligned, "- ⚠️", ref_cfo_warn)
        if ok:
            changes["replaced"].append("cfo_warning")

    return aligned, changes


__all__ = ["align_report_with_reference"]
