FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-max-request-size", "52428800"]
