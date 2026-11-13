# ---------- runtime: deps built IN this image so venv paths are correct ----------
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# venv lives OUTSIDE /app so a dev bind-mount of the source never hides it
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Keep entrypoint outside /app so a Windows bind-mount cannot overwrite it with CRLF.
COPY entrypoint.sh /opt/entrypoint.sh
RUN sed -i 's/\r$//' /opt/entrypoint.sh && chmod +x /opt/entrypoint.sh
COPY . .
RUN if [ -f /app/entrypoint.sh ]; then sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh; fi

EXPOSE 8000
ENTRYPOINT ["/opt/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
