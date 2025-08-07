"""
Rate limiting implementation without external dependencies
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict, deque
import time

class TokenBucket:
    """Token bucket algorithm for rate limiting"""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens, returns True if successful"""
        async with self._lock:
            # Refill tokens based on time passed
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_refill = now
            
            # Try to consume
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait until tokens are available"""
        async with self._lock:
            if self.tokens >= tokens:
                return 0.0
            
            needed = tokens - self.tokens
            return needed / self.refill_rate

class SlidingWindowLog:
    """Sliding window log algorithm for rate limiting"""
    
    def __init__(self, window_size: int, max_requests: int):
        self.window_size = window_size  # seconds
        self.max_requests = max_requests
        self.requests: Dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def check_and_update(self, key: str) -> Tuple[bool, Optional[float]]:
        """
        Check if request is allowed and update log
        Returns (allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()
            window_start = now - self.window_size
            
            # Remove old entries
            requests = self.requests[key]
            while requests and requests[0] < window_start:
                requests.popleft()
            
            # Check limit
            if len(requests) >= self.max_requests:
                # Calculate retry after
                oldest_request = requests[0]
                retry_after = oldest_request + self.window_size - now
                return False, retry_after
            
            # Add new request
            requests.append(now)
            return True, None
    
    async def cleanup(self):
        """Remove old entries from all keys"""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_size
            
            empty_keys = []
            for key, requests in self.requests.items():
                while requests and requests[0] < window_start:
                    requests.popleft()
                if not requests:
                    empty_keys.append(key)
            
            # Remove empty keys
            for key in empty_keys:
                del self.requests[key]

class RateLimiter:
    """Combined rate limiter with multiple strategies"""
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10
    ):
        # Minute-based sliding window
        self.minute_limiter = SlidingWindowLog(60, requests_per_minute)
        
        # Hour-based sliding window  
        self.hour_limiter = SlidingWindowLog(3600, requests_per_hour)
        
        # Burst control with token bucket
        self.burst_limiter = TokenBucket(
            capacity=burst_size,
            refill_rate=requests_per_minute / 60.0
        )
        
        # Cleanup task
        self._cleanup_task = None
    
    async def check_rate_limit(
        self, 
        identifier: str,
        consume_tokens: int = 1
    ) -> Tuple[bool, Optional[Dict[str, any]]]:
        """
        Check if request is allowed
        Returns (allowed, rate_limit_info)
        """
        # Check burst limit first (fastest)
        burst_allowed = await self.burst_limiter.consume(consume_tokens)
        if not burst_allowed:
            wait_time = await self.burst_limiter.get_wait_time(consume_tokens)
            return False, {
                'reason': 'burst_limit_exceeded',
                'retry_after': wait_time
            }
        
        # Check minute limit
        minute_allowed, minute_retry = await self.minute_limiter.check_and_update(identifier)
        if not minute_allowed:
            return False, {
                'reason': 'minute_limit_exceeded',
                'retry_after': minute_retry
            }
        
        # Check hour limit
        hour_allowed, hour_retry = await self.hour_limiter.check_and_update(identifier)
        if not hour_allowed:
            return False, {
                'reason': 'hour_limit_exceeded',
                'retry_after': hour_retry
            }
        
        return True, None
    
    async def start_cleanup_task(self):
        """Start periodic cleanup of old entries"""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(300)  # Clean every 5 minutes
                await self.minute_limiter.cleanup()
                await self.hour_limiter.cleanup()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    async def stop_cleanup_task(self):
        """Stop the cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

class EndpointRateLimiter:
    """Rate limiter with per-endpoint configuration"""
    
    def __init__(self):
        self.limiters: Dict[str, RateLimiter] = {}
        self.default_limiter = RateLimiter()
        
        # Configure specific endpoints
        self._configure_endpoints()
    
    def _configure_endpoints(self):
        """Configure rate limits for specific endpoints"""
        # Search endpoint - more restrictive
        self.limiters["/search"] = RateLimiter(
            requests_per_minute=30,
            requests_per_hour=300,
            burst_size=5
        )
        
        # Stats endpoint - cache-friendly
        self.limiters["/stats"] = RateLimiter(
            requests_per_minute=20,
            requests_per_hour=200,
            burst_size=3
        )
        
        # Health check - very permissive
        self.limiters["/health"] = RateLimiter(
            requests_per_minute=600,
            requests_per_hour=10000,
            burst_size=50
        )
    
    async def check_endpoint_limit(
        self,
        endpoint: str,
        identifier: str
    ) -> Tuple[bool, Optional[Dict[str, any]]]:
        """Check rate limit for specific endpoint"""
        limiter = self.limiters.get(endpoint, self.default_limiter)
        return await limiter.check_rate_limit(identifier)
    
    async def start_all_cleanup_tasks(self):
        """Start cleanup tasks for all limiters"""
        await self.default_limiter.start_cleanup_task()
        for limiter in self.limiters.values():
            await limiter.start_cleanup_task()
    
    async def stop_all_cleanup_tasks(self):
        """Stop all cleanup tasks"""
        await self.default_limiter.stop_cleanup_task()
        for limiter in self.limiters.values():
            await limiter.stop_cleanup_task()