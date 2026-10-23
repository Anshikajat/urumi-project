FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --uid 10001 --no-create-home appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py db.py upstream.py mcp_endpoint.py chat.py ./

RUN mkdir /data && chown 10001:10001 /data
ENV DB_PATH=/data/gateway.db

USER 10001
EXPOSE 9000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]