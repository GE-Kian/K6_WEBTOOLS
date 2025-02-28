# K6 Web Tools

一个基于 K6 的性能测试 Web 工具，提供友好的 Web 界面来管理和执行性能测试。

## 功能特点

- 支持上传和管理 K6 测试脚本
- 实时监控测试执行状态和性能指标
- 可视化测试结果展示
- 支持自定义测试参数（VUs、持续时间、渐进加载等）
- 完整的测试报告导出功能

## 技术栈

- 后端：Python + Flask + SocketIO
- 前端：Vue.js + Element UI
- 测试工具：K6

## 安装要求

- Python 3.8+
- Node.js 14+
- K6

## 快速开始

1. 克隆仓库
```bash
git clone [repository-url]
cd K6_webTools
```

2. 安装后端依赖
```bash
cd backend
pip install -r requirements.txt
```

3. 安装前端依赖
```bash
cd frontend
npm install
```

4. 启动后端服务
```bash
cd backend
python app.py
```

5. 启动前端服务
```bash
cd frontend
npm run serve
```

6. 访问应用
打开浏览器访问 `http://localhost:8080`

## 配置说明

可以通过环境变量配置以下参数：

- `K6_SCRIPTS_DIR`: K6 脚本存储目录
- `K6_REPORTS_DIR`: 测试报告存储目录
- `FLASK_ENV`: 运行环境 (development/production)
- `PORT`: 后端服务端口号

## 目录结构

```
K6_webTools/
├── backend/
│   ├── app.py              # 后端主程序
│   ├── k6_manager.py       # K6 管理模块
│   ├── requirements.txt    # Python 依赖
│   └── scripts/           # K6 脚本目录
├── frontend/
│   ├── src/               # 前端源代码
│   ├── public/           # 静态资源
│   └── package.json      # 前端依赖
└── reports/              # 测试报告目录
```

## 开发说明

- 后端开发请遵循 PEP 8 编码规范
- 前端开发请遵循 Vue.js 风格指南
- 提交代码前请运行测试用例

## 许可证

MIT License