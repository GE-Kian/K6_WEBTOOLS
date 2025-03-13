import React, { useState, useEffect, useRef } from 'react';
import { Layout, Card, Row, Col, Upload, Form, InputNumber, Select, Button, message, Progress, Table, Statistic, Alert, Space, Tooltip, Tag } from 'antd';
import { UploadOutlined, DeleteOutlined } from '@ant-design/icons';
import axios from 'axios';
import * as echarts from 'echarts';
import io from 'socket.io-client';
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
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [selectedScriptId, setSelectedScriptId] = useState(null);

  // 测试监控相关状态
  const [testStatus, setTestStatus] = useState('idle');
  const [testProgress, setTestProgress] = useState(0);
  const [testError, setTestError] = useState(null);
  const [testReportUrl, setTestReportUrl] = useState(null); // 添加测试报告URL状态
  const [metrics, setMetrics] = useState({
    totalRequests: 0,
    failureRate: 0,
    currentRPS: 0,
    avgResponseTime: 0,
    vus: 0
  });
  const [endpointMetrics, setEndpointMetrics] = useState([]); // 添加endpointMetrics状态
  const rpsChartRef = useRef(null);
  const responseTimeChartRef = useRef(null);
  const rpsChart = useRef(null);
  const responseTimeChart = useRef(null);
  const [socket, setSocket] = useState(null);

  const [loading, setLoading] = useState(false);
  const [currentTestId, setCurrentTestId] = useState(null);

  // 添加新的状态
  const [testRunning, setTestRunning] = useState(false);

  // 定义状态变量
  const [testMetrics, setTestMetrics] = useState({
    progress: 0,
    vus: 0,
    rps: 0,
    response_time: 0,
    error_rate: 0,
    total_requests: 0,
    failed_requests: 0
  });

  // Socket.IO 连接状态
  const [socketConnected, setSocketConnected] = useState(false);

  // 处理文件上传
  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.error('请先选择文件');
      return;
    }

    const formData = new FormData();
    // 如果只有一个文件，使用'file'参数名，否则使用'files[]'
    if (fileList.length === 1) {
    formData.append('file', fileList[0]);
    } else {
      fileList.forEach(file => {
        formData.append('files[]', file);
      });
    }
    
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
      
      // 更新上传的文件列表
      if (response.data && response.data.files) {
        // 构建文件对象数组，确保每个文件都有唯一ID
        const files = response.data.files.map((fileName, index) => ({
          id: `${response.data.id}_${index}`,
          name: fileName,
          size: fileList.find(f => f.name === fileName)?.size || 0,
          upload_time: new Date().toISOString(),
          original_id: response.data.id // 保存原始脚本ID
        }));
        setUploadedFiles(files);
        
        // 如果只有一个文件，自动选择它
        if (files.length === 1) {
          setSelectedScriptId(files[0].id);
          form.setFieldsValue({ scriptId: files[0].id });
        }
      } else if (response.data && response.data.id) {
        // 兼容旧的API返回格式
        const newFile = {
          id: response.data.id.toString(), // 确保ID是字符串
          name: fileList[0].name,
          size: fileList[0].size,
          upload_time: new Date().toISOString(),
          original_id: response.data.id // 保存原始脚本ID
        };
        setUploadedFiles([newFile]);
        setSelectedScriptId(newFile.id);
        form.setFieldsValue({ scriptId: newFile.id });
      }
    } catch (error) {
      setUploadStatus('error');
      message.error('上传失败：' + (error.response?.data?.error || error.message));
    } finally {
      setUploading(false);
    }
  };

  // 初始化WebSocket连接和图表
  useEffect(() => {
    const socket = io(API_BASE_URL, {
      transports: ['websocket', 'polling'],
      withCredentials: true
    });

    socket.on('connect', () => {
      console.log('Socket.IO connected');
      setSocketConnected(true);
    });

    socket.on('test_metrics', (data) => {
      console.log('Received test metrics:', data);
      if (data && data.metrics) {
        setTestMetrics(prev => ({
          progress: data.progress || prev.progress,
          vus: data.metrics.vus || prev.vus,
          rps: data.metrics.rps || prev.rps,
          response_time: data.metrics.response_time || prev.response_time,
          error_rate: data.metrics.error_rate || prev.error_rate,
          total_requests: data.metrics.total_requests || prev.total_requests,
          failed_requests: data.metrics.failed_requests || prev.failed_requests
        }));
        
        // 更新指标数据，用于UI展示
        setMetrics({
          totalRequests: data.metrics.total_requests || 0,
          failureRate: data.metrics.error_rate || 0,
          currentRPS: data.metrics.rps || 0,
          avgResponseTime: data.metrics.response_time || 0,
          vus: data.metrics.vus || 0
        });
        
        // 更新接口指标数据
        if (data.endpoints && Array.isArray(data.endpoints)) {
          const formattedEndpoints = data.endpoints.map(endpoint => ({
            key: endpoint.name,
            endpoint: endpoint.name,
            requests: endpoint.requests,
            failures: endpoint.failed,
            failureRate: endpoint.error_rate / 100, // 转换为小数
            rps: endpoint.requests / (data.test_duration || 30), // 估计RPS
            avgResponseTime: endpoint.avg_duration,
            minResponseTime: endpoint.min_duration,
            maxResponseTime: endpoint.max_duration,
            statusCodes: endpoint.status_codes
          }));
          // Sort the formatted endpoints by requests in descending order
          const sortedEndpoints = formattedEndpoints.sort((a, b) => b.requests - a.requests);
          setEndpointMetrics(sortedEndpoints);
          console.log('Updated endpoint metrics:', sortedEndpoints);
        }
        
        // 更新图表数据
        updateCharts(data.metrics);
        
        // 更新进度
        if (data.progress !== undefined) {
          setTestProgress(parseFloat(data.progress || 0));
        }
        
        // 更新测试状态
        if (data.status) {
          setTestStatus(data.status);
          if (data.status === 'completed') {
            setTestRunning(false);
            setCurrentTestId(null);
            
            // 如果有报告URL，设置它
            if (data.report_url) {
              setTestReportUrl(data.report_url);
            }
          }
        }
      }
    });

    socket.on('test_status', (data) => {
      console.log('Received test status:', data);
      if (data && typeof data === 'object') {
        const newStatus = data.status || 'idle';
        setTestStatus(newStatus);
        
        // 确保进度数据被正确处理
        if (data.progress !== undefined) {
          setTestProgress(parseFloat(data.progress || 0).toFixed(1));
        } else if (newStatus === 'completed' || newStatus === 'stopped') {
          // 如果测试完成或停止，确保进度显示为100%
          setTestProgress('100.0');
        }
        
        // 处理错误信息
        if (data.message) {
          if (newStatus === 'failed') {
            setTestError(data.message);
      } else {
            message.info(data.message);
          }
        }
        
        // 如果测试完成，检查是否有报告URL
        if (newStatus === 'completed' && data.report_url) {
          setTestReportUrl(data.report_url);
          message.success('测试已完成，报告已生成！');
        }
        
        // 如果测试停止或完成，重置部分状态
        if (newStatus === 'completed' || newStatus === 'stopped' || newStatus === 'failed') {
          console.log(`测试已${newStatus === 'completed' ? '完成' : newStatus === 'stopped' ? '停止' : '失败'}`);
        }
      }
    });

    socket.on('connect_error', (error) => {
        console.error('WebSocket connection error:', error);
      message.error('监控连接失败');
    });

    socket.on('disconnect', () => {
      console.log('Socket.IO disconnected');
      setSocketConnected(false);
    });

    setSocket(socket);

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
      if (socket) {
        socket.disconnect();
      }
      if (rpsChart.current) {
        rpsChart.current.dispose();
      }
    };
  }, []);

  // 更新图表数据
  const updateCharts = (metricsData) => {
    if (!rpsChart.current) {
      console.warn('RPS chart not initialized');
      return;
    }
    
    try {
      const now = new Date().getTime();
      
      // 确保所有数值有效
      const rps = parseFloat(metricsData.rps || 0);
      const responseTime = parseFloat(metricsData.response_time || 0);
      const errorRate = parseFloat(metricsData.error_rate || 0);
      const vus = parseInt(metricsData.vus || 0);
      
      console.log(`Updating chart with: RPS=${rps}, RT=${responseTime}ms, ErrorRate=${errorRate}%, VUs=${vus}`);
      
      const series = rpsChart.current.getOption().series.map((item, index) => {
        let value = 0;
        switch (index) {
          case 0: // RPS
            value = rps;
            break;
          case 1: // Response Time
            value = responseTime;
            break;
          case 2: // Error Rate
            value = errorRate;
            break;
          case 3: // VUs
            value = vus;
            break;
          default:
            value = 0;
        }
        
        const seriesData = [...(item.data || [])];
        seriesData.push([now, value]);
        
        // 保持最多100个数据点
        while (seriesData.length > 100) {
          seriesData.shift();
        }
        
        return {
          ...item,
          data: seriesData
        };
      });

      rpsChart.current.setOption({ series });
    } catch (error) {
      console.error('Error updating charts:', error);
    }
  };

  // 更新 onFinish 函数
  const onFinish = async (values) => {
    try {
      setLoading(true);
      setTestError(null);
      
      // 检查是否已选择脚本
      if (!values.scriptId) {
        message.error('请先选择测试脚本');
        return;
      }

      // 查找选中文件的原始ID
      const selectedFile = uploadedFiles.find(file => file.id === values.scriptId);
      if (!selectedFile) {
        message.error('无法找到选中的脚本文件');
        setLoading(false);
        return;
      }
      
      // 使用原始脚本ID
      const scriptId = selectedFile.original_id;

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
      setEndpointMetrics([]); // 重置接口指标
      
      // 清空图表数据
      if (rpsChart.current) {
        const option = rpsChart.current.getOption();
        option.series.forEach(series => series.data = []);
        rpsChart.current.setOption(option);
      }

      const response = await axios.post(getApiUrl(API_ENDPOINTS.START_TEST), {
        script_id: scriptId, // 使用原始脚本ID
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
            title="总请求次数"
            value={testMetrics.total_requests || 0}
            suffix="次"
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="失败率"
            value={parseFloat(testMetrics.error_rate || 0).toFixed(2)}
            suffix="%"
            valueStyle={{ color: parseFloat(testMetrics.error_rate) > 5 ? '#cf1322' : '#3f8600' }}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="当前 RPS"
            value={parseFloat(testMetrics.rps || 0).toFixed(1)}
            suffix="次/秒"
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="平均响应时间"
            value={parseFloat(testMetrics.response_time || 0).toFixed(2)}
            suffix="ms"
            valueStyle={{ color: parseFloat(testMetrics.response_time) > 1000 ? '#cf1322' : '#3f8600' }}
          />
        </Card>
      </Col>
    </Row>
  );

  // 渲染测试状态和进度
  const renderTestStatus = () => (
    <div className="test-status">
      <Row gutter={[16, 16]} align="middle">
        <Col flex="auto">
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
        </Col>
        <Col>
          <Statistic 
            title="虚拟用户数" 
            value={testMetrics.vus || 0}
            suffix="VUs" 
            style={{ marginLeft: '16px' }}
          />
        </Col>
        {testStatus === 'completed' && testProgress >= 100 && testReportUrl && (
          <Col>
            <Button 
              type="primary" 
              onClick={() => window.open(testReportUrl, '_blank')}
            >
              查看测试报告
            </Button>
          </Col>
        )}
      </Row>
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

  // 渲染接口指标表格
  const renderEndpointMetrics = () => {
    const columns = [
      {
        title: '接口路径',
        dataIndex: 'endpoint',
        key: 'endpoint',
        width: '28%',
        ellipsis: true,
        render: text => <Tooltip title={text}>{text}</Tooltip>
      },
      {
        title: '请求数',
        dataIndex: 'requests',
        key: 'requests',
        sorter: (a, b) => a.requests - b.requests,
        defaultSortOrder: 'descend',
        render: value => value || 0
      },
      {
        title: '失败数',
        dataIndex: 'failures',
        key: 'failures',
        sorter: (a, b) => a.failures - b.failures,
        render: value => value || 0
      },
      {
        title: '失败率',
        dataIndex: 'failureRate',
        key: 'failureRate',
        sorter: (a, b) => a.failureRate - b.failureRate,
        render: value => `${(parseFloat(value || 0) * 100).toFixed(2)}%`
      },
      {
        title: '平均响应时间',
        dataIndex: 'avgResponseTime',
        key: 'avgResponseTime',
        sorter: (a, b) => a.avgResponseTime - b.avgResponseTime,
        render: value => `${parseFloat(value || 0).toFixed(2)} ms`
      },
      {
        title: '最小响应时间',
        dataIndex: 'minResponseTime',
        key: 'minResponseTime',
        sorter: (a, b) => a.minResponseTime - b.minResponseTime,
        render: value => `${parseFloat(value || 0).toFixed(2)} ms`
      },
      {
        title: '最大响应时间',
        dataIndex: 'maxResponseTime',
        key: 'maxResponseTime',
        sorter: (a, b) => a.maxResponseTime - b.maxResponseTime,
        render: value => `${parseFloat(value || 0).toFixed(2)} ms`
      },
      {
        title: '状态码分布',
        dataIndex: 'statusCodes',
        key: 'statusCodes',
        width: '18%',
        render: (statusCodes) => {
          if (!statusCodes || Object.keys(statusCodes).length === 0) {
            return '-';
          }
          
          // 为不同状态码添加颜色
          const statusItems = Object.entries(statusCodes).map(([code, count]) => {
            let color = 'default';
            if (code.startsWith('2')) {
              color = 'success';
            } else if (code.startsWith('4')) {
              color = 'warning';
            } else if (code.startsWith('5')) {
              color = 'error';
            }
            
            return (
              <Tag color={color} key={code} style={{ marginRight: '5px', marginBottom: '5px' }}>
                {code}: {count}
              </Tag>
            );
          });
          
          return <div style={{ display: 'flex', flexWrap: 'wrap' }}>{statusItems}</div>;
        }
      }
    ];

    return (
      <Card 
        title="接口详情" 
        className="endpoint-metrics-card"
        style={{ marginTop: '20px' }}
      >
        <Table 
          dataSource={endpointMetrics} 
          columns={columns} 
          rowKey="endpoint"
          pagination={endpointMetrics.length > 10 ? { pageSize: 10 } : false}
          size="small"
          scroll={{ x: 'max-content' }}
        />
      </Card>
    );
  };

  // 渲染测试监控区域
  const renderTestMonitoring = () => (
    <div className="test-monitoring">
      {renderTestStatus()}
      {renderMetrics()}
      <Card title="性能指标图表" style={{ marginTop: '20px' }}>
        <div id="metrics-chart" style={{ height: '400px' }} ref={rpsChartRef} />
      </Card>
      {endpointMetrics.length > 0 && renderEndpointMetrics()}
    </div>
  );

  return (
    <Content>
      <div className="test-workbench-container">
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
                          // 检查文件类型
                          // const isJsFile = file.type === 'application/javascript' || file.name.endsWith('.js');
                          // if (!isJsFile) {
                          //   message.error('只能上传 JavaScript (.js) 文件!');
                          //   return false;
                          // }
                          
                          // 添加文件到列表
                          setFileList(prevList => [...prevList, file]);
                          return false;
                        }}
                        onRemove={(file) => {
                          // 从列表中移除文件
                          setFileList(prevList => prevList.filter(item => item.uid !== file.uid));
                        }}
                        multiple={true}
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

                {fileList.length > 0 && (
                  <Card 
                    size="small" 
                    title={`已选择文件 (${fileList.length})`} 
                    style={{ margin: '16px 0' }}
                  >
                    <Table
                      dataSource={fileList}
                      rowKey="uid"
                      size="small"
                      pagination={false}
                      columns={[
                        {
                          title: '文件名',
                          dataIndex: 'name',
                          key: 'name',
                        },
                        {
                          title: '大小',
                          dataIndex: 'size',
                          key: 'size',
                          width: 120,
                          render: (size) => `${(size / 1024).toFixed(2)} KB`,
                        },
                        {
                          title: '操作',
                          key: 'action',
                          width: 100,
                          render: (_, record) => (
                            <Button 
                              type="text" 
                              danger 
                              icon={<DeleteOutlined />} 
                              onClick={() => {
                                setFileList(prevList => prevList.filter(item => item.uid !== record.uid));
                              }}
                              disabled={uploading || testRunning}
                            />
                          ),
                        },
                      ]}
                    />
                  </Card>
                )}
                
                {uploadStatus === 'success' && uploadedFiles.length > 0 && (
                  <>
                    <Form.Item 
                      name="scriptId" 
                      label="选择要测试的脚本" 
                      rules={[{ required: true, message: '请选择要测试的脚本' }]}
                    >
                      <Select placeholder="请选择要测试的脚本">
                        {uploadedFiles.map(file => (
                          <Option key={file.id.toString()} value={file.id.toString()}>
                            {file.name} ({(file.size / 1024).toFixed(2)} KB)
                          </Option>
                        ))}
                      </Select>
                    </Form.Item>

                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item 
                          name="vus"
                          label="并发用户数"
                          rules={[{ required: true, message: '请输入并发用户数' }]}
                          initialValue={1}
                        >
                          <InputNumber min={1} max={100} style={{ width: '100%' }} disabled={testRunning} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item 
                          name="duration"
                          label="测试持续时间(秒)"
                          rules={[{ required: true, message: '请输入测试持续时间' }]}
                          initialValue={30}
                        >
                          <InputNumber min={5} max={3600} style={{ width: '100%' }} disabled={testRunning} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item 
                          name="ramp_time"
                          label="爬坡时间(秒)" 
                          initialValue={0}
                        >
                          <InputNumber min={0} max={600} style={{ width: '100%' }} disabled={testRunning} />
                        </Form.Item>
                      </Col>
                    </Row>

                    <Form.Item>
                      <Space>
                        <Button
                          type="primary"
                          htmlType="submit"
                          loading={loading}
                          disabled={testRunning}
                        >
                          开始测试
                        </Button>
                        {testRunning && currentTestId && (
                          <Button
                            danger
                            onClick={stopTest}
                            loading={loading}
                          >
                            停止测试
                          </Button>
                        )}
                      </Space>
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
                {renderTestMonitoring()}
              </Card>
            </Col>
          )}
        </Row>
      </div>
    </Content>
  );
};

export default TestWorkbench;
