import os
import time
import threading
import yfinance as yf
from flask import Flask, render_template
from flask_socketio import SocketIO
import requests

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Mapeo de pares a formato Yahoo Finance (ej: EURUSD=X)
PARES_MAP = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/CAD": "EURCAD=X"
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

datos_cache = {}
alerta_enviada = {par: False for par in PARES_MAP.keys()}

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            print(f"Error Telegram: {e}")

def actualizar_todos_los_pares():
    symbols = list(PARES_MAP.values())
    try:
        # Descarga masiva e instantánea de los 10 pares a la vez (intervalo 1h o 1d)
        data = yf.download(tickers=symbols, period="5d", interval="1h", progress=False)

        for par_nombre, ticker in PARES_MAP.items():
            try:
                df_par = data.xs(ticker, level=1, axis=1).dropna() if len(symbols) > 1 else data.dropna()
                if len(df_par) < 5:
                    continue

                # Extraer las últimas 5 velas
                ultimas = df_par.tail(5)
                candles = []
                for idx, row in ultimas.iterrows():
                    candles.append({
                        'time': str(idx),
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close'])
                    })

                # Regla Turtle Soup: Referencia vela previa
                vela_ref = candles[-2]
                max_ref = vela_ref['high']
                min_ref = vela_ref['low']

                precio_act = candles[-1]['close']
                high_act = candles[-1]['high']
                low_act = candles[-1]['low']

                barrido_high = high_act > max_ref
                barrido_low = low_act < min_ref

                # Notificaciones Telegram
                if barrido_high and not alerta_enviada[par_nombre]:
                    enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO (Turtle Soup Corto)</b>\n📌 <b>Par:</b> {par_nombre}\n📈 <b>Nivel H4:</b> {max_ref}\n🔥 <b>Precio:</b> {precio_act}")
                    alerta_enviada[par_nombre] = True
                elif barrido_low and not alerta_enviada[par_nombre]:
                    enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO (Turtle Soup Largo)</b>\n📌 <b>Par:</b> {par_nombre}\n📉 <b>Nivel H4:</b> {min_ref}\n🔥 <b>Precio:</b> {precio_act}")
                    alerta_enviada[par_nombre] = True

                if not barrido_high and not barrido_low:
                    alerta_enviada[par_nombre] = False

                info = {
                    'candles': candles,
                    'max_h4': max_ref,
                    'min_h4': min_ref,
                    'barrido_high': barrido_high,
                    'barrido_low': barrido_low
                }
                
                datos_cache[par_nombre] = info
                socketio.emit('update_single', {par_nombre: info})

            except Exception as ex:
                print(f"Error parseando {par_nombre}: {ex}")

    except Exception as e:
        print(f"Error en descarga masiva Yahoo: {e}")

def bucle_monitoreo():
    while True:
        actualizar_todos_los_pares()
        time.sleep(15) # Revisa el mercado completo cada 15 segundos

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
