from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# Define supported tenants
TenantType = Literal["infosec", "quant", "shared"]


class BlogPost(BaseModel):
    """Complete blog post with full content and metadata"""
    slug: str = Field(..., description="URL-friendly identifier for the post")
    title: str = Field(..., description="Blog post title")
    content: str = Field(..., description="Full markdown content of the post")
    excerpt: str = Field(..., description="Short summary of the post")
    tags: List[str] = Field(default=[], description="List of tags associated with the post")
    date: datetime = Field(..., description="Publication date and time")
    author: Optional[str] = Field(None, description="Post author name")
    tenant: TenantType = Field(default="shared", description="Tenant namespace (infosec, quant, or shared)")
    metadata: Dict[str, Any] = Field(default={}, description="Additional metadata from frontmatter")
    attachments: List[str] = Field(default=[], description="List of attachment file paths")
    reading_time: Optional[int] = Field(None, description="Estimated reading time in minutes")


class BlogPostSummary(BaseModel):
    """Blog post summary for listing pages"""
    slug: str = Field(..., description="URL-friendly identifier for the post")
    title: str = Field(..., description="Blog post title")
    excerpt: str = Field(..., description="Short summary of the post")
    tags: List[str] = Field(default=[], description="List of tags associated with the post")
    date: datetime = Field(..., description="Publication date and time")
    author: Optional[str] = Field(None, description="Post author name")
    tenant: TenantType = Field(default="shared", description="Tenant namespace (infosec, quant, or shared)")
    reading_time: Optional[int] = Field(None, description="Estimated reading time in minutes")


class BlogStats(BaseModel):
    """Blog statistics and analytics"""
    total_posts: int = Field(..., description="Total number of published posts")
    tags: Dict[str, int] = Field(..., description="Tag usage counts")
    authors: Dict[str, int] = Field(..., description="Post counts by author")
    posts_by_month: Dict[str, int] = Field(..., description="Post counts by month (YYYY-MM format)")
    posts_by_tenant: Dict[str, int] = Field(..., description="Post counts by tenant")

class TenantStats(BaseModel):
    """Tenant-specific statistics"""
    tenant: TenantType = Field(..., description="Tenant namespace")
    total_posts: int = Field(..., description="Total posts in this tenant")
    tags: Dict[str, int] = Field(..., description="Tag usage counts for this tenant")
    authors: Dict[str, int] = Field(..., description="Post counts by author for this tenant")
    posts_by_month: Dict[str, int] = Field(..., description="Post counts by month for this tenant")
    recent_posts: List[BlogPostSummary] = Field(default=[], description="Recent posts in this tenant")