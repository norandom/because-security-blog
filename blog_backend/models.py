from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class BlogPost(BaseModel):
    slug: str
    title: str
    content: str
    excerpt: str
    tags: List[str]
    date: datetime
    author: Optional[str] = None
    metadata: Dict[str, Any]
    attachments: List[str] = []


class BlogPostSummary(BaseModel):
    slug: str
    title: str
    excerpt: str
    tags: List[str]
    date: datetime
    author: Optional[str] = None


class BlogStats(BaseModel):
    total_posts: int
    tags: Dict[str, int]
    authors: Dict[str, int]
    posts_by_month: Dict[str, int]