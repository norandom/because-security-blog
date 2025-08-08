"""
FastAPI backend with API versioning and security enhancements
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
import time

from .config import get_settings, get_security_settings
from .logging import logger, metrics, request_tracker, request_id_var
from .dependencies import get_container, get_rate_limiter
from .api_v1 import v1_router
from .api_models import error_response, success_response
from .exceptions import BlogBackendException

# Get configuration
settings = get_settings()
security_settings = get_security_settings()

app = FastAPI(
    title=settings.app_name,
    description="""
    # 🚀 Blog Backend API v2.1.0
    
    A production-ready FastAPI backend with **clean architecture** and **API versioning**.
    
    ## 📌 API Versions
    
    * **v1** - Current stable version at `/api/v1`
    * **Legacy** - Deprecated endpoints (will be removed in v3.0)
    
    ## ✨ Features
    
    * **🔒 Security**: Input sanitization, rate limiting, secure headers
    * **🏗️ Clean Architecture**: Service layer with dependency injection
    * **🏢 Multi-Tenant**: InfoSec, Quant, and Shared content streams  
    * **📌 Sticky Posts**: Priority posts appear at top
    * **🔍 Enhanced Search**: In-memory indexing with relevance ranking
    * **⚡ Performance**: Configurable caching and CDN-ready
    
    ## 🔗 Quick Links
    
    * **API v1 Docs**: [`/api/v1/docs`](/api/v1/docs)  
    * **Health Check**: [`/api/v1/health`](/api/v1/health)
    * **OpenAPI Spec**: [`/api/v1/openapi.json`](/api/v1/openapi.json)
    """,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    # Security: Limit request size
    max_request_size=security_settings.max_content_length
)


# Security middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Cache headers for CDN
        if request.url.path.startswith("/api/v1/attachments/"):
            # Cache static assets for 1 hour
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif request.method == "GET" and "/health" not in request.url.path:
            # Cache GET responses for 5 minutes (except health checks)
            response.headers["Cache-Control"] = "public, max-age=300"
        else:
            # Don't cache other responses
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        
        return response


# Apply middleware
app.add_middleware(SecurityHeadersMiddleware)

# Trusted host middleware (prevents host header injection)
if settings.allowed_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts
    )

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600  # Cache preflight requests for 1 hour
)


# Request tracking and rate limiting middleware
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track request performance and add request ID"""
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    start_time = time.time()
    path = request.url.path
    method = request.method
    
    # Check rate limiting
    if settings.rate_limit_enabled and not path.startswith("/docs") and not path.startswith("/redoc"):
        rate_limiter = get_rate_limiter()
        client_ip = request.client.host if request.client else "unknown"
        
        # Apply stricter limits to non-v1 endpoints
        if not path.startswith("/api/v1"):
            allowed, limit_info = await rate_limiter.check_endpoint_limit(path, client_ip, requests_per_minute=10)
        else:
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
        
        # Add request ID and timing to response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}"
        
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


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors with helpful message"""
    return JSONResponse(
        status_code=404,
        content=error_response(
            "NOT_FOUND",
            "Resource not found. API v1 endpoints are available at /api/v1",
            details={"path": str(request.url.path)},
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
                cache_enabled=settings.cache_enabled,
                api_version="v1")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    container = get_container()
    logger.info("Shutting down Blog Backend API")
    
    # Stop rate limiter cleanup tasks
    if settings.rate_limit_enabled:
        await container.rate_limiter.stop_all_cleanup_tasks()
    
    logger.info("Application shutdown complete")


# Create v1 sub-application
v1_app = FastAPI(
    title=f"{settings.app_name} - API v1",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add all v1 routes
v1_app.include_router(v1_router)

# Mount v1 API
app.mount("/api/v1", v1_app)


# Root endpoint redirects to v1 docs
@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API v1 documentation"""
    return RedirectResponse(url="/api/v1/docs")


# API version info
@app.get("/api", 
    summary="📌 API Version Information",
    description="Get available API versions and deprecation notices"
)
async def api_versions():
    """Get API version information"""
    return success_response({
        "current_version": "v1",
        "available_versions": ["v1"],
        "deprecated_endpoints": {
            "message": "Legacy endpoints without /api/v1 prefix are deprecated",
            "removal_date": "2025-01-01",
            "migration_guide": "https://github.com/norandom/because-security-blog/blob/main/MIGRATION.md"
        },
        "links": {
            "v1_docs": "/api/v1/docs",
            "v1_openapi": "/api/v1/openapi.json",
            "health": "/api/v1/health"
        }
    })


# Legacy endpoint warnings (these will be removed in v3.0)
legacy_endpoints = [
    "/posts", "/posts/all-tenants", "/posts/{slug}", "/posts/{slug}/related",
    "/search", "/search/suggest", "/stats", "/tenants", "/tenants/{tenant}",
    "/tenants/{tenant}/posts", "/health", "/metrics", "/attachments/{slug}/{path:path}"
]

for endpoint in legacy_endpoints:
    @app.get(endpoint, include_in_schema=False, deprecated=True)
    async def legacy_endpoint_warning(request: Request):
        """Warn about deprecated endpoint usage"""
        return JSONResponse(
            status_code=301,
            content={
                "error": "DEPRECATED_ENDPOINT",
                "message": f"This endpoint has moved to /api/v1{request.url.path}",
                "new_url": f"/api/v1{request.url.path}",
                "deprecation_date": "2024-12-01",
                "removal_date": "2025-01-01"
            },
            headers={
                "Location": f"/api/v1{request.url.path}",
                "Deprecation": "version=legacy, date=2025-01-01"
            }
        )