"""
Functional FastAPI backend with concurrent processing and enhanced features
"""
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import Counter
import os
import asyncio
import uuid
import time

from .models import BlogPost, BlogPostSummary, BlogStats, TenantStats, TenantType
from .functional_blog_parser import FunctionalBlogParser
from .functional_types import compose, filter_list, sort_list, map_list
from .config import get_settings, get_security_settings
from .logging import logger, metrics, request_tracker, request_id_var
from .cache import StatsCache, cached
from .search import SearchEngine
from .rate_limit import EndpointRateLimiter

# Get configuration
settings = get_settings()
security_settings = get_security_settings()

app = FastAPI(
    title=settings.app_name,
    description="""
    A FastAPI backend using functional programming patterns with concurrent processing and Nuitka compilation support.
    
    ## Features
    
    * **Multi-Tenant**: Separate content streams for InfoSec and Quant research
    * **Functional Programming**: Pure functions, immutable data, Result/Either types
    * **Concurrent Processing**: Async I/O with ThreadPoolExecutor for performance
    * **Type Safety**: Full type annotations with union types and pattern matching
    * **Nuitka Optimized**: Compiles to native binary for production deployment
    * **Enhanced Search**: In-memory indexing with ranking and suggestions
    * **Rate Limiting**: Per-endpoint rate limiting with token bucket algorithm
    * **Observability**: Structured logging and metrics collection
    * **Caching**: Intelligent caching with TTL for performance
    
    ## Tenants
    
    * **infosec**: Information Security research, threat analysis, defensive strategies
    * **quant**: Quantitative Finance, algorithmic trading, market analysis  
    * **shared**: General updates and cross-domain content
    """,
    version=settings.app_version,
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
        {
            "name": "tenants",
            "description": "Multi-tenant operations for infosec and quant content",
        },
    ],
)

# Initialize global components
blog_parser = FunctionalBlogParser(
    posts_directory=str(settings.posts_directory),
    max_workers=settings.max_workers
)
search_engine = SearchEngine()
stats_cache = StatsCache()
rate_limiter = EndpointRateLimiter()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request tracking middleware
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track request performance and add request ID"""
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    start_time = time.time()
    path = request.url.path
    method = request.method
    
    # Check rate limiting
    if settings.rate_limit_enabled:
        client_ip = request.client.host if request.client else "unknown"
        allowed, limit_info = await rate_limiter.check_endpoint_limit(path, client_ip)
        
        if not allowed:
            await metrics.increment("http_requests_rate_limited_total")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "reason": limit_info.get("reason"),
                    "retry_after": limit_info.get("retry_after")
                },
                headers={"Retry-After": str(int(limit_info.get("retry_after", 60)))}
            )
    
    await request_tracker.start_request(request_id, path, method)
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        await request_tracker.end_request(
            request_id, path, method, response.status_code, duration
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        duration = time.time() - start_time
        await request_tracker.end_request(request_id, path, method, 500, duration)
        await metrics.increment("http_requests_errors_total")
        logger.error("Request failed", 
                    request_id=request_id, 
                    error=str(e), 
                    path=path, 
                    method=method)
        raise

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize application components"""
    logger.info("Starting Blog Backend API", version=settings.app_version)
    
    # Start rate limiter cleanup tasks
    if settings.rate_limit_enabled:
        await rate_limiter.start_all_cleanup_tasks()
    
    # Initialize search index
    posts = await blog_parser.get_all_posts()
    await search_engine.rebuild_index(posts)
    
    logger.info("Application started", 
                posts_loaded=len(posts),
                search_index_ready=True,
                rate_limiting=settings.rate_limit_enabled)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Blog Backend API")
    
    # Stop rate limiter cleanup tasks
    if settings.rate_limit_enabled:
        await rate_limiter.stop_all_cleanup_tasks()
    
    logger.info("Application shutdown complete")

# Pure functions for API logic
def create_tag_filter(tag: str) -> callable:
    """Pure function to create tag filter"""
    return lambda posts: [post for post in posts if tag in post.tags]

def create_author_filter(author: str) -> callable:
    """Pure function to create author filter"""
    return lambda posts: [post for post in posts if post.author and post.author.lower() == author.lower()]

def create_tenant_filter(tenant: TenantType) -> callable:
    """Pure function to create tenant filter"""
    return lambda posts: [post for post in posts if post.tenant == tenant]

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
            tenant=post.tenant,
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
    
    # Count posts by tenant
    posts_by_tenant = Counter()
    for post in posts:
        posts_by_tenant[post.tenant] += 1
    
    return BlogStats(
        total_posts=len(posts),
        tags=dict(tag_counter),
        authors=dict(author_counter),
        posts_by_month=dict(posts_by_month),
        posts_by_tenant=dict(posts_by_tenant)
    )

