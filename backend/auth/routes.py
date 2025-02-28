from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import jwt
from app import db
from .models import User, UserTestConfig

auth_bp = Blueprint('auth', __name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': '缺少认证令牌'}), 401
        try:
            token = token.split(' ')[1]
            data = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
        except:
            return jsonify({'message': '无效的认证令牌'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    if not all(k in data for k in ('username', 'password', 'email')):
        return jsonify({'message': '缺少必要字段'}), 400

    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': '用户名已存在'}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': '邮箱已被注册'}), 400

    hashed_password = generate_password_hash(data['password'])
    new_user = User(
        username=data['username'],
        password=hashed_password,
        email=data['email']
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '注册成功'}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    if not all(k in data for k in ('username', 'password')):
        return jsonify({'message': '缺少必要字段'}), 400

    user = User.query.filter_by(username=data['username']).first()
    if not user or not check_password_hash(user.password, data['password']):
        return jsonify({'message': '用户名或密码错误'}), 401

    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, 'your-secret-key', algorithm='HS256')

    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        }
    })

@auth_bp.route('/check-permission/<int:config_id>', methods=['GET'])
@token_required
def check_permission(current_user, config_id):
    if current_user.role == 'admin':
        return jsonify({'permission': 'write'})

    user_config = UserTestConfig.query.filter_by(
        user_id=current_user.id,
        config_id=config_id
    ).first()

    if not user_config:
        return jsonify({'permission': None})

    return jsonify({'permission': user_config.permission})