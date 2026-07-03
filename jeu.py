from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random, re, threading, eventlet

app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")

players = {}
scores = {}
turn_order = []
current_turn = None
history = []
timer_value = 0
timer_lock = threading.Lock()
TURN_SECONDS = 20
MAX_HISTORY = 50


def sanitize(text):
    return re.sub(r'[^A-Z]', '', text.upper() if isinstance(text, str) else '')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/game')
def game():
    return render_template('game.html')

def append_history(message):
    history.append(message)
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    socketio.emit('update_history', history, broadcast=True)


def set_timer(value):
    global timer_value
    with timer_lock:
        timer_value = max(0, int(value))
    socketio.emit('update_timer', {'value': timer_value}, broadcast=True)


def append_message(message, public=True, sid=None):
    append_history(message)
    if public:
        socketio.emit('message', {'text': message}, broadcast=True)
    elif sid:
        socketio.emit('message', {'text': message}, to=sid)


@socketio.on('connect')
def connect():
    emit('update_players', players)
    emit('update_scores', scores)
    if current_turn:
        emit('update_turn', current_turn)
    emit('update_history', history)
    emit('update_timer', {'value': timer_value})


@socketio.on('force_state')
def force_state(data):
    emit('update_players', players)
    emit('update_scores', scores)
    if current_turn:
        emit('update_turn', current_turn)
    emit('update_history', history)
    emit('update_timer', {'value': timer_value})


@socketio.on('register')
def register(data):
    username = sanitize(data.get('username', ''))
    country = sanitize(data.get('country', ''))
    if not username or not country or len(country) < 2 or username in players:
        emit('registration_failed', {'message': 'Pseudo ou pays invalide, ou pseudo déjà utilisé.'})
        return
    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'ready': False,
        'turn': False,
        'eliminated': False
    }
    scores[username] = 0
    append_message(f'{username} a rejoint la partie.')
    emit('update_players', players, broadcast=True)


@socketio.on('set_ready')
def set_ready(data):
    username = sanitize(data.get('username', ''))
    if username in players:
        players[username]['ready'] = True
        append_message(f'{username} est prêt.')
        emit('update_players', players, broadcast=True)
        if len(players) >= 2 and all(p['ready'] for p in players.values()):
            start_game()


@socketio.on('reset_game')
def reset_game(data):
    global turn_order, current_turn, scores
    username = sanitize(data.get('username', ''))
    if username not in players:
        return
    for p in players:
        players[p]['revealed'] = ['_'] * len(players[p]['country'])
        players[p]['ready'] = False
        players[p]['turn'] = False
        players[p]['eliminated'] = False
    scores = {p: 0 for p in players}
    turn_order = [p for p in players]
    random.shuffle(turn_order)
    current_turn = turn_order[0] if turn_order else None
    if current_turn:
        players[current_turn]['turn'] = True
    emit('game_reset', {'players': players, 'scores': scores}, broadcast=True)
    emit('update_turn', current_turn, broadcast=True)
    emit('update_players', players, broadcast=True)
    emit('update_scores', scores, broadcast=True)
    set_timer(0)
    append_message(f'{username} a réinitialisé la partie.')


def start_game():
    global turn_order, current_turn
    turn_order = [p for p in players if not players[p]['eliminated']]
    random.shuffle(turn_order)
    current_turn = turn_order[0]
    players[current_turn]['turn'] = True
    emit('game_start', broadcast=True)
    append_message(f'La partie commence ! C’est au tour de {current_turn}.')
    emit('update_turn', current_turn, broadcast=True)
    emit('update_scores', scores, broadcast=True)
    emit('update_players', players, broadcast=True)
    set_timer(TURN_SECONDS)

@socketio.on('guess_letter')
def guess_letter(data):
    global current_turn
    username = sanitize(data.get('username', ''))
    target = sanitize(data.get('target', ''))
    letter = sanitize(data.get('letter', ''))[:1]
    if not username or not target or not letter:
        return
    if username not in players or players[username]['eliminated']:
        emit('message', {'text': 'Ton joueur est éliminé ou introuvable.'}, to=request.sid)
        return
    if target not in players or players[target]['eliminated']:
        emit('message', {'text': 'Cible invalide ou déjà éliminée.'}, to=request.sid)
        return
    if username == target:
        emit('message', {'text': 'Tu dois choisir un autre joueur.'}, to=request.sid)
        return
    if username != current_turn:
        emit('message', {'text': 'Ce n’est pas ton tour.'}, to=request.sid)
        return

    country = players[target]['country']
    revealed = players[target]['revealed']
    if letter in revealed:
        emit('message', {'text': f'La lettre {letter} est déjà découverte pour {target}.'}, to=request.sid)
        return

    if letter in country:
        found = False
        for i, ch in enumerate(country):
            if ch == letter and revealed[i] == '_':
                revealed[i] = letter
                found = True
        if found:
            scores[username] += 1
            append_message(f'{username} a trouvé {letter} sur {target} !')
            emit('update_word', {'target': target, 'revealed': revealed}, broadcast=True)
            emit('update_scores', scores, broadcast=True)
            if ''.join(revealed) == country:
                players[target]['eliminated'] = True
                scores[username] += 1
                append_message(f'{target} est éliminé(e) par {username} !')
                emit('player_eliminated', {'target': target, 'by': username}, broadcast=True)
                emit('update_scores', scores, broadcast=True)
                if not next_turn():
                    return
        else:
            append_message(f'{letter} ne révèle rien de nouveau pour {target}.')
            next_turn()
    else:
        append_message(f'{letter} n’est pas dans le mot de {target}.')
        next_turn()


@socketio.on('chat_message')
def chat_message(data):
    sender = sanitize(data.get('username', ''))
    text = data.get('text', '')
    if not sender or sender not in players or players[sender]['eliminated']:
        emit('message', {'text': 'Impossible d’envoyer le message.'}, to=request.sid)
        return
    text = str(text).strip()
    if not text:
        return
    message = f'{sender} : {text}'
    append_message(message)


def timer_loop():
    while True:
        socketio.sleep(1)
        if not current_turn:
            continue
        with timer_lock:
            if timer_value <= 0:
                continue
            set_timer(timer_value - 1)
            if timer_value <= 0:
                append_message(f'Le temps est écoulé pour {current_turn}. Tour suivant.')
                next_turn()


def next_turn():
    global current_turn
    active = [p for p in turn_order if not players[p]['eliminated']]
    if len(active) <= 1:
        append_message('Partie terminée.')
        socketio.emit('game_over', {'scores': scores}, broadcast=True)
        return False
    if current_turn not in active:
        current_turn = active[0]
    else:
        idx = active.index(current_turn)
        current_turn = active[(idx + 1) % len(active)]
    for p in players:
        players[p]['turn'] = p == current_turn
    append_message(f'Nouvel ordre : c’est au tour de {current_turn}.')
    socketio.emit('update_turn', current_turn, broadcast=True)
    socketio.emit('update_players', players, broadcast=True)
    set_timer(TURN_SECONDS)
    return True

if __name__ == '__main__':
    socketio.start_background_task(timer_loop)
    socketio.run(app, debug=True)