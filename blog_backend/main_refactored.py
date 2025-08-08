"""
Refactored FastAPI backend with clean architecture and better maintainability
"""
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional
from datetime import datetime
import uuid
import time

from .models import BlogPost, BlogPostSummary, BlogStats, TenantStats, TenantType
from .config import get_settings, get_security_settings
from .logging import logger, metrics, request_tracker, request_id_var
from .dependencies import get_post_service, get_stats_service, get_search_engine, get_rate_limiter, get_container
from .services import PostService, StatsService, PostListRequest, SearchRequest
from .search import SearchEngine
from .rate_limit import EndpointRateLimiter
from .query_builder import SortField, SortOrder
from .exceptions import BlogBackendException, PostNotFoundError, InvalidQueryError
from .api_models import (
    ApiResponse, ErrorResponse, PaginatedResponse, HealthResponse, 
    MetricsResponse, SuggestionsResponse, TenantsListResponse,
    success_response, error_response, paginated_response
)

# Get configuration
settings = get_settings()
security_settings = get_security_settings()

app = FastAPI(
    title=settings.app_name,
    description="""
    A FastAPI backend using functional programming patterns with clean architecture.
    
    ## Features
    
    * **Clean Architecture**: Service layer separation with dependency injection
    * **Multi-Tenant**: Separate content streams for InfoSec and Quant research
    * **Functional Programming**: Pure functions, immutable data, Result/Either types
    * **Enhanced Search**: In-memory indexing with ranking and suggestions
    * **Rate Limiting**: Per-endpoint rate limiting with token bucket algorithm
    * **Observability**: Structured logging and metrics collection
    * **Caching**: Configurable caching with TTL for performance
    * **Type Safety**: Comprehensive type hints and validation
    
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
        {"name": "posts", "description": "Blog post operations"},
        {"name": "search", "description": "Search and discovery"},
        {"name": "stats", "description": "Statistics and analytics"},
        {"name": "tenants", "description": "Multi-tenant operations"},
        {"name": "admin", "description": "Administrative operations"},
    ],
)

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
        rate_limiter = get_rate_limiter()
        client_ip = request.client.host if request.client else "unknown"
        allowed, limit_info = await rate_limiter.check_endpoint_limit(path, client_ip)
        
        if not allowed:
            await metrics.increment("http_requests_rate_limited_total")
            return JSONResponse(
                status_code=429,
                content=error_response(
                    "RATE_LIMIT_EXCEEDED",
                    "Rate limit exceeded",
                    details=limit_info,
                    request_id=request_id
                ).dict(),
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


# Exception handlers
@app.exception_handler(BlogBackendException)
async def blog_exception_handler(request: Request, exc: BlogBackendException):
    """Handle custom blog exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            exc.code,
            exc.message,
            details=exc.details,
            request_id=request_id_var.get()
        ).dict()
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=400,
        content=error_response(
            "VALIDATION_ERROR",
            str(exc),
            request_id=request_id_var.get()
        ).dict()
    )


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize application components"""
    container = get_container()
    logger.info("Starting Blog Backend API", version=settings.app_version)
    
    # Start rate limiter cleanup tasks
    if settings.rate_limit_enabled:
        await container.rate_limiter.start_all_cleanup_tasks()
    
    # Initialize search index
    posts = await container.blog_parser.get_all_posts()
    await container.search_engine.rebuild_index(posts)
    
    logger.info("Application started", 
                posts_loaded=len(posts),
                search_index_ready=True,
                rate_limiting=settings.rate_limit_enabled,
                cache_enabled=settings.cache_enabled)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    container = get_container()
    logger.info("Shutting down Blog Backend API")
    
    # Stop rate limiter cleanup tasks
    if settings.rate_limit_enabled:
        await container.rate_limiter.stop_all_cleanup_tasks()
    
    logger.info("Application shutdown complete")


# API Endpoints

@app.get("/", tags=["admin"])
async def root():
    """API information endpoint"""
    return success_response({
        "message": "Blog Backend API",
        "version": settings.app_version,
        "features": [
            "clean_architecture",
            "functional_programming", 
            "concurrent_processing",
            "multi_tenant_support",
            "enhanced_search",
            "rate_limiting",
            "structured_logging",
            "configurable_caching"
        ]
    })


@app.get("/posts", response_model=PaginatedResponse[BlogPostSummary], tags=["posts"])
async def list_posts(
    sort_by: str = Query("date", regex="^(date|title|author)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    tag: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    tenant: Optional[TenantType] = Query(None),
    enable_sticky: bool = Query(True),
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
    post_service: PostService = Depends(get_post_service)
):
    """List blog posts with filtering, sorting, and pagination"""
    
    request = PostListRequest(
        sort_field=SortField(sort_by),
        sort_order=SortOrder(order),
        tenant=tenant,
        tag=tag,
        author=author,
        enable_sticky=enable_sticky,
        offset=offset,
        limit=limit
    )
    
    posts = await post_service.list_posts(request)
    
    return paginated_response(
        items=posts,
        offset=offset,
        limit=limit
    )


@app.get("/posts/all-tenants", response_model=PaginatedResponse[BlogPostSummary], tags=["posts"])
async def list_all_tenant_posts(
    sort_by: str = Query("date", regex="^(date|title|author)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    tag: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    enable_sticky: bool = Query(True),
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
    post_service: PostService = Depends(get_post_service)
):
    """List posts from all tenants with filtering and sorting"""
    
    request = PostListRequest(
        sort_field=SortField(sort_by),
        sort_order=SortOrder(order),
        tenant=None,  # All tenants
        tag=tag,
        author=author,
        enable_sticky=enable_sticky,
        offset=offset,
        limit=limit
    )
    
    posts = await post_service.list_posts(request)
    
    return paginated_response(
        items=posts,
        offset=offset,
        limit=limit
    )


@app.get("/posts/{slug}", response_model=BlogPost, tags=["posts"])
async def get_post(
    slug: str,
    post_service: PostService = Depends(get_post_service)
):
    """Get a single blog post by slug"""
    return await post_service.get_post(slug)


@app.get("/posts/{slug}/related", response_model=List[BlogPostSummary], tags=["posts"])
async def get_related_posts(
    slug: str,
    limit: int = Query(5, ge=1, le=10),
    post_service: PostService = Depends(get_post_service)
):
    """Get posts related to the given post"""
    return await post_service.get_related_posts(slug, limit)


@app.get("/search", response_model=List[BlogPostSummary], tags=["search"])
async def search_posts(
    q: str = Query(..., min_length=1),
    tenant: Optional[TenantType] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=100),
    post_service: PostService = Depends(get_post_service)
):
    """Search blog posts with advanced indexing"""
    
    request = SearchRequest(
        query=q,
        tenant=tenant,
        limit=limit
    )
    
    return await post_service.search_posts(request)


@app.get("/search/suggest", response_model=SuggestionsResponse, tags=["search"])
async def search_suggest(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(5, ge=1, le=10),
    post_service: PostService = Depends(get_post_service)
):
    """Get search suggestions"""
    suggestions = await post_service.get_suggestions(q, limit)
    
    return SuggestionsResponse(
        suggestions=suggestions,
        query=q
    )


@app.get("/stats", response_model=BlogStats, tags=["stats"])
async def get_stats(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get blog statistics"""
    return await stats_service.get_blog_stats()


