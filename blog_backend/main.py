from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime
from collections import Counter
import os

from .models import BlogPost, BlogPostSummary, BlogStats
from .blog_parser import BlogParser

app = FastAPI(title="Blog Backend API")

# Initialize blog parser
blog_parser = BlogParser(os.getenv("POSTS_DIRECTORY", "posts"))

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this based on your Svelte frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Blog Backend API", "version": "1.0.0"}


@app.get("/posts", response_model=List[BlogPostSummary])
async def list_posts(
    sort_by: Optional[str] = Query("date", regex="^(date|title|author)$"),
    order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    tag: Optional[str] = None,
    author: Optional[str] = None,
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: Optional[int] = Query(0, ge=0)
):
    """Get list of blog post summaries with sorting and filtering"""
    posts = blog_parser.get_all_posts()
    
    # Filter by tag
    if tag:
        posts = [p for p in posts if tag in p.tags]
    
    # Filter by author
    if author:
        posts = [p for p in posts if p.author and p.author.lower() == author.lower()]
    
    # Sort posts
    reverse = order == "desc"
    if sort_by == "date":
        posts.sort(key=lambda p: p.date, reverse=reverse)
    elif sort_by == "title":
        posts.sort(key=lambda p: p.title.lower(), reverse=reverse)
    elif sort_by == "author":
        posts.sort(key=lambda p: (p.author or "").lower(), reverse=reverse)
    
    # Apply pagination
    total = len(posts)
    if limit:
        posts = posts[offset:offset + limit]
    else:
        posts = posts[offset:]
    
    # Convert to summaries
    summaries = [
        BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author
        )
        for post in posts
    ]
    
    return summaries


@app.get("/posts/{slug}", response_model=BlogPost)
async def get_post(slug: str):
    """Get a single blog post by slug"""
    post = blog_parser.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.get("/search", response_model=List[BlogPostSummary])
async def search_posts(
    q: str = Query(..., min_length=1),
    limit: Optional[int] = Query(None, ge=1, le=100)
):
    """Search blog posts by title, content, tags, or author"""
    results = blog_parser.search_posts(q)
    
    # Sort by relevance (posts with query in title come first)
    results.sort(key=lambda p: (
        q.lower() not in p.title.lower(),  # Title matches first
        -len([t for t in p.tags if q.lower() in t.lower()]),  # Then tag matches
        p.date
    ), reverse=True)
    
    if limit:
        results = results[:limit]
    
    return [
        BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author
        )
        for post in results
    ]


@app.get("/stats", response_model=BlogStats)
async def get_stats():
    """Get blog statistics"""
    posts = blog_parser.get_all_posts()
    
    # Count tags
    tag_counter = Counter()
    for post in posts:
        tag_counter.update(post.tags)
    
    # Count authors
    author_counter = Counter()
    for post in posts:
        if post.author:
            author_counter[post.author] += 1
    
    # Count posts by month
    posts_by_month = Counter()
    for post in posts:
        month_key = post.date.strftime("%Y-%m")
        posts_by_month[month_key] += 1
    
    return BlogStats(
        total_posts=len(posts),
        tags=dict(tag_counter),
        authors=dict(author_counter),
        posts_by_month=dict(posts_by_month)
    )


@app.get("/tags")
async def list_tags():
    """Get all unique tags with counts"""
    posts = blog_parser.get_all_posts()
    tag_counter = Counter()
    for post in posts:
        tag_counter.update(post.tags)
    
    return [
        {"tag": tag, "count": count}
        for tag, count in tag_counter.most_common()
    ]


@app.get("/attachments/{slug}/{path:path}")
async def get_attachment(slug: str, path: str):
    """Serve blog post attachments"""
    post = blog_parser.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Security: ensure the path is in the post's attachments
    attachment_path = f"{slug}/{path}"
    if attachment_path not in post.attachments and f"{slug}_assets/{path}" not in post.attachments:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    file_path = blog_parser.posts_directory / attachment_path
    if not file_path.exists():
        file_path = blog_parser.posts_directory / f"{slug}_assets" / path
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)


@app.post("/refresh")
async def refresh_posts():
    """Force refresh the posts cache"""
    blog_parser.scan_posts(force_refresh=True)
    return {"message": "Posts cache refreshed", "post_count": len(blog_parser.posts_cache)}