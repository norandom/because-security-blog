#!/usr/bin/env python3
"""
Functional blog backend entry point for development and Nuitka compilation
"""
import uvicorn
import os
import asyncio

if __name__ == "__main__":
    # Configuration
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Set event loop policy for better performance
    if os.name == 'nt':  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    else:  # Unix/Linux
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass  # uvloop not available, use default
    
    uvicorn.run(
        "blog_backend.main_v2:app",
        host=host,
        port=port,
        workers=1,  # Single worker for Nuitka - concurrency handled internally
        log_level="info",
        access_log=True,
        loop="asyncio"
    )