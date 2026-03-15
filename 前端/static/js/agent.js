const state = {
    sessionId: null,
    supportedFormats: [".csv", ".xlsx", ".xls", ".pdf"],
    chartTypes: [
        "income_trend",
        "profit_composition",
        "balance_sheet",
        "revenue_comparison",
        "expense_breakdown",
    ],
};

const chartLabelMap = {
    income_trend: "收入趋势图",
    profit_composition: "利润构成图",
    balance_sheet: "资产负债图",
    revenue_comparison: "收入对比图",
    expense_breakdown: "费用分解图",
};

function logMessage(text, type = "system") {
    const log = document.getElementById("agentLog");
    if (!log) return;
    const p = document.createElement("p");
    p.className = type === "user" ? "log-user" : "log-system";
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
}

function addDownloadButton(url, label = "下载图表") {
    const log = document.getElementById("agentLog");
    if (!log) return;
    const button = document.createElement("a");
    button.className = "btn btn-sm btn-outline-light mt-2";
    button.href = url;
    button.target = "_blank";
    button.textContent = label;
    log.appendChild(button);
    log.scrollTop = log.scrollHeight;
}

function addChartActionButtons(chart = {}) {
    const log = document.getElementById("agentLog");
    if (!log) return;

    const wrapper = document.createElement("div");
    wrapper.className = "mt-2 mb-2";

    if (chart.view_url) {
        const view = document.createElement("a");
        view.className = "btn btn-sm btn-outline-info me-2";
        view.href = chart.view_url;
        view.target = "_blank";
        view.textContent = "🖼️ 查看图表";
        wrapper.appendChild(view);
    }

    if (chart.download_url) {
        const download = document.createElement("a");
        download.className = "btn btn-sm btn-outline-light me-2";
        download.href = chart.download_url;
        download.target = "_blank";
        download.textContent = "⬇️ 下载图表";
        wrapper.appendChild(download);
    }

    if (chart.charts_center_url) {
        const center = document.createElement("a");
        center.className = "btn btn-sm btn-outline-warning";
        center.href = chart.charts_center_url;
        center.target = "_blank";
        center.textContent = "📁 图表中心";
        wrapper.appendChild(center);
    }

    if (wrapper.children.length) {
        log.appendChild(wrapper);
        log.scrollTop = log.scrollHeight;
    }
}

function setSessionStatus(text, isReady) {
    const status = document.getElementById("sessionStatus");
    if (status) {
        status.textContent = text;
        status.className = `badge ${isReady ? "bg-success" : "bg-secondary"}`;
    }
}

function toggleControls(enabled) {
    document.getElementById("uploadSingleBtn").disabled = !enabled;
    document.getElementById("uploadMultiBtn").disabled = !enabled;
    document.getElementById("cleanDataBtn").disabled = !enabled;
    document.getElementById("chartTypeSelect").disabled = !enabled;
    document.getElementById("chartTitleInput").disabled = !enabled;
    document.getElementById("generateChartBtn").disabled = !enabled;
    document.getElementById("compareChartBtn").disabled = !enabled;
    document.getElementById("compareTableBtn").disabled = !enabled;
    document.getElementById("analyzeBtn").disabled = !enabled;
    document.getElementById("agentInput").disabled = !enabled;
    document.getElementById("sendAgentBtn").disabled = !enabled;
    document.getElementById("resetSessionBtn").disabled = !enabled;
    document.getElementById("getConfigBtn").disabled = !enabled;
    document.getElementById("getLogsBtn").disabled = !enabled;
    document.getElementById("exportJsonBtn").disabled = !enabled;
    document.getElementById("exportHtmlBtn").disabled = !enabled;
    document.getElementById("exportTxtBtn").disabled = !enabled;
    document.getElementById("exportZipBtn").disabled = !enabled;
    document.getElementById("quickSmartBtn").disabled = !enabled;
    document.getElementById("quickRegenBtn").disabled = !enabled;
    document.getElementById("quickStatusBtn").disabled = !enabled;
}

function getFileExtension(filename = "") {
    const index = filename.lastIndexOf(".");
    if (index < 0) return "";
    return filename.slice(index).toLowerCase();
}

