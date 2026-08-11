import os
import time
import threading
import yfinance as yf
from flask import Flask, render_template
from flask_socketio import SocketIO
import requests

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

PARES_MAP = {
    # 1. Mayores
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    
    # 2. Menores / Cruzados
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/CAD": "EURCAD=X",
    "AUD/JPY": "AUDJPY=X",
    "GBP/AUD": "GBPAUD=X",
    "EUR/AUD": "EURAUD=X",
    
    # 3. Exóticos
    "USD/MXN": "MXN=X",
    "USD/ZAR": "ZAR=X",
    "USD/NOK": "NOK=X",
    "USD/SEK": "SEK=X",
    "USD/TRY": "TRY=X",
    "USD/SGD": "SGD=X"
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

def actualizar_par_individual(par_nombre, ticker):
    try:
        # Petición individual rápida por par a Yahoo Finance
        df_par = yf.Ticker(ticker).history(period="7d", interval="1h")
        
        if len(df_par) < 8:
            return

        # Reagrupar datos de 1 hora en velas H4
        df_h4 = df_par.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).dropna()

        ultimas = df_h4.tail(6)
        candles = []
        for idx, row in ultimas.iterrows():
            candles.append({
                'time': str(idx),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close'])
            })

        if len(candles) < 2:
            return

        vela_ref = candles[-2]
        max_ref = vela_ref['high']
        min_ref = vela_ref['low']

        precio_act = candles[-1]['close']
        high_act = candles[-1]['high']
        low_act = candles[-1]['low']

        barrido_high = high_act > max_ref
        barrido_low = low_act < min_ref

        # Alertas de Telegram
        if barrido_high and not alerta_enviada[par_nombre]:
            enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO H4</b>\n📌 <b>Par:</b> {par_nombre}\n📈 <b>Máximo H4 Ref:</b> {max_ref}\n🔥 <b>Precio:</b> {precio_act}")
            alerta_enviada[par_nombre] = True
        elif barrido_low and not alerta_enviada[par_nombre]:
            enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO H4</b>\n📌 <b>Par:</b> {par_nombre}\n📉 <b>Mínimo H4 Ref:</b> {min_ref}\n🔥 <b>Precio:</b> {precio_act}")
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
        print(f"Error procesando {par_nombre}: {ex}")

def bucle_monitoreo():
    while True:
        for par_nombre, ticker in PARES_MAP.items():
            actualizar_par_individual(par_nombre, ticker)
            time.sleep(0.5) # Pequeña pausa fluida de medio segundo entre pares
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
