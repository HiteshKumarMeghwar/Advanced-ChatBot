FROM python:3.11-slim

# =============================
# system deps
# =============================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && rm -rf /var/lib/apt/lists/*


# =============================
# install uv globally
# =============================
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv


# =============================
# copy and install python deps
# =============================
WORKDIR /code
COPY requirements_linux.txt .

RUN pip install \
    --no-cache-dir \
    --default-timeout=600 \
    --retries 5 \
    -r requirements_linux.txt


# =============================
# copy full app source
# =============================
COPY . .
RUN chmod +x /code/expense-tracker-mcp/main.py

COPY ca.pem /ca.pem

# --------------- install Node (needed for many MCP servers) ---------------
RUN apt-get update && apt-get install -y curl \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && npm install -g npm@latest


# =============================
# Alembic DB migrations
# Auto-run migration
# (assumes alembic.ini exists)
# =============================
RUN alembic upgrade head


# =============================
# uvicorn startup
# =============================
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