@app.get("/tenants", response_model=TenantsListResponse, tags=["tenants"])
async def list_tenants():
    """Get list of available tenants"""
    tenants = [
        {"tenant": "infosec", "name": "Information Security", "description": "Security research, threat analysis, and defensive strategies"},
        {"tenant": "quant", "name": "Quantitative Finance", "description": "Algorithmic trading, market analysis, and quantitative research"},
        {"tenant": "shared", "name": "Shared Content", "description": "General updates and cross-domain content"}
    ]
    
    return TenantsListResponse(tenants=tenants)


@app.get("/tenants/{tenant}", response_model=TenantStats, tags=["tenants"])
async def get_tenant_stats(
    tenant: TenantType,
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get tenant-specific statistics"""
    return await stats_service.get_tenant_stats(tenant)


@app.get("/tenants/{tenant}/posts", response_model=PaginatedResponse[BlogPostSummary], tags=["tenants"])
async def get_tenant_posts(
    tenant: TenantType,
    sort_by: str = Query("date", regex="^(date|title|author)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    enable_sticky: bool = Query(True),
    limit: Optional[int] = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
    post_service: PostService = Depends(get_post_service)
):
    """Get posts for a specific tenant"""
    
    request = PostListRequest(
        sort_field=SortField(sort_by),
        sort_order=SortOrder(order),
        tenant=tenant,
        enable_sticky=enable_sticky,
        offset=offset,
        limit=limit
    )
    
    posts = await post_service.list_posts(request)
    
    return paginated_response(
        items=posts,
        offset=offset,
        limit=limit
    )


@app.get("/health", response_model=HealthResponse, tags=["admin"])
async def health_check():
    """Comprehensive health check"""
    container = get_container()
    
    try:
        posts = await container.blog_parser.get_all_posts()
        search_stats = await container.search_engine.get_stats()
        
        # Check if minimum posts threshold is met
        posts_healthy = len(posts) >= settings.health_check_posts_threshold
        search_healthy = search_stats.get("total_posts", 0) > 0
        
        status = "healthy" if posts_healthy and search_healthy else "degraded"
        
        checks = {
            "posts_loaded": len(posts),
            "search_index": search_stats,
            "functional_parser": True,
            "concurrent_processing": True,
            "max_workers": container.blog_parser.max_workers,
            "rate_limiting": settings.rate_limit_enabled,
            "caching_enabled": settings.cache_enabled,
        }
        
        return HealthResponse(
            status=status,
            version=settings.app_version,
            checks=checks
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return HealthResponse(
            status="unhealthy",
            version=settings.app_version,
            checks={"error": str(e)}
        )


@app.get("/metrics", response_model=MetricsResponse, tags=["admin"])
async def get_metrics(
    search_engine: SearchEngine = Depends(get_search_engine)
):
    """Get application metrics"""
    metrics_summary = await metrics.get_summary()
    search_stats = await search_engine.get_stats()
    
    return MetricsResponse(
        performance=metrics_summary,
        search_index=search_stats
    )


# File serving endpoints (kept minimal for backward compatibility)
@app.get("/attachments/{slug}/{path:path}", tags=["attachments"])
async def get_attachment(slug: str, path: str):
    """Serve blog post attachments"""
    container = get_container()
    post = await container.blog_parser.get_post(slug)
    
    if not post:
        raise PostNotFoundError(slug)
    
    # Security: ensure the path is in the post's attachments
    if path not in post.attachments and f"{slug}_assets/{path}" not in post.attachments:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    file_path = container.blog_parser.posts_directory / path
    if not file_path.exists():
        file_path = container.blog_parser.posts_directory / f"{slug}_assets" / path
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)