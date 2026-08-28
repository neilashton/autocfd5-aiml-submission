FROM python:3.12.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libx11-6 libxt6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY . /work
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

ENTRYPOINT ["autocfd5-aiml"]
