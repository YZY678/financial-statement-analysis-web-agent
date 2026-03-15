#!/bin/bash
# 财报分析平台部署脚本

echo "开始部署财报分析平台..."

# 1. 停止现有服务
echo "停止现有服务..."
pkill -f gunicorn || true

# 2. 创建目录结构
echo "创建目录结构..."
mkdir -p logs uploads reports static/css static/js static/images

# 3. 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 4. 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 5. 启动应用
echo "启动应用..."
nohup gunicorn -c gunicorn_config.py app:app > logs/app.log 2>&1 &

# 6. 检查状态
sleep 3
if pgrep -f gunicorn > /dev/null; then
    echo "✅ 部署成功！应用正在运行。"
    echo "🌐 访问地址: http://服务器IP:8000"
    echo "📊 查看日志: tail -f logs/app.log"
else
    echo "❌ 部署失败，请检查日志。"
    tail -n 20 logs/app.log
fi