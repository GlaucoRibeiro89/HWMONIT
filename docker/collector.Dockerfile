FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    openssh-client \
    iputils-ping \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/collector.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

COPY . /app/

CMD ["python3", "-m", "uvicorn", "collector.app:app", "--host", "0.0.0.0", "--port", "8000"]