import os
import json
import subprocess
import logging
from datetime import datetime
import threading
import time
import queue
from threading import Thread, Event
import errno
import re
import io
import shutil
from flask import request, current_app
from models import db, Script, TestResult, PerformanceMetric
from broadcast import broadcast_metrics, broadcast_test_status

logger = logging.getLogger(__name__)

class K6MonitorService:
    # 定义可能的状态
    STATUS_IDLE = 'idle'
    STATUS_RUNNING = 'running'
    STATUS_STOPPED = 'stopped'
    STATUS_ERROR = 'error'
    STATUS_FAILED = 'failed'  # 添加失败状态
    STATUS_PAUSED = 'paused'  # 添加暂停状态

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
        self.current_test = None
        self.websocket_clients = set()
        self.status = self.STATUS_IDLE
        self._lock = threading.Lock()
        self._metrics_buffer = []
        self._last_broadcast_time = 0
        self._broadcast_interval = 1.0  # 广播间隔（秒）
        self._error_message = None
        self._start_time = None
        self._last_activity_time = None
        self._max_inactive_time = 300  # 最大不活动时间（秒）
        self._metrics_count = 0
        self._error_count = 0
        self._last_error = None
        self._status_history = []  # 状态历史记录
        self._pause_time = None  # 暂停时间
        self._total_pause_duration = 0  # 总暂停时间
        self._retry_count = 0  # 重试次数
        self._max_retries = 3  # 最大重试次数

    def _record_status_change(self, old_status, new_status, error_message=None):
        """记录状态变化"""
        status_record = {
            'timestamp': datetime.now().isoformat(),
            'old_status': old_status,
            'new_status': new_status,
            'test_id': self.current_test,
            'error_message': error_message,
            'metrics_count': self._metrics_count,
            'error_count': self._error_count,
            'clients_count': len(self.websocket_clients)
        }
        if self._start_time:
            status_record['running_time'] = time.time() - self._start_time - self._total_pause_duration
        
        self._status_history.append(status_record)
        return status_record

    def _can_transition_to(self, new_status):
        """检查是否可以转换到新状态"""
        if new_status == self.status:
            return True  # 允许相同状态的转换
        
        # 检查是否超过最大重试次数
        if self._retry_count >= self._max_retries and new_status == self.STATUS_RUNNING:
            logger.warning(f'已达到最大重试次数 ({self._max_retries})，无法重新启动')
            return False
            
        return new_status in self._VALID_TRANSITIONS.get(self.status, [])

    def _set_status(self, new_status, error_message=None):
        """安全地设置新状态"""
        if not self._can_transition_to(new_status):
            logger.warning(f'无效的状态转换: {self.status} -> {new_status}')
            return False
        
        old_status = self.status
        self.status = new_status
        
        # 更新错误信息
        if error_message:
            self._last_error = error_message
            if new_status in [self.STATUS_ERROR, self.STATUS_FAILED]:
                self._error_message = error_message
                self._error_count += 1
        elif new_status not in [self.STATUS_ERROR, self.STATUS_FAILED]:
            self._error_message = None
        
        # 更新状态相关的时间戳
        self._last_activity_time = time.time()
        if new_status == self.STATUS_PAUSED:
            self._pause_time = time.time()
        elif old_status == self.STATUS_PAUSED and new_status == self.STATUS_RUNNING:
            if self._pause_time:
                self._total_pause_duration += time.time() - self._pause_time
                self._pause_time = None
        
        # 更新重试计数
        if old_status in [self.STATUS_ERROR, self.STATUS_FAILED] and new_status == self.STATUS_RUNNING:
            self._retry_count += 1
        elif new_status == self.STATUS_IDLE:
            self._retry_count = 0
        
        # 记录状态变化
        status_info = self._record_status_change(old_status, new_status, error_message)
        logger.info(f'状态转换: {status_info}')
        return True

    def _handle_error(self, error_message, is_fatal=False):
        """统一处理错误"""
        if is_fatal:
            new_status = self.STATUS_FAILED
        else:
            new_status = self.STATUS_ERROR
            
        self._set_status(new_status, error_message)
        logger.error(f'测试错误 ({new_status}): {error_message}')
        
        # 如果是致命错误，清理资源
        if is_fatal:
            self._cleanup_resources()
            self._set_status(self.STATUS_IDLE)

    def _cleanup_resources(self):
        """清理资源"""
        self.current_test = None
        self._metrics_buffer.clear()
        self.websocket_clients.clear()
        self._reset_metrics()

    def _check_inactive_timeout(self):
        """检查是否超过最大不活动时间"""
        if (self.status == self.STATUS_RUNNING and 
            self._last_activity_time and 
            time.time() - self._last_activity_time > self._max_inactive_time):
            error_msg = f'测试 {self.current_test} 超过 {self._max_inactive_time} 秒未收到数据'
            logger.warning(error_msg)
            self._set_status(self.STATUS_ERROR, error_msg)
            return True
        return False

    def _reset_metrics(self):
        """重置指标相关的计数器"""
        self._metrics_count = 0
        self._error_count = 0
        self._metrics_buffer.clear()
        self._last_broadcast_time = 0
        self._start_time = None
        self._last_activity_time = None

    def start_monitoring(self, test_id):
        with self._lock:
            if self.status == self.STATUS_RUNNING:
                logger.warning(f'已有测试正在运行: {self.current_test}，无法启动新测试: {test_id}')
                return False
            
            try:
                if not self._set_status(self.STATUS_RUNNING):
                    return False
                
                self.current_test = test_id
                self._metrics_buffer.clear()
                self._last_broadcast_time = time.time()
                self._start_time = time.time()
                logger.info(f'开始监控测试: {test_id}')
                return True
            except Exception as e:
                error_msg = f'启动监控时发生错误: {str(e)}'
                self._set_status(self.STATUS_ERROR, error_msg)
                logger.error(error_msg)
                return False

    def stop_monitoring(self):
        """停止监控"""
        with self._lock:
            if not self.current_test:
                logger.warning('没有正在运行的测试')
                return False

            try:
                prev_test = self.current_test
                prev_status = self.status
                
                # 如果当前状态是失败状态，直接清理资源
                if self.status in [self.STATUS_ERROR, self.STATUS_FAILED]:
                    self._cleanup_resources()
                    self._set_status(self.STATUS_IDLE)
                    logger.info(f'清理失败的测试: {prev_test} (之前状态: {prev_status})')
                    return True
                
                # 正常停止流程
                if not self._set_status(self.STATUS_STOPPED):
                    return False
                
                self._cleanup_resources()
                logger.info(f'停止监控测试: {prev_test}')
                
                # 自动转换到空闲状态
                self._set_status(self.STATUS_IDLE)
                return True
            except Exception as e:
                error_msg = f'停止监控时发生错误: {str(e)}'
                self._handle_error(error_msg, is_fatal=True)
                return False
        
    def add_websocket_client(self, ws):
        with self._lock:
            if ws not in self.websocket_clients:
                self.websocket_clients.add(ws)
                logger.info(f'添加WebSocket客户端: {ws}, 当前连接数: {len(self.websocket_clients)}')
                return True
            return False
        
    def remove_websocket_client(self, ws):
        with self._lock:
            if ws in self.websocket_clients:
                self.websocket_clients.remove(ws)
                logger.info(f'移除WebSocket客户端: {ws}, 当前连接数: {len(self.websocket_clients)}')
                if not self.websocket_clients and self.status == self.STATUS_RUNNING:
                    logger.warning('所有客户端已断开，但测试仍在运行')
                return True
            return False
        
    def broadcast_metrics(self, metrics):
        with self._lock:
            if not self.current_test:
                logger.warning('尝试广播指标但没有活动的测试')
                return False
            
            if self.status != self.STATUS_RUNNING:
                logger.warning(f'测试状态不是运行中 (当前状态: {self.status})')
                return False

            current_time = time.time()
            if current_time - self._last_broadcast_time < self._broadcast_interval:
                self._metrics_buffer.append(metrics)
                return True

            try:
                # 如果有缓存的指标，一起发送
                if self._metrics_buffer:
                    self._metrics_buffer.append(metrics)
                    metrics_to_send = self._aggregate_metrics(self._metrics_buffer)
                    self._metrics_buffer.clear()
                else:
                    metrics_to_send = metrics

                broadcast_metrics(self.current_test, metrics_to_send)
                self._last_broadcast_time = current_time
                logger.debug(f'成功广播测试 {self.current_test} 的指标')
                return True
            except Exception as e:
                logger.error(f'广播指标失败: {str(e)}')
                self.status = self.STATUS_ERROR
                return False

    def _aggregate_metrics(self, metrics_list):
        """聚合多个指标"""
        if not metrics_list:
            return {}
        
        # 使用最后一个指标作为基础
        aggregated = metrics_list[-1].copy()
        
        # 计算平均值的字段
        avg_fields = ['avgResponseTime', 'currentRPS', 'failureRate']
        for field in avg_fields:
            values = [m.get(field, 0) for m in metrics_list if field in m]
            if values:
                aggregated[field] = sum(values) / len(values)
        
        # 累加字段
        sum_fields = ['totalRequests']
        for field in sum_fields:
            values = [m.get(field, 0) for m in metrics_list if field in m]
            if values:
                aggregated[field] = max(values)  # 使用最大值作为累计值
        
        return aggregated

    def get_status_history(self):
        """获取状态历史记录"""
        with self._lock:
            return self._status_history.copy()

    def get_effective_running_time(self):
        """获取有效运行时间（不包括暂停时间）"""
        with self._lock:
            if not self._start_time:
                return 0
            total_time = time.time() - self._start_time
            return max(0, total_time - self._total_pause_duration)

    def get_status(self):
        """获取当前状态的详细信息"""
        with self._lock:
            status_info = {
                'test_id': self.current_test,
                'status': self.status,
                'clients_count': len(self.websocket_clients),
                'metrics_buffer_size': len(self._metrics_buffer),
                'metrics_count': self._metrics_count,
                'error_count': self._error_count,
                'last_broadcast': self._last_broadcast_time,
                'retry_count': self._retry_count,
                'max_retries': self._max_retries
            }
            
            if self._start_time:
                status_info['total_running_time'] = time.time() - self._start_time
                status_info['effective_running_time'] = self.get_effective_running_time()
            
            if self._error_message:
                status_info['error_message'] = self._error_message
                
            if self._last_activity_time:
                status_info['inactive_time'] = time.time() - self._last_activity_time
                
            if self._pause_time:
                status_info['pause_duration'] = time.time() - self._pause_time
                
            return status_info

