"""
Structured logging and observability without external dependencies
"""
import logging
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from functools import wraps
from contextvars import ContextVar
import asyncio

# Context variable for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            log_data['request_id'] = request_id
        
        # Add extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

class BlogLogger:
    """Custom logger with structured logging support"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Add structured JSON handler
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal logging method with extra fields"""
        extra = {'extra_fields': kwargs}
        getattr(self.logger, level)(message, extra=extra)
    
    def info(self, message: str, **kwargs):
        self._log('info', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log('error', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log('warning', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log('debug', message, **kwargs)

# Global logger instance
logger = BlogLogger('blog_backend')

class Metrics:
    """Simple in-memory metrics collection"""
    
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.histograms: Dict[str, list] = {}
        self.gauges: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def increment(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter"""
        key = self._make_key(name, labels)
        async with self._lock:
            self.counters[key] = self.counters.get(key, 0) + value
    
    async def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram observation"""
        key = self._make_key(name, labels)
        async with self._lock:
            if key not in self.histograms:
                self.histograms[key] = []
            self.histograms[key].append(value)
            # Keep only last 1000 observations
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
    
    async def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge value"""
        key = self._make_key(name, labels)
        async with self._lock:
            self.gauges[key] = value
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create metric key with labels"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        async with self._lock:
            summary = {
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'histograms': {}
            }
            
            # Calculate histogram statistics
            for key, values in self.histograms.items():
                if values:
                    summary['histograms'][key] = {
                        'count': len(values),
                        'min': min(values),
                        'max': max(values),
                        'avg': sum(values) / len(values),
                        'p50': sorted(values)[len(values) // 2],
                        'p99': sorted(values)[int(len(values) * 0.99)]
                    }
            
            return summary

# Global metrics instance
metrics = Metrics()

def track_performance(metric_name: str):
    """Decorator to track function performance"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                await metrics.observe(f"{metric_name}_duration_seconds", duration)
                await metrics.increment(f"{metric_name}_total")
                logger.info(f"Function completed", 
                           function=func.__name__, 
                           duration=duration,
                           metric=metric_name)
                return result
            except Exception as e:
                duration = time.time() - start_time
                await metrics.increment(f"{metric_name}_errors_total")
                logger.error(f"Function failed", 
                            function=func.__name__, 
                            duration=duration,
                            metric=metric_name,
                            error=str(e))
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                # Use asyncio.create_task for sync functions
                asyncio.create_task(
                    metrics.observe(f"{metric_name}_duration_seconds", duration)
                )
                asyncio.create_task(
                    metrics.increment(f"{metric_name}_total")
                )
                return result
            except Exception as e:
                asyncio.create_task(
                    metrics.increment(f"{metric_name}_errors_total")
                )
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class RequestTracker:
    """Track request lifecycle and performance"""
    
    def __init__(self):
        self.active_requests = 0
        self._lock = asyncio.Lock()
    
    async def start_request(self, request_id: str, path: str, method: str):
        """Start tracking a request"""
        async with self._lock:
            self.active_requests += 1
        
        await metrics.set_gauge("active_requests", self.active_requests)
        await metrics.increment("http_requests_total", labels={
            "method": method,
            "path": path
        })
        
        logger.info("Request started",
                   request_id=request_id,
                   path=path,
                   method=method,
                   active_requests=self.active_requests)
    
    async def end_request(self, request_id: str, path: str, method: str, 
                         status_code: int, duration: float):
        """End tracking a request"""
        async with self._lock:
            self.active_requests -= 1
        
        await metrics.set_gauge("active_requests", self.active_requests)
        await metrics.observe("http_request_duration_seconds", duration, labels={
            "method": method,
            "path": path,
            "status": str(status_code)
        })
        
        logger.info("Request completed",
                   request_id=request_id,
                   path=path,
                   method=method,
                   status_code=status_code,
                   duration=duration,
                   active_requests=self.active_requests)

# Global request tracker
request_tracker = RequestTracker()