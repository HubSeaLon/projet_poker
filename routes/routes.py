from flask import render_template, request, redirect, url_for, session
from flask_socketio import join_room, emit
from extensions import app, socketio, games, db
from models.user import User
import random




# Fonction pour générer un ID de partie unique
def generate_unique_game_id():
    while True:
        game_id = str(random.randint(1000, 9999))
        if game_id not in games:
            return game_id

# Routes HTTP
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
            if game_mode == "strict":
                return redirect(url_for("game_room", game_id=game_id))
            else:
                return redirect(url_for("game_room_2", game_id=game_id))
            

        elif "join_game" in request.form:
            game_id = request.form["game_id"]
            
            if game_id in games:
                if session["pseudo"] not in games[game_id]["players"]:
                    games[game_id]["players"].append(session["pseudo"])
                session["game_id"] = game_id

                # Récupérer le mode de jeu de la partie
                game_mode = games[game_id]["mode"]

                # Rediriger vers la bonne salle en fonction du mode de jeu
                if game_mode == "strict":
                    return redirect(url_for("game_room", game_id=game_id))
                else:
                    return redirect(url_for("game_room_2", game_id=game_id))
            else:
                error = "L'ID de partie n'existe pas."
                return render_template("dashboard.html", pseudo=session["pseudo"], error=error)


    return render_template("dashboard.html", pseudo=session["pseudo"])



## - Game Room - ##

@app.route("/game_room/<game_id>")
def game_room(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])

@app.route("/game_room_2/<game_id>")
def game_room_2(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room_2.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])



@socketio.on("start_game")
def handle_start_game(data):
    game_id = data["game_id"]
    
    if session["pseudo"] == games[game_id]["host"]: # Vérifie si l'utilisateur qui déclenche est bien l'hôte
        games[game_id]["status"] = "active"
        emit("start_game", {"game_id": game_id}, room=game_id)

@socketio.on("select_problem")
def handle_select_problem(data):
    game_id = data["game_id"]
    problem = data["problem"]

    games[game_id]["current_problem"] = problem # Met à jour le problème actuel dans la partie

    emit("problem_selected", {"problem": problem}, room=game_id)   # Diffuse à tous les joueurs le problème sélectionné

@socketio.on("start_vote")
def handle_start_vote(data):
    game_id = data["game_id"]
    problem = data["problem"]
    
    games[game_id]["votes"][problem] = {} # Initialiser les votes pour ce problème
    
    emit("vote_started", {"problem": problem}, room=game_id) # Notifier tous les joueurs pour démarrer le vote

@socketio.on("cast_vote")
def handle_cast_vote(data):
    game_id = data["game_id"]
    problem = data["problem"]
    vote = data["vote"]
    pseudo = data["pseudo"]

    # Vérifie si le vote pour ce problème est déjà conclu
    if problem in games[game_id].get("concluded_votes", {}):
        return  # Ignore les votes si le problème est déjà conclu

    # Enregistre le vote pour le joueur et le problème
    games[game_id]["votes"][problem][pseudo] = vote

    # Notifie tous les joueurs des votes en cours (ne conclut pas le problème)
    emit("update_votes", {"problem": problem, "votes": games[game_id]["votes"][problem]}, room=game_id)


@socketio.on("join_room")
def handle_join(data):
    game_id = data["game_id"]
    pseudo = data["pseudo"]
    join_room(game_id)

    # Ajoute le joueur à la liste s'il n'est pas déjà dans la partie
    if pseudo not in games[game_id]["players"]:
        games[game_id]["players"].append(pseudo)
    
    # Prépare les données pour l'état de la partie
    game_data = {
        "status": games[game_id]["status"],
        "current_problem": games[game_id].get("current_problem", None),
        "problems": games[game_id]["problems"],
        "votes": games[game_id]["votes"],
        "concluded_votes": games[game_id].get("concluded_votes", {})
    }

    # Envoie l'état actuel de la partie et les problèmes/votes au client
    emit("update_players", {"players": games[game_id]["players"], "host": games[game_id]["host"]}, room=game_id)
    emit("game_state", game_data, room=request.sid)