k6_monitor = K6MonitorService()

class K6Manager:
    def __init__(self, app=None):
        self.app = app
        self.scripts_dir = os.getenv('K6_SCRIPTS_DIR', 'scripts')
        self.reports_dir = os.getenv('K6_REPORTS_DIR', 'reports')
        self.running_tests = {}
        self.test_metrics = {}
        
        # 确保目录存在
        for directory in [self.scripts_dir, self.reports_dir]:
            os.makedirs(directory, exist_ok=True)
            if not os.access(directory, os.W_OK):
                raise PermissionError(f'没有写入权限: {directory}')
        
        logger.info(f'K6Manager初始化，脚本目录: {os.path.abspath(self.scripts_dir)}, 报告目录: {os.path.abspath(self.reports_dir)}')

    def init_app(self, app):
        """初始化应用实例"""
        self.app = app

    def _generate_command(self, script_path, test_id, vus, duration, ramp_time):
        """生成k6命令"""
        command = ['k6', 'run', '--out', 'json=-']
        
        if ramp_time > 0:
            command.extend([
                '--stage', '0s:0',
                '--stage', f'{ramp_time}s:{vus}',
                '--stage', f'{duration}s:{vus}'
            ])
        else:
            command.extend([
                '--vus', str(vus),
                '--duration', f'{duration}s'
            ])
        
        command.append(script_path)
        logger.info(f'生成的K6命令: {" ".join(command)}')
        return command

    def start_test(self, script_id, config):
        try:
            # 创建测试记录
            test_result = TestResult(
                script_id=script_id,
                config=json.dumps(config),
                status='running'
            )
            db.session.add(test_result)
            db.session.commit()
            
            # 启动监控
            k6_monitor.start_monitoring(test_result.id)
            
            # 启动测试进程
            process = self._run_k6_test(script_id, config, test_result)
            
            # 初始化测试信息
            self.running_tests[test_result.id] = {
                'process': process,
                'start_time': time.time(),
                'duration': config.get('duration', 30),
                'status': 'running',
                'metrics': {
                    'http_reqs': 0,
                    'http_req_duration': 0,
                    'http_req_failed': 0,
                    'vus': config.get('vus', 1),
                    'rps': 0,
                    'failure_rate': 0
                },
                'files': {
                    'metrics': os.path.join(self.reports_dir, f'{test_result.id}_metrics.json'),
                    'summary': os.path.join(self.reports_dir, f'{test_result.id}_summary.json')
                }
            }
            
            return test_result.id, process
        except Exception as e:
            logging.error(f"Error starting test: {str(e)}")
            raise

    def _run_k6_test(self, script_id, config, test_result):
        """运行k6测试"""
        try:
            # 获取脚本信息
            script = db.session.get(Script, script_id)
            if not script:
                raise ValueError(f'Script not found: {script_id}')

            # 检查脚本文件是否存在
            if not os.path.exists(script.path):
                raise FileNotFoundError(f'Script file not found: {script.path}')

            # 检查依赖文件
            script_dir = os.path.dirname(script.path)
            if hasattr(script, 'dependencies') and script.dependencies:
                for dep_name, dep_path in script.dependencies.items():
                    # 确保依赖文件在脚本目录中
                    local_dep_path = os.path.join(script_dir, os.path.basename(dep_path))
                    if not os.path.exists(local_dep_path):
                        logger.warning(f'依赖文件不存在: {local_dep_path}，尝试复制或创建...')
                        try:
                            if os.path.exists(dep_path):
                                # 如果原始依赖文件存在，复制到脚本目录
                                shutil.copy2(dep_path, local_dep_path)
                            else:
                                # 创建新的依赖文件
                                with open(local_dep_path, 'w', encoding='utf-8') as f:
                                    f.write(f'// {dep_name} placeholder\n')
                            logger.info(f'依赖文件已就绪: {local_dep_path}')
                        except Exception as e:
                            logger.error(f'处理依赖文件失败: {str(e)}')
                            raise

            # 构建k6命令
            command = ['k6', 'run', '--out', 'json=-']
            
            # 添加配置参数
            vus = config.get('vus', 1)
            duration = config.get('duration', 30)
            ramp_time = config.get('ramp_time', 0)
            
            if ramp_time > 0:
                # 如果有 ramp_time，使用 stages 模式
                command.extend([
                    '--vus', str(vus),
                    '--stage', f'0s:0',  # 开始时 0 VUs
                    '--stage', f'{ramp_time}s:{vus}',  # 在 ramp_time 时间内增加到目标 VUs
                    '--stage', f'{duration}s:{vus}'  # 维持 VUs 直到结束
                ])
            else:
                # 如果没有 ramp_time，使用简单的 vus 和 duration 模式
                command.extend([
                    '--vus', str(vus),
                    '--duration', f'{duration}s'
                ])
            
            # 添加脚本路径
            command.append(script.path)
            
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['LANG'] = 'en_US.UTF-8'
            env['LC_ALL'] = 'en_US.UTF-8'
            env['K6_SCRIPT_ROOT'] = script_dir  # 设置脚本根目录
            
            logger.info(f'执行k6命令: {" ".join(command)}')
            logger.info(f'工作目录: {script_dir}')
            
            # 启动进程
            startupinfo = None
            if os.name == 'nt':  # Windows系统
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                startupinfo=startupinfo,
                bufsize=-1,  # 使用系统默认缓冲
                universal_newlines=False,  # 不自动处理换行符
                cwd=script_dir  # 设置工作目录为脚本所在目录
            )
            
            # 启动输出处理线程
            Thread(
                target=self._process_test_output,
                args=(process, test_result.id, self.app),
                daemon=True
            ).start()
            
            return process
            
        except Exception as e:
            logger.error(f'启动测试失败: {str(e)}')
            raise

    def _process_test_output(self, process, test_id, app):
        """处理测试输出"""
        stdout_wrapper = None
        stderr_wrapper = None
        error_buffer = []
        try:
            with app.app_context():
                # 使用 io.TextIOWrapper 包装输出流，确保正确的编码处理
                stdout_wrapper = io.TextIOWrapper(process.stdout, encoding='utf-8', errors='replace', line_buffering=True)
                stderr_wrapper = io.TextIOWrapper(process.stderr, encoding='utf-8', errors='replace', line_buffering=True)
                
                # 创建错误输出读取线程
                def read_stderr():
                    while True:
                        line = stderr_wrapper.readline()
                        if not line and process.poll() is not None:
                            break
                        if line:
                            error_buffer.append(line.strip())
                            if 'error' in line.lower():
                                logger.error(f'K6错误输出: {line.strip()}')
                
                error_thread = Thread(target=read_stderr, daemon=True)
                error_thread.start()
                
                while True:
                    line = stdout_wrapper.readline()
                    if not line and process.poll() is not None:
                        break
                        
                    if line:
                        try:
                            data = json.loads(line.strip())
                            if data.get('type') == 'Point':
                                self._process_metrics(test_id, data)
                        except json.JSONDecodeError:
                            logger.debug(f'非JSON输出: {line.strip()}')
                        except Exception as e:
                            logger.error(f'处理输出行失败: {str(e)}')
                
                # 等待错误输出线程结束
                error_thread.join(timeout=2)
                
                # 处理进程结束
                return_code = process.poll()
                error_message = None
                
                if error_buffer:
                    # 处理错误信息，去除重复
                    unique_errors = []
                    seen = set()
                    for error in error_buffer:
                        error_key = error.split('time=')[1] if 'time=' in error else error
                        if error_key not in seen:
                            seen.add(error_key)
                            unique_errors.append(error)
                    error_message = '\n'.join(unique_errors)
                
                if return_code == 0:
                    self._update_test_status(test_id, 'completed')
                    logger.info(f'测试 {test_id} 已完成')
                else:
                    if not error_message and stderr_wrapper:
                        error_message = stderr_wrapper.read()
                    
                    # 如果是脚本错误，设置为失败状态
                    if 'ReferenceError' in str(error_message) or 'SyntaxError' in str(error_message):
                        status = 'failed'
                    else:
                        status = 'error'
                    
                    self._update_test_status(test_id, status, error_message)
                    logger.error(f'测试 {test_id} {status}: {error_message}')
                
                # 保存最终报告
                self._save_final_report(test_id)
                
                # 清理资源
                if test_id in self.running_tests:
                    del self.running_tests[test_id]
                
                # 停止监控
                k6_monitor.stop_monitoring()
                
        except Exception as e:
            logger.error(f'处理测试输出失败: {str(e)}')
            with app.app_context():
                self._update_test_status(test_id, 'failed', str(e))
                # 清理资源
                if test_id in self.running_tests:
                    del self.running_tests[test_id]
                k6_monitor.stop_monitoring()
        finally:
            # 关闭包装器
            if stdout_wrapper:
                stdout_wrapper.close()
            if stderr_wrapper:
                stderr_wrapper.close()
            
            # 确保进程被终止
            try:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            except Exception as e:
                logger.error(f'终止进程失败: {str(e)}')

    def _handle_output_line(self, test_id, line, metrics_data, is_error=False):
        """处理单行输出"""
        try:
            if not line:
                return
                
            if is_error:
                if 'error' in line.lower():
                    logger.error(f'K6错误: {line}')
                    self._update_test_status(test_id, 'error', line)
                elif 'warning' in line.lower():
                    logger.warning(f'K6警告: {line}')
                else:
                    logger.info(f'K6信息: {line}')
            else:
                try:
                    data = json.loads(line)
                    metrics_data.append(data)
                    self._process_metrics(test_id, data)
                except json.JSONDecodeError:
                    if 'error' in line.lower():
                        logger.error(f'K6输出: {line}')
                    else:
                        logger.info(f'K6输出: {line}')
                        
        except Exception as e:
            logger.error(f'处理输出行失败: {str(e)}', exc_info=True)

    def _process_metrics(self, test_id, data):
        """处理指标数据"""
        if test_id not in self.running_tests:
            return

        try:
            test_info = self.running_tests[test_id]
            metrics = test_info['metrics']

            if data.get('type') == 'Point':
                metric_name = data.get('metric')
                value = data.get('data', {}).get('value')

                if metric_name and value is not None:
                    if metric_name == 'http_reqs':
                        metrics['http_reqs'] = max(0, int(value))
                    elif metric_name == 'http_req_duration':
                        metrics['http_req_duration'] = max(0, float(value))
                    elif metric_name == 'http_req_failed':
                        metrics['http_req_failed'] = max(0, int(value))
                    elif metric_name == 'vus':
                        metrics['vus'] = max(0, int(value))

                    # 计算衍生指标
                    self._calculate_derived_metrics(test_id)

        except Exception as e:
            logger.error(f'处理指标数据失败: {str(e)}')

    def _calculate_derived_metrics(self, test_id):
        """计算衍生指标"""
        test_info = self.running_tests[test_id]
        metrics = test_info['metrics']
        elapsed_time = max(0.1, time.time() - test_info['start_time'])

        # 计算 RPS
        metrics['rps'] = round(metrics['http_reqs'] / elapsed_time, 2)

        # 计算失败率
        if metrics['http_reqs'] > 0:
            metrics['failure_rate'] = round((metrics['http_req_failed'] / metrics['http_reqs']) * 100, 2)

        # 更新进度
        progress = min(100, (elapsed_time / test_info['duration']) * 100)
        test_info['progress'] = round(progress, 1)

        # 广播更新
        self._broadcast_metrics(test_id)

    def _broadcast_metrics(self, test_id):
        """广播指标更新"""
        try:
            test_info = self.running_tests[test_id]
            metrics = test_info['metrics']
            
            broadcast_data = {
                'test_id': test_id,
                'totalRequests': metrics['http_reqs'],
                'failureRate': metrics['failure_rate'],
                'currentRPS': metrics['rps'],
                'avgResponseTime': metrics['http_req_duration'],
                'vus': metrics['vus'],
                'progress': test_info.get('progress', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            k6_monitor.broadcast_metrics(broadcast_data)
            
        except Exception as e:
            logger.error(f'广播指标失败: {str(e)}')

    def _save_metrics_data(self, test_id, metrics_data):
        """保存指标数据"""
        try:
            test_info = self.running_tests.get(test_id)
            if not test_info or 'files' not in test_info:
                return

            metrics_file = test_info['files'].get('metrics')
            if not metrics_file:
                return

            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(metrics_data, f, ensure_ascii=False, indent=2)
            logger.info(f'已保存指标数据到: {metrics_file}')

        except Exception as e:
            logger.error(f'保存指标数据失败: {str(e)}')

    def _update_test_status(self, test_id, status, message=None):
        """更新测试状态"""
        try:
            test_result = db.session.get(TestResult, test_id)
            if test_result:
                # 如果当前状态已经是终止状态，不再更新
                if test_result.status in ['completed', 'failed', 'stopped']:
                    logger.warning(f'测试 {test_id} 已经处于终止状态: {test_result.status}，忽略状态更新: {status}')
                    return
                
                test_result.status = status
                test_result.end_time = datetime.now() if status in ['completed', 'failed', 'stopped'] else None
                
                # 只在特定状态下更新错误信息
                if status in ['failed', 'error']:
                    test_result.error_message = message
                
                db.session.commit()
                
                # 如果测试结束，停止监控
                if status in ['completed', 'failed', 'stopped']:
                    k6_monitor.stop_monitoring()
                    logger.info(f'测试 {test_id} 状态更新为 {status}，已停止监控')
                
                # 广播状态更新
                broadcast_test_status(test_id, status, message)
                
        except Exception as e:
            logger.error(f'更新测试状态失败: {str(e)}')

    def stop_test(self, test_id):
        """停止测试"""
        try:
            # 确保test_id是整数
            if isinstance(test_id, dict):
                test_id = test_id.get('test_id')
            
            if test_id is None:
                logger.error('无效的test_id: None')
                return False
                
            # 转换为整数
            try:
                test_id = int(test_id)
            except (TypeError, ValueError):
                logger.error(f'无效的test_id格式: {test_id}')
                return False
            
            if test_id not in self.running_tests:
                logger.warning(f'测试 {test_id} 不存在或已停止')
                return False
                
            test_info = self.running_tests[test_id]
            process = test_info.get('process')
            
            if not process:
                logger.warning(f'测试 {test_id} 的进程不存在')
                return False
                
            logger.info(f'正在停止测试 {test_id}')
            
            # 尝试正常终止进程
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f'测试 {test_id} 未能正常终止，强制结束')
                process.kill()
                process.wait(timeout=1)
            
            # 保存最终报告
            self._save_final_report(test_id)
            
            # 更新状态
            self._update_test_status(test_id, 'stopped', '测试已停止')
            
            # 清理资源
            if test_id in self.running_tests:
                del self.running_tests[test_id]
            
            # 停止监控
            k6_monitor.stop_monitoring()
            
            logger.info(f'测试 {test_id} 已停止')
            return True
            
        except Exception as e:
            error_msg = f'停止测试失败: {str(e)}'
            logger.error(error_msg)
            return False

    def _save_final_report(self, test_id):
        """保存最终报告"""
        if test_id in self.running_tests:
            try:
                test_info = self.running_tests[test_id]
                summary_file = test_info['files'].get('summary')
                if not summary_file:
                    return

                summary_data = {
                    'timestamp': datetime.now().isoformat(),
                    'test_id': test_id,
                    'status': test_info['status'],
                    'duration': test_info['duration'],
                    'progress': test_info.get('progress', 0),
                    'metrics': test_info.get('metrics', {})
                }

                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(summary_data, f, ensure_ascii=False, indent=2)
                logger.info(f'已保存最终报告到: {summary_file}')

            except Exception as e:
                logger.error(f'保存最终报告失败: {str(e)}')

    def get_test_status(self, test_id):
        """获取测试状态"""
        if test_id not in self.running_tests:
            return {'status': 'not_found', 'error': '测试不存在'}
        
        test_info = self.running_tests[test_id]
        process = test_info['process']
        
        if process.poll() is not None and test_info['status'] == 'running':
            if process.returncode == 0:
                test_info['status'] = 'completed'
            else:
                test_info['status'] = 'failed'
        
        return {
            'status': test_info['status'],
            'progress': test_info.get('progress', 0),
            'metrics': test_info.get('metrics', {})
        }

    def get_running_tests(self):
        """获取正在运行的测试列表"""
        return [{
            'test_id': test_id,
            'status': info['status'],
            'progress': info.get('progress', 0),
            'start_time': info['start_time'],
            'duration': info['duration'],
            'metrics': info.get('metrics', {})
        } for test_id, info in self.running_tests.items()]

    def _broadcast_with_retry(self, event, data, test_id, max_retries=3):
        """添加重试机制的广播函数"""
        from app import broadcast_metrics, broadcast_test_status
        
        for attempt in range(max_retries):
            try:
                if event == 'metrics':
                    broadcast_metrics(test_id, data)
                else:
                    broadcast_test_status(test_id, data.get('status'), data.get('message'))
                return True
            except Exception as e:
                logger.warning(f'广播失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}')
                if attempt < max_retries - 1:
                    time.sleep(1)
            return False

    def _check_connection(self, test_id):
        """检查客户端连接状态"""
        if not request.namespace.socket.connected:
            logger.warning(f'客户端 {test_id} 已断开连接')
            return False
        return True