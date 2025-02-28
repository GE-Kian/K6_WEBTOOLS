import React from 'react';
import { Layout, Menu } from 'antd';
import { Routes, Route, Link } from 'react-router-dom';
import { HomeOutlined, HistoryOutlined, ControlOutlined } from '@ant-design/icons';
import './App.css';

// 导入页面组件
import Home from './pages/Home';
import TestWorkbench from './pages/TestWorkbench';
import TestHistory from './pages/TestHistory';

const { Header, Content, Sider } = Layout;

const App = () => {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <h1 style={{ color: '#fff', margin: 0 }}>K6 Web性能测试工作台</h1>
      </Header>
      <Layout>
        <Sider width={200}>
          <Menu
            mode="inline"
            defaultSelectedKeys={['home']}
            style={{ height: '100%', borderRight: 0 }}
          >
            <Menu.Item key="home" icon={<HomeOutlined />}>
              <Link to="/">首页</Link>
            </Menu.Item>
            <Menu.Item key="workbench" icon={<ControlOutlined />}>
              <Link to="/workbench">测试工作台</Link>
            </Menu.Item>
            <Menu.Item key="history" icon={<HistoryOutlined />}>
              <Link to="/history">历史记录</Link>
            </Menu.Item>
          </Menu>
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/workbench" element={<TestWorkbench />} />
              <Route path="/history" element={<TestHistory />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
};

export default App;