from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
socketio = SocketIO(app)

players = {}
scores = {}
turn_order = []
current_turn = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/game')
def game():
    return render_template('game.html')

# --- Gestion des joueurs ---
@socketio.on('register')
def register(data):
    username = data['username']
    country = data['country'].upper()

    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'alive': True,
        'ready': False,
        'turn': False
    }
    scores[username] = 0
    emit('update_players', players, broadcast=True)

@socketio.on('set_ready')
def set_ready(data):
    username = data['username']
    players[username]['ready'] = True
    emit('update_players', players, broadcast=True)

    # Vérifier si tous les joueurs sont prêts
    if all(p['ready'] for p in players.values()) and len(players) > 1:
        start_game()

# --- Démarrage de la partie ---
def start_game():
    global turn_order, current_turn
    turn_order = list(players.keys())
    random.shuffle(turn_order)
    current_turn = turn_order[0]
    players[current_turn]['turn'] = True

    emit('game_start', broadcast=True)
    emit('update_turn', current_turn, broadcast=True)
    for username, data in players.items():
        emit('update_word', data['revealed'], room=request.sid)

# --- Gestion des tours ---
@socketio.on('guess_letter')
def guess_letter(data):
    global current_turn
    username = data['username']
    letter = data['letter'].upper()

    country = players[username]['country']
    revealed = players[username]['revealed']

    if letter in country:
        for i, l in enumerate(country):
            if l == letter:
                revealed[i] = letter
        scores[username] += 1
        emit('update_word', revealed, broadcast=True)
        emit('update_scores', scores, broadcast=True)
        # Le joueur garde la main
    else:
        # Passer au joueur suivant
        next_turn()

def next_turn():
    global current_turn
    idx = turn_order.index(current_turn)
    players[current_turn]['turn'] = False
    current_turn = turn_order[(idx + 1) % len(turn_order)]
    players[current_turn]['turn'] = True
    emit('update_turn', current_turn, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)

