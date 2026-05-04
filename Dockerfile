# 1. Usamos una versión ligera de Python
FROM python:3.11-slim

# 2. Configuración (Formato moderno corregido)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Directorio de trabajo
WORKDIR /app

# 4. Instalamos las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiamos el resto del código
COPY . .

# 6. Exponemos el puerto
EXPOSE 8000

# 7. Comando para arrancar (usando python directamente es más seguro)
CMD ["python", "main.py"]