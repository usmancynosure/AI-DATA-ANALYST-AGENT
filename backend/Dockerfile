# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "pydantic-settings>=2.6" \
    "python-multipart>=0.0.12" "duckdb>=1.1" "sqlalchemy>=2.0" "psycopg[binary]>=3.2" \
    "pymysql>=1.1" "pandas>=2.2" "openpyxl>=3.1" "python-dotenv>=1.0" "google-genai>=1.0"

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
