FROM python:3.9-slim

WORKDIR /app

RUN pip install poetry

COPY . .

RUN poetry install

CMD ["poetry", "run", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
