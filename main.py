import os
import asyncio
import json
import requests
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

def get_market_price():
    # Intentamos Kraken (más amigable con Render)
    try:
        url = "https://api.kraken.com/0/public/Ticker?pair=XXBTZUSD"
        response = requests.get(url, timeout=5)
        data = response.json()
        return float(data['result']['XXBTZUSD']['c'][0])
    except:
        # Si falla, backup con Coinbase
        try:
            url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
            res = requests.get(url, timeout=5).json()
            return float(res['data']['amount'])
        except:
            return None

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("DEBUG: Conexión establecida con éxito.")
    
    try:
        while True:
            precio = get_market_price()
            if precio:
                await websocket.send_json({
                    "type": "trade",
                    "price": precio,
                    "alert": None,
                    "color": "emerald"
                })
            await asyncio.sleep(2) # Actualización cada 2 segundos
    except Exception as e:
        print(f"DEBUG: Conexión terminada: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
