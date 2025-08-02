#!/bin/bash
# Build Nuitka binary compatible with distroless Debian 12

docker run --rm -v $(pwd):/app -w /app python:3.11-slim-bookworm bash -c '
apt-get update && apt-get install -y build-essential ccache
pip install uv
uv venv
source .venv/bin/activate
uv pip install -e . nuitka
python -m nuitka \
    --standalone \
    --onefile \
    --assume-yes-for-downloads \
    --output-dir=dist \
    --output-filename=blog-backend-distroless \
    --include-package=blog_backend \
    --include-package=fastapi \
    --include-package=uvicorn \
    --include-package=frontmatter \
    --include-package=markdown \
    --include-package=pydantic \
    --enable-plugin=anti-bloat \
    run.py
'

echo "Built dist/blog-backend-distroless compatible with distroless containers!"