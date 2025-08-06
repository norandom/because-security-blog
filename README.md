# Blog Backend API

A FastAPI-based blog backend using functional programming patterns and concurrent processing. Reads markdown files with frontmatter, optimized for Nuitka compilation and distroless deployment.

## Features

### Core Functionality
- Read markdown files with frontmatter metadata
- Search posts by title, content, tags, or author
- Sort posts by date, title, or author
- Filter posts by tag or author
- Statistics endpoint with tag counts and post analytics
- Attachment handling for images and assets
- Reading time calculation
- Blog post mirroring from external sources

### Technical Features
- **Functional Programming**: Pure functions, immutable data, functional composition
- **Concurrent Processing**: Async/await with ThreadPoolExecutor for I/O operations
- **Error Handling**: Result/Either types for robust error handling
- **Type Safety**: Full type annotations with union types and pattern matching
- **Performance**: Optimized for Nuitka compilation to static binary
- **Containerization**: Distroless container support
- **API Documentation**: OpenAPI/Swagger with comprehensive documentation

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
- `MAX_WORKERS` - Number of concurrent workers for post processing (default: 4)

## Functional Programming Features

This backend uses functional programming patterns that compile efficiently with Nuitka:

### Pure Functions
```python
def calculate_reading_time_pure(content: str) -> int:
    """Pure function - same input always produces same output"""
    words = len(content.split())
    return max(1, round(words / 200))
```

### Functional Composition
```python
# Compose multiple transformations
pipeline = compose(
    filter_list(lambda post: "python" in post.tags),
    sort_list(lambda post: post.date, reverse=True),
    take(5)  # Get first 5 results
)
filtered_posts = pipeline(posts)
```

### Result/Either Error Handling
```python
def parse_post(file_path: Path) -> Result[BlogPost, ParseError]:
    content_result = read_file_safe(file_path)
    return flat_map(lambda content: parse_frontmatter_safe(content))(content_result)
```

### Concurrent Processing
```python
# Process multiple posts concurrently using functional approach
async def scan_posts_concurrent(self) -> Result[Dict[str, BlogPost], List[ParseError]]:
    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        tasks = [loop.run_in_executor(executor, parser) for parser in parsing_functions]
        results = await asyncio.gather(*tasks)
```

## Performance Benefits

- **Nuitka Optimization**: Pure functions and immutable data structures optimize better
- **Concurrent I/O**: Non-blocking file operations with ThreadPoolExecutor
- **Memory Efficiency**: Functional pipelines avoid intermediate collections
- **Type Safety**: Union types and pattern matching prevent runtime errors