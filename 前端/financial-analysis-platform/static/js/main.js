/**
 * 财报分析平台 - 主要JavaScript功能
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    initFinancialAnalysis();
    initFormValidation();
    initTooltips();
    initFileUpload();
});

/**
 * 初始化财务分析相关功能
 */
function initFinancialAnalysis() {
    // 初始化图表容器大小调整
    const charts = document.querySelectorAll('.chart-content');
    if (charts.length > 0) {
        // 页面加载后调整图表大小
        setTimeout(() => {
            window.dispatchEvent(new Event('resize'));
        }, 500);
        
        // 窗口大小变化时调整图表
        window.addEventListener('resize', debounce(() => {
            window.dispatchEvent(new Event('resize'));
        }, 300));
    }
    
    // 初始化数据表格
    const tables = document.querySelectorAll('.financial-table');
    tables.forEach(table => {
        // 为数字列添加格式化
        formatFinancialTable(table);
    });
}

/**
 * 格式化财务表格
 */
function formatFinancialTable(table) {
    const rows = table.querySelectorAll('tbody tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        cells.forEach((cell, index) => {
            // 尝试解析为数字
            const text = cell.textContent.trim();
            const num = parseFloat(text.replace(/,/g, ''));
            
            if (!isNaN(num)) {
                // 格式化数字
                let formatted;
                if (Math.abs(num) >= 1000000000) {
                    formatted = (num / 1000000000).toFixed(2) + 'B';
                } else if (Math.abs(num) >= 1000000) {
                    formatted = (num / 1000000).toFixed(2) + 'M';
                } else if (Math.abs(num) >= 1000) {
                    formatted = (num / 1000).toFixed(2) + 'K';
                } else {
                    formatted = num.toLocaleString('zh-CN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    });
                }
                
                cell.textContent = formatted;
                
                // 根据数值添加颜色
                if (num < 0) {
                    cell.classList.add('text-danger');
                } else if (num > 0) {
                    cell.classList.add('text-success');
                }
            }
        });
    });
}

/**
 * 初始化表单验证
 */
function initFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                highlightInvalidFields(form);
            }
            
            form.classList.add('was-validated');
        }, false);
        
        // 实时验证
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                validateField(this);
            });
            
            input.addEventListener('input', function() {
                clearFieldValidation(this);
            });
        });
    });
}

/**
 * 验证单个字段
 */
function validateField(field) {
    const isValid = field.checkValidity();
    const feedback = field.nextElementSibling;
    
    if (!isValid) {
        field.classList.add('is-invalid');
        field.classList.remove('is-valid');
        
        if (feedback && feedback.classList.contains('invalid-feedback')) {
            feedback.textContent = field.validationMessage;
        }
    } else {
        field.classList.add('is-valid');
        field.classList.remove('is-invalid');
    }
    
    return isValid;
}

/**
 * 清除字段验证状态
 */
function clearFieldValidation(field) {
    field.classList.remove('is-invalid', 'is-valid');
}

/**
 * 高亮无效字段
 */
function highlightInvalidFields(form) {
    const invalidFields = form.querySelectorAll(':invalid');
    
    invalidFields.forEach(field => {
        field.classList.add('is-invalid');
        
        const feedback = field.nextElementSibling;
        if (feedback && feedback.classList.contains('invalid-feedback')) {
            feedback.textContent = field.validationMessage;
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'invalid-feedback';
            errorDiv.textContent = field.validationMessage;
            field.parentNode.insertBefore(errorDiv, field.nextSibling);
        }
    });
}

/**
 * 初始化工具提示
 */
function initTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(
        tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl)
    );
}

/**
 * 初始化文件上传
 */
function initFileUpload() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // 验证文件类型
                const validTypes = ['csv', 'xlsx', 'xls', 'png', 'jpg', 'jpeg', 'docx', 'pdf'];
                const fileExt = file.name.split('.').pop().toLowerCase();
                
                if (!validTypes.includes(fileExt)) {
                    alert('只支持CSV、Excel、图片、DOCX和PDF格式的文件');
                    input.value = '';
                    return;
                }
                
                // 验证文件大小（10MB）
                if (file.size > 10 * 1024 * 1024) {
                    alert('文件大小不能超过10MB');
                    input.value = '';
                    return;
                }
                
                // 显示文件信息
                const container = input.closest('.file-upload-container');
                if (container) {
                    const preview = container.querySelector('.file-preview');
                    const fileName = container.querySelector('.file-name');
                    const fileSize = container.querySelector('.file-size');
                    
                    if (preview) preview.style.display = 'block';
                    if (fileName) fileName.textContent = file.name;
                    if (fileSize) fileSize.textContent = formatFileSize(file.size);
                }
            }
        });
    });
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 防抖函数
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数
 */
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * 显示加载动画
 */
function showLoading(selector, message = '加载中...') {
    const element = document.querySelector(selector);
    if (element) {
        element.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <p class="mt-2 text-muted">${message}</p>
            </div>
        `;
    }
}

/**
 * 隐藏加载动画
 */
function hideLoading(selector) {
    const element = document.querySelector(selector);
    if (element) {
        element.innerHTML = '';
    }
}

/**
 * 复制文本到剪贴板
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(
        () => showToast('已复制到剪贴板', 'success'),
        () => showToast('复制失败', 'error')
    );
}

/**
 * 显示Toast通知
 */
function showToast(message, type = 'info') {
    // 创建Toast容器（如果不存在）
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }
    
    // 创建Toast
    const toastId = 'toast-' + Date.now();
    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">系统提示</strong>
                <small>刚刚</small>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', toastHTML);
    
    const toastEl = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    
    // 移除DOM元素
    toastEl.addEventListener('hidden.bs.toast', function() {
        toastEl.remove();
    });
}

// 全局暴露函数
window.FinancialAnalysis = {
    formatFileSize,
    copyToClipboard,
    showLoading,
    hideLoading,
    showToast
};