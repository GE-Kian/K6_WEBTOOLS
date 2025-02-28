#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit, ConnectionRefusedError, disconnect
from flask_cors import CORS
from datetime import datetime
import os
import json
import logging
from dotenv import load_dotenv
from models import db, TestConfig, TestResult, PerformanceMetric, Script
from k6_manager import K6Manager
from werkzeug.utils import secure_filename
import mysql.connector
import sys
import uuid
import random
import time
import threading
from flask_cors import cross_origin
from engineio.payload import Payload
from gevent import monkey, spawn_later, lock
from collections import defaultdict
monkey.patch_all()

# 增加最大数据包大小
Payload.max_decode_packets = 1000

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding=sys.stdout.encoding),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 文件上传配置
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB限制
ALLOWED_EXTENSIONS = {'js'}
UPLOAD_TIMEOUT = 30  # 30秒超时

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)

# 配置CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = int(os.getenv('DB_POOL_SIZE', 10))
app.config['SQLALCHEMY_MAX_OVERFLOW'] = int(os.getenv('DB_MAX_OVERFLOW', 20))
app.config['SQLALCHEMY_POOL_TIMEOUT'] = int(os.getenv('DB_POOL_TIMEOUT', 30))

# 初始化数据库
db.init_app(app)
with app.app_context():
    try:
        db.create_all()
        logger.info('数据库连接成功并完成初始化')
    except Exception as e:
        logger.error(f'数据库连接或初始化失败: {str(e)}')
        raise

# 配置SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024,  # 1MB
    manage_session=True,
    logger=True,
    engineio_logger=True
)

# 活动连接
active_connections = set()

@socketio.on('connect')
def handle_connect():
    """处理新连接"""
    sid = request.sid
    active_connections.add(sid)
    logger.info(f'客户端已连接: {sid}')
    socketio.emit('connect_response', {
        'status': 'connected',
        'sid': sid,
        'timestamp': datetime.now().isoformat()
    }, room=sid)

@socketio.on('disconnect')
def handle_disconnect():
    """处理断开连接"""
    sid = request.sid
    if sid in active_connections:
        active_connections.remove(sid)
    logger.info(f'客户端已断开: {sid}')

@socketio.on('client_ready')
def handle_client_ready():
    """处理客户端就绪"""
    sid = request.sid
    logger.info(f'客户端就绪: {sid}')
    socketio.emit('server_ready', {
        'status': 'ready',
        'sid': sid,
        'timestamp': datetime.now().isoformat()
    }, room=sid)

@socketio.on('error')
def handle_error(error):
    """处理错误"""
    sid = request.sid
    logger.error(f'Socket错误 (sid: {sid}): {str(error)}')
    socketio.emit('error_response', {
        'error': str(error),
        'sid': sid,
        'timestamp': datetime.now().isoformat()
    }, room=sid)

def broadcast_to_all(event, data):
    """广播消息给所有连接的客户端"""
    socketio.emit(event, {
        **data,
        'timestamp': datetime.now().isoformat()
    })

def broadcast_to_room(event, data, room):
    """广播消息给指定房间的客户端"""
    socketio.emit(event, {
        **data,
        'timestamp': datetime.now().isoformat()
    }, room=room)

def broadcast_metrics(test_id, metrics_data):
    """广播测试指标数据"""
    socketio.emit('test_metrics', {
        'test_id': test_id,
        'data': metrics_data,
        'timestamp': datetime.now().isoformat()
    })

def broadcast_test_status(test_id, status, message=None):
    """广播测试状态更新"""
    socketio.emit('test_status', {
        'test_id': test_id,
        'status': status,
        'message': message,
        'timestamp': datetime.now().isoformat()
    })

# 确保SQLite数据库文件所在目录存在
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'):
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if not os.path.isabs(db_path):  # 如果是相对路径
        db_path = os.path.join(app.root_path, db_path)
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logger.info(f'创建数据库目录: {db_dir}')

# 配置文件上传大小限制和超时
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_TIMEOUT'] = UPLOAD_TIMEOUT

# 初始化K6管理器
k6_manager = K6Manager()

# 确保脚本和报告目录存在
scripts_dir = os.getenv('K6_SCRIPTS_DIR', os.path.join(app.root_path, 'scripts'))
reports_dir = os.getenv('K6_REPORTS_DIR', os.path.join(app.root_path, 'reports'))
os.makedirs(scripts_dir, exist_ok=True)
os.makedirs(reports_dir, exist_ok=True)
logger.info(f'脚本目录: {scripts_dir}')
logger.info(f'报告目录: {reports_dir}')

