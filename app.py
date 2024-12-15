from extensions import app, socketio, db
from routes import routes  # Importez les routes après l'initialisation des extensions

# Initialisation de la base de données
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    socketio.run(app, debug=True)