import os
import asyncio
import requests
import pandas as pd
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Cliente Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_stats():
    try:
        # Kraken es "amigo" de Render, no da Error 451
        res = requests.get("https://api.kraken.com/0/public/OHLC?pair=XXBTZUSD&interval=15", timeout=5).json()
        data = res['result']['XXBTZUSD']
        df = pd.DataFrame(data, columns=['ts','o','h','l','c','v','vol','n'])
        df['c'] = df['c'].astype(float)
        
        # Cálculo manual de RSI(14)
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return {"rsi": round(rsi.iloc[-1], 2), "price": df['c'].iloc[-1]}
    except Exception as e:
        print(f"Error stats: {e}")
        return None

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    stats = get_stats()
    if stats:
        # 1. Enviamos el RSI para la barra
        await websocket.send_json({"type": "rsi_update", "value": stats['rsi']})
        
        # 2. Enviamos el análisis de la IA
        prompt = f"BTC está a ${stats['price']} con un RSI de {stats['rsi']}. Haz un análisis técnico profesional y breve en español."
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        await websocket.send_json({"type": "initial", "ia_content": chat.choices[0].message.content})
    
    # Mantenemos el socket abierto pero sin saturar
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
