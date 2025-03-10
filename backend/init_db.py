import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

def init_database():
    """初始化MySQL数据库"""
    try:
        # 从环境变量获取数据库配置
        db_url = os.getenv('SQLALCHEMY_DATABASE_URI', '')
        if not db_url or not db_url.startswith('mysql://'):
            logger.info('未配置MySQL连接或使用其他数据库，跳过MySQL初始化')
            return

        # 解析数据库URL
        # 格式: mysql://username:password@host:port/database
        db_url = db_url.replace('mysql://', '')
        auth, rest = db_url.split('@')
        username, password = auth.split(':')
        host_port, database = rest.split('/')
        host = host_port.split(':')[0]
        port = int(host_port.split(':')[1]) if ':' in host_port else 3306

        # 首先连接MySQL服务器（不指定数据库）
        connection = mysql.connector.connect(
            host=host,
            user=username,
            password=password,
            port=port
        )

        if connection.is_connected():
            cursor = connection.cursor()
            
            # 创建数据库（如果不存在）
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
            logger.info(f"数据库 '{database}' 创建成功或已存在")

            # 确保使用UTF-8编码
            cursor.execute(f"ALTER DATABASE {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            logger.info(f"数据库 '{database}' 编码设置为 utf8mb4")

            cursor.close()
            connection.close()
            logger.info("数据库初始化完成")

    except Error as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

if __name__ == "__main__":
    init_database() 