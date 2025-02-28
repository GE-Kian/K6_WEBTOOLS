import React, { useState, useEffect, useRef } from 'react';
import { Layout, Card, Row, Col, Upload, Form, InputNumber, Select, Button, message, Progress, Table, Statistic, Alert, Space } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import axios from 'axios';
import * as echarts from 'echarts';
import { io } from 'socket.io-client';
import { API_BASE_URL, WS_BASE_URL, API_ENDPOINTS, getApiUrl } from '../config/api';

const { Option } = Select;
const { Content } = Layout;

// 配置axios默认baseURL
axios.defaults.baseURL = API_BASE_URL;

const TestWorkbench = () => {
  // 脚本上传相关状态
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('');

  // 测试监控相关状态
  const [testStatus, setTestStatus] = useState('idle');
  const [testProgress, setTestProgress] = useState(0);
  const [testError, setTestError] = useState(null);
  const [metrics, setMetrics] = useState({
    totalRequests: 0,
    failureRate: 0,
    currentRPS: 0,
    avgResponseTime: 0,
    vus: 0
  });
  const [endpointMetrics, setEndpointMetrics] = useState([]);
  const rpsChartRef = useRef(null);
  const responseTimeChartRef = useRef(null);
  const rpsChart = useRef(null);
  const responseTimeChart = useRef(null);
  const [socket, setSocket] = useState(null);

  const [loading, setLoading] = useState(false);
  const [currentTestId, setCurrentTestId] = useState(null);

  // 添加新的状态
  const [testRunning, setTestRunning] = useState(false);

  // 处理文件上传
  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.error('请先选择文件');
      return;
    }

    const formData = new FormData();
    formData.append('file', fileList[0]);

    setUploading(true);
    setUploadProgress(0);
    setUploadStatus('');

    try {
      const response = await axios.post('/api/scripts', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percentCompleted);
        }
      });
      
      setUploadStatus('success');
      message.success('脚本上传成功');
      form.setFieldsValue({ scriptId: response.data.id });
    } catch (error) {
      setUploadStatus('error');
      message.error('上传失败：' + (error.response?.data?.error || error.message));
    } finally {
      setUploading(false);
    }
  };

  // 初始化WebSocket连接和图表
  useEffect(() => {
    // 初始化 Socket.IO 连接
    const newSocket = io(WS_BASE_URL, {
      path: '/socket.io',
      transports: ['websocket'],
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      autoConnect: true,
      forceNew: true,
      withCredentials: false,
      timeout: 20000
    });

    newSocket.on('connect', () => {
      console.log('WebSocket connected successfully');
      message.success('监控连接已建立');
    });

    newSocket.on('metrics_update', (data) => {
      console.log('Received metrics update:', data);
      if (data && typeof data === 'object') {
        setMetrics(prevMetrics => ({
          ...prevMetrics,
          totalRequests: data.totalRequests || 0,
          failureRate: parseFloat(data.failureRate || 0).toFixed(2),
          currentRPS: parseFloat(data.currentRPS || 0).toFixed(2),
          avgResponseTime: parseFloat(data.avgResponseTime || 0).toFixed(2),
          vus: data.vus || 0
        }));
        setEndpointMetrics(data.endpointMetrics || []);
        updateCharts(data);
      }
    });

    newSocket.on('test_status', (data) => {
      console.log('Received test status:', data);
      if (data && typeof data === 'object') {
        setTestStatus(data.status || 'idle');
        setTestProgress(parseFloat(data.progress || 0).toFixed(1));
        if (data.message) {
          if (data.status === 'failed') {
            setTestError(data.message);
            message.error(data.message);
          } else if (data.status === 'completed') {
            message.success(data.message);
            // 测试完成后重置指标
            setMetrics({
              totalRequests: 0,
              failureRate: 0,
              currentRPS: 0,
              avgResponseTime: 0,
              vus: 0
            });
            setEndpointMetrics([]);
          }
        }
        if (data.status === 'completed' || data.status === 'failed') {
          setTestRunning(false);
          setCurrentTestId(null);
        }
      }
    });

    newSocket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      message.error('监控连接失败');
    });

    newSocket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      message.warning('监控连接已断开');
    });

    setSocket(newSocket);

    // 初始化图表
    const initChart = () => {
      if (rpsChartRef.current) {
        rpsChart.current = echarts.init(rpsChartRef.current);

        const option = {
          tooltip: {
            trigger: 'axis',
            axisPointer: {
              type: 'cross',
              label: {
                backgroundColor: '#6a7985'
              }
            }
          },
          legend: {
            data: ['每秒接口请求数', '平均响应时间', '请求失败率', '并发用户数'],
            top: '2%',
            left: 'center',
            textStyle: {
              fontSize: '12',
              overflow: 'truncate'
            }
          },
          grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            top: '12%',
            containLabel: true
          },
          xAxis: [{
            type: 'time',
            boundaryGap: false,
            axisLabel: {
              formatter: (value) => {
                const date = new Date(value);
                return date.toLocaleTimeString('zh-CN', { hour12: false });
              },
              hideOverlap: true
            }
          }],
          yAxis: [
            {
              type: 'value',
              name: '请求数/用户数',
              nameLocation: 'middle',
              nameGap: 50,
              position: 'left',
              axisLabel: {
                hideOverlap: true
              }
            },
            {
              type: 'value',
              name: '响应时间(ms)',
              nameLocation: 'middle',
              nameGap: 50,
              position: 'right',
              offset: 0,
              axisLabel: {
                hideOverlap: true
              }
            },
            {
              type: 'value',
              name: '失败率(%)',
              nameLocation: 'middle',
              nameGap: 50,
              position: 'right',
              offset: 80,
              max: 100,
              min: 0,
              axisLabel: {
                hideOverlap: true
              }
            }
          ],
          series: [
            {
              name: '每秒接口请求数',
              type: 'line',
              smooth: true,
              data: [],
              itemStyle: { color: '#FF6B6B' },
              yAxisIndex: 0
            },
            {
              name: '平均响应时间',
              type: 'line',
              smooth: true,
              data: [],
              itemStyle: { color: '#4ECDC4' },
              yAxisIndex: 1
            },
            {
              name: '请求失败率',
              type: 'line',
              smooth: true,
              data: [],
              itemStyle: { color: '#FFE66D' },
              yAxisIndex: 2
            },
            {
              name: '并发用户数',
              type: 'line',
              smooth: true,
              data: [],
              itemStyle: { color: '#95A5A6' },
              yAxisIndex: 0
            }
          ]
        };

        rpsChart.current.setOption(option);
      }
    };

    initChart();

    // 添加窗口大小变化监听
    const handleResize = () => {
      if (rpsChart.current) {
        rpsChart.current.resize();
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (newSocket) {
        newSocket.disconnect();
      }
      if (rpsChart.current) {
        rpsChart.current.dispose();
      }
    };
  }, []);

  // 更新图表数据
  const updateCharts = (data) => {
    const now = new Date().getTime();
    
    if (rpsChart.current) {
      const option = rpsChart.current.getOption();
      const series = option.series.map((s, index) => {
        const seriesData = [...s.data];
        let value;
        switch(index) {
          case 0: // RPS
            value = data.currentRPS;
            break;
          case 1: // 响应时间
            value = data.avgResponseTime;
            break;
          case 2: // 失败率
            value = data.failureRate;
            break;
          case 3: // 并发用户数
            value = data.vus || 0;
            break;
          default:
            value = 0;
        }
        seriesData.push([now, value]);
        if (seriesData.length > 100) seriesData.shift();
        return { data: seriesData };
      });

      rpsChart.current.setOption({ series });
    }
  };

  // 更新 onFinish 函数
  const onFinish = async (values) => {
    try {
      setLoading(true);
      setTestError(null);
      
      // 检查是否已上传脚本
      if (!values.scriptId) {
        message.error('请先上传测试脚本');
        return;
      }

      setTestStatus('starting');
      setTestProgress(0);
      
      // 重置指标
      setMetrics({
        totalRequests: 0,
        failureRate: 0,
        currentRPS: 0,
        avgResponseTime: 0,
        vus: 0
      });
      setEndpointMetrics([]);
      
      // 清空图表数据
      if (rpsChart.current) {
        const option = rpsChart.current.getOption();
        option.series.forEach(series => series.data = []);
        rpsChart.current.setOption(option);
      }

      const response = await axios.post(getApiUrl(API_ENDPOINTS.START_TEST), {
        script_id: values.scriptId,
        vus: values.vus || 1,
        duration: values.duration || 30,
        ramp_time: values.ramp_time || 0
      });

      if (response.data && response.data.test_id) {
        setCurrentTestId(response.data.test_id);
        setTestRunning(true);
        message.success('测试已启动');
      }
    } catch (error) {
      console.error('Error:', error);
      setTestError(error.response?.data?.error || error.message);
      message.error('启动测试失败: ' + (error.response?.data?.error || error.message));
    } finally {
      setLoading(false);
    }
  };

  // 更新 stopTest 函数
  const stopTest = async () => {
    if (!currentTestId) return;

    try {
      setLoading(true);
      const response = await axios.post(getApiUrl(API_ENDPOINTS.STOP_TEST), {
        test_id: currentTestId
      });

      message.success('测试已停止');
      setTestRunning(false);
      setCurrentTestId(null);
      setTestStatus('stopped');
      setTestProgress(100);
    } catch (error) {
      console.error('Error:', error);
      message.error('停止测试失败: ' + (error.response?.data?.error || error.message));
    } finally {
      setLoading(false);
    }
  };

  // 渲染监控数据
  const renderMetrics = () => (
    <Row gutter={[16, 16]} className="metrics-container">
      <Col span={6}>
        <Card>
          <Statistic
            title="总请求数"
            value={metrics.totalRequests}
            suffix="个"
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="失败率"
            value={metrics.failureRate}
            suffix="%"
            valueStyle={{ color: parseFloat(metrics.failureRate) > 5 ? '#cf1322' : '#3f8600' }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="当前 RPS"
            value={metrics.currentRPS}
            suffix="次/秒"
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="平均响应时间"
            value={metrics.avgResponseTime}
            suffix="ms"
            valueStyle={{ color: parseFloat(metrics.avgResponseTime) > 1000 ? '#cf1322' : '#3f8600' }}
          />
        </Card>
      </Col>
    </Row>
  );

  // 渲染测试状态和进度
  const renderTestStatus = () => (
    <div className="test-status">
      <Progress
        percent={parseFloat(testProgress)}
        status={
          testStatus === 'running' ? 'active' :
          testStatus === 'completed' ? 'success' :
          testStatus === 'failed' ? 'exception' :
          'normal'
        }
        strokeColor={
          testStatus === 'running' ? '#1890ff' :
          testStatus === 'completed' ? '#52c41a' :
          testStatus === 'failed' ? '#f5222d' :
          '#d9d9d9'
        }
      />
      {testError && (
        <Alert
          message="测试错误"
          description={testError}
          type="error"
          showIcon
          closable
          onClose={() => setTestError(null)}
        />
      )}
    </div>
  );

  return (
    <Content>
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title="脚本上传与测试配置">
            <Form form={form} onFinish={onFinish} layout="vertical">
              <Row gutter={16} align="middle">
                <Col flex="auto">
                  <Form.Item label="选择测试脚本" style={{ marginBottom: 0 }}>
                    <Upload
                      fileList={fileList}
                      beforeUpload={(file) => {
                        setFileList([file]);
                        return false;
                      }}
                      onRemove={() => setFileList([])}
                    >
                      <Button icon={<UploadOutlined />} disabled={uploading || testRunning}>
                        选择文件
                      </Button>
                    </Upload>
                  </Form.Item>
                </Col>
                <Col>
                  <Form.Item style={{ marginBottom: 0 }}>
                    <Button
                      type="primary"
                      onClick={handleUpload}
                      loading={uploading}
                      disabled={fileList.length === 0 || testRunning}
                    >
                      开始上传
                    </Button>
                  </Form.Item>
                </Col>
              </Row>
              
              {uploadStatus && (
                <Progress
                  percent={uploadProgress}
                  status={uploadStatus === 'error' ? 'exception' : undefined}
                  style={{ margin: '16px 0' }}
                />
              )}

              {uploadStatus === 'success' && (
                <>
                  <Form.Item name="scriptId" hidden>
                    <InputNumber />
                  </Form.Item>
                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item 
                        label="并发用户数" 
                        name="vus"
                        rules={[{ required: true, message: '请输入并发用户数' }]}
                      >
                        <InputNumber min={1} style={{ width: '100%' }} disabled={testRunning} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item 
                        label="测试时长(秒)" 
                        name="duration"
                        rules={[{ required: true, message: '请输入测试时长' }]}
                      >
                        <InputNumber min={1} style={{ width: '100%' }} disabled={testRunning} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item 
                        label="爬坡时间(秒)" 
                        name="ramp_time"
                        rules={[{ required: true, message: '请输入爬坡时间' }]}
                      >
                        <InputNumber min={0} style={{ width: '100%' }} disabled={testRunning} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item>
                    <Button 
                      type="primary" 
                      htmlType="submit" 
                      loading={loading} 
                      disabled={testRunning}
                    >
                      开始测试
                    </Button>
                    {testRunning && (
                      <Button 
                        danger 
                        onClick={stopTest} 
                        style={{ marginLeft: '10px' }}
                        loading={loading}
                      >
                        停止测试
                      </Button>
                    )}
                  </Form.Item>
                </>
              )}
            </Form>
          </Card>
        </Col>

        {/* 测试状态和监控数据显示 */}
        {(testRunning || testStatus) && (
          <Col span={24}>
            <Card title="测试状态">
              {renderTestStatus()}
            </Card>
          </Col>
        )}

        {/* 监控数据卡片 */}
        <Col span={24}>
          <Card title="测试监控">
            {renderMetrics()}

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col span={24}>
                <div ref={rpsChartRef} style={{ height: 400 }} />
              </Col>
            </Row>

            <Table
              style={{ marginTop: 16 }}
              columns={[
                { title: '接口名称', dataIndex: 'endpoint', key: 'endpoint' },
                { title: '总请求数', dataIndex: 'requests', key: 'requests', sorter: (a, b) => a.requests - b.requests },
                { title: 'RPS', dataIndex: 'rps', key: 'rps', sorter: (a, b) => a.rps - b.rps },
                { title: '平均响应时间(ms)', dataIndex: 'avgResponseTime', key: 'avgResponseTime', sorter: (a, b) => a.avgResponseTime - b.avgResponseTime },
                { title: '最小响应时间(ms)', dataIndex: 'minResponseTime', key: 'minResponseTime', sorter: (a, b) => a.minResponseTime - b.minResponseTime },
                { title: '最大响应时间(ms)', dataIndex: 'maxResponseTime', key: 'maxResponseTime', sorter: (a, b) => a.maxResponseTime - b.maxResponseTime },
                { title: '90%响应时间(ms)', dataIndex: 'p90ResponseTime', key: 'p90ResponseTime', sorter: (a, b) => a.p90ResponseTime - b.p90ResponseTime },
                { title: '失败率(%)', dataIndex: 'failureRate', key: 'failureRate', render: (text) => `${(text * 100).toFixed(2)}%`, sorter: (a, b) => a.failureRate - b.failureRate }
              ]}
              dataSource={endpointMetrics}
              rowKey="endpoint"
              scroll={{ x: true }}
            />
          </Card>
        </Col>
      </Row>
    </Content>
  );
};

export default TestWorkbench;
