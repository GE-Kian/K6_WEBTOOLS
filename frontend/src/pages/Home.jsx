import React from 'react';
import { Card, Row, Col, Typography } from 'antd';
import { ControlOutlined, HistoryOutlined } from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const Home = () => {
  return (
    <div style={{ padding: '24px' }}>
      <Typography>
        <Title level={2}>欢迎使用 K6 Web性能测试工具</Title>
        <Paragraph>
          这是一个基于 K6 的性能测试平台，帮助您轻松进行性能测试并生成详细的测试报告。
        </Paragraph>
      </Typography>

      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card
            title={<><ControlOutlined /> 测试工作台</>}
            hoverable
          >
            <Paragraph>
              配置并执行性能测试，实时监控测试进度和指标数据。
            </Paragraph>
          </Card>
        </Col>
        <Col span={12}>
          <Card
            title={<><HistoryOutlined /> 历史记录</>}
            hoverable
          >
            <Paragraph>
              查看历史测试记录和详细的测试报告。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Card style={{ marginTop: '24px' }}>
        <Title level={3}>主要功能</Title>
        <ul>
          <li>一键式配置和执行性能测试</li>
          <li>实时监控测试执行状态和性能指标</li>
          <li>自动生成详细的 HTML 测试报告</li>
          <li>查看和管理历史测试记录</li>
          <li>可视化展示测试结果和性能数据</li>
        </ul>
      </Card>
    </div>
  );
};

export default Home; 