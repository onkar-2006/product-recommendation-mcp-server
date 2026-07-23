# Use the official Playwright Python image containing preinstalled browser requirements
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Set container working directory
WORKDIR /app

# Copy dependencies first to utilize Docker build layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Playwright browser binaries for Chromium are fully installed and configured
RUN playwright install chromium

# Copy the rest of the application files
COPY . .

# Create directories for persistent SQLite databases and logs
RUN mkdir -p data logs

# Expose port for SSE HTTP server mode
EXPOSE 8000

# Set production environment variables
ENV PYTHONUNBUFFERED=1
ENV TRANSPORT=sse
ENV PORT=8000
ENV HOST=0.0.0.0

# Command to boot the server in SSE mode for cloud hosting
CMD ["python", "-m", "src.main"]
