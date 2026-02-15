"""
数据校验与单位统一模块（新增）
解决致命问题：口径混乱、量级错误、加总不一致
"""
import re
from typing import Any, Dict, List, Optional, Tuple


class DataValidator:
    """财报数据校验器"""
    
    def __init__(self, standard_unit: str = "亿元"):
        """
        Args:
            standard_unit: 统一展示单位（元/万元/亿元）
        """
        self.standard_unit = standard_unit
        self.unit_scale = {
            "元": 1,
            "万元": 1e4,
            "亿元": 1e8,
        }
    
    def normalize_value(self, value: Any, unit: str) -> Optional[float]:
        """
        将任意单位的值统一换算为标准单位
        
        Args:
            value: 原始数值（支持带逗号、括号、百分号、中文单位的字符串）
            unit: 原始单位（元/万元/亿元）
        
        Returns:
            换算后的数值（标准单位）
        """
        if value is None:
            return None
        
        # 如果是字符串，先清洗
        if isinstance(value, str):
            value = self._clean_numeric_string(value)
            if value is None:
                return None
        
        try:
            val = float(value)
        except (ValueError, TypeError):
            return None
        
        # 换算到"元"
        original_scale = self.unit_scale.get(unit, 1)
        value_in_yuan = val * original_scale
        
        # 再换算到标准单位
        target_scale = self.unit_scale.get(self.standard_unit, 1)
        return value_in_yuan / target_scale
    
    def _clean_numeric_string(self, s: str) -> Optional[float]:
        """
        清洗数值字符串，支持：
        - 逗号分隔符：1,706,100 → 1706100
        - 括号（负数）：(123) → -123
        - 百分号：15.89% → 15.89
        - 中文单位：85.3万元 → 85.3 * 10000
        
        Returns:
            清洗后的浮点数，失败返回None
        """
        if not s or not isinstance(s, str):
            return None
        
        s = s.strip()
        
        # 处理括号（会计负数表示法）
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        
        # 处理百分号
        if "%" in s:
            s = s.replace("%", "").strip()
            try:
                return float(s)
            except ValueError:
                return None
        
        # 处理中文单位（如"85.3万元"）
        chinese_unit_pattern = r"([-+]?[\d,]+\.?\d*)\s*(万元|亿元|元)"
        m = re.match(chinese_unit_pattern, s)
        if m:
            num_str = m.group(1).replace(",", "")
            unit_str = m.group(2)
            try:
                base_val = float(num_str)
                scale = self.unit_scale.get(unit_str, 1)
                # 返回"元"为单位的值
                return base_val * scale
            except ValueError:
                return None
        
        # 移除逗号
        s = s.replace(",", "")
        
        # 移除其他非数字字符（保留负号、小数点）
        s = re.sub(r"[^\d.+-]", "", s)
        
        try:
            return float(s)
        except ValueError:
            return None
    
    def sanity_check_revenue(self, revenue: float, company_type: str = "unknown") -> Tuple[bool, str]:
        """
        量级合理性检查：营业收入
        
        Args:
            revenue: 营业收入（已换算为标准单位）
            company_type: 公司类型（用于判断合理区间）
        
        Returns:
            (是否合理, 警告信息)
        """
        if revenue is None:
            return False, "营业收入为空"
        
        # 根据标准单位判断合理区间
        if self.standard_unit == "亿元":
            # 上市公司收入通常在 1亿-10万亿 之间
            if revenue < 0.1:
                return False, f"营业收入{revenue:.2f}亿元过小，可能是单位错误（是否应为{revenue*10000:.2f}万元？）"
            if revenue > 100000:
                return False, f"营业收入{revenue:.2f}亿元过大，可能是单位错误"
            
            # 特定公司类型检查
            if "茅台" in company_type or "白酒" in company_type:
                if revenue < 50 or revenue > 3000:
                    return False, f"白酒龙头企业收入{revenue:.2f}亿元不合理（通常在50-3000亿元）"
        
        return True, ""
    
    def validate_breakdown(self, total: float, items: Dict[str, float], 
                          tolerance: float = 0.01) -> Tuple[bool, str]:
        """
        加总校验：分项之和是否等于总数
        
        Args:
            total: 总数
            items: 分项字典 {"项目名": 数值}
            tolerance: 容差（相对误差）
        
        Returns:
            (是否一致, 详细信息)
        """
        if total is None or not items:
            return True, "无需校验"
        
        # 过滤掉None值
        valid_items = {k: v for k, v in items.items() if v is not None}
        if not valid_items:
            return True, "无有效分项"
        
        breakdown_sum = sum(valid_items.values())
        diff = abs(breakdown_sum - total)
        relative_error = diff / total if total != 0 else 0
        
        if relative_error > tolerance:
            detail = "\n".join([f"  - {k}: {v:.2f}" for k, v in valid_items.items()])
            return False, (
                f"加总不一致！\n"
                f"总数: {total:.2f}\n"
                f"分项合计: {breakdown_sum:.2f}\n"
                f"差异: {diff:.2f} ({relative_error*100:.2f}%)\n"
                f"分项明细:\n{detail}"
            )
        
        return True, f"校验通过（误差{relative_error*100:.4f}%）"
    
    def validate_percentage_change(self, value: float, field_name: str) -> Tuple[bool, str]:
        """
        百分比变化合理性检查
        
        Args:
            value: 百分比变化值
            field_name: 字段名
        
        Returns:
            (是否合理, 警告信息)
        """
        if value is None:
            return True, ""
        
        # 百分比下降不能超过100%
        if value < -100:
            return False, f"{field_name}下降{value:.2f}%不合理（下降不能超过100%）"
        
        # 百分比增长超过1000%需要特别说明
        if value > 1000:
            return False, f"{field_name}增长{value:.2f}%异常（超过10倍，需确认是否为倍数而非百分比）"
        
        return True, ""
    
    def validate_ratio(self, ratio: float, field_name: str, 
                      min_val: float = 0, max_val: float = 100) -> Tuple[bool, str]:
        """
        比率合理性检查（如毛利率、费用率）
        
        Args:
            ratio: 比率值（%）
            field_name: 字段名
            min_val: 最小合理值
            max_val: 最大合理值
        
        Returns:
            (是否合理, 警告信息)
        """
        if ratio is None:
            return True, ""
        
        if ratio < min_val or ratio > max_val:
            return False, f"{field_name}为{ratio:.2f}%，超出合理区间[{min_val}, {max_val}]"
        
        return True, ""
    
    def format_value(self, value: Optional[float], decimal: int = 2) -> str:
        """
        格式化数值输出（统一单位）
        
        Args:
            value: 数值
            decimal: 小数位数
        
        Returns:
            格式化字符串（如"170.61亿元"）
        """
        if value is None:
            return "N/A"
        return f"{value:.{decimal}f}{self.standard_unit}"
    
    def format_percentage(self, value: Optional[float], decimal: int = 2) -> str:
        """
        格式化百分比输出
        
        Args:
            value: 百分比值
            decimal: 小数位数
        
        Returns:
            格式化字符串（如"+15.89%"）
        """
        if value is None:
            return "N/A"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{decimal}f}%"
    
    def format_ppt_change(self, value: Optional[float], decimal: int = 2) -> str:
        """
        格式化百分点变化输出
        
        Args:
            value: 百分点变化值
            decimal: 小数位数
        
        Returns:
            格式化字符串（如"+1.2 ppt"）
        """
        if value is None:
            return "N/A"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{decimal}f} ppt"


