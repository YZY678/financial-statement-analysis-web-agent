#!/usr/bin/env python3
"""
财报分析平台启动脚本
"""

import os
import sys
import webbrowser
from threading import Timer
from app import app

def check_environment():
    """检查运行环境"""
    print("=" * 60)
    print("财报分析平台 - 环境检查")
    print("=" * 60)
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ Python版本需要3.8或以上")
        return False
    print("✓ Python版本检查通过")
    
    # 检查必要目录
    required_dirs = ['uploads', 'reports', 'static', 'templates', 'utils']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            print(f"✓ 创建目录: {dir_name}")
        else:
            print(f"✓ 目录存在: {dir_name}")
    
    # 检查示例文件
    sample_files = [
        'data/samples/income_statement.csv',
        'data/samples/balance_sheet.csv'
    ]
    
    for file in sample_files:
        if os.path.exists(file):
            print(f"✓ 示例文件存在: {file}")
        else:
            print(f"⚠ 示例文件不存在: {file}")
    
    return True

def open_browser():
    """自动打开浏览器"""
    port = int(os.environ.get('APP_PORT', '5000'))
    webbrowser.open(f'http://localhost:{port}')

def main():
    """主函数"""
    
    # 检查环境
    if not check_environment():
        print("\\n❌ 环境检查失败，请解决以上问题后再运行。")
        sys.exit(1)
    
    print("\\n" + "=" * 60)
    print("启动财报分析平台...")
    print("=" * 60)
    
    # 显示访问信息
    print(f"📊 应用名称: 财报分析平台")
    host = os.environ.get('APP_HOST', '0.0.0.0')
    port = int(os.environ.get('APP_PORT', '5000'))
    debug_env = os.environ.get('APP_DEBUG')
    debug = app.debug if debug_env is None else debug_env.lower() in ['1', 'true', 'yes']

    print(f"🌐 访问地址: http://127.0.0.1:{port}")
    print(f"📁 上传目录: {os.path.abspath('uploads')}")
    print(f"📄 报告目录: {os.path.abspath('reports')}")
    print(f"⚙️  运行模式: {'开发模式' if debug else '生产模式'}")
    print(f"🧩 运行参数: HOST={host} PORT={port}")
    print("=" * 60)
    print("提示:")
    print("1. 按 Ctrl+C 停止应用")
    print("2. 首次使用建议上传示例文件")
    print("3. 访问 http://localhost:5000/sample/income 下载示例")
    print("=" * 60)
    
    # 延迟打开浏览器（2秒后）
    Timer(2, open_browser).start()
    
    try:
        # 启动应用
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True,
            use_reloader=debug
        )
    except KeyboardInterrupt:
        print("\\n\\n👋 应用已停止")
    except Exception as e:
        print(f"\\n❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()