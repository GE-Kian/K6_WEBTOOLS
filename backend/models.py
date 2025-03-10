from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Script(db.Model):
    __tablename__ = 'scripts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    dependencies = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Add relationship
    test_results = db.relationship('TestResult', back_populates='script')

class TestConfig(db.Model):
    __tablename__ = 'test_configs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    script_path = db.Column(db.String(255), nullable=False)
    parameters = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TestResult(db.Model):
    __tablename__ = 'test_results'
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('scripts.id'), nullable=False)
    config = db.Column(db.Text)
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    report_path = db.Column(db.String(255))
    error_message = db.Column(db.Text)

    # 添加关系
    script = db.relationship('Script', back_populates='test_results')
    metrics = db.relationship('PerformanceMetric', back_populates='test')

class PerformanceMetric(db.Model):
    __tablename__ = 'performance_metrics'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test_results.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    vus = db.Column(db.Integer)
    rps = db.Column(db.Float)
    response_time = db.Column(db.Float)
    error_rate = db.Column(db.Float)
    
    # 修改关系定义
    test = db.relationship('TestResult', back_populates='metrics')