def validate_financial_data(data: Dict[str, Any], validator: DataValidator) -> Dict[str, Any]:
    """
    对提取的财务数据进行全面校验
    
    Args:
        data: 原始财务数据
        validator: 数据校验器
    
    Returns:
        校验后的数据（包含warnings字段）
    """
    warnings = []
    
    # 1. 量级合理性检查
    revenue = data.get("revenue")
    company_name = data.get("company_name", "")
    if revenue is not None:
        is_valid, msg = validator.sanity_check_revenue(revenue, company_name)
        if not is_valid:
            warnings.append(f"⚠️ 收入量级异常: {msg}")
    
    # 2. 加总校验（如果有分项数据）
    if "revenue_breakdown" in data and revenue is not None:
        breakdown = data["revenue_breakdown"]
        is_valid, msg = validator.validate_breakdown(revenue, breakdown)
        if not is_valid:
            warnings.append(f"⚠️ 收入分项加总不一致: {msg}")
    
    # 3. 百分比变化合理性
    for key in ["revenue_yoy", "net_income_yoy"]:
        if key in data:
            is_valid, msg = validator.validate_percentage_change(data[key], key)
            if not is_valid:
                warnings.append(f"⚠️ {msg}")
    
    # 4. 比率合理性
    ratio_checks = [
        ("gross_margin", 0, 100),
        ("net_margin", -50, 100),
        ("sales_expense_ratio", 0, 50),
        ("admin_expense_ratio", 0, 50),
        ("rd_expense_ratio", 0, 30),
    ]
    for key, min_val, max_val in ratio_checks:
        if key in data:
            is_valid, msg = validator.validate_ratio(data[key], key, min_val, max_val)
            if not is_valid:
                warnings.append(f"⚠️ {msg}")
    
    # 5. 现金流质量检查
    cfo = data.get("operating_cashflow")
    net_income = data.get("net_income")
    if cfo is not None and net_income is not None and net_income != 0:
        cfo_to_ni = (cfo / net_income) * 100
        data["cfo_to_ni_ratio"] = cfo_to_ni
        if cfo_to_ni < 80:
            warnings.append(f"⚠️ 现金流质量偏低: CFO/净利润={cfo_to_ni:.1f}%（低于80%需关注）")
    
    # 将警告添加到数据中
    data["validation_warnings"] = warnings
    
    return data

