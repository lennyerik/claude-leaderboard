FROM python:3.12-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN uv sync --no-dev

# Create directory for database
RUN mkdir -p /data

# Set environment variables
ENV DATABASE_PATH=/data/claude_leaderboard.db
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "--", "python", "-m", "claude_leaderboard.main"]
