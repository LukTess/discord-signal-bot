DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1481759403097985167/AASwl2p0p3NzatPh0rZwBDe_w1r-PhKEUcIFRfIVVwBvbdgUPMzSSfWJlDY4_yLjHQpV"
SYMBOL = "BTCUSDT"  # ← change si tu trades ETHUSDT, SOLUSDT, etc.from flask import Flask, request, jsonify
import requests
import ccxt
import threading
import time
from datetime import datetime

app = Flask(__name__)

# ==================== CONFIGURE ÇA ====================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/XXXXXXXXXXXX"  # ← TON webhook Discord ici
SYMBOL = "BTCUSDT"          # change si tu trades autre chose (ETHUSDT, SOLUSDT...)
# =====================================================

exchange = ccxt.binance()

# Variables mémoire
last_1h_low = None
invalidated = False
lock = threading.Lock()

def send_discord(message):
    requests.post(DISCORD_WEBHOOK, json={"content": message})

# Thread qui surveille les lower lows toutes les 20 secondes
def price_monitor():
    global last_1h_low, invalidated
    while True:
        try:
            with lock:
                if last_1h_low is None or invalidated:
                    time.sleep(20)
                    continue
                
                ticker = exchange.fetch_ticker(SYMBOL)
                current_low = ticker['low']
                
                if current_low < last_1h_low - 5:   # -5 pour éviter les micro-bruits
                    invalidated = True
                    send_discord(f"⚠️ **SIGNAL 1H RAVALÉ** sur {SYMBOL}\n"
                                 f"Nouveau low : {current_low:.2f}\n"
                                 f"→ Tous les signaux 1H/45m/30m/15m sont bloqués jusqu’à un signal 2H+")
        except:
            pass
        time.sleep(20)

@app.route('/webhook', methods=['POST'])
def tv_webhook():
    global last_1h_low, invalidated
    
    data = request.get_data(as_text=True)
    
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
            if tf_min == 60:                                 # === SIGNAL 1H ===
                if invalidated:
                    send_discord(f"❌ **NON ACHETE** – Signal 1H déjà ravalé sur {ticker}\n"
                                 f"Attends un signal **2H ou supérieur**")
                else:
                    last_1h_low = low
                    invalidated = False
                    send_discord(f"🟢 **SIGNAL POSITIF 1H** détecté sur {ticker}\n"
                                 f"Low noté : {low:.2f}\n"
                                 f"Je surveille maintenant les lower lows...")
                    
            elif tf_min >= 120:                              # === SIGNAL 2H ou plus ===
                invalidated = False
                last_1h_low = None
                send_discord(f"🔄 **SIGNAL {tf} détecté** → Invalidation 1H RESET\n"
                             f"Tu peux à nouveau prendre les signaux 1H et inférieurs !")
                
    except:
        pass
    
    return jsonify({"status": "ok"})

# Lancement du monitoring prix
threading.Thread(target=price_monitor, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
