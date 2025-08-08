"""
Custom exceptions for better error handling and debugging
"""
from typing import Optional, Dict, Any


class BlogBackendException(Exception):
    """Base exception for all blog backend errors"""
    
    def __init__(
        self, 
        message: str, 
        code: str = "BLOG_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class PostNotFoundError(BlogBackendException):
    """Raised when a requested post is not found"""
    
    def __init__(self, slug: str):
        super().__init__(
            message=f"Post with slug '{slug}' not found",
            code="POST_NOT_FOUND", 
            status_code=404,
            details={"slug": slug}
        )


class InvalidQueryError(BlogBackendException):
    """Raised when a search query is invalid"""
    
    def __init__(self, query: str, reason: str):
        super().__init__(
            message=f"Invalid query '{query}': {reason}",
            code="INVALID_QUERY",
            status_code=400,
            details={"query": query, "reason": reason}
        )


class TenantNotFoundError(BlogBackendException):
    """Raised when an invalid tenant is requested"""
    
    def __init__(self, tenant: str):
        super().__init__(
            message=f"Tenant '{tenant}' not found",
            code="TENANT_NOT_FOUND",
            status_code=404,
            details={"tenant": tenant}
        )


class CacheError(BlogBackendException):
    """Raised when cache operations fail"""
    
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Cache {operation} failed: {reason}",
            code="CACHE_ERROR",
            status_code=500,
            details={"operation": operation, "reason": reason}
        )


class SearchIndexError(BlogBackendException):
    """Raised when search index operations fail"""
    
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Search index {operation} failed: {reason}",
            code="SEARCH_INDEX_ERROR",
            status_code=500,
            details={"operation": operation, "reason": reason}
        )


class ConfigurationError(BlogBackendException):
    """Raised when configuration is invalid"""
    
    def __init__(self, setting: str, reason: str):
        super().__init__(
            message=f"Configuration error for '{setting}': {reason}",
            code="CONFIGURATION_ERROR",
            status_code=500,
            details={"setting": setting, "reason": reason}
        )