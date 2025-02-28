import os
import json
import plotly.graph_objects as go
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from models import TestResult, PerformanceMetric, TestConfig

class ReportGenerator:
    def __init__(self):
        self.reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
        self.templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.templates_dir, exist_ok=True)
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))

    def generate_performance_charts(self, metrics):
        """生成性能图表"""
        timestamps = [m.timestamp for m in metrics]
        durations = [m.metrics.get('http_req_duration', 0) for m in metrics]
        reqs = [m.metrics.get('http_reqs', 0) for m in metrics]
        failures = [m.metrics.get('http_req_failed', 0) for m in metrics]

        # 响应时间图表
        duration_fig = go.Figure()
        duration_fig.add_trace(go.Scatter(
            x=timestamps,
            y=durations,
            mode='lines',
            name='响应时间'
        ))
        duration_fig.update_layout(title='请求响应时间趋势')

        # 请求数和失败数图表
        reqs_fig = go.Figure()
        reqs_fig.add_trace(go.Bar(
            x=timestamps,
            y=reqs,
            name='总请求数'
        ))
        reqs_fig.add_trace(go.Bar(
            x=timestamps,
            y=failures,
            name='失败请求数'
        ))
        reqs_fig.update_layout(title='请求统计')

        return {
            'duration_chart': duration_fig.to_html(full_html=False),
            'requests_chart': reqs_fig.to_html(full_html=False)
        }

    def calculate_statistics(self, metrics):
        """计算性能统计数据"""
        if not metrics:
            return {}

        durations = [m.metrics.get('http_req_duration', 0) for m in metrics]
        total_reqs = sum(m.metrics.get('http_reqs', 0) for m in metrics)
        total_failures = sum(m.metrics.get('http_req_failed', 0) for m in metrics)

        return {
            'avg_response_time': sum(durations) / len(durations) if durations else 0,
            'max_response_time': max(durations) if durations else 0,
            'min_response_time': min(durations) if durations else 0,
            'total_requests': total_reqs,
            'total_failures': total_failures,
            'success_rate': ((total_reqs - total_failures) / total_reqs * 100) if total_reqs > 0 else 0
        }

    def generate_report(self, result_id):
        """生成测试报告"""
        result = TestResult.query.get(result_id)
        if not result:
            raise ValueError('Test result not found')

        config = TestConfig.query.get(result.config_id)
        metrics = PerformanceMetric.query.filter_by(result_id=result_id).all()

        # 生成图表
        charts = self.generate_performance_charts(metrics)
        # 计算统计数据
        stats = self.calculate_statistics(metrics)

        # 准备报告数据
        report_data = {
            'test_name': config.name,
            'start_time': result.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': result.end_time.strftime('%Y-%m-%d %H:%M:%S') if result.end_time else 'N/A',
            'duration': (result.end_time - result.start_time).total_seconds() if result.end_time else 0,
            'status': result.status,
            'parameters': config.parameters,
            'statistics': stats,
            'duration_chart': charts['duration_chart'],
            'requests_chart': charts['requests_chart']
        }

        # 渲染报告模板
        template = self.env.get_template('report_template.html')
        report_html = template.render(**report_data)

        # 保存报告文件
        report_filename = f'report_{result_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        report_path = os.path.join(self.reports_dir, report_filename)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_html)

        # 更新测试结果的报告路径
        result.report_path = report_path
        db.session.commit()

        return report_path