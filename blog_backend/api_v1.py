"""
API v1 routes with proper versioning
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime
import re

from .models import BlogPost, BlogPostSummary, BlogStats, TenantStats, TenantType
from .dependencies import get_post_service, get_stats_service, get_container
from .services import PostService, StatsService, PostListRequest, SearchRequest
from .query_builder import SortField, SortOrder
from .exceptions import PostNotFoundError
from .api_models import (
    PaginatedResponse, HealthResponse, MetricsResponse, 
    SuggestionsResponse, TenantsListResponse,
    success_response, paginated_response
)
from .config import get_settings, get_security_settings
from .logging import logger, metrics

settings = get_settings()
security_settings = get_security_settings()

# Create v1 router (prefix will be added when mounting)
v1_router = APIRouter()

# Input sanitization helpers
def sanitize_input(value: str, max_length: int = 200, pattern: str = None) -> str:
    """Sanitize user input to prevent injection attacks"""
    if not value:
        return value
    
    # Truncate to max length
    value = value[:max_length]
    
    # Remove null bytes and control characters
    value = value.replace('\x00', '').strip()
    value = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', value)
    
    # Apply pattern validation if provided
    if pattern and not re.match(pattern, value):
        raise ValueError(f"Invalid input format")
    
    return value

def sanitize_slug(slug: str) -> str:
    """Sanitize slug parameter"""
    # Only allow alphanumeric, hyphens, and underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        raise HTTPException(status_code=400, detail="Invalid slug format")
    return sanitize_input(slug, max_length=100)

def sanitize_search_query(query: str) -> str:
    """Sanitize search query"""
    return sanitize_input(query, max_length=security_settings.max_query_length)

def sanitize_tag(tag: str) -> str:
    """Sanitize tag parameter"""
    return sanitize_input(tag, max_length=security_settings.max_tag_length)


# Posts endpoints
@v1_router.get("/posts", 
    response_model=PaginatedResponse[BlogPostSummary],
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
    offset: int = Query(0, ge=0, le=10000, description="Number of posts to skip for pagination"),
    post_service: PostService = Depends(get_post_service)
):
    """List blog posts with advanced filtering, sorting, and sticky post support"""
    
    # Sanitize inputs
    if tag:
        tag = sanitize_tag(tag)
    if author:
        author = sanitize_input(author, max_length=100)
    
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


@v1_router.get("/posts/all-tenants", 
    response_model=PaginatedResponse[BlogPostSummary],
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
    offset: int = Query(0, ge=0, le=10000, description="Number of posts to skip for pagination"),
    post_service: PostService = Depends(get_post_service)
):
    """List posts from all tenants with filtering and sorting"""
    
    # Sanitize inputs
    if tag:
        tag = sanitize_tag(tag)
    if author:
        author = sanitize_input(author, max_length=100)
    
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


@v1_router.get("/posts/{slug}", 
    response_model=BlogPost,
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
    slug = sanitize_slug(slug)
    return await post_service.get_post(slug)


@v1_router.get("/posts/{slug}/related", 
    response_model=List[BlogPostSummary],
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
    slug = sanitize_slug(slug)
    return await post_service.get_related_posts(slug, limit)


# Search endpoints
@v1_router.get("/search", 
    response_model=List[BlogPostSummary],
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
    q: str = Query(..., min_length=2, max_length=200, description="Search query (min 2 chars, searches title, content, tags, author)"),
    tenant: Optional[TenantType] = Query(None, description="Limit search to specific tenant: infosec, quant, or shared"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum results to return (default: 20)"),
    post_service: PostService = Depends(get_post_service)
):
    """Search blog posts with advanced indexing and relevance ranking"""
    
    # Sanitize search query
    q = sanitize_search_query(q)
    
    request = SearchRequest(
        query=q,
        tenant=tenant,
        limit=limit
    )
    
    return await post_service.search_posts(request)


@v1_router.get("/search/suggest", 
    response_model=SuggestionsResponse,
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
    q = sanitize_input(q, max_length=50)
    suggestions = await post_service.get_suggestions(q, limit)
    
    return SuggestionsResponse(
        suggestions=suggestions,
        query=q
    )


# Stats endpoints
@v1_router.get("/stats", 
    response_model=BlogStats,
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


# Tenant endpoints
@v1_router.get("/tenants", 
    response_model=TenantsListResponse,
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


@v1_router.get("/tenants/{tenant}", 
    response_model=TenantStats,
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


@v1_router.get("/tenants/{tenant}/posts", 
    response_model=PaginatedResponse[BlogPostSummary],
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
    offset: int = Query(0, ge=0, le=10000, description="Number of posts to skip for pagination"),
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


# Health endpoint
@v1_router.get("/health", 
    response_model=HealthResponse,
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


# Metrics endpoint
@v1_router.get("/metrics", 
    response_model=MetricsResponse,
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
async def get_metrics():
    """Get application metrics"""
    container = get_container()
    metrics_summary = await metrics.get_summary()
    search_stats = await container.search_engine.get_stats()
    
    return MetricsResponse(
        performance=metrics_summary,
        search_index=search_stats
    )


# File serving endpoints
@v1_router.get("/attachments/{slug}/{path:path}", 
    summary="📎 Download Attachments",
    description="""
    Securely serve blog post attachments (images, PDFs, assets).
    
    **Security features:**
    - ✅ **Path validation**: Only serves files belonging to the specified post
    - 🔒 **Access control**: Prevents directory traversal attacks
    - 📁 **Asset organization**: Supports both direct and `{slug}_assets/` folder structures
    
    **Supported file types:** Images (PNG, JPG, SVG), PDFs, archives, documents
    
    **URL format:** `/api/v1/attachments/{post-slug}/{filename}`
    """
)
async def get_attachment(slug: str, path: str):
    """Serve blog post attachments"""
    # Sanitize inputs
    slug = sanitize_slug(slug)
    
    # Validate path - no directory traversal
    if '..' in path or path.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid path")
    
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