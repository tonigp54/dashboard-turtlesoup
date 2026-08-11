import os
import time
import threading
import requests
from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Pares mapeados
PARES_LISTA = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "NZD/USD", "USD/CAD", "USD/CHF",
    "EUR/GBP", "EUR/JPY", "GBP/JPY", "EUR/CAD", "AUD/JPY", "GBP/AUD", "EUR/AUD",
    "USD/MXN", "USD/ZAR", "USD/NOK", "USD/SEK", "USD/TRY", "USD/SGD"
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

datos_cache = {}
alerta_enviada = {par: False for par in PARES_LISTA}

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"Error Telegram: {e}")

def obtener_datos_openforex(par):
    """
    Obtiene velas H4 reales utilizando endpoints públicos de respuesta ultra rápida.
    """
    try:
        base, quote = par.split('/')
        # Petición a proveedor de datos financieros abierto
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{base}{quote}=X?interval=1h&range=5d"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        
        data = res.json()
        timestamps = data['chart']['result'][0]['timestamp']
        indicators = data['chart']['result'][0]['indicators']['quote'][0]
        
        opens = indicators['open']
        highs = indicators['high']
        lows = indicators['low']
        closes = indicators['close']
        
        candles_raw = []
        for i in range(len(timestamps)):
            if None not in (opens[i], highs[i], lows[i], closes[i]):
                candles_raw.append({
                    'time': timestamps[i],
                    'open': float(opens[i]),
                    'high': float(highs[i]),
                    'low': float(lows[i]),
                    'close': float(closes[i])
                })
        
        if len(candles_raw) < 8:
            return None

        # Reagrupar de 1h a H4 (bloques de 4 horas)
        candles_h4 = []
        for i in range(0, len(candles_raw), 4):
            group = candles_raw[i:i+4]
            if len(group) == 4:
                candles_h4.append({
                    'time': group[0]['time'],
                    'open': group[0]['open'],
                    'high': max(g['high'] for g in group),
                    'low': min(g['low'] for g in group),
                    'close': group[-1]['close']
                })

        ultimas = candles_h4[-6:]
        if len(ultimas) < 2:
            return None

        vela_ref = ultimas[-2]
        max_ref = vela_ref['high']
        min_ref = vela_ref['low']

        precio_act = ultimas[-1]['close']
        high_act = ultimas[-1]['high']
        low_act = ultimas[-1]['low']

        barrido_high = high_act > max_ref
        barrido_low = low_act < min_ref

        # Alertas
        if barrido_high and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO H4</b>\n📌 <b>Par:</b> {par}\n📈 <b>Máximo Ref:</b> {max_ref}\n🔥 <b>Precio:</b> {precio_act}")
            alerta_enviada[par] = True
        elif barrido_low and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO H4</b>\n📌 <b>Par:</b> {par}\n📉 <b>Mínimo Ref:</b> {min_ref}\n🔥 <b>Precio:</b> {precio_act}")
            alerta_enviada[par] = True

        if not barrido_high and not barrido_low:
            alerta_enviada[par] = False

        return {
            'candles': ultimas,
            'max_h4': max_ref,
            'min_h4': min_ref,
            'barrido_high': barrido_high,
            'barrido_low': barrido_low
        }

    except Exception as e:
        print(f"Error cargando {par}: {e}")
        return None

def bucle_monitoreo():
    while True:
        for par in PARES_LISTA:
            info = obtener_datos_openforex(par)
            if info:
                datos_cache[par] = info
                socketio.emit('update_single', {par: info})
            time.sleep(0.3) # Consulta fluida sin satuar
        time.sleep(10)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    if datos_cache:
        socketio.emit('update_all', datos_cache)

if __name__ == '__main__':
    t = threading.Thread(target=bucle_monitoreo)
    t.daemon = True
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
