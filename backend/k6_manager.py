import os
import json
import subprocess
import logging
import re
import io
import shutil
import uuid
import math
import errno
from datetime import datetime
import threading
import time
import queue
from threading import Thread, Event
import tempfile
import urllib.parse

from flask import request, current_app as app
from models import db, Script, TestResult, PerformanceMetric
from broadcast import broadcast_metrics, broadcast_test_status

logger = logging.getLogger(__name__)


class K6MonitorService:
    """
    K6 测试监控服务，负责监控和管理测试状态
    """
    # 定义状态常量
    STATUS_IDLE = 'idle'
    STATUS_RUNNING = 'running'
    STATUS_STOPPED = 'stopped'
    STATUS_ERROR = 'error'
    STATUS_FAILED = 'failed'
    STATUS_PAUSED = 'paused'

    # 定义有效的状态转换
    _VALID_TRANSITIONS = {
        STATUS_IDLE: [STATUS_RUNNING, STATUS_ERROR],
        STATUS_RUNNING: [STATUS_STOPPED, STATUS_ERROR, STATUS_FAILED, STATUS_PAUSED],
        STATUS_STOPPED: [STATUS_IDLE, STATUS_ERROR],
        STATUS_ERROR: [STATUS_IDLE],
        STATUS_FAILED: [STATUS_IDLE],
        STATUS_PAUSED: [STATUS_RUNNING, STATUS_STOPPED, STATUS_ERROR]
    }

    def __init__(self):
        """初始化监控服务"""
        self.status = self.STATUS_IDLE
        self.current_test_id = None
        self.monitor_thread = None
        self.stop_event = Event()
        self.metrics_queue = queue.Queue()
        self.last_metrics = {}

    def start_monitoring(self, test_id):
        """
        启动监控
        
        Args:
            test_id: 测试ID
        """
        if self.status == self.STATUS_RUNNING:
            logger.warning(f'Monitor already running for test: {self.current_test_id}')
            return False

        # 设置状态
        self._transition_to(self.STATUS_RUNNING)
        self.current_test_id = test_id
        self.stop_event.clear()

        # 启动监控线程
        self.monitor_thread = Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        logger.info(f'Started monitoring for test: {test_id}')
        return True

    def stop_monitoring(self):
        """停止监控"""
        if self.status != self.STATUS_RUNNING:
            return False

        # 设置停止事件
        self.stop_event.set()

        # 等待线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        # 设置状态
        self._transition_to(self.STATUS_STOPPED)
        self.current_test_id = None

        logger.info('Stopped monitoring')
        return True

    def _monitor_loop(self):
        """监控循环"""
        try:
            while not self.stop_event.is_set():
                # 检查测试状态
                if self.current_test_id:
                    # 处理队列中的指标
                    self._process_metrics_queue()

                # 等待一段时间
                self.stop_event.wait(1.0)
        except Exception as e:
            logger.error(f'Monitor loop error: {str(e)}')
            self._transition_to(self.STATUS_ERROR)

    def _process_metrics_queue(self):
        """处理指标队列"""
        try:
            # 处理队列中的所有指标
            while not self.metrics_queue.empty():
                metric = self.metrics_queue.get_nowait()
                self.last_metrics[metric['name']] = metric['value']
                # 可以在这里添加更多处理逻辑
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f'Error processing metrics queue: {str(e)}')

    def _transition_to(self, new_status):
        """
        转换状态
        
        Args:
            new_status: 新状态
        """
        if new_status not in self._VALID_TRANSITIONS.get(self.status, []):
            logger.warning(f'Invalid status transition: {self.status} -> {new_status}')
            return False

        self.status = new_status
        return True


class K6Monitor:
    def __init__(self):
        self.clients = set()
        self.logger = logging.getLogger('k6_manager')

    def broadcast_metrics(self, test_id, data):
        """广播测试指标数据"""
        try:
            # 确保数据格式正确
            if isinstance(data, dict):
                # 添加必要的字段
                data['test_id'] = test_id
                data['timestamp'] = datetime.now().isoformat()
                
                # 导入broadcast模块的函数来发送消息
                from broadcast import broadcast_metrics
                
                self.logger.info(f"Broadcasting metrics via Socket.IO - Test ID: {test_id}")
                self.logger.debug(f"Broadcast data: {data}")
                
                # 使用broadcast模块的函数发送数据
                broadcast_metrics(data)
            else:
                self.logger.error(f"Invalid data format for broadcasting: {data}")
                
        except Exception as e:
            self.logger.error(f"Error broadcasting metrics: {str(e)}")
            self.logger.exception(e)


