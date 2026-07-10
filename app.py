from flask import Flask
import os
from src.api import parse
from configs.logging_config import logger

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')

# 注册API蓝图
app.register_blueprint(parse.bp, url_prefix='/api')


@app.route('/')
def index():
    """健康检查"""
    return '{"status": "ok", "message": "Media Parser API is running"}'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8051)
