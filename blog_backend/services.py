"""
Service layer for business logic separation and better testability
"""
from typing import List, Optional, Dict, Any, Protocol
from dataclasses import dataclass
import asyncio

from .models import BlogPost, BlogPostSummary, BlogStats, TenantStats, TenantType
from .functional_blog_parser import FunctionalBlogParser
from .search import SearchEngine
from .cache import StatsCache
from .sticky import posts_to_summaries_with_sticky
from .query_builder import QueryBuilder, SortField, SortOrder
from .exceptions import PostNotFoundError, InvalidQueryError, SearchIndexError
from .config import get_settings, get_security_settings
from .logging import logger, metrics


class PostRepository(Protocol):
    """Protocol for post data access"""
    
    async def get_all_posts(self) -> List[BlogPost]:
        ...
    
    async def get_post_by_slug(self, slug: str) -> Optional[BlogPost]:
        ...
    
    async def filter_by_tenant(self, tenant: TenantType) -> List[BlogPost]:
        ...


class SearchService(Protocol):
    """Protocol for search operations"""
    
    async def search(self, query: str, tenant: Optional[TenantType] = None, limit: Optional[int] = None) -> List[BlogPost]:
        ...
    
    async def suggest(self, prefix: str, limit: int = 5) -> List[str]:
        ...
    
    async def get_related_posts(self, slug: str, limit: int = 5) -> List[str]:
        ...


@dataclass
class PostListRequest:
    """Request parameters for listing posts"""
    sort_field: SortField = SortField.DATE
    sort_order: SortOrder = SortOrder.DESC
    tenant: Optional[TenantType] = None
    tag: Optional[str] = None
    author: Optional[str] = None
    enable_sticky: bool = True
    offset: int = 0
    limit: Optional[int] = None


@dataclass
class SearchRequest:
    """Request parameters for search"""
    query: str
    tenant: Optional[TenantType] = None
    limit: Optional[int] = None


class PostService:
    """Service for post-related business logic"""
    
    def __init__(
        self, 
        repository: PostRepository,
        search_service: SearchService,
        stats_cache: Optional[StatsCache] = None
    ):
        self.repository = repository
        self.search_service = search_service
        self.stats_cache = stats_cache
        self.settings = get_settings()
        self.security_settings = get_security_settings()
    
    async def list_posts(self, request: PostListRequest) -> List[BlogPostSummary]:
        """List posts with filtering, sorting, and pagination"""
        try:
            posts = await self.repository.get_all_posts()
            
            # Apply filtering based on request
            if request.tenant:
                filtered_posts = QueryBuilder.for_tenant(
                    posts=posts,
                    tenant=request.tenant,
                    sort_field=request.sort_field,
                    sort_order=request.sort_order,
                    enable_sticky=request.enable_sticky,
                    offset=request.offset,
                    limit=request.limit
                )
            else:
                filtered_posts = QueryBuilder.for_all_tenants(
                    posts=posts,
                    tag=request.tag,
                    author=request.author,
                    sort_field=request.sort_field,
                    sort_order=request.sort_order,
                    enable_sticky=request.enable_sticky,
                    offset=request.offset,
                    limit=request.limit
                )
            
            # Log metrics
            await metrics.increment("posts_listed_total", labels={
                "tenant": request.tenant or "all",
                "sticky_enabled": str(request.enable_sticky)
            })
            
            # Convert to summaries
            return posts_to_summaries_with_sticky(
                filtered_posts, 
                request.enable_sticky, 
                min_posts_for_sticky=3
            )
            
        except Exception as e:
            logger.error("Failed to list posts", error=str(e), request=request)
            await metrics.increment("posts_list_errors_total")
            raise
    
    async def get_post(self, slug: str) -> BlogPost:
        """Get a single post by slug"""
        try:
            post = await self.repository.get_post_by_slug(slug)
            if not post:
                raise PostNotFoundError(slug)
            
            await metrics.increment("posts_retrieved_total")
            return post
            
        except PostNotFoundError:
            await metrics.increment("posts_not_found_total")
            raise
        except Exception as e:
            logger.error("Failed to get post", error=str(e), slug=slug)
            await metrics.increment("posts_get_errors_total")
            raise
    
    async def search_posts(self, request: SearchRequest) -> List[BlogPostSummary]:
        """Search posts with validation and metrics"""
        try:
            # Validate query
            query = request.query.strip()
            if len(query) < self.settings.search_min_length:
                raise InvalidQueryError(query, "Query too short")
            
            if len(query) > self.security_settings.max_query_length:
                raise InvalidQueryError(query, "Query too long")
            
            # Perform search
            search_results = await self.search_service.search(
                query=query,
                tenant=request.tenant,
                limit=request.limit or self.settings.search_max_results
            )
            
            # Log metrics
            await metrics.increment("search_queries_total", labels={
                "tenant": request.tenant or "all"
            })
            
            logger.info("Search performed", 
                       query=query, 
                       tenant=request.tenant, 
                       results_count=len(search_results))
            
            # Convert to summaries
            summaries = [
                BlogPostSummary(
                    slug=post.slug,
                    title=post.title,
                    excerpt=post.excerpt,
                    tags=post.tags,
                    date=post.date,
                    author=post.author,
                    tenant=post.tenant,
                    sticky=post.sticky,
                    reading_time=post.reading_time
                )
                for post in search_results
            ]
            
            return summaries
            
        except (InvalidQueryError, SearchIndexError):
            await metrics.increment("search_errors_total")
            raise
        except Exception as e:
            logger.error("Search failed", error=str(e), request=request)
            await metrics.increment("search_errors_total")
            raise
    
    async def get_suggestions(self, prefix: str, limit: int = 5) -> List[str]:
        """Get search suggestions"""
        try:
            if len(prefix.strip()) < 1:
                return []
            
            suggestions = await self.search_service.suggest(prefix.strip(), limit)
            await metrics.increment("suggestions_requested_total")
            
            return suggestions
            
        except Exception as e:
            logger.error("Suggestions failed", error=str(e), prefix=prefix)
            await metrics.increment("suggestions_errors_total")
            raise
    
    async def get_related_posts(self, slug: str, limit: int = 5) -> List[BlogPostSummary]:
        """Get related posts for a given post"""
        try:
            # Verify post exists
            post = await self.get_post(slug)
            
            # Get related post slugs
            related_slugs = await self.search_service.get_related_posts(slug, limit)
            
            # Get full post data
            all_posts = await self.repository.get_all_posts()
            post_dict = {p.slug: p for p in all_posts}
            
            related_posts = [post_dict[s] for s in related_slugs if s in post_dict]
            
            await metrics.increment("related_posts_retrieved_total")
            
            return [
                BlogPostSummary(
                    slug=post.slug,
                    title=post.title,
                    excerpt=post.excerpt,
                    tags=post.tags,
                    date=post.date,
                    author=post.author,
                    tenant=post.tenant,
                    sticky=post.sticky,
                    reading_time=post.reading_time
                )
                for post in related_posts
            ]
            
        except PostNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to get related posts", error=str(e), slug=slug)
            await metrics.increment("related_posts_errors_total")
            raise