def calculate_tenant_stats(posts: List[BlogPost], tenant: TenantType) -> TenantStats:
    """Pure function to calculate tenant-specific statistics"""
    tenant_posts = [post for post in posts if post.tenant == tenant]
    
    # Count tags for this tenant
    tag_counter = Counter()
    for post in tenant_posts:
        tag_counter.update(post.tags)
    
    # Count authors for this tenant
    author_counter = Counter()
    for post in tenant_posts:
        if post.author:
            author_counter[post.author] += 1
    
    # Count posts by month for this tenant
    posts_by_month = Counter()
    for post in tenant_posts:
        month_key = post.date.strftime("%Y-%m")
        posts_by_month[month_key] += 1
    
    # Get recent posts (last 5)
    recent_posts = sorted(tenant_posts, key=lambda p: p.date, reverse=True)[:5]
    recent_summaries = posts_to_summaries(recent_posts)
    
    return TenantStats(
        tenant=tenant,
        total_posts=len(tenant_posts),
        tags=dict(tag_counter),
        authors=dict(author_counter),
        posts_by_month=dict(posts_by_month),
        recent_posts=recent_summaries
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
    tenant: Optional[TenantType] = Query(None, description="Filter by tenant (infosec, quant, shared)"),
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
    
    if tenant:
        transformations.append(create_tenant_filter(tenant))
    
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
    summary="Enhanced Search",
    description="Search blog posts using advanced indexing with ranking and relevance scoring",
    response_description="List of matching blog post summaries ranked by relevance"
)
async def search_posts(
    q: str = Query(..., min_length=settings.search_min_length, max_length=security_settings.max_query_length, description="Search query"),
    tenant: Optional[TenantType] = Query(None, description="Filter by tenant"),
    limit: Optional[int] = Query(None, ge=1, le=settings.search_max_results, description="Maximum number of results")
):
    # Validate query length
    if len(q.strip()) < settings.search_min_length:
        raise HTTPException(status_code=400, detail="Query too short")
    
    # Use enhanced search engine
    search_results = await search_engine.search(
        query=q.strip(),
        tenant=tenant,
        limit=limit or 20
    )
    
    # Get full post data for results
    posts = await blog_parser.get_all_posts()
    post_dict = {post.slug: post for post in posts}
    
    # Convert search results to summaries
    result_posts = []
    for slug, score in search_results:
        if slug in post_dict:
            result_posts.append(post_dict[slug])
    
    await metrics.increment("search_queries_total", labels={"tenant": tenant or "all"})
    logger.info("Search performed", query=q, tenant=tenant, results_count=len(result_posts))
    
    return posts_to_summaries(result_posts)

@app.get(
    "/stats", 
    response_model=BlogStats,
    tags=["stats"],
    summary="Get Blog Statistics (Cached)",
    description="Get comprehensive blog statistics using pure functions with intelligent caching",
    response_description="Blog statistics and analytics"
)
@cached(ttl=settings.stats_cache_ttl)
async def get_stats():
    async def compute_stats():
        posts = await blog_parser.get_all_posts()
        # Rebuild search index if needed
        await search_engine.rebuild_index(posts)
        return calculate_blog_stats(posts)
    
    return await stats_cache.get_stats(compute_stats)

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
# Tenant-specific endpoints
@app.get(
    "/tenants",
    tags=["tenants"],
    summary="List Tenants",
    description="Get list of available tenants",
    response_description="List of available tenants with descriptions"
)
async def list_tenants():
    return [
        {"tenant": "infosec", "name": "Information Security", "description": "Security research, threat analysis, and defensive strategies"},
        {"tenant": "quant", "name": "Quantitative Finance", "description": "Algorithmic trading, market analysis, and quantitative research"},
        {"tenant": "shared", "name": "Shared Content", "description": "General updates and cross-domain content"}
    ]

@app.get(
    "/tenants/{tenant}",
    response_model=TenantStats,
    tags=["tenants"],
    summary="Get Tenant Statistics",
    description="""
    Get comprehensive statistics for a specific tenant including:
    - Total post count for the tenant
    - Tag usage statistics
    - Author contributions
    - Posts by month timeline
    - Recent posts (last 5)
    
    Perfect for dashboard widgets and tenant overview pages.
    """,
    response_description="Tenant-specific statistics including recent posts"
)
async def get_tenant_stats(tenant: TenantType):
    posts = await blog_parser.get_all_posts()
    return calculate_tenant_stats(posts, tenant)

