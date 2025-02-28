import React, { useState, useEffect } from 'react';
import { Layout, Menu, Upload, Form, Input, Button, Table, Card, message } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { Line } from '@ant-design/charts';
import io from 'socket.io-client';

const { Header, Content } = Layout;

const HomePage = () => {
  const [form] = Form.useForm();
  const [testResults, setTestResults] = useState([]);
  const [currentMetrics, setCurrentMetrics] = useState([]);
  const [socket, setSocket] = useState(null);

  useEffect(() => {
    // 连接WebSocket
    const newSocket = io('http://localhost:5000');
    setSocket(newSocket);

    newSocket.on('metrics_update', (data) => {
      setCurrentMetrics(prev => [...prev, {
        timestamp: new Date().toISOString(),
        ...data.metrics
      }]);
    });

    return () => newSocket.disconnect();
  }, []);

  const columns = [
    {
      title: '测试ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button onClick={() => generateReport(record.id)}>生成报告</Button>
      ),
    },
  ];

  const uploadProps = {
    name: 'script',
    action: 'http://localhost:5000/api/scripts',
    onChange(info) {
      if (info.file.status === 'done') {
        message.success(`${info.file.name} 上传成功`);
        form.setFieldsValue({ script_path: info.file.response.script_path });
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} 上传失败`);
      }
    },
  };

  const onFinish = async (values) => {
    try {
      const response = await fetch('http://localhost:5000/api/tests', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(values),
      });
      const data = await response.json();
      if (response.ok) {
        message.success('测试启动成功');
        setCurrentMetrics([]);
      } else {
        message.error(data.error || '测试启动失败');
      }
    } catch (error) {
      message.error('请求失败');
    }
  };

  const generateReport = async (resultId) => {
    try {
      const response = await fetch(`http://localhost:5000/api/results/${resultId}/report`);
      const data = await response.json();
      if (response.ok) {
        message.success('报告生成成功');
        window.open(data.report_path, '_blank');
      } else {
        message.error(data.error || '报告生成失败');
      }
    } catch (error) {
      message.error('请求失败');
    }
  };

  return (
    <Layout>
      <Header>
        <div className="logo" />
        <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['1']}>
          <Menu.Item key="1">性能测试</Menu.Item>
        </Menu>
      </Header>
      <Content style={{ padding: '50px' }}>
        <Card title="测试配置" style={{ marginBottom: '20px' }}>
          <Form form={form} onFinish={onFinish}>
            <Form.Item
              label="测试名称"
              name="name"
              rules={[{ required: true, message: '请输入测试名称' }]}
            >
              <Input />
            </Form.Item>
            <Form.Item label="测试脚本" name="script_path">
              <Upload {...uploadProps}>
                <Button icon={<UploadOutlined />}>上传脚本</Button>
              </Upload>
            </Form.Item>
            <Form.Item
              label="虚拟用户数"
              name={['parameters', 'vus']}
              rules={[{ required: true, message: '请输入虚拟用户数' }]}
            >
              <Input type="number" />
            </Form.Item>
            <Form.Item
              label="持续时间(s)"
              name={['parameters', 'duration']}
              rules={[{ required: true, message: '请输入持续时间' }]}
            >
              <Input />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">开始测试</Button>
            </Form.Item>
          </Form>
        </Card>

        <Card title="实时监控" style={{ marginBottom: '20px' }}>
          <Line
            data={currentMetrics}
            xField="timestamp"
            yField="http_req_duration"
            seriesField="status"
          />
        </Card>

        <Card title="测试结果">
          <Table columns={columns} dataSource={testResults} />
        </Card>
      </Content>
    </Layout>
  );
};

export default HomePage;