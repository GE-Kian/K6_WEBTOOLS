import React, { useState, useEffect } from 'react';
import { Table, Card, Button, message } from 'antd';
import { getApiUrl, API_ENDPOINTS } from '../config/api';

const TestHistory = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState([]);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const response = await fetch(getApiUrl(API_ENDPOINTS.TEST_HISTORY));
      if (!response.ok) {
        throw new Error('获取历史记录失败');
      }
      const data = await response.json();
      setData(data);
    } catch (error) {
      console.error('Error:', error);
      message.error('获取历史记录失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const viewReport = async (testId) => {
    try {
      const response = await fetch(getApiUrl(API_ENDPOINTS.TEST_REPORT) + `/${testId}`);
      if (!response.ok) {
        throw new Error('获取报告失败');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (error) {
      console.error('Error:', error);
      message.error('获取报告失败: ' + error.message);
    }
  };

  const columns = [
    {
      title: '测试ID',
      dataIndex: 'test_id',
      key: 'test_id',
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      key: 'start_time',
      render: (text) => new Date(text).toLocaleString(),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
    },
    {
      title: '并发用户数',
      dataIndex: 'vus',
      key: 'vus',
    },
    {
      title: '持续时间(秒)',
      dataIndex: 'duration',
      key: 'duration',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Button 
          type="primary" 
          onClick={() => viewReport(record.test_id)}
          disabled={record.status !== 'completed'}
        >
          查看报告
        </Button>
      ),
    },
  ];

  return (
    <Card title="测试历史记录">
      <Table
        columns={columns}
        dataSource={data}
        rowKey="test_id"
        loading={loading}
      />
    </Card>
  );
};

export default TestHistory;