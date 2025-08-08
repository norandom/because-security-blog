"""
API response models for consistent API responses
"""
from typing import List, Optional, Any, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response wrapper"""
    success: bool = Field(..., description="Whether the request was successful")
    data: Optional[T] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Response message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = Field(False, description="Always false for errors")
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    items: List[T] = Field(..., description="List of items")
    total: Optional[int] = Field(None, description="Total number of items (if available)")
    offset: int = Field(0, description="Current offset")
    limit: Optional[int] = Field(None, description="Items per page limit")
    has_more: Optional[bool] = Field(None, description="Whether there are more items")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Health status (healthy, degraded, unhealthy)")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    checks: dict = Field(default_factory=dict, description="Individual health check results")
    uptime_seconds: Optional[float] = Field(None, description="Application uptime in seconds")


class MetricsResponse(BaseModel):
    """Metrics response"""
    performance: dict = Field(..., description="Performance metrics")
    search_index: dict = Field(..., description="Search index statistics")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metrics timestamp")


class SuggestionsResponse(BaseModel):
    """Search suggestions response"""
    suggestions: List[str] = Field(..., description="List of search suggestions")
    query: str = Field(..., description="Original query prefix")


class TenantsListResponse(BaseModel):
    """Tenants list response"""
    tenants: List[dict] = Field(..., description="List of available tenants")


class TagsResponse(BaseModel):
    """Tags response with counts"""
    tags: List[dict] = Field(..., description="List of tags with usage counts")
    total_tags: int = Field(..., description="Total number of unique tags")


# Factory functions for creating consistent responses

def success_response(data: T, message: Optional[str] = None, request_id: Optional[str] = None) -> ApiResponse[T]:
    """Create a successful API response"""
    return ApiResponse(
        success=True,
        data=data,
        message=message,
        request_id=request_id
    )


def error_response(
    error_code: str,
    message: str,
    details: Optional[dict] = None,
    request_id: Optional[str] = None
) -> ErrorResponse:
    """Create an error response"""
    return ErrorResponse(
        error=error_code,
        message=message,
        details=details,
        request_id=request_id
    )


def paginated_response(
    items: List[T],
    offset: int = 0,
    limit: Optional[int] = None,
    total: Optional[int] = None
) -> PaginatedResponse[T]:
    """Create a paginated response"""
    has_more = None
    if total is not None:
        has_more = offset + len(items) < total
    elif limit is not None:
        has_more = len(items) == limit
    
    return PaginatedResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
        has_more=has_more
    )