# =============================================
# Discord Signal Bot - Protection hiérarchique TF courts
# Règle : lower low sur TF → bloque tous < TF, warning sur = TF, accepte > TF
# =============================================

from flask import Flask, request, jsonify
import requests
import ccxt
import time
import threading
from datetime import datetime

# ================== CONFIG ==================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1481759403097985167/AASwl2p0p3NzatPh0rZwBDe_w1r-PhKEUcIFRfIVVwBvbdgUPMzSSfWJlDY4_yLjHQpV"  # ← TON WEBHOOK COMPLET
SYMBOL = "BTCUSDT"

PROTECTED_TFS = [1, 2, 3, 4, 5, 10, 15]               # TF qu'on protège
RESET_TFS = [30, 45, 60, 120, 240, 360, 720, 1440]   # TF qui reset tout

MONITOR_DURATION_MIN = 45                             # fenêtre surveillance lower low
LOWER_LOW_THRESHOLD = 5                               # seuil $ pour ravalement
WARNING_ON_SAME_TF = True                             # activer le warning sur même TF

app = Flask(__name__)
exchange = ccxt.binance()

# Variables mémoire
blocked_below_tf = 0          # tous les signaux < ce TF sont bloqués (0 = rien bloqué)
ravalement_last_tf = None
ravalement_timestamp = 0
lock = threading.Lock()

# ================== FONCTIONS ==================
def send_discord(message):
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message})
        print(f"[DISCORD] {message[:100]}...")
    except:
        pass

def price_monitor():
    global blocked_below_tf, ravalement_last_tf, ravalement_timestamp
    while True:
        try:
            with lock:
                now = time.time()
                if ravalement_timestamp == 0 or now - ravalement_timestamp > MONITOR_DURATION_MIN * 60:
                    time.sleep(30)
                    continue

                if ravalement_last_tf is None:
                    time.sleep(30)
                    continue

                # Récupère les dernières bougies du timeframe exact du signal
                tf_str = f"{ravalement_last_tf}m"
                ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=tf_str, limit=3)

                if len(ohlcv) < 2:
                    time.sleep(30)
                    continue

                # Low de la bougie la plus récente terminée
                current_candle_low = ohlcv[-2][3]  # index 3 = low

                ref_low = globals().get('last_reference_low', None)
                if ref_low is not None and current_candle_low < ref_low - LOWER_LOW_THRESHOLD:
                    blocked_below_tf = ravalement_last_tf
                    send_discord(
                        f"⚠️ **Ravalement confirmé sur {ravalement_last_tf}m** ({SYMBOL})\n"
                        f"Low bougie récente : {current_candle_low:.2f} < ref {ref_low:.2f} - {LOWER_LOW_THRESHOLD}$\n"
                        f"→ Bloque TOUS signaux **< {ravalement_last_tf}m** jusqu'au reset"
                    )
                    print(f"[BLOCAGE ACTIVÉ] blocked_below_tf = {blocked_below_tf}")
                    ravalement_timestamp = 0
                    globals().pop('last_reference_low', None)

        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
        time.sleep(30)  # 30s suffit largement

# ================== ROUTES ==================
@app.route('/', methods=['GET'])
def home():
    return "Bot protection hiérarchique actif (1m-15m)", 200

@app.route('/webhook', methods=['POST'])
def tv_webhook():
    global blocked_below_tf, ravalement_last_tf, ravalement_timestamp

    data = request.get_data(as_text=True).strip()
    print(f"[WEBHOOK] {data}")

    if not data.startswith("POSITIVE|"):
        return jsonify({"status": "ignored"})

    try:
        parts = data.split("|")
        tf_str = parts[1]
        low = float(parts[2].replace("low:", ""))
        ticker = parts[4].replace("ticker:", "")

        tf = int(tf_str) if tf_str.isdigit() else 0

        now = time.time()
        with lock:
            # 1. Cas RESET (signal supérieur)
            if tf in RESET_TFS or (tf > max(PROTECTED_TFS) and tf >= 2 * blocked_below_tf):
                blocked_below_tf = 0
                ravalement_last_tf = None
                ravalement_timestamp = 0
                globals().pop('last_reference_low', None)
                send_discord(f"🔄 **RESET** – Signal {tf}m détecté → tous les blocages supprimés\n"
                             f"Signaux 1m–15m autorisés à nouveau")
                return jsonify({"status": "reset"}), 200

            # 2. Signal dans les TF protégés
            if tf in PROTECTED_TFS:
                if tf < blocked_below_tf:
                    send_discord(f"❌ **IGNORÉ** – Signal {tf}m (inférieur au dernier ravalé {blocked_below_tf}m)")
                    return jsonify({"status": "blocked"}), 200

                # Accepte (avec warning si même niveau que dernier ravalement)
                warning = ""
                if WARNING_ON_SAME_TF and tf == ravalement_last_tf:
                    warning = f"\n⚠️ **Méfiance** : on a déjà eu un {tf}m ravalé récemment → prudence\n" \
                              f"Privilégie la patience ou attends un signal > {tf}m"

                send_discord(f"🟢 **SIGNAL {tf}m ACCEPTÉ** sur {ticker}\n"
                             f"Low noté : {low:.2f}{warning}")

                # Prépare la surveillance lower low
                globals()['last_reference_low'] = low
                ravalement_last_tf = tf
                ravalement_timestamp = now

            else:
                print(f"TF non protégé : {tf}m")

    except Exception as e:
        print(f"[ERREUR] {e}")

    return jsonify({"status": "processed"}), 200

# ================== START ==================
threading.Thread(target=price_monitor, daemon=True).start()
print("Bot démarré – Protection hiérarchique active")
