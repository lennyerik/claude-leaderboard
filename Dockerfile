FROM astral/uv:python3.12-alpine

COPY . /app

WORKDIR /app

RUN uv sync --no-dev

RUN mkdir -p /data

ENV DATABASE_PATH=/data/claude_leaderboard.db
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uv", "run", "--", "python", "-m", "claude_leaderboard.main"]
