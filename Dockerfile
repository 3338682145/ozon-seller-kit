FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/app
COPY pyproject.toml ./
COPY collector ./collector
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY samples ./samples
COPY sql ./sql
# The overlay is installed into a clone of upstream in normal deployment;
# optional ozon_seller/ozon_buyer sources are copied when present.
COPY . .
RUN pip install --no-cache-dir .
RUN useradd --uid 10001 --create-home app && chown -R app:app /srv/app
USER app
EXPOSE 8000
CMD ["uvicorn", "collector.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
