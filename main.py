# =============================================
# Discord Signal Bot - Version propre pour Railway
# =============================================

from flask import Flask, request, jsonify
import requests
import ccxt
import time
import threading
from datetime import datetime

# ================== CONFIG ==================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/14815940309585167/AA..."  # ← REMPLACE par ton webhook Discord COMPLET
SYMBOL = "BTCUSDT"  # Change en ETHUSDT, SOLUSDT, etc. si tu veux

app = Flask(__name__)
exchange = ccxt.binance()

# Variables en mémoire
last_1h_low = None
invalidated = False
lock = threading.Lock()

# ================== FONCTIONS ==================
def send_discord(message):
    """Envoie un message sur Discord"""
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message})
        print(f"[DISCORD] Message envoyé : {message[:100]}...")
    except Exception as e:
        print(f"[ERREUR DISCORD] {e}")

def price_monitor():
    """Thread qui surveille les lower lows toutes les 20 secondes"""
    global last_1h_low, invalidated
    while True:
        try:
            with lock:
                if last_1h_low is None or invalidated:
                    time.sleep(20)
                    continue
                
                ticker = exchange.fetch_ticker(SYMBOL)
                current_low = ticker['low']
                
                if current_low < last_1h_low - 5:  # -5 pour éviter les micro-bruits
                    invalidated = True
                    send_discord(f"⚠️ **SIGNAL 1H RAVALÉ** sur {SYMBOL}\n"
                                 f"Nouveau low : {current_low:.2f}\n"
                                 f"→ Tous les signaux 1H/45m/30m/15m sont bloqués jusqu’à un signal 2H+")
        except Exception as e:
            print(f"[ERREUR MONITOR] {e}")
        time.sleep(20)

# ================== ROUTES FLASK ==================
@app.route('/', methods=['GET'])
def home():
    """Page d'accueil pour tester que le bot tourne"""
    return "✅ Discord Signal Bot is ALIVE !<br><br>Webhook endpoint : /webhook (POST only)", 200

@app.route('/webhook', methods=['POST'])
def tv_webhook():
    global last_1h_low, invalidated
    
    data = request.get_data(as_text=True).strip()
    print(f"[WEBHOOK REÇU] {data}")  # Debug visible dans les logs Railway
    
    if not data.startswith("POSITIVE|"):
        return jsonify({"status": "ignored"})
    
    try:
        parts = data.split("|")
        tf = parts[1]
        low = float(parts[2].replace("low:", ""))
        close_price = float(parts[3].replace("close:", ""))
        ticker = parts[4].replace("ticker:", "")
        
        tf_min = int(tf) if tf.isdigit() else 0
        
        with lock:
            if tf_min == 60:  # SIGNAL 1H
                if invalidated:
                    send_discord(f"❌ **NON ACHETÉ** – Signal 1H déjà ravalé sur {ticker}\n"
                                 f"Attends un signal **2H ou supérieur**")
                else:
                    last_1h_low = low
                    invalidated = False
                    send_discord(f"🟢 **SIGNAL POSITIF 1H** détecté sur {ticker}\n"
                                 f"Low noté : {low:.2f}\n"
                                 f"Je surveille maintenant les lower lows...")
                    
            elif tf_min >= 120:  # SIGNAL 2H ou plus
                invalidated = False
                last_1h_low = None
                send_discord(f"🔄 **SIGNAL {tf} détecté** → Invalidation 1H RESET\n"
                             f"Tu peux à nouveau prendre les signaux 1H et inférieurs !")
                
    except Exception as e:
        print(f"[ERREUR PARSING] {e}")
    
    return jsonify({"status": "ok"}), 200

# ================== LANCEMENT ==================
# Démarrage du thread de surveillance
threading.Thread(target=price_monitor, daemon=True).start()

print("🚀 Bot démarré - Prêt à recevoir les webhooks TradingView")
