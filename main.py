import os
import asyncio
import json
import requests
import pandas as pd
import numpy as np
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()

@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def get_btc_price():
    try:
        ticker = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5).json()
        return float(ticker['lastPrice'])
    except:
        return None

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("DEBUG: Cliente conectado al WebSocket")
    
    last_price = None
    
    try:
        while True:
            price = get_btc_price()
            if price:
                if last_price is None:
                    last_price = price
                
                await websocket.send_json({
                    "type": "trade",
                    "price": price,
                    "alert": None,
                    "color": "emerald" if price >= last_price else "red"
                })
                last_price = price
            
            await asyncio.sleep(2)
    except Exception as e:
        print(f"DEBUG: Error en bucle principal: {e}")
    finally:
        print("DEBUG: Cerrando WebSocket")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