function validateSelectedFiles(fileList) {
    if (!fileList || !fileList.length) return true;
    const allowed = new Set(state.supportedFormats.map((item) => item.toLowerCase()));
    const invalid = Array.from(fileList).find((file) => !allowed.has(getFileExtension(file.name)));
    if (invalid) {
        logMessage(`不支持的文件格式: ${invalid.name}。支持: ${Array.from(allowed).join("/")}`);
        return false;
    }
    return true;
}

function renderChartTypeOptions(chartTypes = []) {
    const select = document.getElementById("chartTypeSelect");
    if (!select) return;
    const values = chartTypes.length ? chartTypes : state.chartTypes;
    select.innerHTML = values
        .map((item) => `<option value="${item}">${chartLabelMap[item] || item}</option>`)
        .join("");
}

async function executeTool(toolName, toolParams = {}) {
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_name: toolName, tool_params: toolParams }),
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.error || "工具执行失败");
    }
    return data;
}

async function createSession() {
    const res = await fetch("/api/agent/sessions", { method: "POST" });
    const data = await res.json();
    state.sessionId = data.session_id;
    logMessage(`会话已创建: ${state.sessionId}`);

    try {
        const configRes = await fetch("/api/agent/config");
        const configData = await configRes.json();
        if (configRes.ok) {
            if (Array.isArray(configData.supported_formats) && configData.supported_formats.length) {
                state.supportedFormats = configData.supported_formats.map((item) => item.toLowerCase());
            }
            if (Array.isArray(configData.chart_types) && configData.chart_types.length) {
                state.chartTypes = configData.chart_types;
            }
            renderChartTypeOptions(state.chartTypes);
        }
    } catch (error) {
        logMessage(`读取配置失败: ${error.message}`);
    }

    setSessionStatus("会话就绪", true);
    toggleControls(true);
    renderFiles(null, []);
    renderCompareTable([]);
}

async function uploadSingleFile() {
    const input = document.getElementById("singleFileInput");
    if (!input.files.length) return;
    if (!validateSelectedFiles(input.files)) return;
    const formData = new FormData();
    formData.append("file", input.files[0]);
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/upload`, {
        method: "POST",
        body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
        logMessage(`上传失败: ${data.error}`, "system");
        return;
    }
    logMessage(`已上传: ${data.session.file_name}`);
    renderFiles(data.session);
}

async function uploadMultipleFiles() {
    const input = document.getElementById("multiFileInput");
    if (!input.files.length) return;
    if (!validateSelectedFiles(input.files)) return;
    const formData = new FormData();
    Array.from(input.files).forEach((file) => formData.append("files", file));
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/upload-multiple`, {
        method: "POST",
        body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
        logMessage(`批量上传失败: ${data.error}`, "system");
        return;
    }
    logMessage(`已加载 ${data.loaded.length} 个文件`);
    renderFiles(data.session, data.loaded);
}

async function cleanData() {
    try {
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/clean`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "清洗失败");
        }
        logMessage("清洗完成，数据已就绪");
        if (data?.session) {
            renderFiles(data.session);
        }
    } catch (error) {
        logMessage(`清洗失败: ${error.message}`);
    }
}

async function generateChart() {
    const chartType = document.getElementById("chartTypeSelect").value;
    const titleInput = document.getElementById("chartTitleInput").value.trim();
    const chartTitle = titleInput || "财经数据分析";
    try {
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/chart`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                chart_type: chartType,
                title: chartTitle,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "图表生成失败");
        }
        if (data?.chart?.download_url) {
            logMessage(`图表已生成: ${data.chart.title || chartType}`);
            addChartActionButtons(data.chart);
            if (Array.isArray(data.charts) && data.charts.length > 1) {
                logMessage(`自动生成图表数量: ${data.charts.length}`);
            }
            return;
        }
        logMessage("图表生成完成");
    } catch (error) {
        logMessage(`图表生成失败: ${error.message}`);
    }
}

