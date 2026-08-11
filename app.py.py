import time
import requests
import MetaTrader5 as mt5
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ==========================================
# CONFIGURACIÓN
# ==========================================
PARES = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "EURGBP", "EURJPY", "GBPJPY", "EURCAD"
]

# Configura tu Bot de Telegram
TELEGRAM_BOT_TOKEN = "TU_BOT_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUI"

alerta_enviada = {par: False for par in PARES}

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN != "TU_BOT_TOKEN_AQUI":
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos_mt5():
    if not mt5.initialize():
        print("Fallo al inicializar MT5")
        return None

    datos_dashboard = {}

    for par in PARES:
        # Obtener las últimas 5 velas de 4 Horas (H4)
        rates_h4 = mt5.copy_rates_from_pos(par, mt5.TIMEFRAME_H4, 0, 5)
        if rates_h4 is None or len(rates_h4) < 2:
            continue

        # Vela H4 cerrada anterior (referencia de liquidez)
        vela_ref = rates_h4[-2]
        max_h4_ref = float(vela_ref['high'])
        min_h4_ref = float(vela_ref['low'])

        # Velas para el mini-gráfico
        candles_h4 = []
        for r in rates_h4:
            candles_h4.append({
                'time': int(r['time']),
                'open': float(r['open']),
                'high': float(r['high']),
                'low': float(r['low']),
                'close': float(r['close'])
            })

        # Comprobar barrido en vivo con el precio actual
        precio_actual = candles_h4[-1]['close']
        high_actual = candles_h4[-1]['high']
        low_actual = candles_h4[-1]['low']

        barrido_high = high_actual > max_h4_ref
        barrido_low = low_actual < min_h4_ref

        # Control de Alertas por Telegram
        if barrido_high and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO DE MÁXIMO H4 (Turtle Soup Corto)</b>\n📌 <b>Par:</b> {par}\n📈 <b>Máximo H4:</b> {max_h4_ref}\n🔥 <b>Precio Actual:</b> {precio_actual}")
            alerta_enviada[par] = True

        elif barrido_low and not alerta_enviada[par]:
            enviar_telegram(f"🚨 <b>BARRIDO DE MÍNIMO H4 (Turtle Soup Largo)</b>\n📌 <b>Par:</b> {par}\n📉 <b>Mínimo H4:</b> {min_h4_ref}\n🔥 <b>Precio Actual:</b> {precio_actual}")
            alerta_enviada[par] = True

        # Resetear alerta si vuelve a zonas normales
        if not barrido_high and not barrido_low:
            alerta_enviada[par] = False

        datos_dashboard[par] = {
            'candles': candles_h4,
            'max_h4': max_h4_ref,
            'min_h4': min_h4_ref,
            'barrido_high': barrido_high,
            'barrido_low': barrido_low
        }

    return datos_dashboard

def bucle_transmision():
    """Bucle que transmite los datos cada segundo a la web"""
    while True:
        datos = obtener_datos_mt5()
        if datos:
            socketio.emit('update_data', datos)
        time.sleep(1) # Actualización en vivo segundo a segundo

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # Hilo secundario para captura continua de precios
    t = threading.Thread(target=bucle_transmision)
    t.daemon = True
    t.start()
    
    print("🚀 Servidor Web en vivo lanzado en http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000)