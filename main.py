import os
import asyncio
import websockets
import json
import requests
import pandas as pd
import numpy as np
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()

# 1. RUTA DE SALUD
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# 2. CONFIGURACIÓN DE CORS REFORZADA
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_sentiment():
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=5).json()
        return f"{r['data'][0]['value']}/100 ({r['data'][0]['value_classification']})"
    except:
        return "50/100 (Neutral)"

def get_complete_market_data():
    try:
        url_klines = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=100"
        data = requests.get(url_klines, timeout=5).json()
        df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'ct', 'qv', 'tr', 'tb', 'tq', 'ig'])
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['vol_usd'] = df['vol'].astype(float) * df['close']
        rsi_val = calculate_rsi(df['close']).iloc[-1]
        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
        sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
        df['is_up'] = df['close'] > df['open']
        top_compras = "".join([f"- COMPRA: ${r['vol_usd']:,.2f}\n" for i, r in df[df['is_up']].nlargest(5, 'vol_usd').iterrows()])
        top_ventas = "".join([f"- VENTA: ${r['vol_usd']:,.2f}\n" for i, r in df[~df['is_up']].nlargest(5, 'vol_usd').iterrows()])
        ticker = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT").json()
        return {
            "rsi": round(rsi_val, 2),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "top_compras": top_compras,
            "top_ventas": top_ventas,
            "precio": float(ticker['lastPrice']),
            "cambio": ticker['priceChangePercent'],
            "sentiment": get_market_sentiment()
        }
    except Exception as e:
        print(f"DEBUG: Error en captura de datos: {e}")
        return None

async def enviar_informe_ia(websocket):
    try:
        data = get_complete_market_data()
        if not data:
            return
        await websocket.send_json({"type": "rsi_update", "value": data['rsi']})
        prompt = f"Analiza BTC: RSI {data['rsi']}, SMA20 ${data['sma_20']}, SMA50 ${data['sma_50']}. Responde técnico en español."
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        await websocket.send_json({"type": "initial", "ia_content": chat.choices[0].message.content})
    except Exception as e:
        print(f"DEBUG: Error en IA: {e}")

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("DEBUG: Cliente conectado al WebSocket")

    url = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    try:
        async with websockets.connect(url) as binance_ws:
            print("DEBUG: Conexión con Binance OK")
            while True:
                data = await binance_ws.recv()
                msg = json.loads(data)
                p = float(msg['p'])
                v_usd = p * float(msg['q'])
                es_venta = msg['m']

                await websocket.send_json({
                    "type": "trade",
                    "price": p,
                    "alert": f"BALLENA: ${v_usd:,.2f}" if v_usd > 50000 else None,
                    "color": "red" if es_venta else "emerald"
                })
    except Exception as e:
        print(f"DEBUG: Error en bucle principal: {e}")
    finally:
        print("DEBUG: Cerrando WebSocket")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
