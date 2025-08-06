#!/usr/bin/env python3
"""
Mirror blog posts from your Squarespace blog
Usage: python mirror_post.py <url> [custom-slug]
"""

from blog_backend.mirror_tool import BlogMirror
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mirror_post.py <url> [custom-slug]")
        print("Example: python mirror_post.py https://www.because-security.com/blog/your-post")
        sys.exit(1)
    
    url = sys.argv[1]
    custom_slug = sys.argv[2] if len(sys.argv) > 2 else None
    
    mirror = BlogMirror()
    try:
        path = mirror.mirror_post(url, custom_slug)
        print(f"✓ Successfully mirrored post to: {path}")
    except Exception as e:
        print(f"✗ Error mirroring post: {e}")
        sys.exit(1)