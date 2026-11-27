# Coin Buddy. Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved.
FROM python:3.12-slim

# The image is meant for hosting, so it uses the hosted settings (Coinbase, which works
# in the US). Override with: docker run -e COIN_BUDDY_CONFIG=/app/config.yaml ...
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 COIN_BUDDY_CONFIG=/app/config.hosted.yaml

WORKDIR /app

# Install dependencies first, in their own layer, so code changes rebuild quickly.
COPY pyproject.toml README.md ./
COPY coin_buddy/__init__.py coin_buddy/__init__.py
RUN pip install --upgrade pip && pip install .

# The app runs from /app (python -m coin_buddy), not from site-packages, so it finds
# its config files and writes data/ and models/ next to them.
COPY coin_buddy ./coin_buddy
COPY config.yaml config.hosted.yaml LICENSE ./

# Non-root user with UID 1000 (required by Hugging Face Spaces, good practice anywhere).
RUN useradd --create-home --uid 1000 buddy && mkdir -p data models reports && chown -R buddy /app
USER buddy

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
CMD ["python", "-m", "coin_buddy", "dashboard", "--host", "0.0.0.0", "--port", "8000"]