class StatsService:
    """Service for statistics and analytics"""
    
    def __init__(
        self,
        repository: PostRepository,
        search_service: SearchService,
        stats_cache: Optional[StatsCache] = None
    ):
        self.repository = repository
        self.search_service = search_service
        self.stats_cache = stats_cache
        self.settings = get_settings()
    
    async def get_blog_stats(self) -> BlogStats:
        """Get comprehensive blog statistics"""
        try:
            async def compute_stats():
                posts = await self.repository.get_all_posts()
                # Rebuild search index if needed
                if hasattr(self.search_service, 'rebuild_index'):
                    await self.search_service.rebuild_index(posts)
                return self._calculate_blog_stats(posts)
            
            if self.settings.cache_enabled and self.stats_cache:
                return await self.stats_cache.get_stats(compute_stats)
            else:
                return await compute_stats()
                
        except Exception as e:
            logger.error("Failed to get blog stats", error=str(e))
            await metrics.increment("stats_errors_total")
            raise
    
    async def get_tenant_stats(self, tenant: TenantType) -> TenantStats:
        """Get tenant-specific statistics"""
        try:
            async def compute_tenant_stats():
                posts = await self.repository.get_all_posts()
                return self._calculate_tenant_stats(posts, tenant)
            
            if self.settings.cache_enabled and self.stats_cache:
                return await self.stats_cache.get_tenant_stats(tenant, compute_tenant_stats)
            else:
                return await compute_tenant_stats()
                
        except Exception as e:
            logger.error("Failed to get tenant stats", error=str(e), tenant=tenant)
            await metrics.increment("tenant_stats_errors_total")
            raise
    
    def _calculate_blog_stats(self, posts: List[BlogPost]) -> BlogStats:
        """Calculate comprehensive blog statistics"""
        from collections import Counter
        
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
    
    def _calculate_tenant_stats(self, posts: List[BlogPost], tenant: TenantType) -> TenantStats:
        """Calculate tenant-specific statistics"""
        from collections import Counter
        
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
        recent_summaries = [
            BlogPostSummary(
                slug=post.slug,
                title=post.title,
                excerpt=post.excerpt,
                tags=post.tags,
                date=post.date,
                author=post.author,
                tenant=post.tenant,
                sticky=post.sticky,
                reading_time=post.reading_time
            )
            for post in recent_posts
        ]
        
        return TenantStats(
            tenant=tenant,
            total_posts=len(tenant_posts),
            tags=dict(tag_counter),
            authors=dict(author_counter),
            posts_by_month=dict(posts_by_month),
            recent_posts=recent_summaries
        )