from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)

players = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('register')
def register(data):
    username = data['username']
    country = data['country'].upper()
    players[username] = {
        'country': country,
        'revealed': ['_'] * len(country),
        'alive': True,
        'ready': False
    }
    emit('update_players', players, broadcast=True)

@socketio.on('set_ready')
def set_ready(data):
    username = data['username']
    players[username]['ready'] = True
    emit('update_players', players, broadcast=True)

    if all(p['ready'] for p in players.values()):
        emit('game_start', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