class K6Manager:
    # 定义状态常量
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_STOPPED = 'stopped'
    STATUS_ERROR = 'error'

    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(K6Manager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        self.app = None
        self.k6_path = 'k6'  # 直接使用k6命令
        self.scripts_dir = 'scripts'
        self.reports_dir = 'reports'
        self.active_tests = {}
        self.logger = logging.getLogger('k6_manager')
        self.monitor = K6Monitor()
        self.initialized = True
        self.encoding = 'utf-8'

    def init_app(self, app, k6_path=None, scripts_dir=None, reports_dir=None):
        """初始化应用配置"""
        self.app = app
        if k6_path:
            self.k6_path = k6_path
        if scripts_dir:
            self.scripts_dir = scripts_dir
        if reports_dir:
            self.reports_dir = reports_dir
        
        self.logger.info(f"K6 Manager initialized with k6_path: {self.k6_path}")
        self.logger.info(f"K6 Manager initialized with app: scripts_dir={self.scripts_dir}, reports_dir={self.reports_dir}")

    def _create_process(self, cmd):
        """创建子进程的通用方法"""
        try:
            # 检查k6命令是否可用
            try:
                result = subprocess.run(['k6', 'version'], capture_output=True, text=True)
                self.logger.info(f"K6版本信息: {result.stdout}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"k6 command check failed: {str(e)}")
                self.logger.error(f"Error output: {e.stderr}")
                return None
            except Exception as e:
                self.logger.error(f"k6 command not found or not executable: {str(e)}")
                return None
            
            # 处理命令中的路径，确保包含空格的路径被正确引用
            if os.name == 'nt':  # Windows
                # Windows下使用列表形式传递命令
                self.logger.info(f"执行命令: {' '.join(cmd)}")
                
                # 使用subprocess.STARTUPINFO来隐藏控制台窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                process_args = {
                    'args': cmd,
                    'shell': False,
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE,
                    'text': True,
                    'encoding': self.encoding,
                    'errors': 'replace',
                    'bufsize': 1,
                    'universal_newlines': True,
                    'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP,
                    'startupinfo': startupinfo
                }
            else:  # Linux/Unix
                self.logger.info(f"执行命令: {' '.join(cmd)}")
                process_args = {
                    'args': cmd,
                    'shell': False,
                    'stdout': subprocess.PIPE,
                    'stderr': subprocess.PIPE,
                    'text': True,
                    'encoding': self.encoding,
                    'errors': 'replace',
                    'bufsize': 1,
                    'universal_newlines': True
                }
            
            # 创建进程
            process = subprocess.Popen(**process_args)
            
            # 检查进程是否成功创建
            if process.poll() is not None:
                self.logger.error("进程创建失败，立即退出")
                error_output = process.stderr.read()
                if error_output:
                    self.logger.error(f"错误输出: {error_output}")
                return None
                
            self.logger.info(f"进程创建成功，PID: {process.pid}")
            return process
            
        except PermissionError as e:
            self.logger.error(f"权限错误: {str(e)}")
            self.logger.error("请确保有权限执行k6命令")
            return None
        except Exception as e:
            self.logger.error(f"创建进程失败: {str(e)}")
            self.logger.exception(e)
            return None

    def _read_output(self, pipe, file):
        """读取进程输出并写入文件"""
        try:
            for line in pipe:
                file.write(line)
                file.flush()  # 确保立即写入
        except Exception as e:
            self.logger.error(f"读取输出失败: {str(e)}")
            self.logger.exception(e)

    def start_test(self, script_id, config):
        """启动k6测试"""
        if not self.app:
            self.logger.error("K6Manager not properly initialized. Call init_app first.")
            return None, None

        try:
            # 获取脚本路径
            from models import Script, db, TestResult
            with self.app.app_context():
                script = Script.query.get(script_id)
                if not script:
                    self.logger.error(f"Script not found: {script_id}")
                    return None, None
                
                # 使用完整的脚本路径
                script_path = os.path.join(os.getcwd(), self.scripts_dir, script.path)
                if not os.path.exists(script_path):
                    self.logger.error(f"Script file not found: {script_path}")
                    return None, None

                # 创建测试记录
                test_result = TestResult(
                    script_id=script_id,
                    status=TestResult.STATUS_RUNNING,
                    start_time=datetime.now(),
                    config=config
                )
                db.session.add(test_result)
                db.session.commit()
                test_id = test_result.id

            # 确保报告目录存在
            os.makedirs(self.reports_dir, exist_ok=True)

            # 构建k6命令
            k6_cmd = self._build_k6_command(config, script_path, test_id)
            self.logger.info(f"K6 command: {' '.join(k6_cmd)}")
            
            # 创建进程
            process = self._create_process(k6_cmd)
            if not process:
                return None, None

            self.active_tests[test_id] = {
                'process': process,
                'start_time': datetime.now(),
                'duration': config.get('duration', 30),
                'status': TestResult.STATUS_RUNNING,
                'stdout_file': None,
                'stderr_file': None,
                'last_read_position': 0  # 添加文件读取位置记录
            }

            # 启动监控线程
            monitor_thread = threading.Thread(
                target=self._monitor_test,
                args=(test_id,),
                daemon=True
            )
            monitor_thread.start()

            return test_id, process

        except Exception as e:
            self.logger.error(f"启动测试失败: {str(e)}")
            return None, None

    def _build_k6_command(self, config, script_path, test_id):
        """构建k6命令"""
        # 初始化k6命令
        k6_cmd = [self.k6_path, 'run']
        
        # 添加JSON输出标志，以便能够解析进度
        k6_cmd.extend(['--out', 'json'])
        
        # 添加并发用户数量
        vus = int(config.get('vus', 1))
        
        # 添加持续时间
        duration = int(config.get('duration', 30))
        
        # 保存配置信息到活动测试字典
        self.active_tests[test_id] = {
            'vus': vus,
            'duration': duration
        }
        
        # 构建输出文件路径
        summary_file = os.path.join(self.reports_dir, f"test_{test_id}_summary.json")

        # 确保k6路径正确
        k6_path = self.k6_path
        if os.name == 'nt':  # Windows
            k6_path = k6_path.strip('"')  # 移除可能存在的引号
            if ' ' in k6_path:
                k6_path = f'"{k6_path}"'  # 如果路径包含空格，添加引号

        # 构建基本命令
        k6_cmd = [
            k6_path,
            'run',
            '--vus', str(vus),
            '--out', 'json=-',  # 输出JSON格式到标准输出
            '--summary-export', summary_file
        ]

        # 添加阶段配置
        if config.get('ramp_time'):
            k6_cmd.extend([
                '--stage', f"0s:{vus}",
                '--stage', f"{config['ramp_time']}s:{vus}",
                '--stage', f"{duration}s:{vus}"
            ])
        else:
            k6_cmd.extend(['--duration', f"{duration}s"])

        # 添加脚本路径
        if os.name == 'nt' and ' ' in script_path:
            script_path = f'"{script_path}"'
        k6_cmd.append(script_path)

        # 记录完整命令
        self.logger.info(f"构建的k6命令: {' '.join(k6_cmd)}")

        return k6_cmd

    def _monitor_test(self, test_id):
        """监控测试进程并更新状态"""
        if test_id not in self.active_tests:
            self.logger.error(f"找不到测试ID: {test_id}")
            return

        test_info = self.active_tests[test_id]
        process = test_info['process']
        total_duration = float(test_info['duration'])  # 确保是浮点数
        configured_vus = int(test_info.get('vus', 0))  # 获取配置的VU数量

        # 初始化指标
        metrics = {
            'vus': configured_vus,  # 使用配置的VU数量初始化，而不是0
            'http_reqs': 0,
            'http_req_duration_avg': 0.0,
            'error_rate': 0.0,
            'iterations': 0,
            'total_requests': 0,
            'total_duration': 0.0,
            'failed_requests': 0,
            'last_update_time': time.time(),
            'start_time': time.time(),
            'endpoints': {}
        }

        try:
            # 初始化时发送一次状态更新
            self._broadcast_metrics(test_id, 0, metrics)
            self.logger.info(f"Started monitoring test {test_id}")
            
            # 创建非阻塞的读取器
            output_queue = queue.Queue()
            error_queue = queue.Queue()

            def read_output(pipe, queue):
                try:
                    for line in pipe:
                        line = line.strip()
                        if line:  # 只处理非空行
                            queue.put(line)
                except Exception as e:
                    self.logger.error(f"读取输出失败: {str(e)}")

            # 启动输出读取线程
            stdout_thread = threading.Thread(target=read_output, args=(process.stdout, output_queue))
            stderr_thread = threading.Thread(target=read_output, args=(process.stderr, error_queue))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            # 监控循环
            last_broadcast_time = time.time()
            broadcast_interval = 0.5  # 每0.5秒广播一次
            
            while process.poll() is None:
                current_time = time.time()
                elapsed_time = current_time - metrics['start_time']
                
                # 计算进度
                progress = min(99.9, (elapsed_time / total_duration) * 100)  # 防止提前显示100%
                
                # 最终完成时强制设为100%
                if process.poll() is not None:
                    progress = 100.0
                
                # 处理标准输出
                metrics_updated = False
                while not output_queue.empty():
                    try:
                        line = output_queue.get_nowait()
                        if line:
                            try:
                                data = json.loads(line)
                                if isinstance(data, dict) and 'type' in data:
                                    self._update_metrics(data, metrics)
                                    metrics_updated = True
                                    self.logger.debug(f"Updated metrics: {metrics}")
                            except json.JSONDecodeError:
                                if not line.startswith('running'):  # 忽略运行状态输出
                                    self.logger.debug(f"Non-JSON output: {line}")
                    except queue.Empty:
                        break
                    except Exception as e:
                        self.logger.error(f"处理输出失败: {str(e)}")

                # 处理错误输出
                while not error_queue.empty():
                    try:
                        error = error_queue.get_nowait()
                        if error:
                            self.logger.error(f"Error output: {error}")
                    except queue.Empty:
                        break

                # 定期广播更新或在指标更新时广播
                if metrics_updated or current_time - last_broadcast_time >= broadcast_interval:
                    self.logger.debug(f"Broadcasting metrics - Progress: {progress}%, Metrics: {metrics}")
                    self._broadcast_metrics(test_id, progress, metrics)
                    last_broadcast_time = current_time

                time.sleep(0.1)  # 减少CPU使用

            # 测试完成，发送最终状态
            final_progress = 100
            self._broadcast_metrics(test_id, final_progress, metrics)
            
            # 等待输出读取线程结束
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            # 处理测试完成
            return_code = process.returncode
            self.logger.info(f"Test process ended, return code: {return_code}")
            self.logger.info(f"Final metrics: {metrics}")
            self._handle_test_completion(test_id, return_code)

        except Exception as e:
            self.logger.error(f"监控测试失败: {str(e)}")
            self.logger.exception(e)
            self._handle_test_completion(test_id, -1)

    def _update_metrics(self, data, metrics):
        """更新测试指标"""
        try:
            # 获取指标名称和值
            metric_name = data.get('metric')
            metric_type = data.get('type')
            metric_value = data.get('data', {}).get('value', 0)
            
            self.logger.debug(f"Processing metric: {metric_name}, type: {metric_type}, value: {metric_value}")
            
            # 初始化endpoint统计数据结构
            if 'endpoints' not in metrics:
                metrics['endpoints'] = {}
                
            # 获取请求的URL信息
            url = data.get('data', {}).get('tags', {}).get('url', '')
            method = data.get('data', {}).get('tags', {}).get('method', '')
            name = data.get('data', {}).get('tags', {}).get('name', '')
            status = data.get('data', {}).get('status', 0)
            
            # 如果有URL信息，更新端点统计
            if url:
                # 解析URL，只提取路径部分
                try:
                    # 如果是完整URL，解析并提取路径
                    if url.startswith('http'):
                        parsed_url = urllib.parse.urlparse(url)
                        endpoint_key = parsed_url.path
                    else:
                        # 如果已经是路径，去除可能的查询参数
                        endpoint_key = url.split('?')[0]
                except Exception as e:
                    self.logger.warning(f"解析URL失败: {url}, {str(e)}")
                    endpoint_key = url
                
                # 确保这个端点的数据结构存在
                if endpoint_key not in metrics['endpoints']:
                    metrics['endpoints'][endpoint_key] = {
                        'requests': 0,
                        'failed': 0,
                        'total_duration': 0,
                        'min_duration': float('inf'),
                        'max_duration': 0,
                        'avg_duration': 0,
                        'status_codes': {},
                        'response_times': []  # 用于存储所有响应时间值，计算90%响应时间
                    }
                
                endpoint = metrics['endpoints'][endpoint_key]
                
                # 更新端点统计 - 只在指标类型为Point时更新，避免重复计数
                if metric_name == 'http_reqs' and metric_type == 'Point':
                    endpoint['requests'] += 1
                    
                    # 更新状态码统计
                    if status > 0:
                        status_str = str(status)
                        endpoint['status_codes'][status_str] = endpoint['status_codes'].get(status_str, 0) + 1
                        
                        # 标记失败的请求 (5xx状态码)
                        if 500 <= status < 600:
                            endpoint['failed'] += 1
                
                elif metric_name == 'http_req_duration' and metric_type == 'Point':
                    endpoint['total_duration'] += metric_value
                    endpoint['min_duration'] = min(endpoint['min_duration'], metric_value)
                    endpoint['max_duration'] = max(endpoint['max_duration'], metric_value)
                    # 保存响应时间值，用于计算90%响应时间
                    endpoint['response_times'].append(metric_value)
                    if endpoint['requests'] > 0:
                        endpoint['avg_duration'] = endpoint['total_duration'] / endpoint['requests']
                
                elif metric_name == 'http_req_failed' and metric_value and metric_type == 'Point':
                    endpoint['failed'] += 1
            
            # 根据指标类型更新metrics字典 (整体统计)
            if metric_name == 'vus' and metric_type == 'Gauge':
                # k6有时使用Gauge类型（而不是Point类型）来报告虚拟用户数量
                metrics['vus'] = int(metric_value)
                self.logger.debug(f"Updated VUs from k6 metric: {metrics['vus']}")
            elif metric_name == 'vus':
                metrics['vus'] = int(metric_value)
                self.logger.debug(f"Updated VUs: {metrics['vus']}")
            
            # 根据指标类型更新metrics字典 (整体统计)
            if metric_name == 'http_reqs':
                # 只在指标类型为Point时更新，避免重复计数
                if metric_type == 'Point':
                    # 增加请求计数
                    current_reqs = metrics.get('http_reqs', 0)
                    metrics['http_reqs'] = current_reqs + 1
                    metrics['total_requests'] = metrics['http_reqs']
                    self.logger.debug(f"Updated requests: {metrics['http_reqs']}")
                
            elif metric_name == 'http_req_duration':
                if metric_type == 'Point':
                    current_total = metrics.get('total_duration', 0)
                    current_count = max(1, metrics.get('http_reqs', 1))
                    metrics['total_duration'] = current_total + metric_value
                    metrics['http_req_duration_avg'] = metrics['total_duration'] / current_count
                    self.logger.debug(f"Updated avg duration: {metrics['http_req_duration_avg']}")
                
            elif metric_name == 'http_req_failed':
                if metric_value and metric_type == 'Point':
                    metrics['failed_requests'] = metrics.get('failed_requests', 0) + 1
                    current_total = max(1, metrics.get('http_reqs', 1))
                    metrics['error_rate'] = (metrics['failed_requests'] / current_total) * 100
                    self.logger.debug(f"Updated error rate: {metrics['error_rate']}%")
                
            elif metric_name == 'iterations':
                metrics['iterations'] = metrics.get('iterations', 0) + 1
                self.logger.debug(f"Updated iterations: {metrics['iterations']}")
            
            # 添加错误请求统计
            if 500 <= int(data.get('data', {}).get('status', 200)) < 600:
                metrics['failed_requests'] = metrics.get('failed_requests', 0) + 1
            
            # 更新错误率计算
            total_requests = metrics.get('http_reqs', 1)
            failed = metrics.get('failed_requests', 0)
            metrics['error_rate'] = (failed / total_requests) * 100 if total_requests > 0 else 0
            
            # 更新时间戳
            metrics['last_update_time'] = time.time()
            
            self.logger.info(f"Metrics updated: {metrics}")
            
        except Exception as e:
            self.logger.error(f"更新指标失败: {str(e)}")
            self.logger.exception(e)

    def _broadcast_metrics(self, test_id, progress, metrics):
        """广播测试指标"""
        try:
            # 计算并格式化指标
            test_duration = max(0.001, (time.time() - metrics.get('start_time', time.time())))
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 计算RPS (限制最大值为1000，避免不合理的数值)
            rps = min(1000, metrics.get('total_requests', 0) / test_duration)
            
            # 转换端点数据
            endpoints_data = []
            for endpoint, data in metrics.get('endpoints', {}).items():
                requests = data.get('requests', 0)
                failures = data.get('failed', 0)
                
                # 计算90%响应时间
                p90_response_time = 0
                if data.get('response_times'):
                    # 对响应时间进行排序
                    sorted_times = sorted(data['response_times'])
                    # 计算90%位置的索引
                    idx = int(len(sorted_times) * 0.9)
                    if idx < len(sorted_times):
                        p90_response_time = sorted_times[idx]
                
                endpoints_data.append({
                    'endpoint': endpoint,
                    'requests': requests,
                    'failures': failures,
                    'failureRate': failures / max(1, requests),
                    'avgResponseTime': data.get('avg_duration', 0),
                    'minResponseTime': data.get('min_duration', 0) if data.get('min_duration', 0) != float('inf') else 0,
                    'maxResponseTime': data.get('max_duration', 0),
                    'statusCodes': data.get('status_codes', {}),
                    'p90ResponseTime': p90_response_time  # 添加90%响应时间
                })
            
            # 按请求数量排序，显示最常用的端点在前面
            endpoints_data.sort(key=lambda x: x['requests'], reverse=True)

            # 构建广播数据
            data = {
                'test_id': test_id,
                'progress': progress,
                'status': K6Manager.STATUS_RUNNING,
                'metrics': {
                    'vus': int(metrics.get('vus', 0)),
                    'rps': round(rps, 2),
                    'response_time': round(float(metrics.get('http_req_duration_avg', 0)), 2),
                    'error_rate': round(float(metrics.get('error_rate', 0)), 2),
                    'total_requests': int(metrics.get('total_requests', 0)),
                    'failed_requests': int(metrics.get('failed_requests', 0))
                },
                'endpoints': endpoints_data
            }

            # 广播数据
            self.monitor.broadcast_metrics(test_id, data)
            
            # 增强日志记录，添加详细的指标数据
            self.logger.info(f"Broadcasting metrics - Test ID: {test_id}, Progress: {progress}%, RPS: {data['metrics']['rps']}, RT: {data['metrics']['response_time']}ms, Error Rate: {data['metrics']['error_rate']}%, VUs: {data['metrics']['vus']}")
            self.logger.debug(f"Endpoint metrics: {len(data['endpoints'])} endpoints tracked")

            # 保存指标到数据库
            self._save_metrics(test_id, data['metrics'])

            # 更新数据库中的测试状态
            with self.app.app_context():
                test = TestResult.query.get(test_id)
                if test:
                    test.status = K6Manager.STATUS_RUNNING
                    test.progress = progress
                    db.session.commit()

        except Exception as e:
            self.logger.error(f"广播指标失败: {str(e)}")
            self.logger.exception(e)

    def _save_metrics(self, test_id, metrics):
        """保存性能指标到数据库"""
        try:
            # 确保所有指标都是有效的数值
            sanitized_metrics = {
                'vus': int(metrics.get('vus', 0)),
                'rps': int(metrics.get('rps', 0)),
                'response_time': round(float(metrics.get('response_time', 0)), 2),
                'error_rate': round(float(metrics.get('error_rate', 0)), 2)
            }
            
            self.logger.info(f"保存指标到数据库: {sanitized_metrics}")
            
            from models import PerformanceMetric, db
            with self.app.app_context():
                metric = PerformanceMetric(
                    test_id=test_id,
                    vus=sanitized_metrics['vus'],
                    rps=sanitized_metrics['rps'],
                    response_time=sanitized_metrics['response_time'],
                    error_rate=sanitized_metrics['error_rate']
                )
                db.session.add(metric)
                db.session.commit()
                self.logger.info(f"指标已保存到数据库，ID: {metric.id}")
        except Exception as e:
            self.logger.error(f"保存性能指标失败: {str(e)}, 原始数据: {metrics}")
            self.logger.exception(e)

    def _handle_test_completion(self, test_id, return_code):
        """处理测试完成"""
        try:
            if test_id not in self.active_tests:
                self.logger.warning(f"Test not found during completion: {test_id}")
                return

            final_status = self.STATUS_COMPLETED if return_code == 0 else self.STATUS_FAILED
            
            # 更新数据库
            with self.app.app_context():
                from models import TestResult, db
                test_result = TestResult.query.get(test_id)
                if test_result:
                    test_result.status = final_status
                    test_result.end_time = datetime.now()
                    db.session.commit()
                    self.logger.info(f"Test {test_id} completed with status: {final_status}")

            # 广播最终状态
            self.monitor.broadcast_metrics(test_id, {
                'progress': 100,
                'status': final_status,
                'timestamp': datetime.now().isoformat()
            })

        except Exception as e:
            self.logger.error(f"处理测试完成时出错: {str(e)}")
            # 尝试设置错误状态
            try:
                with self.app.app_context():
                    from models import TestResult, db
                    test_result = TestResult.query.get(test_id)
                    if test_result:
                        test_result.status = self.STATUS_ERROR
                        test_result.end_time = datetime.now()
                        db.session.commit()
            except Exception as inner_e:
                self.logger.error(f"更新错误状态失败: {str(inner_e)}")
        finally:
            self._cleanup_test(test_id)

    def _cleanup_test(self, test_id):
        """清理测试资源"""
        try:
            if test_id in self.active_tests:
                test_info = self.active_tests[test_id]
                process = test_info.get('process')
                stdout_file = test_info.get('stdout_file')
                stderr_file = test_info.get('stderr_file')

                # 清理进程
                if process and process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    except Exception as e:
                        self.logger.error(f"终止进程失败: {str(e)}")

                # 清理文件
                if stdout_file:
                    try:
                        stdout_file.close()
                        os.unlink(stdout_file.name)
                    except Exception as e:
                        self.logger.error(f"清理stdout文件失败: {str(e)}")

                if stderr_file:
                    try:
                        stderr_file.close()
                        os.unlink(stderr_file.name)
                    except Exception as e:
                        self.logger.error(f"清理stderr文件失败: {str(e)}")

                del self.active_tests[test_id]
                self.logger.info(f"Test {test_id} resources cleaned up")

        except Exception as e:
            self.logger.error(f"清理测试资源失败: {str(e)}")

    def stop_test(self, test_id):
        """停止指定的测试"""
        try:
            if test_id not in self.active_tests:
                self.logger.warning(f"Test not found: {test_id}")
                return False

            test_info = self.active_tests[test_id]
            process = test_info['process']
            
            # 尝试正常终止进程
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                except Exception as e:
                    self.logger.error(f"终止进程失败: {str(e)}")

            # 更新测试状态
            with self.app.app_context():
                from models import TestResult, db
                test_result = TestResult.query.get(test_id)
                if test_result:
                    test_result.status = self.STATUS_STOPPED
                    test_result.end_time = datetime.now()
                    db.session.commit()
                    self.logger.info(f"Test {test_id} stopped successfully")

            # 广播状态更新
            self.monitor.broadcast_metrics(test_id, {
                'progress': 100,
                'status': self.STATUS_STOPPED,
                'timestamp': datetime.now().isoformat()
            })

            # 清理资源
            self._cleanup_test(test_id)
            return True

        except Exception as e:
            self.logger.error(f"停止测试失败: {str(e)}")
            return False

    def get_running_tests(self):
        """获取所有正在运行的测试ID列表"""
        return list(self.active_tests.keys())


# 创建单例实例
k6_manager = K6Manager()
