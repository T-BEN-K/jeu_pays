from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random
import re

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

# --- Inscription des joueurs ---
@socketio.on('register')
def register(data):
    username = data['username'].upper()
    country = re.sub(r'[^A-Z]', '', data['country'].upper())  # force majuscule et lettres uniquement

    if not username or not country:
        return  # ignore si données invalides

    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'ready': False,
        'turn': False
    }
    scores[username] = 0
    emit('update_players', players, broadcast=True)

@socketio.on('set_ready')
def set_ready(data):
    username = data['username'].upper()
    if username in players:
        players[username]['ready'] = True
        emit('update_players', players, broadcast=True)

    # Partie commence uniquement si au moins 2 joueurs
    if len(players) >= 2 and all(p['ready'] for p in players.values()):
        start_game()

def start_game():
    global turn_order, current_turn
    turn_order = list(players.keys())
    random.shuffle(turn_order)
    current_turn = turn_order[0]
    players[current_turn]['turn'] = True

    emit('game_start', broadcast=True)
    emit('update_turn', current_turn, broadcast=True)
    emit('update_scores', scores, broadcast=True)
    emit('update_players', players, broadcast=True)

@socketio.on('guess_letter')
def guess_letter(data):
    global current_turn
    username = data.get('username', '').upper()
    target = data.get('target', '').upper()
    letter = re.sub(r'[^A-Z]', '', data.get('letter', '').upper())

    if not username or not target or not letter:
        return  # ignore si données invalides
    if target not in players:
        return

    country = players[target]['country']
    revealed = players[target]['revealed']

    if letter in country:
        for i, l in enumerate(country):
            if l == letter:
                revealed[i] = letter
        scores[username] += 1
        emit('update_word', {'target': target, 'revealed': revealed}, broadcast=True)
        emit('update_scores', scores, broadcast=True)
        # le joueur garde la main
    else:
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
