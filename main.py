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

# Función para obtener el precio sin usar WebSockets (evita el Error 451)
def get_binance_price():
    try:
        # Usamos la API REST, que es más difícil que bloqueen por región
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url, timeout=2)
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error consultando precio: {e}")
        return None

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("DEBUG: Cliente conectado. Usando modo HTTP Polling para evitar Error 451.")
    
    try:
        while True:
            precio = get_binance_price()
            
            if precio:
                await websocket.send_json({
                    "type": "trade",
                    "price": precio,
                    "alert": None, # Puedes añadir alertas aquí luego
                    "color": "emerald"
                })
            
            # Esperamos 2 segundos entre actualización y actualización
            # Esto evita que Binance nos banee por exceso de peticiones
            await asyncio.sleep(2)
            
    except Exception as e:
        print(f"DEBUG: Conexión cerrada con el cliente: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
