FROM python:3.11-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG STROKE_SEGMENTOR_VERSION=0.0.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /service

# PyTorch 2.7 CUDA 12.8 is the first stable Blackwell-capable wheel line.
RUN python -m pip install --upgrade pip \
    && python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128 \
    && python -m pip install "stroke-segmentor==${STROKE_SEGMENTOR_VERSION}"

COPY requirements-service.txt /service/
RUN python -m pip install -r /service/requirements-service.txt

COPY app /service/app

ENV PYTHONPATH=/service
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
