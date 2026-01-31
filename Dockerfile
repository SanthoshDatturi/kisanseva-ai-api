FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

WORKDIR /app

# Copy only the dependency files first.
COPY pyproject.toml uv.lock ./

# Install the application dependencies.
# This layer will be cached as long as the dependency files don't change.
RUN uv sync --frozen --no-cache

# Now copy the rest of the application code.
COPY . .

# Run the application.
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
