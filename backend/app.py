from gevent import monkey
monkey.patch_all()

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit, ConnectionRefusedError, disconnect
from flask_cors import CORS
from datetime import datetime
import os
import json
import logging
from dotenv import load_dotenv
from models import db, TestConfig, TestResult, PerformanceMetric, Script
from k6_manager import k6_manager
from werkzeug.utils import secure_filename
import mysql.connector
import sys
import uuid
import random
import time
import threading
from flask_cors import cross_origin
from engineio.payload import Payload
from gevent import spawn_later, lock
from collections import defaultdict
from broadcast import init_socketio

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
# ALLOWED_EXTENSIONS = {'js'}
UPLOAD_TIMEOUT = 30  # 30秒超时

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)

# 配置CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# 确保必要的目录存在
data_dir = os.path.join(app.root_path, 'data')
scripts_dir = os.path.join(app.root_path, 'scripts')
reports_dir = os.path.join(app.root_path, 'reports')

for directory in [data_dir, scripts_dir, reports_dir]:
    if not os.path.exists(directory):
        os.makedirs(directory)
        logger.info(f'创建目录: {directory}')

# 数据库配置
db_uri = os.getenv('DATABASE_URL')
if not db_uri:
    logger.error('未找到数据库配置，请检查 .env 文件中的 DATABASE_URL')
    raise ValueError('未找到数据库配置')

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = int(os.getenv('DB_POOL_SIZE', 10))
app.config['SQLALCHEMY_MAX_OVERFLOW'] = int(os.getenv('DB_MAX_OVERFLOW', 20))
app.config['SQLALCHEMY_POOL_TIMEOUT'] = int(os.getenv('DB_POOL_TIMEOUT', 30))

# 初始化数据库
db.init_app(app)
with app.app_context():
    try:
        # 创建新的表结构
        db.create_all()
        logger.info('数据库连接成功并完成初始化')
    except Exception as e:
        logger.error(f'数据库连接或初始化失败: {str(e)}')
        if 'mysql' in str(e).lower():
            logger.error('MySQL连接失败。请确保：\n'
                        '1. MySQL服务已启动\n'
                        '2. 数据库已创建\n'
                        '3. 用户名和密码正确\n'
                        '4. 数据库主机可访问')
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

# 初始化广播功能
init_socketio(socketio)

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

# 配置文件上传大小限制和超时
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['UPLOAD_TIMEOUT'] = UPLOAD_TIMEOUT

