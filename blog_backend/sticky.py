"""
Sticky posts functionality - posts that appear at the top of lists
"""
from typing import List, Optional
from .models import BlogPost, BlogPostSummary


def apply_sticky_sorting(
    posts: List[BlogPost], 
    enable_sticky: bool = True,
    min_posts_for_sticky: int = 3
) -> List[BlogPost]:
    """
    Sort posts with sticky posts at the top if enabled and sufficient posts
    
    Args:
        posts: List of blog posts to sort
        enable_sticky: Whether to apply sticky sorting
        min_posts_for_sticky: Minimum number of posts required to apply sticky sorting
        
    Returns:
        Sorted list with sticky posts at top (if conditions met)
    """
    if not enable_sticky or len(posts) < min_posts_for_sticky:
        return posts
    
    # Separate sticky and non-sticky posts
    sticky_posts = [post for post in posts if post.sticky]
    regular_posts = [post for post in posts if not post.sticky]
    
    # Sort each group by date (most recent first)
    sticky_posts.sort(key=lambda p: p.date, reverse=True)
    regular_posts.sort(key=lambda p: p.date, reverse=True)
    
    # Combine: sticky first, then regular
    return sticky_posts + regular_posts


def apply_sticky_sorting_summaries(
    summaries: List[BlogPostSummary], 
    enable_sticky: bool = True,
    min_posts_for_sticky: int = 3
) -> List[BlogPostSummary]:
    """
    Sort post summaries with sticky posts at the top if enabled and sufficient posts
    
    Args:
        summaries: List of blog post summaries to sort
        enable_sticky: Whether to apply sticky sorting
        min_posts_for_sticky: Minimum number of posts required to apply sticky sorting
        
    Returns:
        Sorted list with sticky summaries at top (if conditions met)
    """
    if not enable_sticky or len(summaries) < min_posts_for_sticky:
        return summaries
    
    # Separate sticky and non-sticky summaries
    sticky_summaries = [summary for summary in summaries if summary.sticky]
    regular_summaries = [summary for summary in summaries if not summary.sticky]
    
    # Sort each group by date (most recent first)
    sticky_summaries.sort(key=lambda p: p.date, reverse=True)
    regular_summaries.sort(key=lambda p: p.date, reverse=True)
    
    # Combine: sticky first, then regular
    return sticky_summaries + regular_summaries


def posts_to_summaries_with_sticky(
    posts: List[BlogPost], 
    enable_sticky: bool = True,
    min_posts_for_sticky: int = 3
) -> List[BlogPostSummary]:
    """
    Convert posts to summaries and apply sticky sorting
    
    Args:
        posts: List of blog posts
        enable_sticky: Whether to apply sticky sorting
        min_posts_for_sticky: Minimum number of posts required to apply sticky sorting
        
    Returns:
        List of post summaries with sticky sorting applied
    """
    summaries = [
        BlogPostSummary(
            slug=post.slug,
            title=post.title,
            excerpt=post.excerpt,
            tags=post.tags,
            date=post.date,
            author=post.author,
            tenant=post.tenant,
            sticky=post.sticky,
            reading_time=post.reading_time
        )
        for post in posts
    ]
    
    return apply_sticky_sorting_summaries(summaries, enable_sticky, min_posts_for_sticky)


def create_sticky_aware_sorter(enable_sticky: bool = True, min_posts_for_sticky: int = 3):
    """
    Create a sorting function that respects sticky posts
    
    Args:
        enable_sticky: Whether to apply sticky sorting
        min_posts_for_sticky: Minimum number of posts required to apply sticky sorting
        
    Returns:
        Function that sorts posts with sticky awareness
    """
    def sort_with_sticky(posts: List[BlogPost]) -> List[BlogPost]:
        return apply_sticky_sorting(posts, enable_sticky, min_posts_for_sticky)
    
    return sort_with_sticky