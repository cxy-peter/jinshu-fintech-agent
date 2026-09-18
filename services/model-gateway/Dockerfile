FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
COPY server.py .
ENV HF_HOME=/models PYTHONUNBUFFERED=1
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8200"]
