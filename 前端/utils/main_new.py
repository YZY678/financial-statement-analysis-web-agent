"""
入口：从命令行传入 PDF 路径生成财务报告，或启动可视化 GUI（main2 + agent2 + brain + tools）。
"""
import sys
from pathlib import Path

from .config import OUTPUT_DIR
from report_generator import generate_financial_report


def run_visualization_gui():
    """启动财经数据可视化智能体 GUI。"""
    try:
        from main2 import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"无法启动可视化 GUI: {e}")
        print("请确认 main2、agent2、brain、tools、role 等模块可用。")
        sys.exit(1)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("--gui", "-g", "gui"):
        run_visualization_gui()
        return
    pdf_path = argv[0]
    out_path = argv[1] if len(argv) > 1 else None
    if not Path(pdf_path).exists():
        print(f"错误: 文件不存在 {pdf_path}")
        sys.exit(1)
    print("正在解析 PDF 并生成报告...")
    article = generate_financial_report(pdf_path)
    if out_path is None:
        out_path = OUTPUT_DIR / "financial_report.md"
    else:
        out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(article, encoding="utf-8")
    print(f"报告已保存: {out_path}")


if __name__ == "__main__":
    main()
