"""
测试财务指标提取功能
"""
import json
from pdf_parser import parse_pdf_with_multimodal_ai
from llm_client import llm

def test_extraction():
    print("=" * 60)
    print("测试财务指标提取")
    print("=" * 60)
    
    # 1. 解析 PDF
    print("\n1. 解析 PDF...")
    pdf_path = "report.pdf"
    raw_text, tables_json = parse_pdf_with_multimodal_ai(pdf_path)
    
    print(f"   原始文本长度: {len(raw_text)} 字符")
    print(f"   表格数据长度: {len(tables_json)} 字符")
    
    # 2. 提取指标
    print("\n2. 提取财务指标...")
    keys = [
        "revenue",
        "revenue_yoy",
        "net_income",
        "net_income_yoy",
        "operating_cashflow",
    ]
    
    result = llm.extract_metrics(tables_json, keys)
    
    # 3. 打印结果
    print("\n3. 提取结果:")
    print("-" * 60)
    
    # 检查是否有 items 字段
    if "items" in result:
        print("✓ 包含 'items' 字段")
        print(f"✓ 提取到 {len(result['items'])} 个指标")
        print("\n指标详情:")
        for key, value in result['items'].items():
            print(f"\n  {key}:")
            if isinstance(value, dict):
                for k, v in value.items():
                    if k != "evidence":  # 证据太长，不打印
                        print(f"    {k}: {v}")
            else:
                print(f"    值: {value}")
    else:
        print("✗ 缺少 'items' 字段")
        print(f"✗ 顶层字段: {list(result.keys())}")
    
    # 检查元数据
    print("\n元数据:")
    print(f"  期间: {result.get('period', 'N/A')}")
    print(f"  口径: {result.get('scope', 'N/A')}")
    print(f"  单位: {result.get('unit_standard', 'N/A')}")
    print(f"  公司: {result.get('company_name', 'N/A')}")
    print(f"  代码: {result.get('ticker', 'N/A')}")
    
    # 检查顶层指标（应该从 items 提升上来）
    print("\n顶层指标（从items提升）:")
    for key in keys:
        value = result.get(key)
        if value is not None:
            print(f"  {key}: {value}")
    
    # 4. 保存完整结果
    output_path = "output/extraction_test_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存到: {output_path}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_extraction()