@app.get(
    "/tenants/{tenant}/posts",
    response_model=List[BlogPostSummary],
    tags=["tenants"],
    summary="Get Posts by Tenant",
    description="Get posts for a specific tenant with sorting and pagination",
    response_description="List of posts for the specified tenant"
)
async def get_tenant_posts(
    tenant: TenantType,
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of posts to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of posts to skip"),
    sort_by: Optional[str] = Query("date", regex="^(date|title|author)$", description="Field to sort by"),
    order: Optional[str] = Query("desc", regex="^(asc|desc)$", description="Sort order")
):
    posts = await blog_parser.filter_by_tenant(tenant)
    
    # Apply sorting
    reverse = order == "desc"
    if sort_by == "date":
        posts = sorted(posts, key=lambda p: p.date, reverse=reverse)
    elif sort_by == "title":
        posts = sorted(posts, key=lambda p: p.title.lower(), reverse=reverse)
    elif sort_by == "author":
        posts = sorted(posts, key=lambda p: (p.author or "").lower(), reverse=reverse)
    
    # Apply pagination
    if offset > 0:
        posts = posts[offset:]
    if limit:
        posts = posts[:limit]
    
    return posts_to_summaries(posts)

@app.get(
    "/tenants/{tenant}/recent",
    response_model=List[BlogPostSummary],
    tags=["tenants"],
    summary="Get Recent Posts by Tenant",
    description="Get recent posts for a specific tenant",
    response_description="Recent posts for the specified tenant"
)
async def get_tenant_recent_posts(
    tenant: TenantType,
    limit: int = Query(5, ge=1, le=20, description="Number of recent posts to return")
):
    return await blog_parser.get_recent_by_tenant(tenant, limit)

@app.get(
    "/tenants/{tenant}/tags",
    tags=["tenants"],
    summary="Get Tags by Tenant",
    description="Get all tags used by posts in a specific tenant",
    response_description="List of tags with counts for the specified tenant"
)
async def get_tenant_tags(tenant: TenantType):
    posts = await blog_parser.filter_by_tenant(tenant)
    
    # Functional approach to count tags for this tenant
    tag_counts = compose(
        lambda posts: [tag for post in posts for tag in post.tags],  # Flatten tags
        lambda tags: Counter(tags),  # Count occurrences
        lambda counter: [{"tag": tag, "count": count} for tag, count in counter.most_common()]
    )(posts)
    
    return tag_counts

# New enhanced endpoints
@app.get(
    "/search/suggest",
    tags=["search"],
    summary="Search Suggestions",
    description="Get auto-complete suggestions for search queries",
    response_description="List of suggested search terms"
)
async def search_suggest(
    q: str = Query(..., min_length=1, max_length=50, description="Search prefix"),
    limit: int = Query(5, ge=1, le=10, description="Maximum number of suggestions")
):
    suggestions = await search_engine.suggest(q, limit)
    return {"suggestions": suggestions}

@app.get(
    "/posts/{slug}/related",
    response_model=List[BlogPostSummary],
    tags=["posts"],
    summary="Related Posts",
    description="Find posts related to the given post",
    response_description="List of related post summaries"
)
async def get_related_posts(slug: str, limit: int = Query(5, ge=1, le=10)):
    post = await blog_parser.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    related_slugs = await search_engine.get_related_posts(slug, limit)
    
    # Get post data for related posts
    posts = await blog_parser.get_all_posts()
    post_dict = {p.slug: p for p in posts}
    
    related_posts = [post_dict[s] for s in related_slugs if s in post_dict]
    return posts_to_summaries(related_posts)

@app.get(
    "/metrics",
    tags=["admin"],
    summary="Application Metrics",
    description="Get application performance metrics",
    response_description="Performance and usage metrics"
)
async def get_metrics():
    metrics_summary = await metrics.get_summary()
    search_stats = await search_engine.get_stats()
    
    return {
        "performance": metrics_summary,
        "search_index": search_stats,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get(
    "/health",
    tags=["admin"],
    summary="Enhanced Health Check",
    description="Comprehensive health check with dependency verification"
)
async def health_check():
    try:
        posts = await blog_parser.get_all_posts()
        tenant_counts = Counter(post.tenant for post in posts)
        search_stats = await search_engine.get_stats()
        
        # Check if minimum posts threshold is met
        posts_healthy = len(posts) >= settings.health_check_posts_threshold
        search_healthy = search_stats.get("total_posts", 0) > 0
        
        status = "healthy" if posts_healthy and search_healthy else "degraded"
        
        return {
            "status": status,
            "posts_loaded": len(posts),
            "tenants": dict(tenant_counts),
            "search_index": search_stats,
            "functional_parser": True,
            "concurrent_processing": True,
            "max_workers": blog_parser.max_workers,
            "rate_limiting": settings.rate_limit_enabled,
            "caching_enabled": True,
            "version": settings.app_version
        }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "functional_parser": True,
            "concurrent_processing": True,
            "version": settings.app_version
        }