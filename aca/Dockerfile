FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY src/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY src/ /app/src/

# Environment for predictable logging/output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# NEWS_API_KEY must be provided at runtime:
# docker run -e NEWS_API_KEY=... <image>
CMD ["python", "/app/src/news_server.py", "--transport", "streamable-http"]
