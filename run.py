#!/usr/bin/env python3
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        "blog_backend.main:app",
        host=host,
        port=port,
        workers=1,  # Single worker for Nuitka
        log_level="info"
    )