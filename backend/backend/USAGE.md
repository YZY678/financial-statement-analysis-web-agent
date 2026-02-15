# 使用示例

## 快速开始

### 1. 环境准备

```bash
# 克隆或进入项目目录
cd /h:/backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（创建 .env 文件）
echo "OPENAI_API_KEY=your_api_key_here" > .env
echo "OPENAI_BASE_URL=http://localhost:11434/v1" >> .env
echo "LOCAL_MODEL_NAME=qwen2.5:7b" >> .env
```

### 2. 运行分析

```bash
# 基本用法
python main.py report.pdf

# 指定输出路径
python main.py report.pdf output/custom_report.md

# 查看帮助
python main.py
```

### 3. 查看结果

```bash
# 报告文件
cat output/financial_report.md

# 图表文件
start output/charts/financial_chart.png  # Windows
open output/charts/financial_chart.png   # macOS
```

---

## 输出示例

### 报告结构预览

```markdown
# 贵州茅台 2024年度 财报解读

本报告基于2024年度合并报表，金额单位：亿元，除非特别说明。

---

## 一、利润表分析

**一、营业收入**
- 总收入：170.61亿元，同比+15.89%（+23.45亿元）
- 拆分：
  * 茅台酒：145.90亿元（占比85.5%，+15.28%）
  * 系列酒：24.71亿元（占比14.5%，+19.65%）
- 驱动：量（+8%）、价（+6%）、结构（高端占比+1.2 ppt）

**二、毛利率**
- 综合毛利率：92.01%，同比-0.15 ppt
- 原因：成本上涨17.30%（原材料+16.4%，人工+19.5%）快于收入增速15.89%

**三、期间费用**
- 销售费用率：12.5%（+1.2 ppt），主要是市场推广增加3.2亿元
- 管理费用率：5.8%（-0.5 ppt），费用控制效果显现
- 研发费用率：2.3%（+0.3 ppt），研发投入同比增长18%

**四、净利润**
- 归母净利润：85.3亿元，同比+16.2%
- 净利率：50.0%，同比+0.1 ppt
- ROE：32.5%（如有数据）

---

## 二、资产负债表分析

**一、营运资本**
- 应收账款：20.5亿元，占收入12.0%（去年8.0%）
- 存货：45.2亿元，周转天数96天（去年89天）
- 合同负债/预收：38.6亿元，同比+12.5%（反映渠道打款意愿强）

**二、资本结构**
- 资产负债率：28.5%
- 货币资金：125.3亿元
- 有息负债：15.2亿元

---

## 三、现金流量表分析

**一、经营现金流**
- CFO：95.2亿元，同比+38.85%
- CFO/净利润：111.6%（>100%为优，<80%需关注）
- 差异原因：应收+2.5亿元，存货+3.8亿元，预收+8.5亿元

**二、投资与筹资**
- 资本开支：12.5亿元（主要投向产能扩建）
- 分红：68.0亿元，分红率79.7%

---

## 四、核心财务图表

![财务指标可视化](H:\backend\output\charts\financial_chart.png)

---

## 五、风险提示

1. **量价风险**：茅台酒批发价格波动较大，需持续跟踪渠道库存和终端动销数据。
   若批价回落超过10%，将影响经销商打款意愿。

2. **成本压力**：原材料成本同比上涨16.4%，若持续将压缩毛利率约1.5个百分点。
   需关注粮食价格走势和人工成本上涨压力。

3. **应收质量**：应收账款占收入比例从8%提升至12%，回款周期延长约15天。
   需关注经销商资金状况和坏账风险。

4. **政策风险**：白酒行业面临反腐、限价等政策不确定性，需关注政策变化对
   高端消费的影响。

5. **海外风险**：海外收入占比提升至30%，面临汇率波动、关税政策、渠道建设
   成本等风险。美元兑人民币汇率每波动1%，影响利润约0.3亿元。

---

**数据溯源**：本报告所有数据均提取自财报原文，关键指标已标注证据来源。如需复核，请参考财报附注。

**免责声明**：本报告仅供参考，不构成投资建议。
```