@socketio.on("add_problem")
def handle_add_problem(data):
    game_id = data["game_id"]
    problem = data["problem"]
    games[game_id]["problems"].append(problem)
    games[game_id]["votes"][problem] = {}
    emit("new_problem", {"problem": problem}, room=game_id)


@socketio.on("end_game")
def handle_end_game(data):
    game_id = data["game_id"]
    pseudo = session.get("pseudo")

    # Vérifie que la partie existe
    if game_id not in games:
        emit("error", {"message": "La partie n'existe pas ou a déjà été terminée."}, room=request.sid)
        return

    # Vérifie si l'utilisateur est l'hôte de la partie
    if games[game_id]["host"] == pseudo:
        # Notifie tous les joueurs que la partie est terminée
        emit("game_ended", {"message": "La partie a été terminée par l'hôte."}, room=game_id)
        # Supprime la partie du dictionnaire des parties (optionnel)
        del games[game_id]


@socketio.on("devoiler_vote")
def devoiler_vote(data):
    game_id = data["game_id"]
    problem = data["problem"]

    # Vérifier que la partie et le problème existent
    if game_id not in games or problem not in games[game_id]["votes"]:
        emit("error", {"message": "Partie ou problème invalide."}, room=request.sid)
        return

    # Récupérer les votes pour le problème en question
    votes = games[game_id]["votes"].get(problem, {})
    players = games[game_id]["players"]

    # Vérification de l'unanimité
    if len(set(votes.values())) == 1 and len(votes) == len(players):
        # Si unanime, enregistrer le résultat et notifier les joueurs
        unanimous_vote = list(votes.values())[0]
        games[game_id].setdefault("concluded_votes", {})[problem] = unanimous_vote
        games[game_id]["current_problem"] = None

        # Émettre un événement de vote unanime
        socketio.emit("unanimous_vote", {
            "problem": problem,
            "result": unanimous_vote,
            "votes": votes
        }, room=game_id)

        # Rafraîchir automatiquement l'interface des joueurs
        socketio.emit("refresh_ui", room=game_id)
    else:
        # Si ce n'est pas unanime, afficher les votes des joueurs et demander un nouveau vote
        socketio.emit("revote", {
            "problem": problem,
            "message": f"Re votez pour le problème {problem}",
            "votes": votes
        }, room=game_id)


@socketio.on("devoiler_vote_2")
def devoiler_vote_2(data):
    game_id = data["game_id"]
    problem = data["problem"]
    compteur = data["compteur"]

    if game_id not in games or problem not in games[game_id]["votes"]:
        emit("error", {"message": "Partie ou problème invalide."}, room=request.sid)
        return
    
    # Récupérer les votes pour le problème en question
    votes = games[game_id]["votes"].get(problem, {})
    players = games[game_id]["players"]

    if compteur == 1:
        if len(set(votes.values())) == 1 and len(votes) == len(players):
            # Si unanime, enregistrer le résultat et notifier les joueurs
            unanimous_vote = list(votes.values())[0]
            games[game_id].setdefault("concluded_votes", {})[problem] = unanimous_vote
            games[game_id]["current_problem"] = None

            # Émettre un événement de vote unanime
            socketio.emit("unanimous_vote", {
                "problem": problem,
                "result": unanimous_vote,
                "votes": votes
            }, room=game_id)

            # Rafraîchir automatiquement l'interface des joueurs
            socketio.emit("refresh_ui", room=game_id)

        else:
            socketio.emit("revote", {
                "problem": problem,
                "message": f"Re votez pour le problème {problem}",
                "votes": votes
            }, room=game_id)
    else:
        # Calculer la moyenne des votes et arrêter le vote
        if votes:
            total_votes = sum(votes.values())
            moyenne_vote = total_votes / len(votes)

            # Enregistrer le résultat moyen
            games[game_id].setdefault("concluded_votes", {})[problem] = moyenne_vote
            games[game_id]["current_problem"] = None

            # Émettre un événement avec le résultat de la moyenne des votes
            socketio.emit("average_vote", {
                "problem": problem,
                "average_result": moyenne_vote,
                "votes": votes
            }, room=game_id)

            # Rafraîchir automatiquement l'interface des joueurs
            socketio.emit("refresh_ui", room=game_id)
        else:
            emit("error", {"message": "Aucun vote enregistré pour le problème."}, room=request.sid)