# API路由
@app.route('/api/scripts', methods=['POST', 'OPTIONS'])
def upload_script():
    """上传测试脚本文件"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        logger.info(f'收到脚本上传请求')
        logger.info(f'请求表单: {request.form}')
        logger.info(f'请求文件: {request.files}')
        
        # 检查是否有文件
        if 'file' not in request.files:
            logger.error('没有文件部分')
            return jsonify({'error': '没有文件部分'}), 400
            
        file = request.files['file']
        logger.info(f'接收到文件: {file.filename}')
        
        # 检查文件名
        if file.filename == '':
            logger.error('没有选择文件')
            return jsonify({'error': '没有选择文件'}), 400
            
        # 检查文件类型
        if not file.filename.endswith('.js'):
            logger.error(f'不支持的文件类型: {file.filename}')
            return jsonify({'error': '只支持.js文件'}), 400
            
        # 安全处理文件名
        filename = secure_filename(file.filename)
        logger.info(f'安全处理后的文件名: {filename}')
        
        # 确保目录存在
        scripts_dir = os.getenv('K6_SCRIPTS_DIR', 'scripts')
        full_scripts_dir = os.path.join(app.root_path, scripts_dir)
        os.makedirs(full_scripts_dir, exist_ok=True)
        logger.info(f'脚本目录: {full_scripts_dir}, 是否存在: {os.path.exists(full_scripts_dir)}')
        
        # 保存文件
        try:
            file_path = os.path.join(full_scripts_dir, filename)
            logger.info(f'尝试保存文件到: {file_path}')
            file.save(file_path)
            logger.info(f'文件已保存到: {file_path}, 文件大小: {os.path.getsize(file_path)} 字节')
        except Exception as e:
            logger.error(f'保存文件失败: {str(e)}', exc_info=True)
            return jsonify({'error': f'保存文件失败: {str(e)}'}), 500
        
        # 创建脚本记录
        try:
            script = Script(
                name=filename,  # 直接使用文件名作为脚本名称
                filename=filename,
                path=file_path
            )
            db.session.add(script)
            db.session.commit()
            logger.info(f'脚本记录已创建: ID={script.id}, 名称={filename}')
        except Exception as e:
            logger.error(f'创建脚本记录失败: {str(e)}', exc_info=True)
            return jsonify({'error': f'创建脚本记录失败: {str(e)}'}), 500
        
        return jsonify({
            'id': script.id,
            'name': script.name,
            'filename': script.filename,
            'path': script.path,
            'description': script.description,
            'created_at': script.created_at.isoformat()
        }), 201
        
    except Exception as e:
        logger.error(f'文件上传处理失败: {str(e)}', exc_info=True)
        return jsonify({'error': f'文件上传处理失败: {str(e)}'}), 500

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    """健康检查接口"""
    if request.method == 'OPTIONS':
        return '', 204
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'k6-web-tools'
    }), 200

@app.route('/api/tests/start', methods=['POST', 'OPTIONS'])
@cross_origin()
def start_test():
    """启动性能测试"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'})

    try:
        data = request.get_json()
        script_id = data.get('script_id')
        vus = data.get('vus', 1)
        duration = data.get('duration', 30)
        ramp_time = data.get('ramp_time', 0)

        if not script_id:
            return jsonify({'success': False, 'message': '缺少脚本ID'}), 400

        # 获取脚本信息
        script = Script.query.get(script_id)
        if not script:
            return jsonify({'success': False, 'message': '脚本不存在'}), 404

        script_path = script.path
        if not os.path.exists(script_path):
            return jsonify({'success': False, 'message': '脚本文件不存在'}), 404

        # 生成测试ID
        test_id = str(uuid.uuid4())

        # 启动测试
        success = k6_manager.start_test(script_path, test_id, vus, duration, ramp_time)
        if success:
            return jsonify({
                'success': True,
                'message': '测试已启动',
                'test_id': test_id
            })
        else:
            return jsonify({'success': False, 'message': '启动测试失败'}), 500

    except Exception as e:
        logger.error(f'启动测试失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tests/stop', methods=['POST', 'OPTIONS'])
@cross_origin()
def stop_test():
    """停止性能测试"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'})

    try:
        # 获取当前运行的测试
        running_tests = k6_manager.get_running_tests()
        if not running_tests:
            return jsonify({'success': False, 'message': '没有正在运行的测试'}), 404

        # 停止所有运行的测试
        for test_id in running_tests:
            k6_manager.stop_test(test_id)

        return jsonify({'success': True, 'message': '测试已停止'})

    except Exception as e:
        logger.error(f'停止测试失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500

# 主程序入口
if __name__ == '__main__':
    # 初始化数据库
    with app.app_context():
        try:
            logger.info('正在初始化数据库...')
            db.create_all()
            logger.info('数据库表已成功初始化')
        except Exception as e:
            logger.error(f'数据库初始化失败: {str(e)}', exc_info=True)
            sys.exit(1)

    # 启动服务器
    port = int(os.getenv('FLASK_PORT', 5001))
    logger.info(f'服务器正在启动，监听端口: {port}')
    
    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False
        )
    except Exception as e:
        logger.error(f'服务器启动失败: {str(e)}', exc_info=True)
        sys.exit(1)