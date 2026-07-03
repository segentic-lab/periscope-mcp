FROM python:3.13-slim

# curl + ca-certificates so playwright can install its own system deps below
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium AND its system libraries. Let Playwright manage the full
# dependency set — hand-listing apt packages silently misses libraries
# (e.g. libXfixes) and the browser fails to launch at runtime.
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/screenshots data/reports

# Run the MCP server
CMD ["python", "server.py"]
