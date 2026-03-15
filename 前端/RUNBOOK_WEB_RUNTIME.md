# Web 正确运行方式（已验证）

本文记录当前财报分析平台的稳定运行流程，适用于本仓库：`/root/web/financial-analysis-platform`。

## 1. 一键稳定启动（推荐）

在仓库根目录执行：

```bash
bash scripts/stabilize_runtime.sh
```

脚本会自动完成：
- 清理重复 Web 进程
- 检查并拉起 Ollama (`127.0.0.1:11434`)
- 用生产参数启动 Web
- 执行健康检查

成功后访问：
- `http://127.0.0.1:5000`

日志文件：
- Web: `logs/web_runtime.log`
- Ollama: `logs/ollama_runtime.log`

## 2. 手工启动（备用）

```bash
cd /root/web/financial-analysis-platform
pkill -f "python3 run.py" || true
APP_ENV=production APP_DEBUG=0 SECRET_KEY="${SECRET_KEY:-financial-analysis-secret-2024}" \
UPSTREAM_REPORT_TIMEOUT_SECONDS=1200 nohup python3 run.py > logs/web_runtime.log 2>&1 &
```

然后检查：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/upload
curl -s http://127.0.0.1:11434/api/tags >/dev/null
```

预期：`200 / 200 / ollama tags 可访问`。

## 3. 任务运行判定（是否真在分析）

查看任务状态：

```bash
curl -s http://127.0.0.1:5000/api/task/<task_id>/status
```

判断标准：
- `processing + 50%`（PDF）不等于卡死；这是上游引擎阶段。
- 若对应上游进程存在且有 CPU 占用，说明在真实分析。
- 若超过超时上限（20 分钟）且无上游进程，系统会自动收敛为 `failed`，不再无限显示处理中。

## 4. 已修复并需保持的关键配置

1. CSRF 密钥兜底
- `production` 模式必须有 `SECRET_KEY`，否则 `/upload` 会 500。
- 当前已做双兜底：配置层 + app 启动层。

2. 任务持久化序列化
- 结果中可能含 `Timestamp` 等对象。
- 当前已在 `task_store` 增加 JSON 默认序列化，避免 `Object of type Timestamp is not JSON serializable`。

3. 状态落库
- 任务在完成/失败/取消时会强制落库，避免页面与真实进程状态脱节。

4. 超时与自愈
- `UPSTREAM_REPORT_TIMEOUT_SECONDS` 当前上限 1200 秒（20 分钟）。
- 超时且进程消失时会自动改为失败状态。

## 5. 报告页正确展示逻辑

在线报告页 `GET /report/<task_id>` 当前应包含两层：
- 结构化财务分析（由后端报告提取并可视化）
- 后端原始报告正文（原样保留）

如果原报告正文里图表相对路径失效，当前通过 `/report_asset/<task_id>/<path>` 路由提供资源映射。

## 6. 文件格式支持（当前验证结论）

- `csv`: 可分析（已验证）
- `docx`: 可分析（已验证）
- `pdf`: 可分析（上游阶段可能耗时较长）
- `png/jpg/jpeg`: 支持上传与 OCR 解析；若图片无可识别文本，会失败（这是数据质量问题，不是链路故障）

## 7. 常用运维命令

查看最近日志：

```bash
tail -n 200 logs/web_runtime.log
```

查看任务表：

```bash
sqlite3 -header -column data/task_store.db "SELECT id,filename,status,progress,start_time,end_time,error FROM tasks ORDER BY rowid DESC LIMIT 20;"
```

停止/删除任务（接口）：
- 停止：`POST /api/task/<task_id>/stop`
- 删除：`DELETE /api/task/<task_id>`（进行中任务需先停止）
