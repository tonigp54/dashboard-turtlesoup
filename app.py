import os
import time
import requests
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ==========================================
# CONFIGURACIÓN
# ==========================================
PARES = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "USD/CHF", "EUR/GBP", "EUR/JPY", "GBP/JPY", "EUR/CAD"
]

TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Cache en memoria de los datos
datos_cache = {}
alerta_enviada = {par: False for par in PARES}

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"Error enviando Telegram: {e}")

def obtener_par(par):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={par}&interval=4h&outputsize=5&apikey={TWELVEDATA_API_KEY}"
        res = requests.get(url, timeout=5).json()

        if "values" not in res:
            print(f"Sin datos para {par}: {res}")
            return None

        # TwelveData devuelve las velas de más reciente a más antigua
        values = list(reversed(res["values"]))
        
        candles_h4 = []
        for v in values:
            candles_h4.append({
                'time': v['datetime'],
                'open': float(v['open']),
                'high': float(v['high']),
                'low': float(v['low']),
                'close': float(v['close'])
            })

        # Vela H4 cerrada anterior (referencia de liquidez)
        vela_ref = candles_h4[-2]
        max_h4_ref = vela_ref['high']
        min_h4_ref = vela_ref['low']

        # Vela actual en desarrollo
        precio_actual = candles_h4[-1]['close']
        high_actual = candles_h4[-1]['high']
        low_actual = candles_h4[-1]['low']

        barrido_high = high_actual > max_h4_ref
        barrido_low = low_actual < min_h4_ref

        # Alertas de Telegram
        if barrido_high and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO H4 (Turtle Soup Corto)</b>\n📌 <b>Par:</b> {par}\n📈 <b>Nivel H4:</b> {max_h4_ref}\n🔥 <b>Precio Actual:</b> {precio_actual}")
            alerta_enviada[par] = True
        elif barrido_low and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO H4 (Turtle Soup Largo)</b>\n📌 <b>Par:</b> {par}\n📉 <b>Nivel H4:</b> {min_h4_ref}\n🔥 <b>Precio Actual:</b> {precio_actual}")
            alerta_enviada[par] = True

        if not barrido_high and not barrido_low:
            alerta_enviada[par] = False

        return {
            'candles': candles_h4,
            'max_h4': max_h4_ref,
            'min_h4': min_h4_ref,
            'barrido_high': barrido_high,
            'barrido_low': barrido_low
        }
    except Exception as e:
        print(f"Excepción en {par}: {e}")
        return None

def bucle_monitoreo():
    """Escanea par por par respetando la cuota de la API"""
    while True:
        for par in PARES:
            data_par = obtener_par(par)
            if data_par:
                datos_cache[par] = data_par
                # Transmitir el par actualizado inmediatamente a la web
                socketio.emit('update_single', {par: data_par})
            # Pausa estratégica de 8 segundos entre peticiones para no saturar la API gratuita
            time.sleep(8)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # Enviar todos los datos guardados en cuanto un usuario abre la web
    if datos_cache:
        socketio.emit('update_all', datos_cache)

if __name__ == '__main__':
    t = threading.Thread(target=bucle_monitoreo)
    t.daemon = True
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
