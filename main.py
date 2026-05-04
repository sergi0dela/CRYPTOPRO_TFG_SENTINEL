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
from datetime import datetime

app = FastAPI()

# --- CAMBIO 1: RUTA DE SALUD PARA RENDER ---
@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

# Permitimos CORS para que el frontend pueda conectar con el backend en la nube
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURACIÓN ---
# Usamos os.getenv para no dejar la clave escrita (Seguridad para Akash)
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
        val = r['data'][0]['value']
        cls = r['data'][0]['value_classification']
        return f"{val}/100 ({cls})"
    except: return "50/100 (Neutral)"

def get_complete_market_data():
    try:
        # 1. Obtener 100 velas de 15m
        url_klines = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=100"
        data = requests.get(url_klines, timeout=5).json()
        df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'ct', 'qv', 'tr', 'tb', 'tq', 'ig'])
        
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['vol_usd'] = df['vol'].astype(float) * df['close']

        # 2. Indicadores Técnicos
        rsi_val = calculate_rsi(df['close']).iloc[-1]
        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
        sma_50 = df['close'].rolling(window=50).mean().iloc[-1]

        # 3. TOP COMPRAS Y VENTAS 24H
        df['is_up'] = df['close'] > df['open']
        top_compras_df = df[df['is_up'] == True].nlargest(5, 'vol_usd')
        top_ventas_df = df[df['is_up'] == False].nlargest(5, 'vol_usd')

        res_c = "".join([f"- COMPRA TOP: ${r['vol_usd']:,.2f} USD\n" for i, r in top_compras_df.iterrows()])
        res_v = "".join([f"- VENTA TOP: ${r['vol_usd']:,.2f} USD\n" for i, r in top_ventas_df.iterrows()])

        # 4. Datos generales
        ticker = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT").json()

        return {
            "rsi": round(rsi_val, 2),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "top_compras": res_c if res_c else "No detectadas",
            "top_ventas": res_v if res_v else "No detectadas",
            "precio": float(ticker['lastPrice']),
            "cambio": ticker['priceChangePercent'],
            "sentiment": get_market_sentiment()
        }
    except Exception as e:
        print(f"Error recopilando datos: {e}")
        return None

async def enviar_informe_ia(websocket):
    data = get_complete_market_data()
    if not data: return
    
    await websocket.send_json({"type": "rsi_update", "value": data['rsi']})

    prompt = f"""ERES UN ANALISTA FINANCIERO SENIOR.
    Analiza la situación actual de Bitcoin con estos datos de las ÚLTIMAS 24 HORAS:
    
    1. MÉTRICAS TÉCNICAS:
       - RSI (14 periodos): {data['rsi']}
       - Media Móvil Simple (SMA 20): ${data['sma_20']:,.2f}
       - Media Móvil Simple (SMA 50): ${data['sma_50']:,.2f}
       - Tendencia: {'ALCISTA (SMA20 > SMA50)' if data['sma_20'] > data['sma_50'] else 'BAJISTA (SMA20 < SMA50)'}
    
    2. MOVIMIENTOS TOP 24H (BALLENAS):
       COMPRAS MÁS GRANDES:
       {data['top_compras']}
       
       VENTAS MÁS GRANDES:
       {data['top_ventas']}
    
    3. CONTEXTO DE MERCADO:
       - Precio Actual: ${data['precio']:,.2f} ({data['cambio']}% hoy)
       - Sentimiento (Fear & Greed): {data['sentiment']}
    
    Tarea: Explica cómo influyen las compras/ventas top en el RSI y si las medias móviles confirman una entrada o salida. Responde en español de forma técnica y profesional."""
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        await websocket.send_json({"type": "initial", "ia_content": completion.choices[0].message.content})
    except Exception as e:
        print(f"Error Groq: {e}")

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    asyncio.create_task(enviar_informe_ia(websocket))
    
    url = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    async with websockets.connect(url) as binance_ws:
        while True:
            data = await binance_ws.recv()
            msg = json.loads(data)
            p = float(msg['p'])
            v_usd = p * float(msg['q'])
            es_venta = msg['m']
            
            alerta = None
            if v_usd > 50000:
                tipo = "VENTA 🔴" if es_venta else "COMPRA 🟢"
                alerta = f"{tipo}: ${v_usd:,.2f}"

            await websocket.send_json({
                "type": "trade", 
                "price": p, 
                "alert": alerta, 
                "color": "red" if es_venta else "emerald"
            })

# --- ARRANQUE (CAMBIO 2: PUERTO DINÁMICO PARA RENDER) ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
