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
    
    game_routes = {
                "strict": "game_room",
                "moyenne": "game_room_2",
                "mediane": "game_room_3",
                "majorite_absolue": "game_room_4",
                "majorite_relative": "game_room_5"
            }

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
    
            # Obtenir la route correspondant au mode de jeu
            route = game_routes.get(game_mode)

            if route:
                return redirect(url_for(route, game_id=game_id))

        elif "join_game" in request.form:
            game_id = request.form["game_id"]
            
            if game_id in games:
                if session["pseudo"] not in games[game_id]["players"]:
                    games[game_id]["players"].append(session["pseudo"])
                session["game_id"] = game_id

                # Récupérer le mode de jeu de la partie
                game_mode = games[game_id]["mode"]

                route = game_routes.get(game_mode)

                if route:
                    return redirect(url_for(route, game_id=game_id))

            else:
                error = "L'ID de partie n'existe pas."
                return render_template("dashboard.html", pseudo=session["pseudo"], error=error)
        

    return render_template("dashboard.html", pseudo=session["pseudo"])



## - Game Room - ##


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


## Unanimite 

@app.route("/game_room/<game_id>")
def game_room(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])

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





## Moyenne ##

@app.route("/game_room_2/<game_id>")
def game_room_2(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room_2.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])

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

## Médiane ## 

@app.route("/game_room_3/<game_id>")
def game_room_3(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room_3.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])



@socketio.on("devoiler_vote_3")
def devoiler_vote_3(data):
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
        # Calculer la médiane des votes et arrêter le vote
        if votes:
            # Récupérer les votes dans une liste triée
            sorted_votes = sorted(votes.values())
            num_votes = len(sorted_votes)
            
            # Calculer la médiane
            if num_votes % 2 == 1:
                # Nombre impair de votes
                median_vote = sorted_votes[num_votes // 2]
            else:
                # Nombre pair de votes : moyenne des deux valeurs centrales
                median_vote = (sorted_votes[num_votes // 2 - 1] + sorted_votes[num_votes // 2]) / 2
            
            # Enregistrer le résultat médian
            games[game_id].setdefault("concluded_votes", {})[problem] = median_vote
            games[game_id]["current_problem"] = None

            # Émettre un événement avec le résultat de la médiane des votes
            socketio.emit("median_vote", {
                "problem": problem,
                "median_result": median_vote,
                "votes": votes
            }, room=game_id)

            # Rafraîchir automatiquement l'interface des joueurs
            socketio.emit("refresh_ui", room=game_id)
        else:
            emit("error", {"message": "Aucun vote enregistré pour le problème."}, room=request.sid)



## Majorité Absolue ## 

@app.route("/game_room_4/<game_id>")
def game_room_4(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room_4.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])



@socketio.on("devoiler_vote_4")
def devoiler_vote_4(data):
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
        
        # Calculer la majorité absolue des votes et arrêter le vote
        if votes:
            # Compter les occurrences de chaque vote
            vote_counts = {}
            for vote in votes.values():
                vote_counts[vote] = vote_counts.get(vote, 0) + 1

            # Déterminer si une valeur dépasse la moitié des votes
            num_votes = len(votes)
            majority_vote = None
            for vote, count in vote_counts.items():
                if count > num_votes / 2:
                    majority_vote = vote
                    break

            if majority_vote is not None:
                # Enregistrer le résultat de la majorité absolue
                games[game_id].setdefault("concluded_votes", {})[problem] = majority_vote
                games[game_id]["current_problem"] = None

                # Émettre un événement avec le résultat de la majorité absolue
                socketio.emit("majority_vote", {
                    "problem": problem,
                    "majority_result": majority_vote,
                    "votes": votes
                }, room=game_id)

                # Rafraîchir automatiquement l'interface des joueurs
                socketio.emit("refresh_ui", room=game_id)
            else:
                # Pas de majorité absolue, demander un nouveau vote
                socketio.emit("revote", {
                    "problem": problem,
                    "votes": votes,
                    "message": "Pas de majorité absolue. Veuillez revoter."
                }, room=game_id)
        else:
            emit("error", {"message": "Aucun vote enregistré pour le problème."}, room=request.sid)



## Majorité relative 

@app.route("/game_room_5/<game_id>")
def game_room_5(game_id):
    if game_id not in games or session["pseudo"] not in games[game_id]["players"]:
        return redirect(url_for("dashboard"))

    players = games[game_id]["players"]

    return render_template("game_room_5.html", game_id=game_id, pseudo=session["pseudo"], host=games[game_id]["host"])


@socketio.on("devoiler_vote_5")
def devoiler_vote_5(data):
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
        
       # Calculer la majorité relative des votes et arrêter le vote
        if votes:
            # Compter les occurrences de chaque vote
            vote_counts = {}
            for vote in votes.values():
                vote_counts[vote] = vote_counts.get(vote, 0) + 1

            # Trouver le(s) vote(s) ayant le plus d'occurrences
            max_votes = max(vote_counts.values())
            majority_candidates = [vote for vote, count in vote_counts.items() if count == max_votes]

            # Vérifier s'il y a une majorité claire ou une égalité
            if len(majority_candidates) == 1:
                # Une seule option a la majorité relative
                majority_vote = majority_candidates[0]

                # Enregistrer le résultat de la majorité relative
                games[game_id].setdefault("concluded_votes", {})[problem] = majority_vote
                games[game_id]["current_problem"] = None

                # Émettre un événement avec le résultat de la majorité relative
                socketio.emit("relative_majority_vote", {
                    "problem": problem,
                    "majority_result": majority_vote,
                    "votes": votes
                }, room=game_id)

                # Rafraîchir automatiquement l'interface des joueurs
                socketio.emit("refresh_ui", room=game_id)
            else:
                # Pas de majorité relative (égalité entre plusieurs options)
                socketio.emit("revote", {
                    "problem": problem,
                    "votes": votes,
                    "message": "Pas de majorité relative. Veuillez revoter."
                }, room=game_id)
        else:
            # Aucun vote enregistré pour le problème
            emit("error", {"message": "Aucun vote enregistré pour le problème."}, room=request.sid)




