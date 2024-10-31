from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room # type: ignore
import json
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

# Configuration de la partie
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        num_players = int(request.form["num_players"])
        player_names = [request.form[f"player_{i}"] for i in range(num_players)]
        rule = request.form["rule"]
        
        # Création d'une session de partie
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        session["num_players"] = num_players
        session["player_names"] = player_names
        session["rule"] = rule
        session["backlog"] = json.loads(request.form["backlog"])

        return redirect(url_for("game", session_id=session_id))
    
    return render_template("index.html")

# Page de jeu
@app.route("/game")
def game():
    session_id = session.get("session_id")
    players = session.get("player_names")
    backlog = session.get("backlog")
    rule = session.get("rule")

    return render_template("game.html", players=players, backlog=backlog, rule=rule, session_id=session_id)

# Gestion des votes en temps réel
@socketio.on('join')
def handle_join(data):
    session_id = data["session_id"]
    join_room(session_id)
    emit('status', {'msg': f"{data['username']} a rejoint la partie."}, room=session_id)

@socketio.on('vote')
def handle_vote(data):
    session_id = data["session_id"]
    vote = data["vote"]
    emit('vote_received', {'username': data['username'], 'vote': vote}, room=session_id)

if __name__ == "__main__":
    socketio.run(app, debug=True)
