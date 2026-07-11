FROM python:3.12-slim

# Brak buforowania stdout/stderr + brak plików .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Najpierw zależności (lepsze cache warstw Dockera)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kod aplikacji i frontend
COPY app ./app
COPY static ./static
COPY zapraszam.png ./static/images/zaproszenie.png
COPY entrypoint.sh .

# Katalog na bazę SQLite (montowany jako wolumen na VPS)
RUN mkdir -p /app/data && chmod +x entrypoint.sh

EXPOSE 8000

# Seeduje bazę (gdy pusta) i startuje serwer
CMD ["./entrypoint.sh"]
