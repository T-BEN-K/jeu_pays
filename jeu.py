from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import random, re

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

@socketio.on('register')
def register(data):
    username = re.sub(r'[^A-Z]', '', data['username'].upper())
    country = re.sub(r'[^A-Z]', '', data['country'].upper())
    if not username or not country:
        return
    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'ready': False,
        'turn': False,
        'eliminated': False
    }
    scores[username] = 0
    emit('update_players', players, broadcast=True)

@socketio.on('set_ready')
def set_ready(data):
    username = data['username'].upper()
    if username in players:
        players[username]['ready'] = True
        emit('update_players', players, broadcast=True)
    if len(players) >= 2 and all(p['ready'] for p in players.values()):
        start_game()

def start_game():
    global turn_order, current_turn
    turn_order = [p for p in players if not players[p]['eliminated']]
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
    username = re.sub(r'[^A-Z]', '', data.get('username','').upper())
    target = re.sub(r'[^A-Z]', '', data.get('target','').upper())
    letter = re.sub(r'[^A-Z]', '', data.get('letter','').upper())
    if not username or not target or not letter:
        return
    if target not in players or players[target]['eliminated']:
        return
    if username != current_turn:
        return
    country = players[target]['country']
    revealed = players[target]['revealed']
    if letter in country:
        for i,l in enumerate(country):
            if l == letter:
                revealed[i] = letter
        scores[username] += 1
        emit('update_word', {'target':target,'revealed':revealed}, broadcast=True)
        emit('update_scores', scores, broadcast=True)
        if ''.join(revealed) == country:
            players[target]['eliminated'] = True
            scores[username] += 1
            emit('player_eliminated', target, broadcast=True)
            emit('update_scores', scores, broadcast=True)
            active = [p for p in players if not players[p]['eliminated']]
            if len(active) <= 1:
                emit('game_over', scores, broadcast=True)
                return
    else:
        next_turn()

def next_turn():
    global current_turn
    idx = turn_order.index(current_turn)
    players[current_turn]['turn'] = False
    for i in range(1,len(turn_order)+1):
        candidate = turn_order[(idx+i)%len(turn_order)]
        if not players[candidate]['eliminated']:
            current_turn = candidate
            players[current_turn]['turn'] = True
            emit('update_turn', current_turn, broadcast=True)
            break

if __name__ == '__main__':
    socketio.run(app, debug=True)