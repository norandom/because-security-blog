"""
Functional blog parser with concurrency support for Nuitka compilation
"""
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import frontmatter
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import re

from .models import BlogPost, BlogPostSummary, TenantType
from .functional_types import (
    Result, Success, Failure, ParseError,
    map_result, flat_map, pipe, compose,
    safe_parse_date, safe_parse_tags, calculate_reading_time_pure, create_excerpt_pure,
    filter_list, sort_list, map_list, take
)

# Pure functions for blog processing
def read_file_safe(file_path: Path) -> Result[str, ParseError]:
    """Safely read file contents"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return Success(content)
    except Exception as e:
        return Failure(ParseError(f"Failed to read file {file_path}", file_path, e))

def parse_frontmatter_safe(content: str) -> Result[frontmatter.Post, ParseError]:
    """Safely parse frontmatter from content"""
    try:
        post = frontmatter.loads(content)
        return Success(post)
    except Exception as e:
        return Failure(ParseError(f"Failed to parse frontmatter", exception=e))

def find_attachments_pure(post_path: Path, posts_directory: Path) -> List[str]:
    """Pure function to find post attachments"""
    attachments = []
    post_dir = post_path.parent
    post_stem = post_path.stem
    
    # Look for files with same name but different extensions
    for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.zip', '.webp']:
        attachment_path = post_dir / f"{post_stem}{ext}"
        if attachment_path.exists():
            rel_path = attachment_path.relative_to(posts_directory)
            attachments.append(str(rel_path))
    
    # Look for assets folder
    assets_dir = post_dir / f"{post_stem}_assets"
    if assets_dir.exists():
        for file_path in assets_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(posts_directory)
                attachments.append(str(rel_path))
    
    return attachments

def create_blog_post_pure(
    frontmatter_post: frontmatter.Post,
    slug: str,
    file_path: Path,
    posts_directory: Path
) -> Result[BlogPost, ParseError]:
    """Pure function to create BlogPost from frontmatter"""
    try:
        metadata = frontmatter_post.metadata
        content = frontmatter_post.content
        
        # Extract and validate data
        title = metadata.get('title', slug.replace('-', ' ').title())
        tags = safe_parse_tags(metadata.get('tags', []))
        author = metadata.get('author')
        tenant = metadata.get('tenant', 'shared')
        
        # Validate tenant
        if tenant not in ['infosec', 'quant', 'shared']:
            tenant = 'shared'
        
        # Parse date
        date_result = safe_parse_date(metadata.get('date'))
        if date_result.is_failure():
            # Fallback to file modification time
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            date_result = safe_parse_date(file_mtime)
        
        match date_result:
            case Success(date):
                pass
            case Failure(error):
                return Failure(error)
        
        # Generate excerpt and reading time
        excerpt = metadata.get('excerpt') or create_excerpt_pure(content)
        reading_time = metadata.get('reading_time') or calculate_reading_time_pure(content)
        
        # Find attachments
        attachments = find_attachments_pure(file_path, posts_directory)
        
        blog_post = BlogPost(
            slug=slug,
            title=title,
            content=content,
            excerpt=excerpt,
            tags=tags,
            date=date,
            author=author,
            tenant=tenant,
            metadata=metadata,
            attachments=attachments,
            reading_time=reading_time
        )
        
        return Success(blog_post)
        
    except Exception as e:
        return Failure(ParseError(f"Failed to create blog post for {slug}", file_path, e))

# Functional pipeline for parsing a single post
def parse_single_post(file_path: Path, posts_directory: Path) -> Result[BlogPost, ParseError]:
    """Functional pipeline to parse a single blog post"""
    slug = file_path.stem
    
    # Read file content
    content_result = read_file_safe(file_path)
    
    # Parse frontmatter
    frontmatter_result = flat_map(lambda content: parse_frontmatter_safe(content))(content_result)
    
    # Create blog post
    blog_post_result = flat_map(lambda fm_post: create_blog_post_pure(fm_post, slug, file_path, posts_directory))(frontmatter_result)
    
    return blog_post_result

class FunctionalBlogParser:
    """Functional blog parser with concurrency support"""
    
    def __init__(self, posts_directory: str = "posts", max_workers: int = 4):
        self.posts_directory = Path(posts_directory)
        self.max_workers = max_workers
        self._posts_cache: Dict[str, BlogPost] = {}
        self._last_scan_time: Optional[datetime] = None
    
    async def scan_posts_concurrent(self, force_refresh: bool = False) -> Result[Dict[str, BlogPost], List[ParseError]]:
        """Concurrently scan and parse all blog posts"""
        if not self.posts_directory.exists():
            return Success({})
        
        current_time = datetime.now()
        
        # Check if refresh is needed
        if not force_refresh and self._last_scan_time:
            dir_mtime = datetime.fromtimestamp(self.posts_directory.stat().st_mtime)
            if dir_mtime <= self._last_scan_time:
                return Success(self._posts_cache)
        
        # Find all markdown files
        md_files = list(self.posts_directory.rglob("*.md"))
        
        if not md_files:
            return Success({})
        
        # Create parsing functions for concurrent execution
        def create_parser(file_path: Path) -> Callable[[], Result[BlogPost, ParseError]]:
            return lambda: parse_single_post(file_path, self.posts_directory)
        
        parsing_functions = [create_parser(path) for path in md_files]
        
        # Execute parsing concurrently
        async def parse_concurrent() -> List[Result[BlogPost, ParseError]]:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                loop = asyncio.get_event_loop()
                tasks = [
                    loop.run_in_executor(executor, parser)
                    for parser in parsing_functions
                ]
                return await asyncio.gather(*tasks)
        
        results = await parse_concurrent()
        
        # Separate successes and failures
        successes = {}
        failures = []
        
        for result in results:
            match result:
                case Success(blog_post):
                    successes[blog_post.slug] = blog_post
                case Failure(error):
                    failures.append(error)
        
        # Update cache and timestamp
        if force_refresh:
            self._posts_cache = successes
        else:
            self._posts_cache.update(successes)
        
        self._last_scan_time = current_time
        
        return Success(self._posts_cache) if not failures else Failure(failures)
    
    async def get_all_posts(self) -> List[BlogPost]:
        """Get all posts using functional approach"""
        result = await self.scan_posts_concurrent()
        
        match result:
            case Success(posts_dict):
                return list(posts_dict.values())
            case Failure(errors):
                # Log errors but return what we can
                print(f"Warning: {len(errors)} posts failed to parse")
                return list(self._posts_cache.values())
    
    async def get_post(self, slug: str) -> Optional[BlogPost]:
        """Get a single post by slug"""
        await self.scan_posts_concurrent()
        return self._posts_cache.get(slug)
    
    async def get_post_summaries(self) -> List[BlogPostSummary]:
        """Get post summaries using functional transformations"""
        posts = await self.get_all_posts()
        
        # Functional transformation
        to_summary = lambda post: BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author,
            tenant=post.tenant,
            reading_time=post.reading_time
        )
        
        return compose(
            map_list(to_summary),
            sort_list(lambda p: p.date, reverse=True)
        )(posts)
    
    async def search_posts(self, query: str) -> List[BlogPost]:
        """Search posts using functional approach"""
        posts = await self.get_all_posts()
        query_lower = query.lower()
        
        # Functional search predicate
        matches_query = lambda post: (
            query_lower in post.title.lower() or
            query_lower in post.content.lower() or
            any(query_lower in tag.lower() for tag in post.tags) or
            (post.author and query_lower in post.author.lower())
        )
        
        # Relevance scorer (title matches score higher)
        def relevance_score(post: BlogPost) -> int:
            score = 0
            if query_lower in post.title.lower():
                score += 10
            if any(query_lower in tag.lower() for tag in post.tags):
                score += 5
            if post.author and query_lower in post.author.lower():
                score += 3
            if query_lower in post.content.lower():
                score += 1
            return score
        
        return compose(
            filter_list(matches_query),
            sort_list(relevance_score, reverse=True)
        )(posts)
    
    async def filter_by_tag(self, tag: str, limit: Optional[int] = None) -> List[BlogPost]:
        """Filter posts by tag using functional approach"""
        posts = await self.get_all_posts()
        
        pipeline_functions = [
            filter_list(lambda post: tag in post.tags),
            sort_list(lambda post: post.date, reverse=True)
        ]
        
        if limit:
            pipeline_functions.append(take(limit))
        
        return compose(*pipeline_functions)(posts)
    
    async def filter_by_author(self, author: str, limit: Optional[int] = None) -> List[BlogPost]:
        """Filter posts by author using functional approach"""
        posts = await self.get_all_posts()
        
        pipeline_functions = [
            filter_list(lambda post: post.author and post.author.lower() == author.lower()),
            sort_list(lambda post: post.date, reverse=True)
        ]
        
        if limit:
            pipeline_functions.append(take(limit))
        
        return compose(*pipeline_functions)(posts)
    
    async def filter_by_tenant(self, tenant: TenantType, limit: Optional[int] = None) -> List[BlogPost]:
        """Filter posts by tenant using functional approach"""
        posts = await self.get_all_posts()
        
        pipeline_functions = [
            filter_list(lambda post: post.tenant == tenant),
            sort_list(lambda post: post.date, reverse=True)
        ]
        
        if limit:
            pipeline_functions.append(take(limit))
        
        return compose(*pipeline_functions)(posts)
    
    async def get_recent_by_tenant(self, tenant: TenantType, limit: int = 5) -> List[BlogPostSummary]:
        """Get recent posts for a specific tenant"""
        posts = await self.filter_by_tenant(tenant, limit)
        
        to_summary = lambda post: BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author,
            tenant=post.tenant,
            reading_time=post.reading_time
        )
        
        return [to_summary(post) for post in posts]
    
    async def get_posts_with_transformations(
        self,
        filters: Optional[List[Callable[[List[BlogPost]], List[BlogPost]]]] = None,
        sort_key: Optional[Callable[[BlogPost], Any]] = None,
        reverse: bool = True,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[BlogPost]:
        """Get posts with functional transformations pipeline"""
        posts = await self.get_all_posts()
        
        # Build transformation pipeline
        transformations = []
        
        # Apply filters
        if filters:
            for filter_func in filters:
                transformations.append(filter_func)
        
        # Apply sorting
        if sort_key:
            transformations.append(sort_list(sort_key, reverse))
        
        # Apply pagination
        if offset > 0:
            transformations.append(lambda lst: lst[offset:])
        
        if limit:
            transformations.append(take(limit))
        
        return compose(*transformations)(posts) if transformations else posts