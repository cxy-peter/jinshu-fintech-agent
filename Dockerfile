FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY unified/requirements.txt unified/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY core core
COPY jinshu/__init__.py jinshu/tools.py jinshu/fixtures.py jinshu/model_config.py jinshu/
COPY unified/__init__.py unified/tools.py unified/
COPY data/synthetic data/synthetic
COPY index.py ./
EXPOSE 8766
CMD ["python", "-m", "uvicorn", "index:app", "--host", "0.0.0.0", "--port", "8766"]
