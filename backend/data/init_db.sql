-- 创建数据库
CREATE DATABASE IF NOT EXISTS k6_web_tools;
USE k6_web_tools;

-- 删除现有表（按照外键依赖的反序删除）
DROP TABLE IF EXISTS performance_metrics;
DROP TABLE IF EXISTS test_results;
DROP TABLE IF EXISTS test_configs;
DROP TABLE IF EXISTS scripts;

-- 测试配置表
CREATE TABLE test_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL COMMENT '测试名称',
    script_path VARCHAR(512) NOT NULL COMMENT 'K6脚本路径',
    parameters JSON NOT NULL COMMENT '压测参数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_name (name),
    INDEX idx_created_at (created_at),
    INDEX idx_script_path (script_path)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试配置表';

-- 脚本表
CREATE TABLE scripts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL COMMENT '脚本名称',
    filename VARCHAR(255) NOT NULL COMMENT '文件名',
    path VARCHAR(512) NOT NULL COMMENT '脚本路径',
    description TEXT COMMENT '脚本描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_name (name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='脚本表';

-- 测试结果表
CREATE TABLE test_results (
    id INT PRIMARY KEY AUTO_INCREMENT,
    script_id INT NOT NULL COMMENT '关联的脚本ID',
    config TEXT COMMENT '测试配置',
    start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    end_time TIMESTAMP NULL COMMENT '结束时间',
    status VARCHAR(50) NOT NULL COMMENT '测试状态',
    report_path VARCHAR(512) COMMENT '报告文件路径',
    error_message TEXT COMMENT '错误信息',
    FOREIGN KEY (script_id) REFERENCES scripts(id),
    INDEX idx_script_id (script_id),
    INDEX idx_start_time (start_time),
    INDEX idx_end_time (end_time),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试结果表';

-- 性能数据表
CREATE TABLE performance_metrics (
    id INT PRIMARY KEY AUTO_INCREMENT,
    test_id INT NOT NULL COMMENT '关联的测试结果ID',
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '时间戳',
    vus INT COMMENT '并发用户数',
    rps FLOAT COMMENT '每秒请求数',
    response_time FLOAT COMMENT '响应时间',
    error_rate FLOAT COMMENT '错误率',
    FOREIGN KEY (test_id) REFERENCES test_results(id),
    INDEX idx_test_id (test_id),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='性能数据表';