import urllib.parse
from flask import Flask, render_template_string, request, redirect

app = Flask(__name__)

# =======================================================
#  ZONE DE CRYPTAGE : ICI TU METTRAS TON CODE MORSE PLUS TARD
# =======================================================

def mon_chiffrement_morse(texte_normal):
    # Pour l'instant, on met juste en majuscules pour tester le site
    texte_crypte = texte_normal.upper()
    return texte_crypte

def mon_dechiffrement_morse(texte_morse):
    # Pour l'instant, on met juste en minuscules pour tester le site
    texte_decouvert = texte_morse.lower()
    return texte_decouvert

# =======================================================
#         ZONE WEB : LA STRUCTURE DE LA PAGE
# =======================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mon Application Morse WhatsApp</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 500px; margin: 40px auto; padding: 15px; background-color: #f0f2f5; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin-bottom: 20px; }
        h2 { color: #008069; margin-top: 0; font-size: 1.2em; }
        textarea { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #bfc5c9; border-radius: 8px; box-sizing: border-box; font-size: 15px; }
        button { color: white; border: none; padding: 14px; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px; background-color: #00a884; width: 100%; }
        button:hover { background-color: #008069; }
        .btn-decrypt { background-color: #53bdeb; }
        .btn-decrypt:hover { background-color: #027eb5; }
        .result-box { background: #f0f9eb; color: #1e4620; padding: 15px; border-radius: 8px; margin-top: 15px; word-break: break-all; }
    </style>
</head>
<body>

    <div class="card">
        <h2>🔒 1. Écrire un message (Sera traduit en Morse)</h2>
        <form method="POST" action="/encrypt-and-redirect">
            <textarea name="message" rows="4" placeholder="Tape ton texte ici..." required></textarea>
            <button type="submit">Traduire et Envoyer sur WhatsApp</button>
        </form>
    </div>

    <div class="card">
        <h2>🔓 2. Déchiffrer du Morse reçu</h2>
        <form method="POST" action="/decrypt">
            <textarea name="encrypted_message" rows="3" placeholder="Colle le morse reçu ici..." required></textarea>
            <button type="submit" class="btn-decrypt">Traduire en texte clair</button>
        </form>

        {% if decrypted_message %}
        <div class="result-box">
            <strong>Message traduit :</strong><br><br>
            <span style="white-space: pre-wrap;">{{ decrypted_message }}</span>
        </div>
        {% endif %}
    </div>

</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/encrypt-and-redirect", methods=["POST"])
def encrypt_and_redirect():
    message_saisi = request.form.get("message")
    message_morse = mon_chiffrement_morse(message_saisi)
    encoded_morse = urllib.parse.quote(message_morse)
    whatsapp_url = f"https://wa.me/?text={encoded_morse}"
    return redirect(whatsapp_url)

@app.route("/decrypt", methods=["POST"])
def decrypt():
    morse_recu = request.form.get("encrypted_message").strip()
    texte_decode = mon_dechiffrement_morse(morse_recu)
    return render_template_string(HTML_TEMPLATE, decrypted_message=texte_decode)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)