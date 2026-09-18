FROM nvidia/cuda:11.3.1-cudnn8-runtime-ubuntu20.04

ARG DEBIAN_FRONTEND=noninteractive
ARG DEEPISLES_COMMIT=7658b608fc0d890cf14448ff3e58c47ad5c761e7

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git p7zip-full python3.8 python3.8-distutils \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://bootstrap.pypa.io/pip/3.8/get-pip.py | python3.8
RUN python3.8 -m pip install --no-cache-dir \
    torch==1.11.0+cu113 torchvision==0.12.0+cu113 torchaudio==0.11.0 \
    --extra-index-url https://download.pytorch.org/whl/cu113
RUN git clone https://github.com/ezequieldlrosa/DeepIsles.git /opt/deepisles \
    && cd /opt/deepisles \
    && git checkout "$DEEPISLES_COMMIT"
RUN python3.8 -m pip install --no-cache-dir -r /opt/deepisles/requirements.txt

WORKDIR /service
COPY requirements-service.txt /service/
RUN python3.8 -m pip install --no-cache-dir -r requirements-service.txt
COPY app /service/app
COPY scripts/fetch_weights.sh /service/scripts/fetch_weights.sh
RUN chmod +x /service/scripts/fetch_weights.sh \
    && ln -s /models/weights /opt/deepisles/weights
ENV PYTHONPATH=/service:/opt/deepisles
EXPOSE 8080
CMD ["/bin/bash", "-c", "/service/scripts/fetch_weights.sh && exec python3.8 -m uvicorn app.main:app --host 0.0.0.0 --port 8080"]
