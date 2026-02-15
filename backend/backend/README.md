# 财报分析系统 - 专业级（V2.2 稳定性修复版）

## ⚠️ 重要更新（V2.2）

本版本修复了**3个稳定性问题**，提升系统鲁棒性。

### V2.2 修复的问题

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | 指标提取范围太小（12000字符） | 🟡 数据缺失 | ✅ 已修复 |
| 2 | matplotlib硬依赖导致崩溃 | 🟡 程序崩溃 | ✅ 已修复 |
| 3 | Windows反斜杠路径不兼容 | 🟢 显示问题 | ✅ 已修复 |

### V2.1 修复的致命问题

| # | 问题 | 严重程度 | 状态 |
|---|------|----------|------|
| 1 | 单位混用（亿元/万元/元混用） | 🔴 致命 | ✅ 已修复 |
| 2 | 量级错误（7亿vs700亿） | 🔴 致命 | ✅ 已修复 |
| 3 | 加总不一致（分项≠总数） | 🔴 致命 | ✅ 已修复 |
| 4 | 数学错误（下降3798%） | 🔴 致命 | ✅ 已修复 |
| 5 | 三张表边界混乱 | 🟡 严重 | ✅ 已修复 |
| 6 | 风险提示写成业绩总结 | 🟡 严重 | ✅ 已修复 |

详细修复方案见 [`CRITICAL_FIXES.md`](CRITICAL_FIXES.md)

---

## 核心特性

### 1. 单位强制统一 ✅
- 全文统一使用一个单位（默认：亿元）
- 自动换算所有数值
- 禁止混用不同单位

### 2. 数据自动校验 ✅
- 量级合理性检查（收入是否在合理区间）
- 加总一致性校验（分项之和=总数）
- 百分比合理性检查（下降不超过100%）
- 比率合理性检查（毛利率0-100%）

### 3. 三张表严格边界 ✅
- 利润表：只写收入/成本/费用/利润
- 资产负债表：只写资产/负债/权益
- 现金流量表：只写经营/投资/筹资现金流

### 4. 风险提示可验证 ✅
- 格式："如果发生X，会影响Y"
- 给出可观察指标（批价、库存、动销、汇率）
- 不写成业绩总结

### 5. 稳定性增强（V2.2新增）✅
- 扩大指标提取范围（12000→30000字符）
- matplotlib改为可选依赖，失败时优雅降级
- 使用相对路径，兼容所有Markdown渲染器

---

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件：
```bash
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL_NAME=qwen2.5:7b
```

### 运行

```bash
python main.py report.pdf
```

### 查看结果

```bash
# 报告
cat output/financial_report.md

# 图表
start output/charts/financial_chart.png
```

---

## 输出示例

### 报告头部（强制元数据声明）

```markdown
# 贵州茅台 2024年度 财报解读

本报告基于2024年度合并报表，全文金额统一使用亿元。

⚠️ 数据校验警告（如有）
- ⚠️ 收入量级异常: 营业收入7.40亿元过小
- ⚠️ 收入分项加总不一致: 差异46.70 (27.37%)

请人工复核上述警告项。
```

### 利润表分析（严格边界）

```markdown
## 一、利润表分析

**一、营业收入**
- 总收入：170.61亿元，同比+15.89%（绝对增加23.45亿元）
- 分产品：茅台酒145.90亿元（占比85.5%，同比+15.28%）
- 驱动因素：量（+8%）、价（+6%）、结构（高端占比+1.2 ppt）

**二、毛利率**
- 综合毛利率：92.01%，同比-0.15 ppt
- 原因：成本增速17.30% vs 收入增速15.89%

**三、期间费用**
- 销售费用率：12.5%（同比+1.2 ppt）
- 管理费用率：5.8%（同比-0.5 ppt）
- 研发费用率：2.3%（同比+0.3 ppt）

**四、净利润**
- 归母净利润：85.30亿元，同比+16.20%
- 净利率：50.0%，同比+0.1 ppt
- ROE：32.5%
```

### 风险提示（可触发格式）

```markdown
## 五、风险提示

1. **量价风险**：若茅台酒批发价格回落超过10%，将影响经销商打款意愿，导致预收款下降15-20%。
   需跟踪：批价走势、渠道库存天数、终端动销数据。

2. **成本压力**：原材料价格若持续上涨，每上涨5%将压缩毛利率约0.8 ppt。
   需跟踪：粮食价格指数、人工成本增速。

3. **应收质量**：应收账款占收入比例若继续提升至15%以上，回款周期延长将增加坏账风险。
   需跟踪：应收账款周转天数、账龄结构、主要客户资信状况。

4. **政策风险**：白酒行业面临反腐、限价等政策不确定性，若政策收紧将影响高端消费10-15%。
   需跟踪：政策动向、公务消费数据、高端餐饮景气度。

5. **海外风险**：海外收入占比30%，汇率每波动1%影响利润约0.5亿元。
   需跟踪：汇率走势、关税政策变化、海外渠道建设进度。
```

---

## 文件结构

```
h:/backend/
├── main.py                    # 入口文件
├── report_generator.py        # 报告生成（集成校验）
├── llm_client.py             # LLM客户端（强化约束）
├── data_validator.py         # 数据校验（新增）⭐
├── code_runner.py            # 图表生成
├── pdf_parser.py             # PDF解析
├── historical_data.py        # 历史数据
├── config.py                 # 配置管理
├── requirements.txt          # 依赖列表
├── README.md                 # 本文件
├── CRITICAL_FIXES.md         # 致命问题修复报告 ⭐
├── CHANGELOG.md              # 改进对比
├── USAGE.md                  # 使用指南
├── SUMMARY.md                # 完成总结
└── QUICKREF.md               # 快速参考
```

