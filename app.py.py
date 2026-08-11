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

TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "demo")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

alerta_enviada = {par: False for par in PARES}

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"Error enviado Telegram: {e}")

def obtener_datos_forex():
    datos_dashboard = {}

    for par in PARES:
        try:
            # Petición de velas de 4 Horas (H4) a la API en la nube
            url = f"https://api.twelvedata.com/time_series?symbol={par}&interval=4h&outputsize=5&apikey={TWELVEDATA_API_KEY}"
            res = requests.get(url, timeout=5).json()

            if "values" not in res:
                continue

            values = list(reversed(res["values"])) # Ordenar de más antigua a más reciente
            
            candles_h4 = []
            for v in values:
                candles_h4.append({
                    'time': v['datetime'],
                    'open': float(v['open']),
                    'high': float(v['high']),
                    'low': float(v['low']),
                    'close': float(v['close'])
                })

            # Vela de referencia (H4 cerrada previa)
            vela_ref = candles_h4[-2]
            max_h4_ref = vela_ref['high']
            min_h4_ref = vela_ref['low']

            # Estado actual
            precio_actual = candles_h4[-1]['close']
            high_actual = candles_h4[-1]['high']
            low_actual = candles_h4[-1]['low']

            barrido_high = high_actual > max_h4_ref
            barrido_low = low_actual < min_h4_ref

            # Alertas Telegram
            if barrido_high and not alerta_enviada[par]:
                enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO H4 (Turtle Soup Corto)</b>\n📌 <b>Par:</b> {par}\n📈 <b>Nivel H4:</b> {max_h4_ref}\n🔥 <b>Precio:</b> {precio_actual}")
                alerta_enviada[par] = True
            elif barrido_low and not alerta_enviada[par]:
                enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO H4 (Turtle Soup Largo)</b>\n📌 <b>Par:</b> {par}\n📉 <b>Nivel H4:</b> {min_h4_ref}\n🔥 <b>Precio:</b> {precio_actual}")
                alerta_enviada[par] = True

            if not barrido_high and not barrido_low:
                alerta_enviada[par] = False

            datos_dashboard[par] = {
                'candles': candles_h4,
                'max_h4': max_h4_ref,
                'min_h4': min_h4_ref,
                'barrido_high': barrido_high,
                'barrido_low': barrido_low
            }
        except Exception as e:
            print(f"Error procesando {par}: {e}")

    return datos_dashboard

def bucle_monitoreo():
    while True:
        datos = obtener_datos_forex()
        if datos:
            socketio.emit('update_data', datos)
        time.sleep(15) # Consulta periódica en la nube

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=bucle_monitoreo)
    t.daemon = True
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
