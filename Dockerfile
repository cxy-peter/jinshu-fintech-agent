FROM python:3.11-slim
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-services.txt
COPY engine ./engine
COPY jinshu ./jinshu
COPY data ./data
COPY static ./static
COPY scripts ./scripts
ENV PYTHONUNBUFFERED=1
CMD ["python","-m","jinshu","serve","--profile","services","--host","0.0.0.0","--port","8766"]
