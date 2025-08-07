"""
Enhanced search functionality with in-memory indexing
"""
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import re
from pathlib import Path
import asyncio

from .models import BlogPost
from .functional_types import Result, Success, Failure

@dataclass
class SearchIndex:
    """In-memory search index for blog posts"""
    
    # Inverted indices
    title_index: Dict[str, Set[str]] = None  # word -> set of slugs
    content_index: Dict[str, Set[str]] = None
    tag_index: Dict[str, Set[str]] = None
    author_index: Dict[str, Set[str]] = None
    tenant_index: Dict[str, Set[str]] = None
    
    # Forward index for scoring
    post_data: Dict[str, Dict] = None  # slug -> post metadata
    
    def __post_init__(self):
        self.title_index = defaultdict(set)
        self.content_index = defaultdict(set)
        self.tag_index = defaultdict(set)
        self.author_index = defaultdict(set)
        self.tenant_index = defaultdict(set)
        self.post_data = {}

class SearchEngine:
    """Enhanced search engine with indexing and ranking"""
    
    def __init__(self):
        self.index = SearchIndex()
        self._lock = asyncio.Lock()
        self._stop_words = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for',
            'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on',
            'that', 'the', 'to', 'was', 'will', 'with', 'the'
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into searchable words"""
        # Convert to lowercase and split on non-alphanumeric
        words = re.findall(r'\b\w+\b', text.lower())
        # Remove stop words and short words
        return [w for w in words if w not in self._stop_words and len(w) > 2]
    
    def _get_ngrams(self, text: str, n: int = 3) -> List[str]:
        """Generate n-grams for fuzzy matching"""
        text = text.lower()
        return [text[i:i+n] for i in range(len(text) - n + 1)]
    
    async def index_post(self, post: BlogPost):
        """Index a single blog post"""
        async with self._lock:
            slug = post.slug
            
            # Store post metadata for scoring
            self.index.post_data[slug] = {
                'title': post.title,
                'date': post.date,
                'author': post.author,
                'tenant': post.tenant,
                'tags': post.tags,
                'excerpt': post.excerpt
            }
            
            # Index title
            title_tokens = self._tokenize(post.title)
            for token in title_tokens:
                self.index.title_index[token].add(slug)
            
            # Index content
            content_tokens = self._tokenize(post.content)
            for token in content_tokens[:1000]:  # Limit tokens per post
                self.index.content_index[token].add(slug)
            
            # Index tags
            for tag in post.tags:
                tag_lower = tag.lower()
                self.index.tag_index[tag_lower].add(slug)
            
            # Index author
            if post.author:
                author_lower = post.author.lower()
                self.index.author_index[author_lower].add(slug)
            
            # Index tenant
            self.index.tenant_index[post.tenant].add(slug)
    
    async def remove_post(self, slug: str):
        """Remove a post from the index"""
        async with self._lock:
            if slug not in self.index.post_data:
                return
            
            # Remove from all indices
            for index in [self.index.title_index, self.index.content_index,
                         self.index.tag_index, self.index.author_index,
                         self.index.tenant_index]:
                for key in list(index.keys()):
                    index[key].discard(slug)
                    if not index[key]:
                        del index[key]
            
            # Remove metadata
            del self.index.post_data[slug]
    
    async def search(
        self, 
        query: str,
        tenant: Optional[str] = None,
        limit: int = 20
    ) -> List[Tuple[str, float]]:
        """
        Search posts and return ranked results
        Returns list of (slug, score) tuples
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        
        async with self._lock:
            # Collect matching posts with scores
            post_scores: Dict[str, float] = defaultdict(float)
            
            # Title matches (highest weight)
            for token in query_tokens:
                for slug in self.index.title_index.get(token, set()):
                    post_scores[slug] += 10.0
            
            # Tag matches (high weight)
            query_lower = query.lower()
            for tag, slugs in self.index.tag_index.items():
                if query_lower in tag or tag in query_lower:
                    for slug in slugs:
                        post_scores[slug] += 5.0
            
            # Author matches (medium weight)
            for author, slugs in self.index.author_index.items():
                if query_lower in author:
                    for slug in slugs:
                        post_scores[slug] += 3.0
            
            # Content matches (lower weight)
            for token in query_tokens:
                for slug in self.index.content_index.get(token, set()):
                    post_scores[slug] += 1.0
            
            # Filter by tenant if specified
            if tenant:
                tenant_slugs = self.index.tenant_index.get(tenant, set())
                post_scores = {
                    slug: score for slug, score in post_scores.items()
                    if slug in tenant_slugs
                }
            
            # Boost recent posts slightly
            for slug, score in post_scores.items():
                post_data = self.index.post_data.get(slug, {})
                # Add recency boost (you could make this more sophisticated)
                post_scores[slug] = score
            
            # Sort by score and return top results
            results = sorted(
                post_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]
            
            return results
    
    async def suggest(self, prefix: str, limit: int = 5) -> List[str]:
        """Auto-suggest based on prefix matching"""
        prefix_lower = prefix.lower()
        suggestions = set()
        
        async with self._lock:
            # Check titles
            for slug, data in self.index.post_data.items():
                title_lower = data['title'].lower()
                if title_lower.startswith(prefix_lower):
                    suggestions.add(data['title'])
            
            # Check tags
            for tag in self.index.tag_index.keys():
                if tag.startswith(prefix_lower):
                    suggestions.add(tag)
        
        return sorted(list(suggestions))[:limit]
    
    async def get_related_posts(self, slug: str, limit: int = 5) -> List[str]:
        """Find related posts based on tags and content similarity"""
        async with self._lock:
            if slug not in self.index.post_data:
                return []
            
            post_data = self.index.post_data[slug]
            related_scores: Dict[str, float] = defaultdict(float)
            
            # Find posts with similar tags
            for tag in post_data.get('tags', []):
                tag_lower = tag.lower()
                for related_slug in self.index.tag_index.get(tag_lower, set()):
                    if related_slug != slug:
                        related_scores[related_slug] += 2.0
            
            # Find posts by same author
            if post_data.get('author'):
                author_lower = post_data['author'].lower()
                for related_slug in self.index.author_index.get(author_lower, set()):
                    if related_slug != slug:
                        related_scores[related_slug] += 1.0
            
            # Same tenant posts
            tenant = post_data.get('tenant', 'shared')
            for related_slug in self.index.tenant_index.get(tenant, set()):
                if related_slug != slug:
                    related_scores[related_slug] += 0.5
            
            # Sort by score and return top related
            results = sorted(
                related_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]
            
            return [slug for slug, _ in results]
    
    async def rebuild_index(self, posts: List[BlogPost]):
        """Rebuild the entire search index"""
        async with self._lock:
            # Clear existing index
            self.index = SearchIndex()
        
        # Re-index all posts
        for post in posts:
            await self.index_post(post)
    
    async def get_stats(self) -> Dict[str, int]:
        """Get search index statistics"""
        async with self._lock:
            return {
                'total_posts': len(self.index.post_data),
                'unique_title_words': len(self.index.title_index),
                'unique_content_words': len(self.index.content_index),
                'unique_tags': len(self.index.tag_index),
                'unique_authors': len(self.index.author_index),
                'tenants': len(self.index.tenant_index)
            }