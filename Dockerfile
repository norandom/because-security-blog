# Multi-stage build
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    ccache \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY blog_backend ./blog_backend
COPY run.py ./

# Install uv and dependencies
RUN pip install uv
RUN uv venv && . .venv/bin/activate && uv pip install -e .
RUN . .venv/bin/activate && uv pip install nuitka

# Build with Nuitka
RUN . .venv/bin/activate && python -m nuitka \
    --standalone \
    --onefile \
    --assume-yes-for-downloads \
    --output-dir=dist \
    --output-filename=blog-backend \
    --include-package=blog_backend \
    --include-package=fastapi \
    --include-package=uvicorn \
    --include-package=frontmatter \
    --include-package=markdown \
    --include-package=pydantic \
    --enable-plugin=anti-bloat \
    --show-progress \
    run.py

# Final distroless stage
FROM gcr.io/distroless/cc-debian12

# Copy the binary
COPY --from=builder /app/dist/blog-backend /app/blog-backend

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000
ENV POSTS_DIRECTORY=/posts

# Expose port
EXPOSE 8000

# Run the binary
ENTRYPOINT ["/app/blog-backend"]