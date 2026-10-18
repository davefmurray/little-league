FROM python:3.12-slim

WORKDIR /app

COPY web ./web
COPY tools/serve.py ./tools/serve.py

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "tools/serve.py", "--host", "0.0.0.0"]
