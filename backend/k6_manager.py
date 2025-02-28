import os
import json
import subprocess
import logging
from datetime import datetime
import threading
import time
from flask_socketio import emit
import queue
from threading import Thread, Event
import errno
import re
import io
import shutil
from flask import request

logger = logging.getLogger(__name__)

class K6Manager:
    def __init__(self):
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

    def start_test(self, script_path, test_id, vus=1, duration=30, ramp_time=0):
        """启动性能测试"""
        if not os.path.exists(script_path):
            raise FileNotFoundError(f'脚本文件不存在: {script_path}')

        if test_id in self.running_tests:
            self.stop_test(test_id)

        metrics_file = os.path.join(self.reports_dir, f'{test_id}_metrics.json')
        summary_file = os.path.join(self.reports_dir, f'{test_id}_summary.json')

        try:
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['LANG'] = 'en_US.UTF-8'
            env['LC_ALL'] = 'en_US.UTF-8'
            
            # 创建进程，使用 utf-8 编码，并设置缓冲区为行缓冲
            process = subprocess.Popen(
                self._generate_command(script_path, test_id, vus, duration, ramp_time),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=1,  # 行缓冲
                universal_newlines=False  # 不要自动解码，我们将在读取线程中处理
            )
            
            self.running_tests[test_id] = {
                'process': process,
                'start_time': time.time(),
                'duration': duration + (ramp_time if ramp_time > 0 else 0),
                'status': 'running',
                'metrics': {
                    'http_reqs': 0,
                    'http_req_duration': 0,
                    'http_req_failed': 0,
                    'vus': vus,
                    'rps': 0,
                    'failure_rate': 0
                },
                'files': {
                    'metrics': metrics_file,
                    'summary': summary_file
                },
                'output_buffer': {
                    'stdout': [],
                    'stderr': []
                }
            }

            # 启动输出处理线程
            Thread(
                target=self._process_test_output,
                args=(test_id,),
                daemon=True
            ).start()

            logger.info(f'测试 {test_id} 已启动')
            return True

        except Exception as e:
            error_msg = f'启动测试失败: {str(e)}'
            logger.error(error_msg)
            self._update_test_status(test_id, 'failed', error_msg)
            raise

    def _process_test_output(self, test_id):
        """处理测试输出的主函数"""
        if test_id not in self.running_tests:
            return

        test_info = self.running_tests[test_id]
        process = test_info['process']
        metrics_data = []

        try:
            # 使用队列存储输出
            stdout_queue = queue.Queue()
            stderr_queue = queue.Queue()

            # 启动输出读取线程
            def read_output(pipe, queue):
                try:
                    # 确保使用 UTF-8 编码读取
                    for line in io.TextIOWrapper(pipe, encoding='utf-8', errors='replace'):
                        if line:
                            queue.put(line.strip())
                except Exception as e:
                    logger.error(f'读取输出失败: {str(e)}', exc_info=True)
                finally:
                    queue.put(None)  # 发送结束信号

            stdout_thread = Thread(target=read_output, args=(process.stdout, stdout_queue))
            stderr_thread = Thread(target=read_output, args=(process.stderr, stderr_queue))
            
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            # 主循环处理输出
            stdout_done = stderr_done = False
            while not (stdout_done and stderr_done):
                # 处理标准输出
                try:
                    if not stdout_done:
                        line = stdout_queue.get(timeout=0.1)
                        if line is None:
                            stdout_done = True
                        else:
                            self._handle_output_line(test_id, line, metrics_data, is_error=False)
                except queue.Empty:
                    pass
                
                # 处理错误输出
                try:
                    if not stderr_done:
                        line = stderr_queue.get(timeout=0.1)
                        if line is None:
                            stderr_done = True
                        else:
                            self._handle_output_line(test_id, line, metrics_data, is_error=True)
                except queue.Empty:
                    pass

                # 检查进程是否结束
                if process.poll() is not None:
                    break

            # 等待线程结束
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            
            # 保存收集的数据
            if metrics_data:
                self._save_metrics_data(test_id, metrics_data)
            
            # 更新最终状态
            if process.returncode == 0:
                self._update_test_status(test_id, 'completed', '测试成功完成')
            else:
                self._update_test_status(test_id, 'failed', f'测试失败，退出码: {process.returncode}')
                
        except Exception as e:
            logger.error(f'处理测试输出失败: {str(e)}', exc_info=True)
            self._update_test_status(test_id, 'failed', f'处理输出失败: {str(e)}')

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
            
            from app import broadcast_metrics
            broadcast_metrics(test_id, broadcast_data)
            
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
        if test_id in self.running_tests:
            try:
                test_info = self.running_tests[test_id]
                test_info['status'] = status
                
                progress = 100 if status in ['completed', 'stopped', 'failed'] else test_info.get('progress', 0)
                
                status_data = {
                    'test_id': test_id,
                    'status': status,
                    'progress': progress,
                    'message': message or f'测试{status}',
                    'metrics': test_info.get('metrics', {})
                }
                
                from app import broadcast_test_status
                broadcast_test_status(test_id, status, message)
                
                if status in ['completed', 'failed', 'stopped']:
                    self._save_final_report(test_id)
                    self.running_tests.pop(test_id, None)
                    
            except Exception as e:
                logger.error(f'更新测试状态失败: {str(e)}')

    def stop_test(self, test_id):
        """停止测试"""
        if not isinstance(test_id, str):
            logger.error(f'无效的test_id类型: {type(test_id)}')
            return False
            
        if test_id not in self.running_tests:
            logger.warning(f'测试 {test_id} 不存在或已停止')
            return False
            
        try:
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
            
            self._update_test_status(test_id, 'stopped', '测试已停止')
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