import argparse
import difflib
import re
from pathlib import Path


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    # Collapse repeated blank lines and normalize spaces for robust comparisons.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare generated markdown report with reference report")
    parser.add_argument("--generated", required=True, help="Generated report markdown path")
    parser.add_argument("--reference", default="/root/web/financial_report.md", help="Reference report markdown path")
    parser.add_argument("--show-lines", type=int, default=120, help="Max diff lines to print")
    args = parser.parse_args()

    gen_path = Path(args.generated)
    ref_path = Path(args.reference)

    if not gen_path.exists():
        print(f"ERROR: generated file not found: {gen_path}")
        return 2
    if not ref_path.exists():
        print(f"ERROR: reference file not found: {ref_path}")
        return 2

    gen_raw = gen_path.read_text(encoding="utf-8")
    ref_raw = ref_path.read_text(encoding="utf-8")
    gen = normalize(gen_raw)
    ref = normalize(ref_raw)

    exact_match = gen == ref
    sm = difflib.SequenceMatcher(a=ref, b=gen)
    similarity = sm.ratio()

    print("=== Report Comparison ===")
    print(f"reference: {ref_path}")
    print(f"generated: {gen_path}")
    print(f"exact_match: {exact_match}")
    print(f"similarity: {similarity:.4f}")

    if not exact_match:
        ref_lines = ref.splitlines()
        gen_lines = gen.splitlines()
        diff = list(difflib.unified_diff(ref_lines, gen_lines, fromfile="reference", tofile="generated", lineterm=""))
        print(f"diff_lines: {len(diff)}")
        print("--- diff (truncated) ---")
        for line in diff[: args.show_lines]:
            print(line)

    return 0 if exact_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
