from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random, re, threading

app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")

players = {}
scores = {}
turn_order = []
current_turn = None
game_active = False
sid_to_username = {}
username_to_sid = {}
history = []
timer_value = 0
timer_lock = threading.RLock()
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
    socketio.emit('update_history', history)


def set_timer(value):
    global timer_value
    with timer_lock:
        timer_value = max(0, int(value))
    socketio.emit('update_timer', {'value': timer_value})


def append_message(message, public=True, sid=None):
    append_history(message)
    if public:
        socketio.emit('message', {'text': message})
    elif sid:
        socketio.emit('message', {'text': message}, to=sid)


@socketio.on('connect')
def connect():
    emit('update_players', players)
    emit('update_scores', scores)
    emit('game_active', {'active': game_active})
    if current_turn:
        emit('update_turn', current_turn)
    emit('update_history', history)
    emit('update_timer', {'value': timer_value})


@socketio.on('disconnect')
def disconnect():
    global current_turn, turn_order, game_active
    username = sid_to_username.pop(request.sid, None)
    if username:
        username_to_sid.pop(username, None)
    if not username or username not in players:
        return

    leaving = players.pop(username)
    scores.pop(username, None)
    turn_order = [p for p in turn_order if p != username]

    if game_active and leaving['active'] and not leaving['eliminated']:
        append_message(f'{username} a quitté la partie et est retiré(e) du jeu.')
        if username == current_turn or current_turn not in players or players.get(current_turn, {}).get('eliminated', True):
            if not next_turn():
                game_active = False
                socketio.emit('game_active', {'active': game_active})
                socketio.emit('update_players', players)
                socketio.emit('update_scores', scores)
                return
        else:
            socketio.emit('update_players', players)
    else:
        append_message(f'{username} a quitté.')
        socketio.emit('update_players', players)

    socketio.emit('update_scores', scores)
    if game_active:
        remaining = [p for p in players.values() if p['active'] and not p['eliminated']]
        if len(remaining) <= 1:
            append_message('Il ne reste plus qu’un joueur, fin de la partie.')
            game_active = False
            socketio.emit('game_active', {'active': game_active})
            socketio.emit('game_over', {'scores': scores})


@socketio.on('force_state')
def force_state(data):
    emit('update_players', players)
    emit('update_scores', scores)
    if current_turn:
        emit('update_turn', current_turn)
    emit('update_history', history)
    emit('update_timer', {'value': timer_value})


@socketio.on('reconnect_player')
def reconnect_player(data):
    username = sanitize(data.get('username', ''))
    country = sanitize(data.get('country', ''))
    if not username or username not in players or players[username]['country'] != country:
        emit('reconnect_failed', {'message': 'Impossible de reprendre la partie. Retour à l’accueil.'})
        return
    if username in username_to_sid and username_to_sid[username] != request.sid:
        emit('reconnect_failed', {'message': 'Cet utilisateur est déjà connecté ailleurs.'})
        return

    sid_to_username[request.sid] = username
    username_to_sid[username] = request.sid
    emit('game_active', {'active': game_active})
    emit('reconnect_success', {'message': 'Reconnecté avec succès.'})
    emit('update_players', players)
    emit('update_scores', scores)
    if current_turn:
        emit('update_turn', current_turn)
    emit('update_history', history)
    emit('update_timer', {'value': timer_value})


@socketio.on('register')
def register(data):
    global game_active
    username = sanitize(data.get('username', ''))
    country = sanitize(data.get('country', ''))
    if not username or not country or len(country) < 2:
        emit('registration_failed', {'message': 'Pseudo ou pays invalide ou pseudo déjà utilisé.'})
        return
    if username in players:
        emit('registration_failed', {'message': 'Pseudo déjà utilisé ou reconnecte-toi si tu es déjà inscrit.'})
        return
    active = not game_active
    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'ready': False,
        'turn': False,
        'eliminated': False,
        'active': active,
        'status': 'en attente' if not active else 'en attente de prêt',
        'eliminations': 0
    }
    scores[username] = 0
    sid_to_username[request.sid] = username
    username_to_sid[username] = request.sid
    append_message(f'{username} a rejoint la partie.')
    socketio.emit('update_players', players)
    socketio.emit('game_active', {'active': game_active}, to=request.sid)
    if not active:
        socketio.emit('message', {'text': f'{username} est arrivé(e) et attend la fin de la partie en cours.'}, to=request.sid)


