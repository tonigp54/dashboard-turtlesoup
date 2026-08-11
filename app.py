import os
import time
import threading
import yfinance as yf
from flask import Flask, render_template
from flask_socketio import SocketIO
import requests

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# MAPEO COMPLETO DE LOS 20 PARES CON SUS TICKERS DE YAHOO FINANCE
PARES_MAP = {
    # 1. Mayores (Majors)
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    
    # 2. Menores / Cruzados (Crosses)
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "EUR/CAD": "EURCAD=X",
    "AUD/JPY": "AUDJPY=X",
    "GBP/AUD": "GBPAUD=X",
    "EUR/AUD": "EURAUD=X",
    
    # 3. Exóticos (Exotics)
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
            print(f"Error enviado Telegram: {e}")

def actualizar_todos_los_pares():
    symbols = list(PARES_MAP.values())
    try:
        # Descarga masiva e instantánea de los 20 pares (velas H4 de los últimos 7 días)
        data = yf.download(tickers=symbols, period="7d", interval="1h", progress=False)

        for par_nombre, ticker in PARES_MAP.items():
            try:
                # Extraer serie temporal del ticker
                if len(symbols) > 1:
                    df_par = data.xs(ticker, level=1, axis=1).dropna()
                else:
                    df_par = data.dropna()

                if len(df_par) < 8:
                    continue

                # Reagrupar datos de 1 hora en bloques de 4 horas (H4)
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
                    continue

                # Vela H4 cerrada previa (Nivel de Liquidez)
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
                    enviar_telegram(f"🚨 <b>BARRIDO MÁXIMO H4 (Turtle Soup Corto)</b>\n📌 <b>Par:</b> {par_nombre}\n📈 <b>Máximo H4 Ref:</b> {max_ref}\n🔥 <b>Precio Actual:</b> {precio_act}")
                    alerta_enviada[par_nombre] = True
                elif barrido_low and not alerta_enviada[par_nombre]:
                    enviar_telegram(f"🚨 <b>BARRIDO MÍNIMO H4 (Turtle Soup Largo)</b>\n📌 <b>Par:</b> {par_nombre}\n📉 <b>Mínimo H4 Ref:</b> {min_ref}\n🔥 <b>Precio Actual:</b> {precio_act}")
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
                print(f"Error en {par_nombre}: {ex}")

    except Exception as e:
        print(f"Error en descarga masiva Yahoo: {e}")

def bucle_monitoreo():
    while True:
        actualizar_todos_los_pares()
        time.sleep(20) # Revisa el mercado completo cada 20 segundos

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
