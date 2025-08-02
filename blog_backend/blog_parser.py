import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import frontmatter
import markdown
from .models import BlogPost, BlogPostSummary


class BlogParser:
    def __init__(self, posts_directory: str = "posts"):
        self.posts_directory = Path(posts_directory)
        self.posts_cache: Dict[str, BlogPost] = {}
        self.last_scan_time: Optional[datetime] = None
        
    def _get_slug_from_filename(self, filename: str) -> str:
        return Path(filename).stem
    
    def _extract_excerpt(self, content: str, max_length: int = 200) -> str:
        plain_text = re.sub(r'<[^>]+>', '', markdown.markdown(content))
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if len(plain_text) <= max_length:
            return plain_text
        return plain_text[:max_length].rsplit(' ', 1)[0] + '...'
    
    def _find_attachments(self, post_path: Path) -> List[str]:
        attachments = []
        post_dir = post_path.parent
        post_stem = post_path.stem
        
        # Look for files with same name but different extensions
        for file_path in post_dir.glob(f"{post_stem}.*"):
            if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.zip']:
                attachments.append(str(file_path.relative_to(self.posts_directory)))
        
        # Look for assets folder
        assets_dir = post_dir / f"{post_stem}_assets"
        if assets_dir.exists():
            for file_path in assets_dir.rglob("*"):
                if file_path.is_file():
                    attachments.append(str(file_path.relative_to(self.posts_directory)))
        
        return attachments
    
    def _parse_post(self, file_path: Path) -> BlogPost:
        with open(file_path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)
        
        slug = self._get_slug_from_filename(file_path.name)
        title = post.metadata.get('title', slug.replace('-', ' ').title())
        
        # Parse date
        date_str = post.metadata.get('date')
        if isinstance(date_str, str):
            try:
                date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                date = datetime.fromtimestamp(file_path.stat().st_mtime)
        elif isinstance(date_str, datetime):
            date = date_str
        else:
            date = datetime.fromtimestamp(file_path.stat().st_mtime)
        
        # Extract tags
        tags = post.metadata.get('tags', [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(',')]
        
        content = post.content
        excerpt = post.metadata.get('excerpt') or self._extract_excerpt(content)
        attachments = self._find_attachments(file_path)
        
        return BlogPost(
            slug=slug,
            title=title,
            content=content,
            excerpt=excerpt,
            tags=tags,
            date=date,
            author=post.metadata.get('author'),
            metadata=post.metadata,
            attachments=attachments
        )
    
    def scan_posts(self, force_refresh: bool = False) -> None:
        if not self.posts_directory.exists():
            return
        
        current_time = datetime.now()
        
        # Check if we need to refresh
        if not force_refresh and self.last_scan_time:
            # Only scan if directory was modified since last scan
            dir_mtime = datetime.fromtimestamp(self.posts_directory.stat().st_mtime)
            if dir_mtime <= self.last_scan_time:
                return
        
        # Clear cache if forcing refresh
        if force_refresh:
            self.posts_cache.clear()
        
        # Scan for markdown files
        for md_file in self.posts_directory.rglob("*.md"):
            slug = self._get_slug_from_filename(md_file.name)
            file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
            
            # Skip if cached and not modified
            if slug in self.posts_cache and not force_refresh:
                cached_post = self.posts_cache[slug]
                if file_mtime <= self.last_scan_time:
                    continue
            
            try:
                post = self._parse_post(md_file)
                self.posts_cache[slug] = post
            except Exception as e:
                print(f"Error parsing {md_file}: {e}")
                continue
        
        self.last_scan_time = current_time
    
    def get_all_posts(self) -> List[BlogPost]:
        self.scan_posts()
        return list(self.posts_cache.values())
    
    def get_post(self, slug: str) -> Optional[BlogPost]:
        self.scan_posts()
        return self.posts_cache.get(slug)
    
    def get_post_summaries(self) -> List[BlogPostSummary]:
        posts = self.get_all_posts()
        return [
            BlogPostSummary(
                slug=post.slug,
                title=post.title,
                excerpt=post.excerpt,
                tags=post.tags,
                date=post.date,
                author=post.author
            )
            for post in posts
        ]
    
    def search_posts(self, query: str) -> List[BlogPost]:
        posts = self.get_all_posts()
        query_lower = query.lower()
        
        results = []
        for post in posts:
            # Search in title, content, tags, and author
            if (query_lower in post.title.lower() or
                query_lower in post.content.lower() or
                any(query_lower in tag.lower() for tag in post.tags) or
                (post.author and query_lower in post.author.lower())):
                results.append(post)
        
        return results