from flask import Blueprint, request, jsonify
from app import db
from auth.routes import token_required
from auth.models import TestTemplate

templates_bp = Blueprint('templates', __name__)

@templates_bp.route('/', methods=['POST'])
@token_required
def create_template(current_user):
    data = request.json
    if not all(k in data for k in ('name', 'script_content')):
        return jsonify({'message': '缺少必要字段'}), 400

    template = TestTemplate(
        name=data['name'],
        description=data.get('description', ''),
        script_content=data['script_content'],
        default_parameters=data.get('default_parameters', {}),
        created_by=current_user.id
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'id': template.id,
        'name': template.name,
        'message': '模板创建成功'
    }), 201

@templates_bp.route('/', methods=['GET'])
@token_required
def list_templates(current_user):
    templates = TestTemplate.query.all()
    return jsonify({
        'templates': [{
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'default_parameters': t.default_parameters,
            'created_by': t.created_by,
            'created_at': t.created_at.isoformat()
        } for t in templates]
    })

@templates_bp.route('/<int:template_id>', methods=['GET'])
@token_required
def get_template(current_user, template_id):
    template = TestTemplate.query.get(template_id)
    if not template:
        return jsonify({'message': '模板不存在'}), 404

    return jsonify({
        'id': template.id,
        'name': template.name,
        'description': template.description,
        'script_content': template.script_content,
        'default_parameters': template.default_parameters,
        'created_by': template.created_by,
        'created_at': template.created_at.isoformat()
    })

@templates_bp.route('/<int:template_id>', methods=['PUT'])
@token_required
def update_template(current_user, template_id):
    template = TestTemplate.query.get(template_id)
    if not template:
        return jsonify({'message': '模板不存在'}), 404

    if template.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'message': '没有权限修改此模板'}), 403

    data = request.json
    template.name = data.get('name', template.name)
    template.description = data.get('description', template.description)
    template.script_content = data.get('script_content', template.script_content)
    template.default_parameters = data.get('default_parameters', template.default_parameters)

    db.session.commit()

    return jsonify({
        'message': '模板更新成功',
        'id': template.id
    })

@templates_bp.route('/<int:template_id>', methods=['DELETE'])
@token_required
def delete_template(current_user, template_id):
    template = TestTemplate.query.get(template_id)
    if not template:
        return jsonify({'message': '模板不存在'}), 404

    if template.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'message': '没有权限删除此模板'}), 403

    db.session.delete(template)
    db.session.commit()

    return jsonify({'message': '模板删除成功'})