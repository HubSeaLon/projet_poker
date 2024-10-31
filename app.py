from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, emit
from models.user import db, User
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db.init_app(app)

socketio = SocketIO(app, async_mode='eventlet')


# Dictionnaire pour stocker les parties, les joueurs, les problèmes et les votes
games = {}

with app.app_context():
    db.create_all()

@app.route("/", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        pseudo = request.form.get("pseudo")
        if pseudo:
            existing_user = User.query.filter_by(pseudo=pseudo).first()
            if existing_user:
                error = "Ce pseudo est déjà pris. Choisissez un autre pseudo."
                return render_template("signup.html", error=error)
            new_user = User(pseudo=pseudo)
            db.session.add(new_user)
            db.session.commit()
            session["pseudo"] = pseudo
            return redirect(url_for("dashboard"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pseudo = request.form.get("pseudo")
        user = User.query.filter_by(pseudo=pseudo).first()
        if user:
            session["pseudo"] = pseudo
            return redirect(url_for("dashboard"))
        else:
            error = "Pseudo incorrect. Veuillez vous inscrire."
            return render_template("login.html", error=error)
    return render_template("login.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "pseudo" not in session:
        return redirect(url_for("signup"))

    if request.method == "POST":
        if "create_game" in request.form:
            game_mode = request.form["game_mode"]
            game_id = generate_unique_game_id()
            games[game_id] = {
                "mode": game_mode,
                "players": [session["pseudo"]],
                "host": session["pseudo"],
                "status": "waiting",
                "problems": [],
                "votes": {}
            }
            session["game_id"] = game_id
            return redirect(url_for("game_room", game_id=game_id))

        elif "join_game" in request.form:
            game_id = request.form["game_id"]
            if game_id in games:
                if session["pseudo"] not in games[game_id]["players"]:
                    games[game_id]["players"].append(session["pseudo"])
                session["game_id"] = game_id
                return redirect(url_for("game_room", game_id=game_id))
            else:
                error = "L'ID de partie n'existe pas."
                return render_template("dashboard.html", pseudo=session["pseudo"], error=error)

    return render_template("dashboard.html", pseudo=session["pseudo"])

@app.route("/start_game/<game_id>", methods=["POST"])
def start_game(game_id):
    # L'hôte démarre la partie, ce qui active l'interface de vote pour tous
    if session["pseudo"] == games[game_id]["host"]:
        games[game_id]["status"] = "active"
        socketio.emit("start_game", {"game_id": game_id}, room=game_id)
    return redirect(url_for("game_room", game_id=game_id))


@socketio.on("start_game")
def handle_start_game(data):
    game_id = data["game_id"]
    # Vérifie si l'utilisateur qui déclenche est bien l'hôte
    if session["pseudo"] == games[game_id]["host"]:
        games[game_id]["status"] = "active"
        # Notifie tous les utilisateurs dans la salle que le jeu a commencé
        emit("start_game", {"game_id": game_id}, room=game_id)


@app.route("/game_room/<game_id>")
def game_room(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]
    players_display = players + ["vide"] * (4 - len(players))

    return render_template("game_room.html", game_id=game_id, players=players_display, pseudo=session["pseudo"], host=games[game_id]["host"])


@socketio.on("join_room")
def handle_join(data):
    game_id = data["game_id"]
    pseudo = data["pseudo"]
    join_room(game_id)
    emit("update_players", {"players": games[game_id]["players"], "host": games[game_id]["host"]}, room=game_id)

@socketio.on("add_problem")
def handle_add_problem(data):
    game_id = data["game_id"]
    problem = data["problem"]
    games[game_id]["problems"].append(problem)
    games[game_id]["votes"][problem] = {}
    emit("new_problem", {"problem": problem}, room=game_id)

@socketio.on("cast_vote")
def handle_cast_vote(data):
    game_id = data["game_id"]
    problem = data["problem"]
    vote = data["vote"]
    pseudo = data["pseudo"]

    # Enregistre le vote pour le joueur et le problème
    games[game_id]["votes"][problem][pseudo] = vote

    # Récupère tous les joueurs et leurs votes pour le problème actuel
    players = games[game_id]["players"]
    all_votes = [games[game_id]["votes"][problem].get(player) for player in players]

    # Vérifie si tous les joueurs ont voté et si les votes sont unanimes
    if all(all_votes) and len(set(all_votes)) == 1:
        unanimous_vote = all_votes[0]  # Tous les votes sont les mêmes
        emit("unanimous_vote", {"problem": problem, "result": unanimous_vote}, room=game_id)
    else:
        # Met à jour les votes pour les autres joueurs
        emit("update_votes", {"problem": problem, "votes": games[game_id]["votes"][problem]}, room=game_id)

@socketio.on("select_problem")
def handle_select_problem(data):
    game_id = data["game_id"]
    problem = data["problem"]
    emit("problem_selected", {"problem": problem}, room=game_id)


def generate_unique_game_id():
    while True:
        game_id = str(random.randint(1000, 9999))
        if game_id not in games:
            return game_id

if __name__ == "__main__":
    socketio.run(app, debug=True)
