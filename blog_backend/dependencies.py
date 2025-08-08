"""
Dependency injection container for better testability and maintainability
"""
from functools import lru_cache
from typing import Optional

from .functional_blog_parser import FunctionalBlogParser
from .search import SearchEngine
from .cache import StatsCache
from .rate_limit import EndpointRateLimiter
from .services import PostService, StatsService
from .config import get_settings


class ServiceContainer:
    """Dependency injection container"""
    
    def __init__(self):
        self._instances = {}
        self._settings = get_settings()
    
    @property
    def settings(self):
        """Get application settings"""
        return self._settings
    
    @property
    def blog_parser(self) -> FunctionalBlogParser:
        """Get blog parser instance"""
        if 'blog_parser' not in self._instances:
            self._instances['blog_parser'] = FunctionalBlogParser(
                posts_directory=str(self._settings.posts_directory),
                max_workers=self._settings.max_workers
            )
        return self._instances['blog_parser']
    
    @property
    def search_engine(self) -> SearchEngine:
        """Get search engine instance"""
        if 'search_engine' not in self._instances:
            self._instances['search_engine'] = SearchEngine()
        return self._instances['search_engine']
    
    @property
    def stats_cache(self) -> Optional[StatsCache]:
        """Get stats cache instance if caching is enabled"""
        if not self._settings.cache_enabled:
            return None
            
        if 'stats_cache' not in self._instances:
            self._instances['stats_cache'] = StatsCache()
        return self._instances['stats_cache']
    
    @property
    def rate_limiter(self) -> EndpointRateLimiter:
        """Get rate limiter instance"""
        if 'rate_limiter' not in self._instances:
            self._instances['rate_limiter'] = EndpointRateLimiter()
        return self._instances['rate_limiter']
    
    @property
    def post_service(self) -> PostService:
        """Get post service instance"""
        if 'post_service' not in self._instances:
            self._instances['post_service'] = PostService(
                repository=self.blog_parser,
                search_service=self.search_engine,
                stats_cache=self.stats_cache
            )
        return self._instances['post_service']
    
    @property
    def stats_service(self) -> StatsService:
        """Get stats service instance"""
        if 'stats_service' not in self._instances:
            self._instances['stats_service'] = StatsService(
                repository=self.blog_parser,
                search_service=self.search_engine,
                stats_cache=self.stats_cache
            )
        return self._instances['stats_service']
    
    def reset(self):
        """Reset all instances (useful for testing)"""
        self._instances.clear()


@lru_cache()
def get_container() -> ServiceContainer:
    """Get the global service container"""
    return ServiceContainer()


# FastAPI dependency functions
def get_post_service() -> PostService:
    """FastAPI dependency to get post service"""
    return get_container().post_service


def get_stats_service() -> StatsService:
    """FastAPI dependency to get stats service"""
    return get_container().stats_service


def get_search_engine() -> SearchEngine:
    """FastAPI dependency to get search engine"""
    return get_container().search_engine


def get_rate_limiter() -> EndpointRateLimiter:
    """FastAPI dependency to get rate limiter"""
    return get_container().rate_limiter