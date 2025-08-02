# Blog Backend API

A FastAPI-based blog backend that reads markdown files with frontmatter, optimized for Nuitka compilation and distroless deployment.

## Features

- Read markdown files with frontmatter metadata
- Search posts by title, content, tags, or author
- Sort posts by date, title, or author
- Filter posts by tag or author
- Statistics endpoint with tag counts and post analytics
- Attachment handling for images and assets
- CORS support for Svelte frontend
- Optimized for Nuitka compilation to static binary
- Distroless container support

## Quick Start

### Use Pre-built Binary (Recommended)

Download the latest binary from GitHub:

```bash
# Download from latest release
curl -L https://github.com/norandom/because-security-blog/releases/latest/download/blog-backend -o blog-backend
chmod +x blog-backend
./blog-backend
```

### Use Docker Image

```bash
docker run -p 8000:8000 -v $(pwd)/posts:/posts:ro ghcr.io/norandom/because-security-blog:latest
```

## Development

```bash
# Create virtual environment with uv
uv venv
source .venv/bin/activate

# Install dependencies
uv add fastapi uvicorn python-frontmatter python-multipart pydantic markdown

# Run development server
python run.py
```

### Build with Nuitka

```bash
./build_nuitka.sh
# Binary will be at dist/blog-backend
```

### Docker (Distroless)

```bash
docker-compose up
```

## API Endpoints

- `GET /` - API info
- `GET /posts` - List posts with sorting/filtering
  - Query params: `sort_by`, `order`, `tag`, `author`, `limit`, `offset`
- `GET /posts/{slug}` - Get single post
- `GET /search?q={query}` - Search posts
- `GET /stats` - Get blog statistics
- `GET /tags` - List all tags with counts
- `GET /attachments/{slug}/{path}` - Serve post attachments
- `POST /refresh` - Force refresh posts cache

## Post Format

Create markdown files in the `posts` directory:

```markdown
---
title: Post Title
date: 2025-08-01T10:00:00Z
author: John Doe
tags: [tag1, tag2]
excerpt: Optional excerpt
---

# Post content here...
```

## Attachments

Place attachments in:
- Same directory as post with same name: `post-name.png`
- Assets folder: `post-name_assets/image.png`

## Environment Variables

- `POSTS_DIRECTORY` - Directory containing markdown posts (default: "posts")
- `HOST` - Server host (default: "0.0.0.0")
- `PORT` - Server port (default: 8000)