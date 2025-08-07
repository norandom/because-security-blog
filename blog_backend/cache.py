"""
In-memory caching implementation without external dependencies
"""
from typing import Dict, Any, Optional, Tuple, Callable
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import asyncio
from pathlib import Path
import time

class TTLCache:
    """Thread-safe in-memory cache with TTL support"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL"""
        ttl = ttl or self._default_ttl
        expiry = time.time() + ttl
        async with self._lock:
            self._cache[key] = (value, expiry)
    
    async def delete(self, key: str):
        """Remove key from cache"""
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self):
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self):
        """Remove expired entries"""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, expiry) in self._cache.items()
                if current_time >= expiry
            ]
            for key in expired_keys:
                del self._cache[key]

class FileContentCache:
    """Cache based on file content hash"""
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache = TTLCache(default_ttl=ttl_seconds)
        self._file_hashes: Dict[str, str] = {}
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Generate hash based on file content and modification time"""
        try:
            stat = file_path.stat()
            # Use mtime and size for quick hash
            content = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
            return hashlib.md5(content.encode()).hexdigest()
        except:
            return hashlib.md5(str(file_path).encode()).hexdigest()
    
    async def get_or_compute(
        self, 
        file_path: Path, 
        compute_func: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        """Get from cache or compute if file changed"""
        file_hash = self._get_file_hash(file_path)
        cache_key = str(file_path)
        
        # Check if file changed
        old_hash = self._file_hashes.get(cache_key)
        if old_hash != file_hash:
            # File changed, invalidate cache
            await self._cache.delete(cache_key)
            self._file_hashes[cache_key] = file_hash
        
        # Try cache
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Compute and cache
        result = await compute_func()
        await self._cache.set(cache_key, result, ttl)
        return result

def cached(ttl: int = 300):
    """Async function decorator for caching"""
    def decorator(func):
        cache = TTLCache(default_ttl=ttl)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)
            
            # Try cache
            result = await cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result)
            return result
        
        wrapper.cache = cache
        return wrapper
    
    return decorator

class StatsCache:
    """Specialized cache for expensive statistics calculations"""
    
    def __init__(self):
        self._stats_cache = None
        self._stats_time = None
        self._tenant_stats_cache = {}
        self._tenant_stats_time = {}
        self._ttl = timedelta(minutes=5)
    
    async def get_stats(self, compute_func: Callable) -> Any:
        """Get cached stats or recompute if expired"""
        now = datetime.now()
        
        if (self._stats_cache is None or 
            self._stats_time is None or
            now - self._stats_time > self._ttl):
            
            self._stats_cache = await compute_func()
            self._stats_time = now
        
        return self._stats_cache
    
    async def get_tenant_stats(self, tenant: str, compute_func: Callable) -> Any:
        """Get cached tenant stats or recompute if expired"""
        now = datetime.now()
        
        if (tenant not in self._tenant_stats_cache or
            tenant not in self._tenant_stats_time or
            now - self._tenant_stats_time[tenant] > self._ttl):
            
            self._tenant_stats_cache[tenant] = await compute_func()
            self._tenant_stats_time[tenant] = now
        
        return self._tenant_stats_cache[tenant]
    
    def invalidate(self):
        """Invalidate all cached stats"""
        self._stats_cache = None
        self._stats_time = None
        self._tenant_stats_cache.clear()
        self._tenant_stats_time.clear()