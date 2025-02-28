// K6 HTML Reporter
export function htmlReport(data, options = {}) {
    return `
        <!DOCTYPE html>
        <html lang="zh-CN">
            <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>K6 性能测试报告</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: #f5f5f5;
                    }
                    .container {
                        max-width: 1200px;
                        margin: 0 auto;
                        background: white;
                        padding: 20px;
                        border-radius: 8px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    .header {
                        text-align: center;
                        margin-bottom: 30px;
                        padding-bottom: 20px;
                        border-bottom: 1px solid #eee;
                    }
                    .metrics {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 20px;
                        margin-bottom: 30px;
                    }
                    .metric-card {
                        background: #f8f9fa;
                        padding: 20px;
                        border-radius: 6px;
                        text-align: center;
                    }
                    .metric-value {
                        font-size: 24px;
                        font-weight: bold;
                        color: #2c3e50;
                    }
                    .metric-label {
                        color: #666;
                        margin-top: 8px;
                    }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 20px;
                    }
                    th, td {
                        padding: 12px;
                        text-align: left;
                        border-bottom: 1px solid #ddd;
                    }
                    th {
                        background: #f8f9fa;
                    }
                    .chart {
                        margin: 20px 0;
                        height: 400px;
                    }
                </style>
                <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>K6 性能测试报告</h1>
                        <p>测试时间: ${new Date().toLocaleString()}</p>
                    </div>
                    
                    <div class="metrics">
                        <div class="metric-card">
                            <div class="metric-value">${data.metrics.iterations}</div>
                            <div class="metric-label">总请求数</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${data.metrics.vus}</div>
                            <div class="metric-label">并发用户数</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${data.metrics.http_req_duration.avg.toFixed(2)}ms</div>
                            <div class="metric-label">平均响应时间</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${(data.metrics.http_req_failed.rate * 100).toFixed(2)}%</div>
                            <div class="metric-label">错误率</div>
                        </div>
                    </div>

                    <div id="responseTimeChart" class="chart"></div>
                    <div id="requestsChart" class="chart"></div>

                    <script>
                        // 响应时间图表
                        const responseTimeChart = echarts.init(document.getElementById('responseTimeChart'));
                        responseTimeChart.setOption({
                            title: { text: '响应时间分布' },
                            tooltip: { trigger: 'axis' },
                            xAxis: { type: 'category', data: ['最小值', '平均值', '中位数', '90%', '95%', '最大值'] },
                            yAxis: { type: 'value', name: '毫秒' },
                            series: [{
                                data: [
                                    ${data.metrics.http_req_duration.min.toFixed(2)},
                                    ${data.metrics.http_req_duration.avg.toFixed(2)},
                                    ${data.metrics.http_req_duration.med.toFixed(2)},
                                    ${data.metrics.http_req_duration.p90.toFixed(2)},
                                    ${data.metrics.http_req_duration.p95.toFixed(2)},
                                    ${data.metrics.http_req_duration.max.toFixed(2)}
                                ],
                                type: 'bar'
                            }]
                        });

                        // 请求统计图表
                        const requestsChart = echarts.init(document.getElementById('requestsChart'));
                        requestsChart.setOption({
                            title: { text: '请求统计' },
                            tooltip: { trigger: 'item' },
                            legend: { orient: 'vertical', left: 'left' },
                            series: [{
                                type: 'pie',
                                radius: '50%',
                                data: [
                                    { value: ${data.metrics.iterations - data.metrics.http_req_failed.count}, name: '成功请求' },
                                    { value: ${data.metrics.http_req_failed.count}, name: '失败请求' }
                                ]
                            }]
                        });

                        // 自适应窗口大小
                        window.addEventListener('resize', function() {
                            responseTimeChart.resize();
                            requestsChart.resize();
                        });
                    </script>
                </div>
            </body>
        </html>
    `;
} 