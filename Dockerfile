FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml README.md ./
COPY coin_buddy/__init__.py coin_buddy/__init__.py
RUN pip install --upgrade pip && pip install .

COPY coin_buddy ./coin_buddy
COPY config.yaml ./
RUN pip install --no-deps .

# Run as a non-root user.
RUN useradd --create-home buddy && mkdir -p data models reports && chown -R buddy /app
USER buddy

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["coin-buddy", "dashboard", "--host", "0.0.0.0", "--port", "8000"]
