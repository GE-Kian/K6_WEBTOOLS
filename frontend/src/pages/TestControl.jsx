import React, { useState, useEffect } from 'react';
import { Upload, Button, message, Card, Row, Col, Form, InputNumber, Select, Progress } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import axios from 'axios';
import * as echarts from 'echarts';
import { io } from 'socket.io-client';

const { Option } = Select;

// 移除 axios 默认配置
// axios.defaults.baseURL = 'http://localhost:5000';

const ScriptUpload = () => {
    const [form] = Form.useForm();
    const [fileList, setFileList] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploadStatus, setUploadStatus] = useState(''); // 'success' | 'error' | ''
  
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
        form.setFieldsValue({ scriptId: response.data.config_id });
      } catch (error) {
        setUploadStatus('error');
        message.error('上传失败：' + (error.response?.data?.error || error.message));
      } finally {
        setUploading(false);
      }
    };
  
    const handleStartTest = async (values) => {
      if (!form.getFieldValue('scriptId')) {
        message.error('请先上传脚本文件');
        return;
      }
  
      try {
        const testConfig = {
          config_id: form.getFieldValue('scriptId'),
          parameters: {
            duration: `${values.duration}${values.durationUnit}`,
            vus: values.vus,
            rampUp: `${values.rampUp}${values.rampUpUnit}`,
          }
        };
  
        const response = await axios.post('/api/tests', testConfig);
        message.success('测试已启动');
        window.location.href = '/monitor';
      } catch (error) {
        message.error('启动测试失败：' + (error.response?.data?.error || error.message));
      }
    };
  
    const beforeUpload = (file) => {
      // 只检查文件扩展名，不检查MIME类型
      const isJS = file.name.endsWith('.js');
      if (!isJS) {
        message.error('只能上传 JavaScript 文件！');
      }
      const isLt2M = file.size / 1024 / 1024 < 2;
      if (!isLt2M) {
        message.error('文件大小不能超过 2MB！');
      }
      return isJS && isLt2M;
    };
  
    const handleChange = (info) => {
      setFileList(info.fileList.slice(-1));
      // 重置上传状态
      setUploadProgress(0);
      setUploadStatus('');
    };
  
    return (
      <div>
        <h2>上传性能测试脚本</h2>
        <Form
          form={form}
          onFinish={handleStartTest}
          layout="vertical"
        >
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
              <div style={{ marginTop: 8 }}>
                <Progress
                  percent={uploadProgress}
                  status={uploadStatus === 'error' ? 'exception' : 
                         uploadStatus === 'success' ? 'success' : 'active'}
                  size="small"
                />
              </div>
            )}
            <Form.Item
              name="scriptId"
              hidden
            >
              <InputNumber />
            </Form.Item>
          </Form.Item>
  
          <Form.Item
            label="压测时长"
            required
            style={{ marginBottom: 0 }}
          >
            <Form.Item
              name="duration"
              rules={[{ required: true, message: '请输入压测时长' }]}
              style={{ display: 'inline-block', width: 'calc(60% - 8px)' }}
            >
              <InputNumber min={1} placeholder="压测持续时间" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="durationUnit"
              initialValue="s"
              style={{ display: 'inline-block', width: '40%', marginLeft: 8 }}
            >
              <Select>
                <Option value="s">秒</Option>
                <Option value="m">分钟</Option>
                <Option value="h">小时</Option>
              </Select>
            </Form.Item>
          </Form.Item>
  
          <Form.Item
            name="vus"
            label="并发用户数"
            rules={[{ required: true, message: '请输入并发用户数' }]}
            tooltip="模拟的并发虚拟用户数量"
          >
            <InputNumber min={1} max={1000} style={{ width: '100%' }} placeholder="请输入并发用户数" />
          </Form.Item>
  
          <Form.Item
            label="爬坡时间"
            required
            style={{ marginBottom: 0 }}
            tooltip="从0增长到目标并发数所需时间"
          >
            <Form.Item
              name="rampUp"
              rules={[{ required: true, message: '请输入爬坡时间' }]}
              style={{ display: 'inline-block', width: 'calc(60% - 8px)' }}
            >
              <InputNumber min={0} placeholder="爬坡时间" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="rampUpUnit"
              initialValue="s"
              style={{ display: 'inline-block', width: '40%', marginLeft: 8 }}
            >
              <Select>
                <Option value="s">秒</Option>
                <Option value="m">分钟</Option>
              </Select>
            </Form.Item>
          </Form.Item>
  
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              开始测试
            </Button>
          </Form.Item>
        </Form>
      </div>
    );
  };

// 导出 ScriptUpload 组件供其他模块使用
export { ScriptUpload };

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
        avgResponseTime: data.avgResponseTime
      });
  
      setEndpointMetrics(data.endpoints);
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
              <Statistic title="当前RPS" value={metrics.currentRPS} precision={2} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic title="平均响应时间(ms)" value={metrics.avgResponseTime} precision={2} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="失败率(%)"
                value={metrics.failureRate}
                precision={2}
                suffix="%"
              />
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