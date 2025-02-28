import React, { useState, useEffect, useRef } from 'react';
import { 
  Layout, Card, Tabs, Upload, Form, InputNumber, Select, Button, 
  message, Progress, Statistic, Row, Col, Table, Divider, Space, Input
} from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import axios from 'axios';
import * as echarts from 'echarts';
import { io } from 'socket.io-client';

const { TabPane } = Tabs;
const { Option } = Select;

// 配置axios默认设置
axios.defaults.baseURL = 'http://localhost:5000';  // 设置后端服务器地址
axios.defaults.withCredentials = false;  // 不发送凭证
axios.defaults.timeout = 30000;  // 30秒超时

const TestDashboard = () => {
  // 文件上传状态
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('');
  
  // 测试状态
  const [testRunning, setTestRunning] = useState(false);
  const [activeTab, setActiveTab] = useState('1');
  
  // 测试监控数据
  const [metrics, setMetrics] = useState({
    totalRequests: 0,
    failureRate: 0,
    currentRPS: 0,
    avgResponseTime: 0
  });
  const [endpointMetrics, setEndpointMetrics] = useState([]);
  
  // 图表引用
  const rpsChartRef = useRef(null);
  const responseTimeChartRef = useRef(null);
  const rpsChart = useRef(null);
  const responseTimeChart = useRef(null);
  const ws = useRef(null);
  const selectedScript = useRef(null);
  const currentTestId = useRef(null);

  // 文件上传处理
  const handleUpload = async () => {
    if (!fileList[0]) {
      message.error('请先选择一个脚本文件');
      return;
    }

    setUploading(true);
    setUploadStatus('uploading');
    setUploadProgress(0);

    // 创建FormData对象
    const formData = new FormData();
    // 确保使用原始文件对象
    const file = fileList[0].originFileObj || fileList[0];
    formData.append('file', file);
    
    // 获取表单值
    const scriptNameValue = form.getFieldValue('scriptName') || file.name;
    const descriptionValue = form.getFieldValue('description') || '';
    formData.append('name', scriptNameValue);
    formData.append('description', descriptionValue);

    console.log('准备上传文件:', file.name);
    console.log('脚本名称:', scriptNameValue);
    console.log('脚本描述:', descriptionValue);
    
    try {
      console.log('发送上传请求...');
      // 打印FormData内容（仅用于调试）
      for (let pair of formData.entries()) {
        console.log(pair[0] + ': ' + (pair[0] === 'file' ? pair[1].name : pair[1]));
      }
      
      // 使用相对URL
      const response = await axios.post('/api/scripts', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          console.log('上传进度:', percentCompleted + '%');
          setUploadProgress(percentCompleted);
        }
      });
      
      console.log('上传成功:', response.data);
      setUploadStatus('success');
      message.success('脚本上传成功');
      selectedScript.current = response.data;
    } catch (error) {
      console.error('上传失败:', error);
      
      // 详细记录错误信息
      if (error.response) {
        // 服务器返回了错误响应
        console.error('错误响应:', error.response.status, error.response.data);
        message.error(`上传失败 (${error.response.status}): ${error.response.data.error || '未知错误'}`);
      } else if (error.request) {
        // 请求已发送但没有收到响应
        console.error('无响应:', error.request);
        message.error('上传失败: 服务器没有响应');
      } else {
        // 请求设置时出错
        console.error('请求错误:', error.message);
        message.error(`上传失败: ${error.message}`);
      }
      
      setUploadStatus('error');
    } finally {
      setUploading(false);
    }
  };

  const beforeUpload = (file) => {
    console.log('选择文件:', file.name, '大小:', (file.size / 1024).toFixed(2), 'KB');
    // 只检查文件扩展名，不检查MIME类型
    const isJS = file.name.endsWith('.js');
    if (!isJS) {
      message.error('只能上传 JavaScript 文件！');
      console.log('文件类型验证失败:', file.name);
    }
    const isLt2M = file.size / 1024 / 1024 < 2;
    if (!isLt2M) {
      message.error('文件大小不能超过 2MB！');
      console.log('文件大小验证失败:', file.name, '大小:', (file.size / 1024 / 1024).toFixed(2), 'MB');
    }
    return isJS && isLt2M;
  };

  const handleChange = (info) => {
    console.log('文件列表更新:', info.fileList.map(f => f.name).join(', '));
    setFileList(info.fileList.slice(-1));
    // 重置上传状态
    setUploadProgress(0);
    setUploadStatus('');
  };

  // 启动测试
  const startTest = async () => {
    try {
      // 验证表单
      await form.validateFields();
      const values = form.getFieldsValue();
      
      // 检查是否选择了脚本
      if (!selectedScript.current) {
        message.error('请先选择一个测试脚本');
        return;
      }
      
      // 构建测试配置
      const testConfig = {
        vus: parseInt(values.vus),
        duration: values.duration,
        rampUp: parseInt(values.rampUp || 0),
        thresholds: {
          http_req_duration: values.responseTimeThreshold ? 
            `p(95)<${values.responseTimeThreshold}` : undefined,
          http_req_failed: values.errorRateThreshold ? 
            `rate<${values.errorRateThreshold/100}` : undefined
        }
      };
      
      console.log('启动测试:', selectedScript.current, testConfig);
      setTestRunning(true);
      
      // 发送测试启动请求
      const response = await axios.post('/api/tests/start', {
        scriptId: selectedScript.current.id,
        config: testConfig
      });
      
      console.log('测试启动响应:', response.data);
      
      // 获取测试ID
      const testId = response.data.testId;
      if (!testId) {
        throw new Error('服务器未返回测试ID');
      }
      
      // 初始化WebSocket连接
      initWebSocket(testId);
      
      // 切换到监控标签页
      setActiveTab('2');
      message.success('测试已成功启动');
      
      currentTestId.current = testId;
    } catch (error) {
      console.error('启动测试失败:', error);
      setTestRunning(false);
      message.error(`启动测试失败: ${error.response?.data?.error || error.message}`);
    }
  };

  // 初始化WebSocket连接
  const initWebSocket = (resultId) => {
    // 关闭之前的连接
    if (ws.current) {
      ws.current.disconnect();
    }

    // 创建新连接
    const wsUrl = `http://${window.location.hostname}:5000`;
    console.log('连接WebSocket:', wsUrl);
    
    // 创建Socket.IO连接
    ws.current = io(wsUrl, {
      transports: ['websocket'],
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000
    });

    // 连接成功
    ws.current.on('connect', () => {
      console.log('WebSocket连接已建立');
      // 加入测试房间
      ws.current.emit('join_test', { test_id: resultId });
      message.success('已连接到测试服务器');
    });

    // 连接错误
    ws.current.on('connect_error', (error) => {
      console.error('WebSocket连接错误:', error);
      message.error('连接测试服务器失败');
    });

    // 确认加入测试房间
    ws.current.on('joined_test', (data) => {
      console.log('已加入测试房间:', data);
      message.success(data.message || '已加入测试监控');
    });

    // 接收指标更新
    ws.current.on('metrics_update', (data) => {
      console.log('收到指标更新:', data);
      updateMetrics(data);
      updateCharts(data);
    });

    // 测试停止
    ws.current.on('test_stopped', (data) => {
      console.log('测试已停止:', data);
      setTestRunning(false);
      message.info(data.message || '测试已完成');
    });

    // 断开连接
    ws.current.on('disconnect', () => {
      console.log('WebSocket连接已关闭');
      setTestRunning(false);
    });
  };

  // 初始化图表
  useEffect(() => {
    if (activeTab === '2' && rpsChartRef.current && responseTimeChartRef.current) {
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
    }
  }, [activeTab]);

  // 更新指标数据
  const updateMetrics = (data) => {
    setMetrics({
      totalRequests: data.totalRequests || 0,
      failureRate: data.failureRate || 0,
      currentRPS: data.currentRPS || 0,
      avgResponseTime: data.avgResponseTime || 0
    });

    setEndpointMetrics(data.endpoints || []);
  };

  // 更新图表数据
  const updateCharts = (data) => {
    if (!rpsChart.current || !responseTimeChart.current) return;
    
    const now = new Date().getTime();

    // 更新RPS图表
    const rpsOption = rpsChart.current.getOption();
    const rpsData = [...rpsOption.series[0].data];
    rpsData.push([now, data.currentRPS || 0]);
    
    // 保留最近30个数据点
    if (rpsData.length > 30) {
      rpsData.shift();
    }
    
    rpsChart.current.setOption({
      series: [{
        data: rpsData
      }]
    });

    // 更新响应时间图表
    const rtOption = responseTimeChart.current.getOption();
    const rtData = [...rtOption.series[0].data];
    rtData.push([now, data.avgResponseTime || 0]);
    
    // 保留最近30个数据点
    if (rtData.length > 30) {
      rtData.shift();
    }
    
    responseTimeChart.current.setOption({
      series: [{
        data: rtData
      }]
    });
  };

  // 停止测试
  const handleStopTest = async () => {
    if (!currentTestId.current) {
      message.error('没有正在运行的测试');
      return;
    }
    
    try {
      console.log('停止测试:', currentTestId.current);
      await axios.post(`/api/tests/${currentTestId.current}/stop`);
      message.success('测试已停止');
      setTestRunning(false);
      
      // 关闭WebSocket连接
      if (ws.current) {
        ws.current.disconnect();
      }
    } catch (error) {
      console.error('停止测试失败:', error);
      message.error(`停止测试失败: ${error.response?.data?.error || error.message}`);
    }
  };

  // 标签页切换
  const handleTabChange = (key) => {
    setActiveTab(key);
  };

  // 端点指标表格列
  const endpointColumns = [
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
    },
    {
      title: '请求数',
      dataIndex: 'requests',
      key: 'requests',
      sorter: (a, b) => a.requests - b.requests,
    },
    {
      title: '平均响应时间 (ms)',
      dataIndex: 'avgResponseTime',
      key: 'avgResponseTime',
      sorter: (a, b) => a.avgResponseTime - b.avgResponseTime,
    },
    {
      title: '错误率 (%)',
      dataIndex: 'errorRate',
      key: 'errorRate',
      sorter: (a, b) => a.errorRate - b.errorRate,
      render: (text) => `${text.toFixed(2)}%`,
    },
  ];

  useEffect(() => {
    // 配置axios默认值
    axios.defaults.baseURL = '';  // 使用相对路径
    axios.defaults.timeout = 60000;  // 增加超时时间到60秒
    axios.defaults.withCredentials = false;  // 不需要凭证

    // 添加请求拦截器
    axios.interceptors.request.use(
      (config) => {
        console.log('发送请求:', config.method, config.url);
        return config;
      },
      (error) => {
        console.error('请求错误:', error);
        return Promise.reject(error);
      }
    );

    // 添加响应拦截器
    axios.interceptors.response.use(
      (response) => {
        console.log('收到响应:', response.status, response.config.url);
        return response;
      },
      (error) => {
        if (error.response) {
          console.error('响应错误:', error.response.status, error.response.data);
        } else if (error.request) {
          console.error('无响应:', error.request);
        } else {
          console.error('请求配置错误:', error.message);
        }
        return Promise.reject(error);
      }
    );
  }, []);

  return (
    <Layout style={{ padding: '20px' }}>
      <div style={{ margin: '0 auto' }}>
        <Tabs activeKey={activeTab} onChange={handleTabChange}>
          <TabPane tab="脚本上传" key="1">
            <Card title="上传性能测试脚本" style={{ marginBottom: 20 }}>
              <Form form={form} layout="vertical">
                <Form.Item
                  label="K6 脚本文件"
                  required
                  tooltip="请上传 .js 格式的 K6 性能测试脚本"
                >
                  <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'nowrap' }}>
                    <Upload
                      beforeUpload={beforeUpload}
                      onChange={handleChange}
                      fileList={fileList}
                      maxCount={1}
                      showUploadList={false}
                    >
                      <Button icon={<UploadOutlined />}>选择文件</Button>
                    </Upload>
                    <span style={{ marginLeft: 8, flex: '1 1 auto', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {fileList[0]?.name || ''}
                    </span>
                    <Button
                      type="primary"
                      onClick={handleUpload}
                      disabled={fileList.length === 0 || uploading}
                      loading={uploading}
                      style={{ flexShrink: 0 }}
                    >
                      {uploading ? '上传中' : '上传'}
                    </Button>
                  </div>
                  {(uploading || uploadStatus) && (
                    <Row style={{ marginTop: 16 }}>
                      <Col span={24}>
                        <Progress
                          percent={uploadProgress}
                          status={uploadStatus === 'error' ? 'exception' : undefined}
                        />
                      </Col>
                    </Row>
                  )}
                </Form.Item>
              </Form>
            </Card>

            {/* 测试参数配置区域 */}
            <Card title="测试参数配置" style={{ marginBottom: 20 }}>
              <Form.Item
                name="vus"
                label="并发用户数"
                rules={[{ required: true, message: '请输入并发用户数' }]}
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="请输入并发用户数" />
              </Form.Item>

              <Form.Item
                name="duration"
                label="测试时长(秒)"
                rules={[{ required: true, message: '请输入测试时长' }]}
              >
                <InputNumber min={1} style={{ width: '100%' }} placeholder="请输入测试时长" />
              </Form.Item>

              <Form.Item
                name="rampUp"
                label="爬坡时间(秒)"
                tooltip="从0增长到目标并发数所需时间"
              >
                <InputNumber min={0} style={{ width: '100%' }} placeholder="请输入爬坡时间" />
              </Form.Item>

              <Form.Item
                name="responseTimeThreshold"
                label="响应时间阈值(ms)"
                tooltip="95%的请求响应时间应小于此值"
              >
                <InputNumber min={0} style={{ width: '100%' }} placeholder="请输入响应时间阈值" />
              </Form.Item>

              <Form.Item
                name="errorRateThreshold"
                label="错误率阈值(%)"
                tooltip="允许的最大错误率百分比"
              >
                <InputNumber
                  min={0}
                  max={100}
                  style={{ width: '100%' }}
                  placeholder="请输入错误率阈值"
                />
              </Form.Item>

              <Form.Item>
                <Button
                  type="primary"
                  onClick={startTest}
                  disabled={!selectedScript.current || testRunning}
                  block
                >
                  {testRunning ? '测试运行中...' : '开始测试'}
                </Button>
              </Form.Item>
            </Card>
          </TabPane>
          <TabPane tab="测试监控" key="2">
            <Card title="测试监控" style={{ marginBottom: 20 }}>
              <Row gutter={[16, 16]}>
                <Col span={6}>
                  <Card>
                    <Statistic title="总请求数" value={metrics.totalRequests} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="失败率"
                      value={metrics.failureRate}
                      suffix="%"
                      precision={2}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic title="当前RPS" value={metrics.currentRPS} />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="平均响应时间"
                      value={metrics.avgResponseTime}
                      suffix="ms"
                    />
                  </Card>
                </Col>
              </Row>

              <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
                <Col span={12}>
                  <div ref={rpsChartRef} style={{ height: 300 }} />
                </Col>
                <Col span={12}>
                  <div ref={responseTimeChartRef} style={{ height: 300 }} />
                </Col>
              </Row>

              <Row style={{ marginTop: 20 }}>
                <Col span={24}>
                  <Table
                    dataSource={endpointMetrics}
                    columns={[
                      { title: '端点', dataIndex: 'endpoint', key: 'endpoint' },
                      { title: 'RPS', dataIndex: 'rps', key: 'rps' },
                      { title: '平均响应时间', dataIndex: 'avgResponseTime', key: 'avgResponseTime' },
                      { title: '失败率', dataIndex: 'failureRate', key: 'failureRate' }
                    ]}
                  />
                </Col>
              </Row>
            </Card>
          </TabPane>
        </Tabs>
      </div>
    </Layout>
  );
};

export default TestDashboard;