async function analyzeHealth() {
    try {
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "分析失败");
        }
        if (data.analysis) {
            logMessage(`分析结果: ${JSON.stringify(data.analysis)}`);
        } else {
            logMessage(data.response || "分析完成");
        }
    } catch (error) {
        logMessage(`分析失败: ${error.message}`);
    }
}

async function compareChart() {
    try {
        const dataPayload = { title: "多文件对比" };
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/compare/chart`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(dataPayload),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "对比图生成失败");
        }
        if (data.charts?.length) {
            data.charts.forEach((chart) => {
                logMessage(`对比图已生成: ${chart.download_url}`);
                addChartActionButtons(chart);
            });
            return;
        }
        logMessage(`对比图已生成: ${data.chart.download_url}`);
        addChartActionButtons(data.chart);
    } catch (error) {
        logMessage(`对比图失败: ${error.message}`);
    }
}

async function compareTable() {
    try {
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/compare/table`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "对比表失败");
        }
        logMessage(`对比表已生成，共 ${data.table.length} 行`);
        renderCompareTable(data.table);
    } catch (error) {
        logMessage(`对比表失败: ${error.message}`);
    }
}

async function fetchConfig() {
    const res = await fetch("/api/agent/config");
    const data = await res.json();
    if (!res.ok) {
        logMessage(`获取配置失败: ${data.error || "未知错误"}`);
        return;
    }
    if (Array.isArray(data.supported_formats) && data.supported_formats.length) {
        state.supportedFormats = data.supported_formats.map((item) => item.toLowerCase());
    }
    if (Array.isArray(data.chart_types) && data.chart_types.length) {
        state.chartTypes = data.chart_types;
        renderChartTypeOptions(state.chartTypes);
    }
    logMessage(`工具配置: ${JSON.stringify(data)}`);
}

async function fetchLogs() {
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/logs`);
    const data = await res.json();
    if (!res.ok) {
        logMessage(`获取日志失败: ${data.error || "未知错误"}`);
        return;
    }
    logMessage(`日志条数: ${data.logs.length}`);
}

function exportSession(format) {
    const url = `/api/agent/sessions/${state.sessionId}/export?format=${encodeURIComponent(format)}`;
    addDownloadButton(url, `下载 ${format.toUpperCase()}`);
}

async function fetchSessionStatus() {
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/status`);
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.error || "获取状态失败");
    }
    logMessage(`状态: ${JSON.stringify(data)}`);
}

async function runQuickCommand(command) {
    logMessage(command, "user");
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: command }),
    });
    const data = await res.json();
    if (!res.ok) {
        logMessage(`处理失败: ${data.error || "未知错误"}`);
        return;
    }
    if (data.charts?.length) {
        data.charts.forEach((chart) => addChartActionButtons(chart));
    } else if (data.chart) {
        addChartActionButtons(data.chart);
    }
    if (data.message) {
        logMessage(data.message);
    }
    if (data.suggestions?.length) {
        logMessage(`建议: ${data.suggestions.join("；")}`);
    }
}

