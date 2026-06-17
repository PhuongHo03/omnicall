FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir huggingface_hub==1.2.2

COPY infras/model-init/model_init.py /app/model_init.py

ENTRYPOINT ["python", "/app/model_init.py"]
