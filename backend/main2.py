"""
财经数据可视化Agent - 智能体模式界面
修复：精简快速指令，支持多文件上传
版本：2.0
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 导入Agent（与 main.py 连接的可视化程序：agent2 + brain + tools + role）
try:
    from agent2 import FinanceAgent
    AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 无法导入Agent模块: {e}")
    AGENT_AVAILABLE = False


class ToolTip:
    """简单的工具提示类"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.tip_window = None

    def enter(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tip_window, text=self.text,
                         justify=tk.LEFT, background="#ffffe0",
                         relief=tk.SOLID, borderwidth=1,
                         font=("微软雅黑", 8))
        label.pack(ipadx=1)

    def leave(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class FinanceAgentGUI:
    """财经Agent图形用户界面 - 智能体模式"""

    def __init__(self, root):
        self.root = root
        self.root.title("💰 财经数据可视化智能体")
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)

        # 居中窗口
        self._center_window()

        # 创建界面组件
        self._create_widgets()

        # 状态变量
        self.agent = None
        self.current_files = []  # 改为列表，存储多个文件路径
        self.is_processing = False

        # 显示欢迎信息
        self._show_welcome()

        # 确保输出目录存在
        self._ensure_directories()

        # 延迟初始化Agent
        self.root.after(100, self._init_agent)

    def _center_window(self):
        """窗口居中显示"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def _create_widgets(self):
        """创建界面组件 - 简化版，符合智能体逻辑"""
        # 主容器
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 左侧面板 - 对话区
        left_panel = self._create_left_panel(main_container)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # 右侧面板 - 控制区
        right_panel = self._create_right_panel(main_container)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_left_panel(self, parent):
        """创建左侧对话面板"""
        frame = ttk.Frame(parent)

        # 标题
        title_frame = ttk.Frame(frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = tk.Label(
            title_frame,
            text="💰 财经数据可视化智能体",
            font=("微软雅黑", 18, "bold"),
            fg="#2c3e50"
        )
        title_label.pack(side=tk.LEFT)

        # 状态指示器
        self.status_indicator = tk.Label(
            title_frame,
            text="●",
            font=("Arial", 16, "bold"),
            fg="#27ae60"
        )
        self.status_indicator.pack(side=tk.RIGHT, padx=(0, 10))

        # 对话显示区域
        self.chat_text = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            font=("微软雅黑", 10),
            bg="white",
            height=25
        )
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # 配置标签
        self.chat_text.tag_config("user", foreground="#2980b9", font=("微软雅黑", 10, "bold"))
        self.chat_text.tag_config("agent", foreground="#27ae60")
        self.chat_text.tag_config("system", foreground="#7f8c8d")
        self.chat_text.tag_config("success", foreground="#27ae60")
        self.chat_text.tag_config("warning", foreground="#f39c12")
        self.chat_text.tag_config("error", foreground="#e74c3c")

        self.chat_text.config(state=tk.DISABLED)

        # 输入和控制区
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))

        # 输入框
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(
            control_frame,
            textvariable=self.input_var,
            font=("微软雅黑", 11)
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.input_entry.bind("<Return>", lambda e: self.send_message())

        # 发送按钮
        self.send_btn = ttk.Button(
            control_frame,
            text="发送",
            command=self.send_message,
            width=8
        )
        self.send_btn.pack(side=tk.RIGHT)

        return frame

    def _create_right_panel(self, parent):
        """创建右侧控制面板 - 简化版，只有文件操作和快速指令"""
        frame = ttk.Frame(parent, width=220)

        # 文件操作部分
        file_frame = ttk.LabelFrame(frame, text="📁 文件操作", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 15))

        # 上传按钮 - 支持多文件选择
        self.upload_btn = ttk.Button(
            file_frame,
            text="选择财经数据文件（可多选）",
            command=self.upload_file,
            width=20
        )
        self.upload_btn.pack(pady=5)

        # 文件信息显示
        self.file_label = ttk.Label(
            file_frame,
            text="当前文件: 无",
            font=("微软雅黑", 9),
            foreground="#7f8c8d"
        )
        self.file_label.pack(pady=5)

        # 快速指令部分 - 精简为3个核心操作
        cmd_frame = ttk.LabelFrame(frame, text="⚡ 快捷操作", padding="10")
        cmd_frame.pack(fill=tk.X, pady=(0, 15))

        # 核心操作指令
        commands = [
            ("📈 智能生成图表", "请分析数据并生成最合适的图表"),
            ("🔄 重新生成", "重新生成图表"),
            ("📄 系统状态", "查看当前状态")
        ]

        for btn_text, command in commands:
            btn = ttk.Button(
                cmd_frame,
                text=btn_text,
                command=lambda cmd=command: self.use_quick_command(cmd),
                width=20
            )
            btn.pack(pady=3)

        # 系统操作部分
        sys_frame = ttk.LabelFrame(frame, text="⚙️ 系统操作", padding="10")
        sys_frame.pack(fill=tk.X)

        # 重置按钮
        reset_btn = ttk.Button(
            sys_frame,
            text="🔄 重置智能体",
            command=self.reset_agent,
            width=20
        )
        reset_btn.pack(pady=5)

        # 导出会话按钮
        export_btn = ttk.Button(
            sys_frame,
            text="💾 导出会话",
            command=self.export_session,
            width=20
        )
        export_btn.pack(pady=5)

        return frame

    def _ensure_directories(self):
        """确保输出目录存在"""
        directories = ["./output/charts", "./output/reports"]
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def _init_agent(self):
        """初始化Agent"""
        if AGENT_AVAILABLE:
            try:
                self.agent = FinanceAgent("财经可视化智能体")
                self.add_message("system", "✅ 智能体初始化成功，随时为您服务")
                self._update_status("ready")
            except Exception as e:
                self.add_message("error", f"❌ 智能体初始化失败: {str(e)}")
                self.agent = None
                self._update_status("error")
        else:
            self.add_message("error", "❌ 智能体模块不可用")
            self._update_status("error")

    def _update_status(self, status):
        """更新状态指示器"""
        colors = {
            "ready": "#27ae60",      # 绿色
            "processing": "#f39c12", # 黄色
            "error": "#e74c3c"       # 红色
        }
        self.status_indicator.config(fg=colors.get(status, "#95a5a6"))

    def _show_welcome(self):
        """显示欢迎信息"""
        welcome_text = """🤖 欢迎使用财经数据可视化智能体

    🌟 我是您的专属财经分析助手，具备智能决策能力：
    • 我能理解您的自然语言需求
    • 我能自动推断最适合的图表类型
    • 我能智能规划分析工作流
    • 我能一次生成多种类型的图表
    • 我能提供专业的财经分析建议

    💡 智能交互示例：
    • "分析一下销售数据" - 我会自动生成趋势图
    • "对比不同产品收入" - 我会生成对比图
    • "看看费用构成" - 我会生成构成图
    • "评估资产负债状况" - 我会生成资产图

    📁 如何使用：
    1. 点击右侧「选择财经数据文件（可多选）」按钮上传数据
       - 按住Ctrl键可选择多个文件进行对比分析
       - 支持CSV、Excel格式
    2. 在下方输入您的需求，或点击快捷操作
    3. 我会自动分析您的意图并执行最佳操作

    🔄 智能图表生成：
    • 根据数据特征，我可能会生成1-3种不同类型的图表
    • 每种图表都会有清晰的标题、坐标轴、图例
    • 图表文件名会反映数据和图表类型

    当前状态：初始化中..."""

        self.add_message("system", welcome_text)

    def add_message(self, sender, message, tag=None):
        """添加消息到聊天框"""
        self.chat_text.config(state=tk.NORMAL)

        timestamp = datetime.now().strftime("%H:%M:%S")

        if sender == "user":
            prefix = f"[{timestamp}] 👤 您: "
            sender_tag = "user"
        elif sender == "agent":
            prefix = f"[{timestamp}] 🤖 智能体: "
            sender_tag = "agent"
        else:
            prefix = f"[{timestamp}] ⚙️ 系统: "
            sender_tag = "system"

        self.chat_text.insert(tk.END, prefix, sender_tag)

        if tag:
            self.chat_text.insert(tk.END, message + "\n\n", tag)
        else:
            self.chat_text.insert(tk.END, message + "\n\n", sender_tag)

        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def upload_file(self):
        """上传文件 - 真正的多文件选择功能"""
        if self.is_processing:
            return

        file_types = [
            ("财经数据文件", "*.csv;*.xlsx;*.xls"),
            ("所有文件", "*.*")
        ]

        # 🆕 使用askopenfilenames（带s）支持真正的多选
        file_paths = filedialog.askopenfilenames(
            title="选择财经数据文件（按住Ctrl键可多选，Shift键连续选择）",
            filetypes=file_types
        )

        if not file_paths:  # 用户取消了选择
            return

        # 🆕 将选择的文件路径转换为列表
        self.current_files = list(file_paths)

        if len(self.current_files) == 1:
            # 单个文件
            file_name = os.path.basename(self.current_files[0])
            self.file_label.config(text=f"文件: {file_name}")
            self.add_message("system", f"📁 已选择文件: {file_name}")

            # 加载这个文件
            self._load_single_file(self.current_files[0])

        elif len(self.current_files) > 1:
            # 多个文件
            file_names = [os.path.basename(f) for f in self.current_files]
            self.file_label.config(text=f"已选{len(self.current_files)}个文件")

            # 显示所有文件名
            file_list = "\n".join([f"  📄 {name}" for name in file_names])
            self.add_message("system",
                             f"📁 已选择{len(self.current_files)}个文件:\n{file_list}"
                             )

            # 加载所有文件
            self._load_multiple_files(self.current_files)

    def _load_single_file(self, file_path):
                """加载单个文件"""
                if not self.agent:
                    self.add_message("error", "❌ Agent未初始化")
                    return

                file_name = os.path.basename(file_path)
                self.add_message("user", f"加载文件: {file_name}")

                # 处理文件加载
                result = self.agent.process(f"加载文件: {file_path}")

                if result.get("status") == "success":
                    self.add_message("agent", result.get("response", ""))
                else:
                    self.add_message("error", result.get("response", ""))

    def _load_multiple_files(self, file_paths):
                """加载多个文件"""
                if not self.agent:
                    self.add_message("error", "❌ Agent未初始化")
                    return

                if len(file_paths) == 0:
                    return

                # 加载第一个文件作为主文件
                primary_file = file_paths[0]
                primary_name = os.path.basename(primary_file)

                self.add_message("user", f"加载主文件: {primary_name}")

                result = self.agent.process(f"加载文件: {primary_file}")

                if result.get("status") == "success":
                    self.add_message("agent", result.get("response", ""))

                    # 记录其他文件
                    if len(file_paths) > 1:
                        other_files = file_paths[1:]
                        other_names = [os.path.basename(f) for f in other_files]

                        self.add_message("system",
                                         f"💡 已加载{len(file_paths)}个文件，可用于对比分析。\n"
                                         f"主文件: {primary_name}\n"
                                         f"对比文件: {', '.join(other_names)}\n\n"
                                         f"📊 您现在可以：\n"
                                         f"• 输入'对比分析这些数据'\n"
                                         f"• 输入'生成对比图表'\n"
                                         f"• 点击'智能生成图表'按钮"
                                         )
                else:
                    self.add_message("error", result.get("response", ""))

    def use_quick_command(self, command):
        """使用快速指令"""
        if self.is_processing or not command:
            return

        # 检查多文件上下文
        if hasattr(self, 'current_files') and len(self.current_files) > 1:
            if command == "请分析数据并生成最合适的图表":
                # 智能生成图表时，如果有多文件，自动添加对比说明
                file_count = len(self.current_files)
                file_names = [os.path.basename(f) for f in self.current_files[:3]]
                display_names = ', '.join(file_names)
                if file_count > 3:
                    display_names += f" 等{file_count}个文件"

                self.add_message("user", f"智能分析{file_count}个文件的数据: {display_names}")
                command = f"对比分析以下{file_count}个文件: {display_names}"
            else:
                self.add_message("user", command)
        else:
            self.add_message("user", command)

        self.process_request(command)

    def send_message(self):
        """发送消息"""
        user_input = self.input_var.get().strip()

        if not user_input or self.is_processing:
            return

        if not self.agent:
            self.add_message("error", "智能体未就绪，请稍候...")
            return

        # 检查多文件上下文
        if hasattr(self, 'current_files') and len(self.current_files) > 1:
            if "对比" in user_input or "比较" in user_input or "多个" in user_input:
                # 用户明确要求对比
                file_count = len(self.current_files)
                file_names = [os.path.basename(f) for f in self.current_files]
                self.add_message("user",
                                 f"对比分析{file_count}个文件的数据: {', '.join(file_names)}"
                                 )
                user_input = f"对比分析{file_count}个文件: {', '.join(file_names)}"

        # 显示用户消息
        self.add_message("user", user_input)
        self.input_var.set("")

        # 处理请求
        self.process_request(user_input)

    def process_request(self, user_input):
        """处理请求"""
        if not self.agent:
            self.add_message("error", "智能体未就绪，请稍候...")
            return

        # 更新状态
        self.is_processing = True
        self._update_status("processing")
        self._set_buttons_state(tk.DISABLED)

        # 后台处理
        thread = threading.Thread(
            target=self._process_request_thread,
            args=(user_input,),
            daemon=True
        )
        thread.start()

    def _process_request_thread(self, user_input):
        """后台处理线程"""
        try:
            result = self.agent.process(user_input)
            self.root.after(0, lambda: self._show_result(result))
        except Exception as e:
            self.root.after(0, lambda: self._show_error(str(e)))

    def _show_result(self, result):
        """显示处理结果"""
        self.is_processing = False
        self._update_status("ready")
        self._set_buttons_state(tk.NORMAL)

        status = result.get("status")
        response = result.get("response", "")

        if status == "success":
            self.add_message("agent", response)

            # 显示图表信息
            chart_info = result.get("chart_info")
            if chart_info and "charts" in chart_info:
                charts = chart_info["charts"]
                for chart in charts:
                    chart_path = chart.get("path")
                    chart_type = chart.get("type", "未知")
                    chart_title = chart.get("title", "")

                    if chart_path and os.path.exists(chart_path):
                        # 添加打开图表按钮
                        self.root.after(0, lambda path=chart_path, ctype=chart_type, ctitle=chart_title:
                        self._add_chart_button(path, ctype, ctitle))

            # 显示建议
            if result.get("suggestions"):
                suggestions = "\n💡 建议:\n" + "\n".join(f"  • {s}" for s in result.get("suggestions", []))
                self.add_message("agent", suggestions)

        elif status == "error":
            self.add_message("error", response)

    def _show_error(self, error_msg):
        """显示错误"""
        self.is_processing = False
        self._update_status("error")
        self._set_buttons_state(tk.NORMAL)

        self.add_message("error", f"❌ 处理失败: {error_msg}")

    def _set_buttons_state(self, state):
        """设置按钮状态"""
        self.send_btn.config(state=state)
        self.upload_btn.config(state=state)

    def _add_chart_button(self, chart_path, chart_type, chart_title):
        """添加打开图表按钮 - 明确功能区别"""
        if not os.path.exists(chart_path):
            # 🆕 如果文件不存在，提供有用的错误信息
            self.add_message("error", f"图表文件不存在，可能保存失败: {os.path.basename(chart_path)}")
            return

        self.chat_text.config(state=tk.NORMAL)

        # 图表类型名称映射
        chart_type_names = {
            "income_trend": "📈 趋势图",
            "profit_composition": "🥧 构成图",
            "balance_sheet": "📄 资产图",
            "revenue_comparison": "📊 对比图",
            "expense_breakdown": "💰 费用图"
        }

        chart_type_display = chart_type_names.get(chart_type, "📈 图表")
        file_name = os.path.basename(chart_path)

        # 创建按钮框架
        button_frame = tk.Frame(self.chat_text, bg="white")

        # 图表信息标签
        info_label = tk.Label(
            button_frame,
            text=f"{chart_type_display}: {chart_title}",
            font=("微软雅黑", 9),
            bg="white"
        )
        info_label.pack(side=tk.LEFT, padx=(0, 10))

        # 🆕 修改按钮文本，明确功能区别
        # 按钮1：直接打开图表图片
        open_btn = ttk.Button(
            button_frame,
            text="🖼️ 查看图表",  # 🆕 改为"查看图表"
            command=lambda: self._open_file(chart_path),
            width=10
        )
        open_btn.pack(side=tk.LEFT, padx=2)

        # 🆕 添加工具提示说明 - 修复ToolTip类引用
        try:
            # 尝试使用ToolTip类，如果存在的话
            if hasattr(self, 'ToolTip') or 'ToolTip' in globals():
                ToolTip(open_btn, "直接打开图表图片文件")
            else:
                # 如果ToolTip类不存在，创建一个简单的替代方案
                self._add_tooltip(open_btn, "直接打开图表图片文件")
        except (NameError, AttributeError):
            # 如果ToolTip类未定义，静默失败
            pass

        # 按钮2：打开图表所在的文件夹
        dir_btn = ttk.Button(
            button_frame,
            text="📁 打开文件夹",  # 🆕 明确是打开文件夹
            command=lambda: self._open_file_directory(chart_path),
            width=10
        )
        dir_btn.pack(side=tk.LEFT, padx=2)

        # 🆕 添加工具提示说明 - 修复ToolTip类引用
        try:
            # 尝试使用ToolTip类，如果存在的话
            if hasattr(self, 'ToolTip') or 'ToolTip' in globals():
                ToolTip(dir_btn, "打开图表文件所在的文件夹，方便管理多个图表")
            else:
                # 如果ToolTip类不存在，创建一个简单的替代方案
                self._add_tooltip(dir_btn, "打开图表文件所在的文件夹，方便管理多个图表")
        except (NameError, AttributeError):
            # 如果ToolTip类未定义，静默失败
            pass

        # 插入按钮
        self.chat_text.window_create(tk.END, window=button_frame)
        self.chat_text.insert(tk.END, "\n")

        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    # 添加一个简单的工具提示替代方法，以防ToolTip类不存在
    def _add_tooltip(self, widget, text):
        """简单的工具提示替代方案"""

        def on_enter(event):
            try:
                # 创建简单的工具提示窗口
                x, y, _, _ = widget.bbox("insert")
                x += widget.winfo_rootx() + 25
                y += widget.winfo_rooty() + 20

                # 创建工具提示窗口
                tooltip = tk.Toplevel(widget)
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{x}+{y}")

                label = tk.Label(tooltip, text=text,
                                 justify=tk.LEFT, background="#ffffe0",
                                 relief=tk.SOLID, borderwidth=1,
                                 font=("微软雅黑", 8))
                label.pack(ipadx=1)

                # 保存工具提示引用，以便离开时销毁
                widget.tooltip_window = tooltip
            except Exception:
                pass

        def on_leave(event):
            if hasattr(widget, 'tooltip_window') and widget.tooltip_window:
                try:
                    widget.tooltip_window.destroy()
                    widget.tooltip_window = None
                except Exception:
                    pass

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    def _open_file(self, file_path):
        """打开文件 - 修复版本"""
        try:
            if not file_path or not os.path.exists(file_path):
                # 🆕 尝试多种可能路径
                filename = os.path.basename(file_path)
                possible_paths = [
                    file_path,
                    os.path.join("./charts", filename),
                    os.path.join(os.getcwd(), "charts", filename),
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts", filename)
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        file_path = path
                        print(f"✅ 找到文件: {file_path}")
                        break

                if not os.path.exists(file_path):
                    self.add_message("error", f"文件不存在: {filename}")
                    print(f"❌ 尝试了以下路径但未找到文件:")
                    for path in possible_paths:
                        print(f"   - {path}")
                    return

            # 🆕 记录实际打开的文件路径
            print(f"📂 正在打开文件: {file_path}")

            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "dar32":
                import subprocess
                subprocess.run(["open", file_path])
            else:
                import subprocess
                subprocess.run(["xdg-open", file_path])

        except Exception as e:
            error_msg = str(e)
            self.add_message("error", f"打开失败: {error_msg}")
            print(f"❌ 打开文件异常: {error_msg}")

    def _open_file_directory(self, file_path):
        """打开文件所在目录 - 修复版本"""
        try:
            if not file_path or not os.path.exists(file_path):
                # 🆕 尝试查找文件
                filename = os.path.basename(file_path)
                possible_paths = [
                    file_path,
                    os.path.join("./charts", filename),
                    os.path.join(os.getcwd(), "charts", filename)
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        file_path = path
                        break

            if os.path.exists(file_path):
                directory = os.path.dirname(file_path)
            else:
                # 🆕 如果文件不存在，尝试打开charts目录
                possible_dirs = [
                    "./charts",
                    os.path.join(os.getcwd(), "charts"),
                    os.path.dirname(os.path.abspath(__file__)) + "/charts"
                ]

                for dir_path in possible_dirs:
                    if os.path.exists(dir_path):
                        directory = dir_path
                        print(f"📁 使用备选目录: {directory}")
                        break
                else:
                    self.add_message("error", "找不到图表目录，请检查是否已生成图表")
                    return

            print(f"📁 正在打开目录: {directory}")

            if sys.platform == "win32":
                os.startfile(directory)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", directory])
            else:
                import subprocess
                subprocess.run(["xdg-open", directory])

        except Exception as e:
            error_msg = str(e)
            self.add_message("error", f"打开目录失败: {error_msg}")
            print(f"❌ 打开目录异常: {error_msg}")

    def reset_agent(self):
        """重置智能体"""
        if messagebox.askyesno("确认", "确定要重置智能体状态吗？"):
            if self.agent:
                result = self.agent.reset("hard")
                self.current_files = []  # 清空文件列表
                self.file_label.config(text="当前文件: 无")
                self.add_message("system", "🔄 智能体已重置，可以开始新的会话")
            else:
                self.add_message("error", "智能体未初始化")

    def export_session(self):
        """导出会话"""
        if self.agent:
            result = self.agent.export_session_report()
            if result.get("status") == "success":
                self.add_message("system", f"💾 {result.get('response')}")
            else:
                self.add_message("error", f"导出失败: {result.get('response')}")
        else:
            self.add_message("error", "智能体未初始化")


def main():
    """主函数"""
    root = tk.Tk()

    # 创建界面
    app = FinanceAgentGUI(root)

    # 设置窗口关闭事件
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出程序吗？"):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()


if __name__ == "__main__":
    main()