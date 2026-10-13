FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Recreate the folder structure expected by main.py from the flattened repo.
WORKDIR /workspace/apps/api
COPY requirements-render.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py audio_utils.py providers.py db.py catalog.py storage.py voice_catalog.json env.example ./

WORKDIR /workspace/apps/web
COPY index.html app.js styles.css config.js ./

WORKDIR /workspace/apps/api
EXPOSE 8000
CMD ["sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
