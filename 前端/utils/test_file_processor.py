#!/usr/bin/env python3
"""
测试文件处理器
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from file_processor import FileProcessor
import pandas as pd

def test_detection():
    """测试编码检测功能"""
    print("=" * 50)
    print("测试文件处理器")
    print("=" * 50)
    
    # 创建测试数据
    test_data = {
        '期间': ['2020Q1', '2020Q2', '2020Q3', '2020Q4'],
        '营业收入': [1000000, 1200000, 1300000, 1400000],
        '净利润': [200000, 240000, 260000, 280000],
        '营业成本': [600000, 720000, 780000, 840000]
    }
    
    df = pd.DataFrame(test_data)
    
    print("测试detect_file_type:")
    report_type = FileProcessor.detect_file_type(df)
    print(f"检测结果: {report_type}")
    
    print("\\n测试extract_financial_periods:")
    periods = FileProcessor.extract_financial_periods(df)
    print(f"期间: {periods}")
    
    print("\\n测试clean_financial_data:")
    df_cleaned = FileProcessor.clean_financial_data(df)
    print(f"清洗后数据:")
    print(df_cleaned.head())
    
    print("\\n测试validate_financial_data:")
    try:
        FileProcessor.validate_financial_data(df_cleaned, report_type)
        print("数据验证通过")
    except Exception as e:
        print(f"数据验证失败: {e}")
    
    print("\\n测试编码检测:")
    # 创建一个测试文件
    test_file = "test_sample.csv"
    df.to_csv(test_file, index=False, encoding='utf-8')
    
    try:
        encoding = FileProcessor.detect_file_encoding(test_file)
        print(f"文件编码检测: {encoding}")
        
        # 读取文件
        df_read, report_type_read = FileProcessor.read_financial_file(test_file, "test_sample.csv")
        print(f"成功读取文件，形状: {df_read.shape}")
        print(f"检测到的报表类型: {report_type_read}")
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        # 清理测试文件
        if os.path.exists(test_file):
            os.remove(test_file)
    
    print("\\n✓ 所有测试完成")

if __name__ == '__main__':
    test_detection()