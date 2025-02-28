import eventlet
eventlet.monkey_patch()

import os
import sys
import logging
from app import app, socketio

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding=sys.stdout.encoding),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    try:
        # 启动服务器
        port = int(os.getenv('FLASK_PORT', 5000))
        debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        logger.info(f'服务器正在启动，监听端口: {port}, 调试模式: {debug}')
        
        # 使用socketio启动
        socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)
        
        # 备选方法：使用Flask内置的run方法
        # app.run(host='0.0.0.0', port=port, debug=debug)
        
        logger.info('服务器已成功启动')
    except Exception as e:
        logger.error(f'服务器启动失败: {str(e)}', exc_info=True)
        sys.exit(1)
    finally:
        logger.info('服务器已关闭')