---

## 核心改进（V2.1）

### 1. 新增数据校验模块（`data_validator.py`）

```python
from data_validator import DataValidator, validate_financial_data

# 创建校验器（统一单位：亿元）
validator = DataValidator(standard_unit="亿元")

# 单位统一换算
unified_val = validator.normalize_value(1706100, "万元")  # → 170.61

# 量级合理性检查
is_valid, msg = validator.sanity_check_revenue(7.40, "贵州茅台")
# → False, "营业收入7.40亿元过小，可能是单位错误"

# 加总校验
is_valid, msg = validator.validate_breakdown(
    total=170.61,
    items={"国内": 165.42, "国外": 51.89}
)
# → False, "加总不一致！差异46.70 (27.37%)"

# 格式化输出
validator.format_value(170.61)  # → "170.61亿元"
validator.format_percentage(15.89)  # → "+15.89%"
validator.format_ppt_change(-0.15)  # → "-0.15 ppt"
```

### 2. 强化Prompt约束（`llm_client.py`）

```python
system = """
【致命错误必须避免】：
1. 单位混用：全文必须统一使用元数据中声明的单位
2. 数学错误：百分比下降不能超过-100%
3. 三张表边界：利润表只写收入/成本/费用/利润
4. 风险提示：不要写成"业绩总结"
"""
```

### 3. 集成校验流程（`report_generator.py`）

```python
# 提取数据
financial_data = llm.extract_metrics(tables_json, keys=[...])

# 统一单位
validator = DataValidator(standard_unit="亿元")
for key, val_obj in items.items():
    unified_val = validator.normalize_value(
        val_obj["value_original"], 
        val_obj["unit_original"]
    )
    financial_data[key] = unified_val

# 全面校验
financial_data = validate_financial_data(financial_data, validator)

# 展示警告
warnings = financial_data.get("validation_warnings", [])
if warnings:
    print("=== 数据校验警告 ===")
    for w in warnings:
        print(w)
```

---

## 配置项

### 基础配置（`.env`）

```bash
# API配置
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL_NAME=qwen2.5:7b

# 质量控制
REQUIRE_METADATA=1          # 强制元数据
VALIDATE_BREAKDOWN=1        # 校验加总
MIN_INDICATORS=5            # 最少指标数
ENABLE_EVIDENCE_TRACE=1     # 证据溯源
```

---

## 验证清单

### 自动检查（系统完成）

- ✅ 单位统一性
- ✅ 量级合理性
- ✅ 加总一致性
- ✅ 百分比合理性
- ✅ 比率合理性
- ✅ 现金流质量

### 人工复核（使用者完成）

- [ ] 元数据正确（期间/口径/单位）
- [ ] 关键数据准确（收入/净利润/现金流）
- [ ] 分项数据一致（能加回总数）
- [ ] 三张表边界清晰
- [ ] 风险提示实用

---

## 常见问题

### Q1: 出现"数据校验警告"怎么办？

**A**: 必须人工复核：
1. 对照原始财报，确认数值是否正确
2. 检查单位是否换算错误
3. 确认分项口径是否一致

### Q2: 如何修改统一单位？

**A**: 修改 `report_generator.py`：
```python
validator = DataValidator(standard_unit="万元")  # 改为万元
```

### Q3: 如何关闭某些校验？

**A**: 修改 `.env`：
```bash
VALIDATE_BREAKDOWN=0  # 关闭加总校验
```

---

## 适用场景

✅ 卖方研究报告（可直接使用）  
✅ 投资决策参考（数据可复核）  
✅ 财务尽调材料（证据完整）  
✅ 内部经营分析（结构清晰）  
✅ 监管报送材料（口径统一）  

---

## 技术架构

```
PDF → 解析 → 提取 → 校验 → 分析 → 报告
       ↓      ↓      ↓      ↓      ↓
   pdf_parser llm  validator llm  markdown
              ↓              ↓
          tables_json    warnings
```

---

## 文档导航

- **快速上手** → [`QUICKREF.md`](QUICKREF.md)（1页速查）
- **致命问题修复** → [`CRITICAL_FIXES.md`](CRITICAL_FIXES.md)（本次重点）⭐
- **详细教程** → [`USAGE.md`](USAGE.md)（完整指南）
- **改进对比** → [`CHANGELOG.md`](CHANGELOG.md)（前后对比）
- **完成总结** → [`SUMMARY.md`](SUMMARY.md)（V2.0总结）

---

## 版本历史

- **V2.2** (2026-02-12) - 稳定性修复 ⭐
  - 扩大指标提取范围（避免截断）
  - matplotlib改为可选依赖（优雅降级）
  - 修复图片路径（相对路径+正斜杠）

- **V2.1** (2026-02-12) - 修复6个致命问题 ⭐
  - 单位强制统一
  - 数据自动校验
  - 三张表严格边界
  - 风险提示可验证

- **V2.0** (2026-02-12) - 专业级重写
  - 16个核心指标
  - 三张表思维
  - 证据溯源
  - 多维度图表

- **V1.0** - 初始版本
  - 基础PDF解析
  - 简单指标提取
  - 通用分析模板

---

**版本**：V2.2 (稳定性修复版)  
**状态**：✅ 生产就绪  
**更新日期**：2026-02-12

**重要提示**：首次使用请务必阅读 [`CRITICAL_FIXES.md`](CRITICAL_FIXES.md)，了解修复的致命问题。
