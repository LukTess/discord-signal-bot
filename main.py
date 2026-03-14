# =============================================
# Discord Signal Bot - Protection hiérarchique TF courts
# Règle : lower low sur TF → bloque tous < TF, warning sur = TF, accepte > TF
# =============================================
from flask import Flask, request, jsonify
import requests
import ccxt
import time
import threading
import os
from datetime import datetime

# ================== CONFIG ==================
# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
if not DISCORD_WEBHOOK:
    print("ERREUR CRITIQUE : Variable DISCORD_WEBHOOK manquante dans Railway !")
    # Le bot va quand même démarrer mais n'enverra rien

SYMBOL = "BTCUSDT"
PROTECTED_TFS = [1, 2, 3, 4, 5, 10, 15]
RESET_TFS = [30, 45, 60, 120, 240, 360, 720, 1440]
MONITOR_DURATION_MIN = 45
LOWER_LOW_THRESHOLD = 5
WARNING_ON_SAME_TF = True

app = Flask(__name__)
exchange = ccxt.binance()

# Variables mémoire
blocked_below_tf = 0
ravalement_last_tf = None
ravalement_timestamp = 0
lock = threading.Lock()

# ================== FONCTIONS ==================
def send_discord(message):
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message})
        print(f"[DISCORD] {message[:100]}...")
    except Exception as e:
        print(f"[DISCORD ERROR] {e}")

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

                tf_str = f"{ravalement_last_tf}m"
                ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=tf_str, limit=3)
                if len(ohlcv) < 2:
                    time.sleep(30)
                    continue

                current_candle_low = ohlcv[-2][3]
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
        time.sleep(30)

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
        return jsonify({"status": "ignored"}), 200

    try:
        parts = [p.strip() for p in data.split("|")]
        if len(parts) < 4:
            print("[ERREUR] Format d'alerte incorrect")
            return jsonify({"status": "error"}), 400

        tf_str = parts[1]
        low_str = parts[2]
        ticker_str = parts[3]

        tf = int(tf_str) if tf_str.isdigit() else 0
        low = float(low_str.replace("low:", ""))
        ticker = ticker_str.replace("ticker:", "")

        now = time.time()

        with lock:
            # 1. RESET
            if tf in RESET_TFS or (tf > max(PROTECTED_TFS) and tf >= 2 * blocked_below_tf):
                blocked_below_tf = 0
                ravalement_last_tf = None
                ravalement_timestamp = 0
                globals().pop('last_reference_low', None)
                send_discord(f"🔄 **RESET** – Signal {tf}m détecté → tous les blocages supprimés\n"
                             f"Signaux 1m–15m autorisés à nouveau")
                return jsonify({"status": "reset"}), 200

            # 2. Signal protégé
            if tf in PROTECTED_TFS:
                if tf < blocked_below_tf:
                    send_discord(f"❌ **IGNORÉ** – Signal {tf}m (inférieur au dernier ravalé {blocked_below_tf}m)")
                    return jsonify({"status": "blocked"}), 200

                warning = ""
                if WARNING_ON_SAME_TF and tf == ravalement_last_tf:
                    warning = f"\n⚠️ **Méfiance** : on a déjà eu un {tf}m ravalé récemment → prudence\n" \
                              f"Privilégie la patience ou attends un signal > {tf}m"

                send_discord(f"🟢 **SIGNAL {tf}m ACCEPTÉ** sur {ticker}\n"
                             f"Low noté : {low:.2f}{warning}")

                globals()['last_reference_low'] = low
                ravalement_last_tf = tf
                ravalement_timestamp = now
            else:
                print(f"TF non protégé : {tf}m")

    except Exception as e:
        print(f"[ERREUR PARSING] {e}")

    return jsonify({"status": "processed"}), 200

# ================== START ==================
threading.Thread(target=price_monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Bot démarré – Protection hiérarchique active sur port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
