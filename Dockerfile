# Usar una imagen ligera de Python
FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y forzar stdout sin buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalar dependencias del sistema necesarias para ChromaDB y otras libs
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de la app
WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Exponer el puerto configurado
EXPOSE 3040

# Comando para iniciar la aplicación con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:3040