# 初始化k6_manager
k6_manager.init_app(
    app,
    scripts_dir=scripts_dir,
    reports_dir=reports_dir
)

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
        if 'file' in request.files:
            # 单文件上传
            files = [request.files['file']]
            logger.info(f'接收到单个文件: {files[0].filename}')
        elif 'files[]' in request.files:
            # 多文件上传
            files = request.files.getlist('files[]')
            logger.info(f'接收到多个文件: {len(files)}个')
        else:
            logger.error('没有文件部分')
            return jsonify({'error': '没有文件部分'}), 400
        
        if len(files) == 0 or all(f.filename == '' for f in files):
            logger.error('没有选择文件')
            return jsonify({'error': '没有选择文件'}), 400
        
        # 获取第一个有效文件名作为文件夹名称的基础
        main_filename = None
        for file in files:
            if file.filename and file.filename != '':
                main_filename = os.path.splitext(file.filename)[0]
                break
                
        if not main_filename:
            main_filename = "script"
            
        # 创建以第一个文件名为基础的文件夹名称
        folder_name = f"{main_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 确保目录存在
        scripts_dir = os.getenv('K6_SCRIPTS_DIR', 'scripts')
        full_scripts_dir = os.path.join(app.root_path, scripts_dir)
        folder_path = os.path.join(full_scripts_dir, folder_name)
        dist_dir = os.path.join(folder_path, 'dist')  # 添加dist目录
        
        # 创建必要的目录
        for directory in [full_scripts_dir, folder_path, dist_dir]:
            os.makedirs(directory, exist_ok=True)
            logger.info(f'确保目录存在: {directory}')
        
        # 保存所有文件
        saved_files = []
        main_file = None
        
        for file in files:
            # 检查文件名
            if file.filename == '':
                continue
                
            # 安全处理文件名
            filename = secure_filename(file.filename)
            
            # 检查文件类型
            if not (filename.endswith('.js') or filename.endswith('.json')):
                logger.warning(f'跳过不支持的文件类型: {filename}')
                continue
                
            logger.info(f'处理文件: {filename}')
            
            # 保存文件
            try:
                file_path = os.path.join(folder_path, filename)
                logger.info(f'尝试保存文件到: {file_path}')
                file.save(file_path)
                logger.info(f'文件已保存到: {file_path}, 文件大小: {os.path.getsize(file_path)} 字节')
                
                saved_files.append({
                    'name': filename,
                    'path': file_path
                })
                
                # 第一个JS文件作为主文件
                if main_file is None and filename.endswith('.js'):
                    main_file = {
                        'name': filename,
                        'path': file_path
                    }
                
            except Exception as e:
                logger.error(f'保存文件失败: {str(e)}', exc_info=True)
                return jsonify({'error': f'保存文件失败: {str(e)}'}), 500
        
        if not saved_files:
            logger.error('没有成功保存任何文件')
            return jsonify({'error': '没有成功保存任何文件'}), 400
            
        if main_file is None:
            main_file = saved_files[0]
        
        # 检查并创建crypto-bundle.js在同一目录
        crypto_bundle_path = os.path.join(folder_path, 'crypto-bundle.js')
        if not os.path.exists(crypto_bundle_path):
            with open(crypto_bundle_path, 'w', encoding='utf-8') as f:
                f.write('// Crypto bundle placeholder\n')
            logger.info(f'创建crypto-bundle.js: {crypto_bundle_path}')
            
        # 创建user.json文件
        user_json_path = os.path.join(folder_path, 'user.json')
        if not os.path.exists(user_json_path):
            default_user_data = {
                "baseUrl": "http://localhost:8080",
                "users": [
                    {"username": "testuser1", "password": "password123"},
                    {"username": "testuser2", "password": "password123"}
                ],
                "thinkTime": {
                    "min": 1,
                    "max": 3
                }
            }
            with open(user_json_path, 'w', encoding='utf-8') as f:
                json.dump(default_user_data, f, ensure_ascii=False, indent=2)
            logger.info(f'创建默认user.json文件: {user_json_path}')
            
        # 创建脚本记录
        try:
            script = Script(
                name=main_file['name'],
                filename=main_file['name'],
                path=main_file['path'],
                folder_path=folder_path,
                folder_name=folder_name,
                dependencies={
                    'crypto_bundle': crypto_bundle_path,
                    'files': [f['name'] for f in saved_files]
                }
            )
            db.session.add(script)
            db.session.commit()
            logger.info(f'脚本记录已创建: ID={script.id}, 名称={main_file["name"]}, 文件夹={folder_name}')
        except Exception as e:
            logger.error(f'创建脚本记录失败: {str(e)}', exc_info=True)
            return jsonify({'error': f'创建脚本记录失败: {str(e)}'}), 500
        
        return jsonify({
            'id': script.id,
            'name': script.name,
            'filename': script.filename,
            'path': script.path,
            'folder_path': script.folder_path,
            'folder_name': script.folder_name,
            'description': script.description,
            'created_at': script.created_at.isoformat(),
            'dependencies': script.dependencies,
            'files': [f['name'] for f in saved_files]
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

@app.route('/api/tests/start', methods=['POST'])
def start_test():
    try:
        data = request.get_json()
        script_id = data.get('script_id')
        config = {
            'vus': data.get('vus', 1),
            'duration': data.get('duration', 30),
            'ramp_time': data.get('ramp_time')
        }
        
        app.logger.info(f"收到测试启动请求: {data}")
        app.logger.info(f"启动测试: 脚本ID={script_id}, 配置={config}")

        test_id, process = k6_manager.start_test(script_id, config)
        
        if test_id is None:
            return jsonify({
                'status': 'error',
                'message': '启动测试失败'
            }), 500

        return jsonify({
            'status': 'success',
            'test_id': test_id
        }), 201

    except Exception as e:
        app.logger.error(f"启动测试失败: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/tests/stop', methods=['POST', 'OPTIONS'])
def stop_test():
    """停止性能测试"""
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()
        logger.info(f'收到测试停止请求: {data}')
        
        # 获取请求中的test_id
        test_id = data.get('test_id')
        
        # 直接尝试停止指定的测试，不检查是否在运行列表中
        if test_id:
            logger.info(f'尝试停止测试: {test_id}')
            result = k6_manager.stop_test(test_id)
            if result:
                return jsonify({'success': True, 'message': f'测试 {test_id} 已停止'})
            else:
                # 即使测试不在运行列表中，也返回成功，因为最终目标是确保测试不在运行
                return jsonify({'success': True, 'message': f'测试 {test_id} 不在运行中或已停止'})
        else:
            # 停止所有运行的测试
            running_tests = k6_manager.get_running_tests()
            logger.info(f'停止所有测试: {running_tests}')
            for test_id in running_tests:
                k6_manager.stop_test(test_id)
            return jsonify({'success': True, 'message': '所有测试已停止'})

    except Exception as e:
        logger.error(f'停止测试失败: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@socketio.on('connect', namespace='/ws/metrics')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect', namespace='/ws/metrics')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('join', namespace='/ws/metrics')
def handle_join(test_id):
    k6_manager.add_websocket_client(request.sid)
    emit('joined', {'test_id': test_id})

# 主程序入口
if __name__ == '__main__':
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