async function sendMessage() {
    const input = document.getElementById("agentInput");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    logMessage(message, "user");
    const res = await fetch(`/api/agent/sessions/${state.sessionId}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) {
        logMessage(`处理失败: ${data.error || "未知错误"}`);
        return;
    }
    if (data.charts?.length) {
        data.charts.forEach((chart) => {
            logMessage(`图表生成成功: ${chart.download_url}`);
            addChartActionButtons(chart);
        });
    } else if (data.chart?.download_url) {
        logMessage(`图表生成成功: ${data.chart.download_url}`);
        addChartActionButtons(data.chart);
    } else if (data.analysis) {
        logMessage(`分析结果: ${JSON.stringify(data.analysis)}`);
    } else if (data.session) {
        logMessage("会话状态已更新");
    } else {
        logMessage(data.message || "已处理");
    }
    if (data.suggestions?.length) {
        logMessage(`建议: ${data.suggestions.join("；")}`);
    }
}

async function resetSession() {
    try {
        const res = await fetch(`/api/agent/sessions/${state.sessionId}/reset`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reset_type: "soft" }),
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "重置失败");
        }
        logMessage("会话已重置");
        renderCompareTable([]);
        renderFiles(null, []);
    } catch (error) {
        logMessage(`重置失败: ${error.message}`);
    }
}

function renderFiles(session, loaded = []) {
    const list = document.getElementById("fileList");
    if (!list) return;
    list.innerHTML = "";

    const fileNames = new Set();
    if (session?.files?.length) {
        session.files.forEach((item) => {
            if (item.file_name) {
                fileNames.add(item.file_name);
            }
        });
    }
    if (loaded.length) {
        loaded.forEach((item) => {
            if (item.file) {
                fileNames.add(item.file);
            }
        });
    }

    if (fileNames.size > 0) {
        Array.from(fileNames).forEach((name) => {
            const span = document.createElement("span");
            span.className = "file-tag";
            span.textContent = name;
            list.appendChild(span);
        });
        return;
    }

    if (session?.file_name) {
        const span = document.createElement("span");
        span.className = "file-tag";
        span.textContent = session.file_name;
        list.appendChild(span);
    }
}

function renderCompareTable(rows = []) {
    const container = document.getElementById("compareTable");
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = "";
        return;
    }
    const headers = Object.keys(rows[0]);
    const headHtml = headers.map((h) => `<th>${h}</th>`).join("");
    const bodyHtml = rows
        .slice(0, 20)
        .map((row) => {
            const cols = headers.map((h) => `<td>${row[h] ?? ""}</td>`).join("");
            return `<tr>${cols}</tr>`;
        })
        .join("");
    container.innerHTML = `
        <table>
            <thead><tr>${headHtml}</tr></thead>
            <tbody>${bodyHtml}</tbody>
        </table>
    `;
}

function bindAgentEvents() {
    document.getElementById("createSessionBtn").addEventListener("click", createSession);
    document.getElementById("resetSessionBtn").addEventListener("click", resetSession);
    document.getElementById("uploadSingleBtn").addEventListener("click", uploadSingleFile);
    document.getElementById("uploadMultiBtn").addEventListener("click", uploadMultipleFiles);
    document.getElementById("cleanDataBtn").addEventListener("click", cleanData);
    document.getElementById("generateChartBtn").addEventListener("click", generateChart);
    document.getElementById("compareChartBtn").addEventListener("click", compareChart);
    document.getElementById("compareTableBtn").addEventListener("click", compareTable);
    document.getElementById("analyzeBtn").addEventListener("click", analyzeHealth);
    document.getElementById("sendAgentBtn").addEventListener("click", sendMessage);
    document.getElementById("getConfigBtn").addEventListener("click", fetchConfig);
    document.getElementById("getLogsBtn").addEventListener("click", fetchLogs);
    document.getElementById("exportJsonBtn").addEventListener("click", () => exportSession("json"));
    document.getElementById("exportHtmlBtn").addEventListener("click", () => exportSession("html"));
    document.getElementById("exportTxtBtn").addEventListener("click", () => exportSession("txt"));
    document.getElementById("exportZipBtn").addEventListener("click", () => exportSession("zip"));
    document.getElementById("quickSmartBtn").addEventListener("click", () => runQuickCommand("请分析数据并生成最合适的图表"));
    document.getElementById("quickRegenBtn").addEventListener("click", () => runQuickCommand("重新生成图表"));
    document.getElementById("quickStatusBtn").addEventListener("click", async () => {
        try {
            await fetchSessionStatus();
        } catch (error) {
            logMessage(`状态获取失败: ${error.message}`);
        }
    });

    document.getElementById("agentInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });

    document.getElementById("singleFileInput").addEventListener("change", (event) => {
        document.getElementById("uploadSingleBtn").disabled = !event.target.files.length;
    });

    document.getElementById("multiFileInput").addEventListener("change", (event) => {
        document.getElementById("uploadMultiBtn").disabled = !event.target.files.length;
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindAgentEvents();
    renderChartTypeOptions(state.chartTypes);
    toggleControls(false);
    setSessionStatus("未创建会话", false);
    logMessage("请先创建会话，然后上传文件或输入指令。", "system");
});
