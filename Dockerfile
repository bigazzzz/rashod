FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY porovnu_logging.py .

ENV UVICORN_HOST=0.0.0.0
ENV FORWARDED_ALLOW_IPS=*
EXPOSE 8000

CMD ["python", "-m", "app"]
