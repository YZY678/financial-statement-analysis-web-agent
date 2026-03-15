/**
 * 图表相关功能
 */

class FinancialChart {
    /**
     * 创建财务趋势图
     * @param {string} containerId - 容器ID
     * @param {Array} periods - 期间数组
     * @param {Object} data - 数据对象
     * @param {Object} options - 配置选项
     */
    static createTrendChart(containerId, periods, data, options = {}) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return null;
        
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += new Intl.NumberFormat('zh-CN', {
                                    style: 'currency',
                                    currency: 'CNY'
                                }).format(context.parsed.y);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: options.beginAtZero || false,
                    ticks: {
                        callback: function(value) {
                            if (value >= 1000000000) {
                                return (value / 1000000000).toFixed(1) + 'B';
                            } else if (value >= 1000000) {
                                return (value / 1000000).toFixed(1) + 'M';
                            } else if (value >= 1000) {
                                return (value / 1000).toFixed(1) + 'K';
                            }
                            return value;
                        }
                    }
                }
            }
        };
        
        // 合并自定义选项
        Object.assign(chartOptions, options);
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: periods,
                datasets: data
            },
            options: chartOptions
        });
    }
    
    /**
     * 创建财务构成图
     * @param {string} containerId - 容器ID
     * @param {Array} labels - 标签数组
     * @param {Array} values - 数值数组
     * @param {Object} options - 配置选项
     */
    static createCompositionChart(containerId, labels, values, options = {}) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return null;
        
        const backgroundColors = [
            '#2E86AB', '#68C3D4', '#A8D5BA', '#F9C784', '#F76C5E',
            '#6C757D', '#20C997', '#FFC107', '#DC3545', '#6610F2'
        ];
        
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value.toLocaleString()} (${percentage}%)`;
                        }
                    }
                }
            }
        };
        
        // 合并自定义选项
        Object.assign(chartOptions, options);
        
        return new Chart(ctx, {
            type: options.chartType || 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: backgroundColors.slice(0, labels.length),
                    borderWidth: 1
                }]
            },
            options: chartOptions
        });
    }
    
    /**
     * 创建财务比率图
     * @param {string} containerId - 容器ID
     * @param {Array} periods - 期间数组
     * @param {Object} ratios - 比率数据
     * @param {Object} options - 配置选项
     */
    static createRatioChart(containerId, periods, ratios, options = {}) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return null;
        
        const datasets = [];
        const colors = ['#2E86AB', '#28a745', '#ffc107', '#dc3545', '#6c757d'];
        
        let colorIndex = 0;
        for (const [key, values] of Object.entries(ratios)) {
            datasets.push({
                label: key,
                data: values,
                borderColor: colors[colorIndex % colors.length],
                backgroundColor: colors[colorIndex % colors.length] + '20',
                tension: 0.1,
                fill: options.fill || false
            });
            colorIndex++;
        }
        
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                y: {
                    beginAtZero: options.beginAtZero || true,
                    ticks: {
                        callback: function(value) {
                            if (options.percentage) {
                                return value + '%';
                            }
                            return value;
                        }
                    }
                }
            }
        };
        
        // 合并自定义选项
        Object.assign(chartOptions, options);
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: periods,
                datasets: datasets
            },
            options: chartOptions
        });
    }
    
    /**
     * 创建对比柱状图
     * @param {string} containerId - 容器ID
     * @param {Array} labels - 标签数组
     * @param {Object} data - 对比数据
     * @param {Object} options - 配置选项
     */
    static createComparisonChart(containerId, labels, data, options = {}) {
        const ctx = document.getElementById(containerId);
        if (!ctx) return null;
        
        const datasets = [];
        const companies = Object.keys(data);
        const colors = ['#2E86AB', '#F76C5E', '#A8D5BA', '#F9C784'];
        
        companies.forEach((company, index) => {
            datasets.push({
                label: company,
                data: data[company],
                backgroundColor: colors[index % colors.length],
                borderColor: colors[index % colors.length],
                borderWidth: 1
            });
        });
        
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            if (value >= 1000000000) {
                                return (value / 1000000000).toFixed(1) + 'B';
                            } else if (value >= 1000000) {
                                return (value / 1000000).toFixed(1) + 'M';
                            } else if (value >= 1000) {
                                return (value / 1000).toFixed(1) + 'K';
                            }
                            return value;
                        }
                    }
                }
            }
        };
        
        // 合并自定义选项
        Object.assign(chartOptions, options);
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: chartOptions
        });
    }
}

/**
 * 保存图表为图片
 * @param {Chart} chart - Chart.js实例
 * @param {string} filename - 文件名
 */
function saveChartAsImage(chart, filename = 'chart.png') {
    if (!chart) return;
    
    const link = document.createElement('a');
    link.download = filename;
    link.href = chart.toBase64Image();
    link.click();
}

/**
 * 导出图表数据
 * @param {Chart} chart - Chart.js实例
 * @param {string} filename - 文件名
 */
function exportChartData(chart, filename = 'chart_data.csv') {
    if (!chart) return;
    
    const data = chart.data;
    let csvContent = '';
    
    // 添加标题行
    const headers = ['Period', ...data.datasets.map(dataset => dataset.label)];
    csvContent += headers.join(',') + '\\n';
    
    // 添加数据行
    data.labels.forEach((label, index) => {
        const row = [label];
        data.datasets.forEach(dataset => {
            row.push(dataset.data[index] || '');
        });
        csvContent += row.join(',') + '\\n';
    });
    
    // 创建下载链接
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

// 全局暴露
window.FinancialChart = FinancialChart;
window.saveChartAsImage = saveChartAsImage;
window.exportChartData = exportChartData;s