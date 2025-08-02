#!/bin/bash
set -e

echo "Installing Nuitka..."
source .venv/bin/activate
uv add --dev nuitka

echo "Building with Nuitka..."
python -m nuitka \
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
    --include-data-dir=posts=posts \
    --enable-plugin=anti-bloat \
    --show-progress \
    --show-memory \
    run.py

echo "Build complete! Binary at: dist/blog-backend"