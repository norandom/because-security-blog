"""
Functional FastAPI backend with concurrent processing
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import Counter
import os
import asyncio

from .models import BlogPost, BlogPostSummary, BlogStats
from .functional_blog_parser import FunctionalBlogParser
from .functional_types import compose, filter_list, sort_list, map_list

app = FastAPI(
    title="Blog Backend API",
    description="A FastAPI backend using functional programming patterns with concurrent processing and Nuitka compilation support",
    version="2.0.0",
    contact={
        "name": "Blog API Support",
        "url": "https://github.com/norandom/because-security-blog",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {
            "name": "posts",
            "description": "Operations with blog posts using functional patterns",
        },
        {
            "name": "search",
            "description": "Search operations with functional composition",
        },
        {
            "name": "stats",
            "description": "Statistics and analytics with pure functions",
        },
        {
            "name": "attachments",
            "description": "File and image serving",
        },
        {
            "name": "admin",
            "description": "Administrative operations",
        },
    ],
)

# Initialize functional blog parser with concurrency
blog_parser = FunctionalBlogParser(
    posts_directory=os.getenv("POSTS_DIRECTORY", "posts"),
    max_workers=int(os.getenv("MAX_WORKERS", "4"))
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this based on your Svelte frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pure functions for API logic
def create_tag_filter(tag: str) -> callable:
    """Pure function to create tag filter"""
    return lambda posts: [post for post in posts if tag in post.tags]

def create_author_filter(author: str) -> callable:
    """Pure function to create author filter"""
    return lambda posts: [post for post in posts if post.author and post.author.lower() == author.lower()]

def create_date_sorter(reverse: bool = True) -> callable:
    """Pure function to create date sorter"""
    return lambda posts: sorted(posts, key=lambda p: p.date, reverse=reverse)

def create_title_sorter(reverse: bool = False) -> callable:
    """Pure function to create title sorter"""
    return lambda posts: sorted(posts, key=lambda p: p.title.lower(), reverse=reverse)

def create_author_sorter(reverse: bool = False) -> callable:
    """Pure function to create author sorter"""
    return lambda posts: sorted(posts, key=lambda p: (p.author or "").lower(), reverse=reverse)

def apply_pagination(offset: int, limit: Optional[int] = None) -> callable:
    """Pure function for pagination"""
    if limit:
        return lambda posts: posts[offset:offset + limit]
    else:
        return lambda posts: posts[offset:]

def posts_to_summaries(posts: List[BlogPost]) -> List[BlogPostSummary]:
    """Pure function to convert posts to summaries"""
    return [
        BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author,
            reading_time=post.reading_time
        )
        for post in posts
    ]

def calculate_blog_stats(posts: List[BlogPost]) -> BlogStats:
    """Pure function to calculate blog statistics"""
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

# API Endpoints using functional patterns

@app.get(
    "/",
    summary="API Information",
    description="Get basic information about the Functional Blog Backend API",
    response_description="API information including version"
)
async def root():
    return {"message": "Blog Backend API", "version": "2.0.0", "features": ["functional_programming", "concurrent_processing", "nuitka_optimized"]}

@app.get(
    "/posts", 
    response_model=List[BlogPostSummary],
    tags=["posts"],
    summary="List Blog Posts",
    description="Get a paginated list of blog post summaries using functional transformations and concurrent processing",
    response_description="List of blog post summaries"
)
async def list_posts(
    sort_by: Optional[str] = Query("date", regex="^(date|title|author)$", description="Field to sort by"),
    order: Optional[str] = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    author: Optional[str] = Query(None, description="Filter by author"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of posts to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of posts to skip")
):
    # Build functional transformation pipeline
    transformations = []
    
    # Add filters
    if tag:
        transformations.append(create_tag_filter(tag))
    
    if author:
        transformations.append(create_author_filter(author))
    
    # Add sorting
    reverse = order == "desc"
    if sort_by == "date":
        transformations.append(create_date_sorter(reverse))
    elif sort_by == "title":
        transformations.append(create_title_sorter(reverse))
    elif sort_by == "author":
        transformations.append(create_author_sorter(reverse))
    
    # Add pagination
    transformations.append(apply_pagination(offset, limit))
    
    # Get posts and apply transformations
    posts = await blog_parser.get_all_posts()
    
    # Apply functional pipeline
    filtered_posts = compose(*transformations)(posts) if transformations else posts
    
    return posts_to_summaries(filtered_posts)

@app.get(
    "/posts/{slug}", 
    response_model=BlogPost,
    tags=["posts"],
    summary="Get Blog Post",
    description="Get a single blog post by its slug using functional approach",
    response_description="Full blog post with content"
)
async def get_post(slug: str):
    post = await blog_parser.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.get(
    "/search", 
    response_model=List[BlogPostSummary],
    tags=["search"],
    summary="Search Posts (Functional)",
    description="Search blog posts using functional composition",
    response_description="List of matching blog post summaries"
)
async def search_posts(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of results")
):
    results = await blog_parser.search_posts(q)
    
    if limit:
        results = results[:limit]
    
    return posts_to_summaries(results)

@app.get(
    "/stats", 
    response_model=BlogStats,
    tags=["stats"],
    summary="Get Blog Statistics (Functional)",
    description="Get comprehensive blog statistics using pure functions",
    response_description="Blog statistics and analytics"
)
async def get_stats():
    posts = await blog_parser.get_all_posts()
    return calculate_blog_stats(posts)

@app.get(
    "/tags",
    tags=["stats"],
    summary="List Tags (Functional)",
    description="Get all unique tags with their usage counts using functional approach",
    response_description="List of tags with counts"
)
async def list_tags():
    posts = await blog_parser.get_all_posts()
    
    # Functional approach to count tags
    tag_counts = compose(
        lambda posts: [tag for post in posts for tag in post.tags],  # Flatten tags
        lambda tags: Counter(tags),  # Count occurrences
        lambda counter: [{"tag": tag, "count": count} for tag, count in counter.most_common()]
    )(posts)
    
    return tag_counts

@app.get(
    "/posts/by-tag/{tag}",
    response_model=List[BlogPostSummary],
    tags=["posts"],
    summary="Get Posts by Tag",
    description="Get posts filtered by a specific tag",
    response_description="List of posts with the specified tag"
)
async def get_posts_by_tag(
    tag: str,
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of results")
):
    posts = await blog_parser.filter_by_tag(tag, limit)
    return posts_to_summaries(posts)

@app.get(
    "/posts/by-author/{author}",
    response_model=List[BlogPostSummary],
    tags=["posts"],
    summary="Get Posts by Author",
    description="Get posts filtered by a specific author",
    response_description="List of posts by the specified author"
)
async def get_posts_by_author(
    author: str,
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of results")
):
    posts = await blog_parser.filter_by_author(author, limit)
    return posts_to_summaries(posts)

@app.get(
    "/attachments/{slug}/{path:path}",
    tags=["attachments"],
    summary="Get Attachment",
    description="Serve blog post attachments (images, files)",
    response_description="File content"
)
async def get_attachment(slug: str, path: str):
    post = await blog_parser.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Security: ensure the path is in the post's attachments
    if path not in post.attachments and f"{slug}_assets/{path}" not in post.attachments:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    file_path = blog_parser.posts_directory / path
    if not file_path.exists():
        file_path = blog_parser.posts_directory / f"{slug}_assets" / path
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)

@app.post(
    "/refresh",
    tags=["admin"],
    summary="Refresh Cache (Functional)",
    description="Force refresh the blog posts cache using concurrent processing",
    response_description="Cache refresh status with performance metrics"
)
async def refresh_posts():
    start_time = datetime.now()
    
    result = await blog_parser.scan_posts_concurrent(force_refresh=True)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    from .functional_types import Success, Failure
    
    match result:
        case Success(posts_dict):
            return {
                "message": "Posts cache refreshed successfully",
                "post_count": len(posts_dict),
                "duration_seconds": duration,
                "concurrent_processing": True
            }
        case Failure(errors):
            return {
                "message": f"Cache refresh completed with {len(errors)} errors",
                "post_count": len(blog_parser._posts_cache),
                "errors": [error.message for error in errors[:5]],  # Show first 5 errors
                "duration_seconds": duration,
                "concurrent_processing": True
            }

# Health check endpoint
@app.get(
    "/health",
    tags=["admin"],
    summary="Health Check",
    description="Check API health and functional parser status"
)
async def health_check():
    try:
        posts = await blog_parser.get_all_posts()
        return {
            "status": "healthy",
            "posts_loaded": len(posts),
            "functional_parser": True,
            "concurrent_processing": True,
            "max_workers": blog_parser.max_workers
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "functional_parser": True,
            "concurrent_processing": True
        }