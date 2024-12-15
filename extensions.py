from flask import Flask
from flask_socketio import SocketIO
from models.user import db

# Initialisation des extensions
app = Flask(__name__)
app.secret_key = 'hubert_nicolas'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db.init_app(app)

socketio = SocketIO(app, async_mode='eventlet')

# Dictionnaire pour stocker les parties, les joueurs, les problèmes et les votes
games = {}
