import React, { useEffect, useRef, useState } from 'react';
import { Card, Table, Statistic, Row, Col } from 'antd';
import * as echarts from 'echarts';

const TestMonitor = () => {
  const [metrics, setMetrics] = useState({
    totalRequests: 0,
    failureRate: 0,
    currentRPS: 0,
    avgResponseTime: 0
  });

  const [endpointMetrics, setEndpointMetrics] = useState([]);
  const rpsChartRef = useRef(null);
  const responseTimeChartRef = useRef(null);
  const rpsChart = useRef(null);
  const responseTimeChart = useRef(null);
  const ws = useRef(null);

  // 初始化WebSocket连接
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:5000/ws/metrics');

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      updateMetrics(data);
      updateCharts(data);
    };

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  // 初始化图表
  useEffect(() => {
    // RPS图表
    rpsChart.current = echarts.init(rpsChartRef.current);
    const rpsOption = {
      title: { text: '每秒请求数 (RPS)' },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'time' },
      yAxis: { type: 'value' },
      series: [{
        name: 'RPS',
        type: 'line',
        smooth: true,
        data: []
      }]
    };
    rpsChart.current.setOption(rpsOption);

    // 响应时间图表
    responseTimeChart.current = echarts.init(responseTimeChartRef.current);
    const responseTimeOption = {
      title: { text: '平均响应时间 (ms)' },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'time' },
      yAxis: { type: 'value' },
      series: [{
        name: '响应时间',
        type: 'line',
        smooth: true,
        data: []
      }]
    };
    responseTimeChart.current.setOption(responseTimeOption);

    // 窗口大小变化时重绘图表
    const handleResize = () => {
      rpsChart.current?.resize();
      responseTimeChart.current?.resize();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      rpsChart.current?.dispose();
      responseTimeChart.current?.dispose();
    };
  }, []);

  // 更新指标数据
  const updateMetrics = (data) => {
    setMetrics({
      totalRequests: data.totalRequests,
      failureRate: data.failureRate,
      currentRPS: data.currentRPS,
      avgResponseTime: data.avgResponseTime,
      maxResponseTime: data.maxResponseTime,
      minResponseTime: data.minResponseTime,
      p90ResponseTime: data.p90ResponseTime
    });

    setEndpointMetrics(data.endpoints.map(endpoint => ({
      ...endpoint,
      failureRate: (endpoint.failures / endpoint.requests * 100).toFixed(2)
    })));
  };

  // 更新图表数据
  const updateCharts = (data) => {
    const now = new Date().getTime();

    // 更新RPS图表
    rpsChart.current?.setOption({
      series: [{
        data: [...rpsChart.current.getOption().series[0].data, [
          now,
          data.currentRPS
        ]].slice(-60) // 保留最近60个数据点
      }]
    });

    // 更新响应时间图表
    responseTimeChart.current?.setOption({
      series: [{
        data: [...responseTimeChart.current.getOption().series[0].data, [
          now,
          data.avgResponseTime
        ]].slice(-60)
      }]
    });
  };

  // 表格列定义
  const columns = [
    { title: '接口名称', dataIndex: 'name', key: 'name' },
    { title: '总请求数', dataIndex: 'requests', key: 'requests' },
    { title: 'RPS', dataIndex: 'rps', key: 'rps' },
    { title: '平均响应时间(ms)', dataIndex: 'avgResponseTime', key: 'avgResponseTime' },
    { title: '最小响应时间(ms)', dataIndex: 'minResponseTime', key: 'minResponseTime' },
    { title: '最大响应时间(ms)', dataIndex: 'maxResponseTime', key: 'maxResponseTime' },
    { title: '90%响应时间(ms)', dataIndex: 'p90', key: 'p90' },
    { title: '失败率(%)', dataIndex: 'failureRate', key: 'failureRate' },
  ];

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic title="总请求数" value={metrics.totalRequests} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="每秒请求数" value={metrics.currentRPS} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="失败率(%)" value={metrics.failureRate} precision={2} suffix="%" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="平均响应时间(ms)" value={metrics.avgResponseTime} precision={2} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="最大响应时间(ms)" value={metrics.maxResponseTime} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="最小响应时间(ms)" value={metrics.minResponseTime} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="90%响应时间(ms)" value={metrics.p90ResponseTime} precision={2} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <div ref={rpsChartRef} style={{ height: 300 }} />
        </Col>
        <Col span={12}>
          <div ref={responseTimeChartRef} style={{ height: 300 }} />
        </Col>
      </Row>

      <Card style={{ marginTop: 16 }}>
        <Table
          columns={columns}
          dataSource={endpointMetrics}
          rowKey="name"
          pagination={false}
          scroll={{ x: true }}
        />
      </Card>
    </div>
  );
};

export default TestMonitor;