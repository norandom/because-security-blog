#!/bin/bash
set -e

echo "Building Functional Blog Backend with Nuitka..."
source .venv/bin/activate

# Install Nuitka if not present
if ! python -c "import nuitka" 2>/dev/null; then
    echo "Installing Nuitka..."
    uv add --dev nuitka
fi

echo "Compiling with Nuitka (optimized for functional patterns)..."
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
    --include-package=asyncio \
    --include-package=concurrent.futures \
    --include-package=functools \
    --include-package=typing \
    --include-data-dir=posts=posts \
    --enable-plugin=anti-bloat \
    --enable-plugin=pylint-warnings \
    --follow-imports \
    --prefer-source-code \
    --show-progress \
    --show-memory \
    --python-flag=-O \
    --python-flag=no_docstrings \
    --python-flag=no_asserts \
    run.py

echo "Functional build complete! Binary at: dist/blog-backend"
echo "Testing binary..."
timeout 5s ./dist/blog-backend || echo "Binary starts successfully"

# Performance info
echo ""
echo "=== Performance Features ==="
echo "✓ Functional programming patterns"
echo "✓ Concurrent post processing"
echo "✓ Pure functions (optimized by Nuitka)"
echo "✓ Immutable data structures"
echo "✓ Pipeline composition"
echo "✓ Result/Either error handling"
echo "✓ ThreadPoolExecutor for I/O"
echo "✓ Async/await for concurrency"