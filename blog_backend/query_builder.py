"""
Query builder pattern for blog post filtering and sorting
"""
from typing import List, Optional, Callable, Any, Protocol
from dataclasses import dataclass
from enum import Enum

from .models import BlogPost, TenantType


class SortOrder(Enum):
    """Sort order enumeration"""
    ASC = "asc"
    DESC = "desc"


class SortField(Enum):
    """Available sort fields"""
    DATE = "date"
    TITLE = "title"
    AUTHOR = "author"


@dataclass
class FilterCriteria:
    """Encapsulates all filter criteria for blog posts"""
    tenant: Optional[TenantType] = None
    tag: Optional[str] = None
    author: Optional[str] = None
    search_query: Optional[str] = None


@dataclass
class SortCriteria:
    """Encapsulates sorting criteria"""
    field: SortField = SortField.DATE
    order: SortOrder = SortOrder.DESC
    enable_sticky: bool = True


@dataclass
class PaginationCriteria:
    """Encapsulates pagination criteria"""
    offset: int = 0
    limit: Optional[int] = None


class PostFilter(Protocol):
    """Protocol for post filter functions"""
    
    def __call__(self, posts: List[BlogPost]) -> List[BlogPost]:
        ...


class PostSorter(Protocol):
    """Protocol for post sorter functions"""
    
    def __call__(self, posts: List[BlogPost]) -> List[BlogPost]:
        ...


class PostQuery:
    """Fluent query builder for blog posts"""
    
    def __init__(self, posts: List[BlogPost]):
        self._posts = posts
        self._filters: List[PostFilter] = []
        self._sort_criteria: Optional[SortCriteria] = None
        self._pagination: Optional[PaginationCriteria] = None
    
    def filter_by_tenant(self, tenant: TenantType) -> 'PostQuery':
        """Filter posts by tenant"""
        def tenant_filter(posts: List[BlogPost]) -> List[BlogPost]:
            return [post for post in posts if post.tenant == tenant]
        
        self._filters.append(tenant_filter)
        return self
    
    def filter_by_tag(self, tag: str) -> 'PostQuery':
        """Filter posts by tag"""
        def tag_filter(posts: List[BlogPost]) -> List[BlogPost]:
            return [post for post in posts if tag.lower() in [t.lower() for t in post.tags]]
        
        self._filters.append(tag_filter)
        return self
    
    def filter_by_author(self, author: str) -> 'PostQuery':
        """Filter posts by author"""
        def author_filter(posts: List[BlogPost]) -> List[BlogPost]:
            return [
                post for post in posts 
                if post.author and post.author.lower() == author.lower()
            ]
        
        self._filters.append(author_filter)
        return self
    
    def filter_by_search(self, query: str) -> 'PostQuery':
        """Filter posts by search query"""
        query_lower = query.lower()
        
        def search_filter(posts: List[BlogPost]) -> List[BlogPost]:
            return [
                post for post in posts
                if (query_lower in post.title.lower() or
                    query_lower in post.content.lower() or
                    any(query_lower in tag.lower() for tag in post.tags) or
                    (post.author and query_lower in post.author.lower()))
            ]
        
        self._filters.append(search_filter)
        return self
    
    def sort_by(
        self, 
        field: SortField, 
        order: SortOrder = SortOrder.DESC,
        enable_sticky: bool = True
    ) -> 'PostQuery':
        """Sort posts by field"""
        self._sort_criteria = SortCriteria(field, order, enable_sticky)
        return self
    
    def paginate(self, offset: int = 0, limit: Optional[int] = None) -> 'PostQuery':
        """Apply pagination"""
        self._pagination = PaginationCriteria(offset, limit)
        return self
    
    def execute(self) -> List[BlogPost]:
        """Execute the query and return filtered/sorted posts"""
        result = self._posts.copy()
        
        # Apply filters
        for filter_func in self._filters:
            result = filter_func(result)
        
        # Apply sorting
        if self._sort_criteria:
            result = self._apply_sorting(result, self._sort_criteria)
        
        # Apply pagination
        if self._pagination:
            result = self._apply_pagination(result, self._pagination)
        
        return result
    
    def _apply_sorting(self, posts: List[BlogPost], criteria: SortCriteria) -> List[BlogPost]:
        """Apply sorting with sticky post support"""
        reverse = criteria.order == SortOrder.DESC
        
        # Get sort key function
        if criteria.field == SortField.DATE:
            key_func = lambda p: p.date
        elif criteria.field == SortField.TITLE:
            key_func = lambda p: p.title.lower()
        elif criteria.field == SortField.AUTHOR:
            key_func = lambda p: (p.author or "").lower()
        else:
            key_func = lambda p: p.date
        
        # Apply sticky sorting if enabled and we're sorting by date
        if criteria.enable_sticky and criteria.field == SortField.DATE and len(posts) >= 3:
            sticky_posts = [p for p in posts if p.sticky]
            regular_posts = [p for p in posts if not p.sticky]
            
            # Sort each group
            sticky_posts.sort(key=key_func, reverse=reverse)
            regular_posts.sort(key=key_func, reverse=reverse)
            
            return sticky_posts + regular_posts
        else:
            # Regular sorting
            return sorted(posts, key=key_func, reverse=reverse)
    
    def _apply_pagination(self, posts: List[BlogPost], criteria: PaginationCriteria) -> List[BlogPost]:
        """Apply pagination"""
        start = criteria.offset
        end = start + criteria.limit if criteria.limit else None
        return posts[start:end]


def create_post_query(posts: List[BlogPost]) -> PostQuery:
    """Factory function to create a new PostQuery"""
    return PostQuery(posts)


class QueryBuilder:
    """High-level query builder for common use cases"""
    
    @staticmethod
    def for_tenant(
        posts: List[BlogPost],
        tenant: TenantType,
        sort_field: SortField = SortField.DATE,
        sort_order: SortOrder = SortOrder.DESC,
        enable_sticky: bool = True,
        offset: int = 0,
        limit: Optional[int] = None
    ) -> List[BlogPost]:
        """Quick query for tenant posts"""
        return (create_post_query(posts)
                .filter_by_tenant(tenant)
                .sort_by(sort_field, sort_order, enable_sticky)
                .paginate(offset, limit)
                .execute())
    
    @staticmethod
    def for_all_tenants(
        posts: List[BlogPost],
        tag: Optional[str] = None,
        author: Optional[str] = None,
        sort_field: SortField = SortField.DATE,
        sort_order: SortOrder = SortOrder.DESC,
        enable_sticky: bool = True,
        offset: int = 0,
        limit: Optional[int] = None
    ) -> List[BlogPost]:
        """Quick query for all tenant posts with optional filters"""
        query = create_post_query(posts)
        
        if tag:
            query = query.filter_by_tag(tag)
        
        if author:
            query = query.filter_by_author(author)
        
        return (query
                .sort_by(sort_field, sort_order, enable_sticky)
                .paginate(offset, limit)
                .execute())
    
    @staticmethod
    def search(
        posts: List[BlogPost],
        search_query: str,
        tenant: Optional[TenantType] = None,
        limit: Optional[int] = None
    ) -> List[BlogPost]:
        """Quick search query"""
        query = create_post_query(posts).filter_by_search(search_query)
        
        if tenant:
            query = query.filter_by_tenant(tenant)
        
        return (query
                .sort_by(SortField.DATE, SortOrder.DESC, enable_sticky=False)
                .paginate(0, limit)
                .execute())