@socketio.on('set_ready')
def set_ready(data):
    username = sanitize(data.get('username', ''))
    if username not in players:
        return
    players[username]['ready'] = True
    append_message(f'{username} est prêt.')
    socketio.emit('update_players', players)

    # Correction : on vérifie directement tous les joueurs
    if not game_active:
        if len(players) >= 2 and all(p['ready'] for p in players.values()):
            start_game()


@socketio.on('reset_game')
def reset_game(data):
    global turn_order, current_turn, scores, game_active
    username = sanitize(data.get('username', ''))
    if username not in players:
        return
    game_active = False
    for p in players:
        players[p]['revealed'] = ['_'] * len(players[p]['country'])
        players[p]['ready'] = False
        players[p]['turn'] = False
        players[p]['eliminated'] = False
        players[p]['active'] = True
        players[p]['status'] = 'en attente de prêt'
    scores = {p: 0 for p in players}
    turn_order = [p for p in players]
    current_turn = None
    socketio.emit('game_reset', {'players': players, 'scores': scores})
    socketio.emit('update_turn', current_turn)
    socketio.emit('update_players', players)
    socketio.emit('update_scores', scores)
    set_timer(0)
    append_message(f'{username} a réinitialisé la partie.')


def start_game():
    global turn_order, current_turn, game_active
    game_active = True
    turn_order = [p for p in players if not players[p]['eliminated']]
    for p in turn_order:
        players[p]['status'] = 'en jeu'
    random.shuffle(turn_order)
    current_turn = turn_order[0] if turn_order else None
    if current_turn:
        players[current_turn]['turn'] = True
    socketio.emit('game_start')
    append_message(f'La partie commence ! C’est au tour de {current_turn}.')
    socketio.emit('game_active', {'active': game_active})
    socketio.emit('update_turn', current_turn)
    socketio.emit('update_scores', scores)
    socketio.emit('update_players', players)
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
            socketio.emit('update_word', {'target': target, 'revealed': revealed})
            socketio.emit('update_scores', scores)
            if ''.join(revealed) == country:
                players[target]['eliminated'] = True
                scores[username] += 1
                append_message(f'{target} est éliminé(e) par {username} !')
                socketio.emit('player_eliminated', {'target': target, 'by': username})
                socketio.emit('update_scores', scores)
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
        if not game_active or not current_turn:
            continue
        with timer_lock:
            if timer_value <= 0:
                continue
            set_timer(timer_value - 1)
            if timer_value <= 0:
                append_message(f'Le temps est écoulé pour {current_turn}. Tour suivant.')
                next_turn()


def activate_waiting_players():
    for p in players.values():
        if not p['active']:
            p['active'] = True
            p['status'] = 'en attente de prêt'


def next_turn():
    global current_turn, game_active
    active = [p for p in turn_order if p in players and not players[p]['eliminated']]
    if len(active) <= 1:
        append_message('Partie terminée.')
        socketio.emit('game_over', {'scores': scores})
        activate_waiting_players()
        for p in players:
            players[p]['turn'] = False
        current_turn = None
        game_active = False
        socketio.emit('game_active', {'active': game_active})
        socketio.emit('update_players', players)
        set_timer(0)
        active_players = [p for p in players.values() if p['active']]
        if len(active_players) >= 2 and all(p['ready'] for p in active_players):
            start_game()
        return False
    if current_turn not in active:
        current_turn = active[0]
    else:
        idx = active.index(current_turn)
        current_turn = active[(idx + 1) % len(active)]
    for p in players:
        players[p]['turn'] = p == current_turn
    append_message(f'Nouvel ordre : c’est au tour de {current_turn}.')
    socketio.emit('update_turn', current_turn)
    socketio.emit('update_players', players)
    set_timer(TURN_SECONDS)
    return True


if __name__ == '__main__':
    socketio.start_background_task(timer_loop)
    socketio.run(app, debug=True)