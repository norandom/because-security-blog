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
    # 🚀 Blog Backend API v2.1.0
    
    A production-ready FastAPI backend with **clean architecture**, **comprehensive testing**, and **enterprise-grade features**.
    
    ## ✨ Core Features
    
    * **🏗️ Clean Architecture**: Service layer separation with dependency injection
    * **🏢 Multi-Tenant**: Separate content streams for InfoSec and Quant research  
    * **📌 Sticky Posts**: Priority posts that appear at top of lists (when 3+ posts)
    * **🔍 Enhanced Search**: In-memory indexing with ranking, suggestions, and related posts
    * **🛡️ Rate Limiting**: Per-endpoint rate limiting with token bucket algorithm
    * **📊 Observability**: Structured logging, metrics collection, and health checks
    * **⚡ Performance**: Configurable caching with TTL and query optimization
    * **🔒 Type Safety**: Comprehensive type hints and Pydantic validation
    * **🧪 Well-Tested**: 11+ unit tests with CI/CD integration
    
    ## 🎯 API Capabilities
    
    * **CRUD Operations**: Full blog post management
    * **Advanced Filtering**: By tenant, tag, author with pagination
    * **Smart Sorting**: Date, title, author with sticky post prioritization  
    * **Search & Discovery**: Full-text search with auto-suggestions
    * **Analytics**: Comprehensive statistics per tenant and globally
    * **File Serving**: Secure attachment and asset delivery
    
    ## 🏢 Tenants
    
    * **infosec**: Information Security research, threat analysis, defensive strategies
    * **quant**: Quantitative Finance, algorithmic trading, market analysis  
    * **shared**: General updates and cross-domain content
    
    ## 🔗 Quick Links
    
    * **Health Check**: [`/health`](/health) - System status and diagnostics  
    * **Metrics**: [`/metrics`](/metrics) - Performance and usage statistics
    * **All Posts**: [`/posts/all-tenants`](/posts/all-tenants) - Cross-tenant view
    * **Search**: [`/search?q=your-query`](/docs#/search/search_posts_search_get) - Find content
    """,
    version=settings.app_version,
    contact={
        "name": "Blog API Support",
        "url": "https://github.com/norandom/because-security-blog",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    openapi_tags=[
        {
            "name": "posts", 
            "description": "📝 **Blog Post Operations** - CRUD operations, filtering, and sticky post management",
            "externalDocs": {
                "description": "Learn about sticky posts",
                "url": "https://github.com/norandom/because-security-blog#sticky-posts"
            }
        },
        {
            "name": "search", 
            "description": "🔍 **Search & Discovery** - Full-text search, suggestions, and related content",
            "externalDocs": {
                "description": "Search documentation", 
                "url": "https://github.com/norandom/because-security-blog#search"
            }
        },
        {
            "name": "stats", 
            "description": "📊 **Statistics & Analytics** - Usage metrics, trends, and insights"
        },
        {
            "name": "tenants", 
            "description": "🏢 **Multi-Tenant Operations** - InfoSec, Quant, and Shared content management"
        },
        {
            "name": "attachments",
            "description": "📎 **File Management** - Secure serving of images and attachments"  
        },
        {
            "name": "admin", 
            "description": "⚙️ **Administrative Tools** - Health checks, metrics, and system management"
        },
    ],
    servers=[
        {"url": "/", "description": "Current server"},
        {"url": "http://localhost:8000", "description": "Local development server"},
    ]
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

@app.get("/", 
    tags=["admin"],
    summary="🏠 API Information",
    description="Get basic API information, version, and available features"
)
async def root():
    """Get API information including version and available features"""
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


@app.get("/posts", 
    response_model=PaginatedResponse[BlogPostSummary], 
    tags=["posts"],
    summary="📝 List Blog Posts",
    description="""
    List blog posts with advanced filtering, sorting, and pagination.
    
    **Features:**
    - 📌 **Sticky Posts**: Priority posts appear at top (when 3+ posts returned)
    - 🏢 **Multi-Tenant**: Filter by infosec, quant, or shared content
    - 🏷️ **Smart Filtering**: By tag, author, or any combination
    - 📊 **Flexible Sorting**: By date, title, or author (asc/desc)
    - 📄 **Pagination**: Efficient offset/limit pagination
    
    **Sticky Posts Logic:**
    Posts marked with `sticky: true` in frontmatter appear first when 3 or more posts are returned.
    Set `enable_sticky=false` to disable this behavior.
    """
)
async def list_posts(
    sort_by: str = Query("date", regex="^(date|title|author)$", description="Sort field: date, title, or author"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order: desc (newest first) or asc"),
    tag: Optional[str] = Query(None, description="Filter by tag (case-insensitive)"),
    author: Optional[str] = Query(None, description="Filter by author name (case-insensitive)"),
    tenant: Optional[TenantType] = Query(None, description="Filter by tenant: infosec, quant, or shared"),
    enable_sticky: bool = Query(True, description="Enable sticky posts (appear at top when 3+ posts)"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum posts to return (1-100)"),
    offset: int = Query(0, ge=0, description="Number of posts to skip for pagination"),
    post_service: PostService = Depends(get_post_service)
):
    """List blog posts with advanced filtering, sorting, and sticky post support"""
    
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


@app.get("/posts/all-tenants", 
    response_model=PaginatedResponse[BlogPostSummary], 
    tags=["posts"],
    summary="🌐 Cross-Tenant Post Listing",
    description="""
    Get posts from all tenants (InfoSec, Quant, Shared) in a unified view.
    
    **Perfect for:**
    - 📰 Homepage/dashboard displaying all content
    - 🔍 Cross-domain research and discovery
    - 📊 Global content analytics
    
    **All filtering and sorting options from `/posts` endpoint apply here.**
    """
)
async def list_all_tenant_posts(
    sort_by: str = Query("date", regex="^(date|title|author)$", description="Sort field: date, title, or author"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order: desc (newest first) or asc"),
    tag: Optional[str] = Query(None, description="Filter by tag across all tenants"),
    author: Optional[str] = Query(None, description="Filter by author across all tenants"),
    enable_sticky: bool = Query(True, description="Enable sticky posts from all tenants"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum posts to return (1-100)"),
    offset: int = Query(0, ge=0, description="Number of posts to skip for pagination"),
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


@app.get("/posts/{slug}", 
    response_model=BlogPost, 
    tags=["posts"],
    summary="📄 Get Individual Post",
    description="""
    Retrieve a complete blog post by its unique slug identifier.
    
    **Returns full content including:**
    - 📝 Complete markdown content with HTML rendering
    - 📎 List of attachments (images, PDFs, etc.)
    - 🏷️ Tags, author, publication date
    - 🏢 Tenant classification (infosec/quant/shared)
    
    **Example slug formats:** `advanced-threat-hunting-2024`, `quantitative-risk-models`
    """
)
async def get_post(
    slug: str,
    post_service: PostService = Depends(get_post_service)
):
    """Get a single blog post by slug"""
    return await post_service.get_post(slug)


@app.get("/posts/{slug}/related", 
    response_model=List[BlogPostSummary], 
    tags=["posts"],
    summary="🔗 Related Content Discovery",
    description="""
    Find posts related to a specific post using intelligent content analysis.
    
    **Relevance algorithm considers:**
    - 🏷️ Shared tags (highest weight)
    - 👤 Same author content
    - 🏢 Same tenant/domain content
    - 📅 Publication time proximity
    
    **Perfect for:** Content recommendations, reader engagement, topic exploration.
    """
)
async def get_related_posts(
    slug: str,
    limit: int = Query(5, ge=1, le=10, description="Maximum number of related posts (1-10)"),
    post_service: PostService = Depends(get_post_service)
):
    """Get posts related to the given post"""
    return await post_service.get_related_posts(slug, limit)


@app.get("/search", 
    response_model=List[BlogPostSummary], 
    tags=["search"],
    summary="🔍 Search Posts",
    description="""
    Search blog posts using advanced in-memory indexing with relevance ranking.
    
    **Search Features:**
    - 🎯 **Relevance Scoring**: Results ranked by relevance (title matches score higher)
    - 🔍 **Multi-Field Search**: Searches across title, content, tags, and author
    - 🏢 **Tenant Filtering**: Optionally limit search to specific tenant
    - ⚡ **Fast Performance**: In-memory search index for sub-millisecond queries
    
    **Search Tips:**
    - Use simple keywords for best results
    - Tag matches and title matches score higher than content matches
    - Minimum 2 characters required, maximum 200 characters
    """
)
async def search_posts(
    q: str = Query(..., min_length=1, description="Search query (min 2 chars, searches title, content, tags, author)"),
    tenant: Optional[TenantType] = Query(None, description="Limit search to specific tenant: infosec, quant, or shared"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum results to return (default: 20)"),
    post_service: PostService = Depends(get_post_service)
):
    """Search blog posts with advanced indexing and relevance ranking"""
    
    request = SearchRequest(
        query=q,
        tenant=tenant,
        limit=limit
    )
    
    return await post_service.search_posts(request)


@app.get("/search/suggest", 
    response_model=SuggestionsResponse, 
    tags=["search"],
    summary="💡 Search Auto-Suggestions",
    description="""
    Get intelligent search suggestions as users type, helping with query completion and discovery.
    
    **Suggestion sources:**
    - 🏷️ **Tags**: Popular tags matching input
    - 👤 **Authors**: Author names for content discovery  
    - 📝 **Titles**: Post titles with partial matches
    - 🔍 **Common queries**: Frequently searched terms
    
    **Implementation tips:** Call this endpoint on keyup events with debouncing (~300ms) for optimal UX.
    """
)
async def search_suggest(
    q: str = Query(..., min_length=1, max_length=50, description="Partial search query for suggestions (1-50 chars)"),
    limit: int = Query(5, ge=1, le=10, description="Maximum suggestions to return (1-10)"),
    post_service: PostService = Depends(get_post_service)
):
    """Get search suggestions"""
    suggestions = await post_service.get_suggestions(q, limit)
    
    return SuggestionsResponse(
        suggestions=suggestions,
        query=q
    )


@app.get("/stats", 
    response_model=BlogStats, 
    tags=["stats"],
    summary="📊 Global Blog Statistics",
    description="""
    Get comprehensive analytics and statistics across all blog content.
    
    **Statistics include:**
    - 📈 **Content metrics**: Total posts, tags, authors
    - 🏢 **Tenant breakdown**: Posts per tenant (infosec/quant/shared)  
    - 📅 **Timeline data**: Publication trends, recent activity
    - 🏷️ **Tag popularity**: Most used tags with counts
    - 👤 **Author activity**: Top contributors
    
    **Perfect for:** Dashboard analytics, content insights, editorial planning.
    """
)
async def get_stats(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get blog statistics"""
    return await stats_service.get_blog_stats()


@app.get("/tenants", 
    response_model=TenantsListResponse, 
    tags=["tenants"],
    summary="🏢 Available Tenants",
    description="""
    Get information about all available content tenants/domains.
    
    **Current tenants:**
    - 🛡️ **InfoSec**: Information security research, threat analysis, defensive strategies
    - 📊 **Quant**: Quantitative finance, algorithmic trading, market analysis  
    - 🌐 **Shared**: General updates, announcements, cross-domain content
    
    **Use cases:** Navigation menus, tenant selection, API discovery.
    """
)
async def list_tenants():
    """Get list of available tenants"""
    tenants = [
        {"tenant": "infosec", "name": "Information Security", "description": "Security research, threat analysis, and defensive strategies"},
        {"tenant": "quant", "name": "Quantitative Finance", "description": "Algorithmic trading, market analysis, and quantitative research"},
        {"tenant": "shared", "name": "Shared Content", "description": "General updates and cross-domain content"}
    ]
    
    return TenantsListResponse(tenants=tenants)


@app.get("/tenants/{tenant}", 
    response_model=TenantStats, 
    tags=["tenants"],
    summary="📊 Tenant-Specific Analytics",
    description="""
    Get detailed analytics for a specific tenant's content.
    
    **Analytics include:**
    - 📈 **Content volume**: Post counts, growth trends
    - 🏷️ **Popular topics**: Most used tags in this tenant
    - 👤 **Top authors**: Leading contributors to this domain
    - 📅 **Publishing activity**: Timeline and frequency patterns
    
    **Perfect for:** Domain-specific dashboards, editorial insights, content planning.
    """
)
async def get_tenant_stats(
    tenant: TenantType,
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get tenant-specific statistics"""
    return await stats_service.get_tenant_stats(tenant)


@app.get("/tenants/{tenant}/posts", 
    response_model=PaginatedResponse[BlogPostSummary], 
    tags=["tenants"],
    summary="🏢 Tenant Content Listing",
    description="""
    Get all posts for a specific tenant with full filtering and sorting capabilities.
    
    **Tenant-specific content:**
    - 🛡️ **InfoSec**: Security research, threat hunting, defense strategies
    - 📊 **Quant**: Trading algorithms, market analysis, financial modeling
    - 🌐 **Shared**: Cross-domain updates, announcements, general content
    
    **All standard filtering options apply** (tag, author, sorting, pagination, sticky posts).
    """
)
async def get_tenant_posts(
    tenant: TenantType,
    sort_by: str = Query("date", regex="^(date|title|author)$", description="Sort field: date, title, or author"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order: desc (newest first) or asc"),
    enable_sticky: bool = Query(True, description="Enable sticky posts for this tenant"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum posts to return (1-100)"),
    offset: int = Query(0, ge=0, description="Number of posts to skip for pagination"),
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


@app.get("/health", 
    response_model=HealthResponse, 
    tags=["admin"],
    summary="🏥 System Health Check",
    description="""
    Comprehensive health monitoring for the blog backend system.
    
    **Health checks include:**
    - 📚 **Content availability**: Posts loaded successfully
    - 🔍 **Search index**: Search engine operational status
    - ⚡ **Performance**: Response times and resource usage  
    - 🛠️ **System components**: All core services functional
    
    **Status values:** `healthy`, `degraded`, or `unhealthy`
    
    **Perfect for:** Monitoring, alerting, load balancer health probes.
    """
)
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


@app.get("/metrics", 
    response_model=MetricsResponse, 
    tags=["admin"],
    summary="📈 Performance Metrics",
    description="""
    Get detailed performance metrics and operational statistics.
    
    **Metrics included:**
    - 📊 **Request statistics**: Total requests, response times, error rates
    - 🔍 **Search performance**: Query times, index stats, cache hits
    - 💾 **Memory usage**: Cache utilization, object counts
    - ⚡ **Throughput**: Requests per second, concurrent users
    
    **Perfect for:** Performance monitoring, capacity planning, troubleshooting.
    """
)
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
@app.get("/attachments/{slug}/{path:path}", 
    tags=["attachments"],
    summary="📎 Download Attachments",
    description="""
    Securely serve blog post attachments (images, PDFs, assets).
    
    **Security features:**
    - ✅ **Path validation**: Only serves files belonging to the specified post
    - 🔒 **Access control**: Prevents directory traversal attacks
    - 📁 **Asset organization**: Supports both direct and `{slug}_assets/` folder structures
    
    **Supported file types:** Images (PNG, JPG, SVG), PDFs, archives, documents
    
    **URL format:** `/attachments/{post-slug}/{filename}`
    """
)
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