---

## 高级用法

### 自定义配置

编辑 `config.py` 或设置环境变量：

```bash
# 修改统一单位（默认：元）
export DEFAULT_SCALE="亿元"

# 关闭分项加总校验（如果财报格式特殊）
export VALIDATE_BREAKDOWN="0"

# 降低最少指标数量要求
export MIN_INDICATORS="3"

# 关闭证据溯源（加快速度）
export ENABLE_EVIDENCE_TRACE="0"
```

### 批量处理

```bash
# 批量处理多个财报
for pdf in reports/*.pdf; do
    python main.py "$pdf" "output/$(basename $pdf .pdf).md"
done
```

### 集成到工作流

```python
# 在Python代码中调用
from report_generator import generate_financial_report

# 生成报告
report_md = generate_financial_report("report.pdf")

# 进一步处理
with open("output/report.md", "w", encoding="utf-8") as f:
    f.write(report_md)

# 发送邮件、上传到系统等
send_email(report_md)
upload_to_system(report_md)
```

---

## 常见问题

### Q1: 提取的数据不准确怎么办？

**A**: 检查以下几点：
1. PDF质量：确保PDF是文字版，不是扫描件
2. 表格结构：复杂表格（跨页、合并单元格）可能需要人工校验
3. 模型能力：尝试更强的模型（如GPT-4）
4. 调试输出：查看 `=== 原始抽取结果 ===` 部分，确认提取是否正确

### Q2: 图表显示中文乱码？

**A**: 确保系统安装了中文字体：
```python
# code_runner.py 已配置
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
```

如果仍有问题，手动安装字体或修改配置。

### Q3: 某些指标提取不到？

**A**: 可能原因：
1. 财报中确实没有该指标
2. 表格格式特殊，LLM未识别
3. 指标名称不匹配（如"归属于母公司股东的净利润"vs"归母净利润"）

解决方案：
- 查看 `validation` 字段，确认哪些指标为 null
- 调整 `extract_metrics()` 的 prompt，增加指标别名
- 人工补充缺失数据

### Q4: 生成速度慢？

**A**: 优化建议：
1. 使用本地模型（Ollama + Qwen）代替API调用
2. 减少提取指标数量（修改 `keys` 列表）
3. 关闭证据溯源（`ENABLE_EVIDENCE_TRACE=0`）
4. 缩小PDF范围（只提取关键页面）

### Q5: 如何验证报告准确性？

**A**: 三步验证法：
1. **元数据检查**：期间、口径、单位是否正确
2. **数值校验**：分项加总是否等于总数（查看 `validation` 字段）
3. **证据溯源**：关键数据是否有 `evidence` 字段，能否在原文找到

---

## 最佳实践

### 1. 首次使用

```bash
# 用样本财报测试
python main.py sample_report.pdf

# 检查输出质量
cat output/financial_report.md

# 对比原始财报，验证准确性
```

### 2. 生产环境

```bash
# 启用所有质量控制
export REQUIRE_METADATA="1"
export VALIDATE_BREAKDOWN="1"
export ENABLE_EVIDENCE_TRACE="1"

# 运行
python main.py production_report.pdf

# 人工复核关键指标
```

### 3. 快速预览

```bash
# 关闭部分功能，加快速度
export MIN_INDICATORS="3"
export ENABLE_EVIDENCE_TRACE="0"

# 运行
python main.py quick_preview.pdf
```

---

## 技术支持

遇到问题？
1. 查看 `README.md` 了解系统架构
2. 查看 `CHANGELOG.md` 了解改进细节
3. 检查日志输出，定位问题
4. 提交 Issue 或联系开发者

---

**版本**：2.0  
**更新日期**：2026-02-12

