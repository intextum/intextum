FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required for OpenCV (Docling/EasyOCR) and Video Processing
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ARG WORKER_REQUIREMENTS=cpu.txt
COPY requirements ./requirements
RUN python --version | grep -E '^Python 3\.12\.' \
    && pip install --no-cache-dir -r "requirements/${WORKER_REQUIREMENTS}" \
    && ! pip freeze | grep -i '^nvidia-'

COPY . .

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app /home/worker

ENV HOME=/home/worker
USER worker

CMD ["python", "main.py"]
