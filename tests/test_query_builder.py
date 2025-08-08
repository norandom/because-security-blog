"""
Unit tests for query builder functionality
"""
import pytest
from datetime import datetime, timezone
from typing import List

from blog_backend.models import BlogPost, TenantType
from blog_backend.query_builder import (
    PostQuery, QueryBuilder, SortField, SortOrder, 
    create_post_query
)


@pytest.fixture
def sample_posts() -> List[BlogPost]:
    """Create sample posts for testing"""
    posts = [
        BlogPost(
            slug="post-1",
            title="First Post",
            content="Content of first post",
            excerpt="First excerpt",
            tags=["tag1", "tag2"],
            date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            author="Author 1",
            tenant="infosec",
            sticky=True,
            metadata={},
            attachments=[],
            reading_time=5
        ),
        BlogPost(
            slug="post-2", 
            title="Second Post",
            content="Content of second post",
            excerpt="Second excerpt",
            tags=["tag2", "tag3"],
            date=datetime(2025, 1, 2, tzinfo=timezone.utc),
            author="Author 2",
            tenant="quant",
            sticky=False,
            metadata={},
            attachments=[],
            reading_time=3
        ),
        BlogPost(
            slug="post-3",
            title="Third Post", 
            content="Content of third post with tag1",
            excerpt="Third excerpt",
            tags=["tag1"],
            date=datetime(2025, 1, 3, tzinfo=timezone.utc),
            author="Author 1",
            tenant="infosec",
            sticky=False,
            metadata={},
            attachments=[],
            reading_time=7
        )
    ]
    return posts


def test_query_builder_filter_by_tenant(sample_posts):
    """Test filtering by tenant"""
    result = (create_post_query(sample_posts)
              .filter_by_tenant("infosec")
              .execute())
    
    assert len(result) == 2
    assert all(post.tenant == "infosec" for post in result)


def test_query_builder_filter_by_tag(sample_posts):
    """Test filtering by tag"""
    result = (create_post_query(sample_posts)
              .filter_by_tag("tag1")
              .execute())
    
    assert len(result) == 2
    assert all("tag1" in post.tags for post in result)


def test_query_builder_filter_by_author(sample_posts):
    """Test filtering by author"""
    result = (create_post_query(sample_posts)
              .filter_by_author("Author 1")
              .execute())
    
    assert len(result) == 2
    assert all(post.author == "Author 1" for post in result)


def test_query_builder_sort_by_date_desc(sample_posts):
    """Test sorting by date descending"""
    result = (create_post_query(sample_posts)
              .sort_by(SortField.DATE, SortOrder.DESC, enable_sticky=False)
              .execute())
    
    # Should be in reverse chronological order
    assert result[0].slug == "post-3"
    assert result[1].slug == "post-2" 
    assert result[2].slug == "post-1"


def test_query_builder_sort_by_title_asc(sample_posts):
    """Test sorting by title ascending"""
    result = (create_post_query(sample_posts)
              .sort_by(SortField.TITLE, SortOrder.ASC, enable_sticky=False)
              .execute())
    
    # Should be in alphabetical order
    assert result[0].title == "First Post"
    assert result[1].title == "Second Post"
    assert result[2].title == "Third Post"


def test_query_builder_sticky_sorting(sample_posts):
    """Test sticky post sorting"""
    result = (create_post_query(sample_posts)
              .sort_by(SortField.DATE, SortOrder.DESC, enable_sticky=True)
              .execute())
    
    # Sticky posts should come first
    assert result[0].sticky is True
    assert result[0].slug == "post-1"
    
    # Then regular posts in date order
    assert result[1].sticky is False
    assert result[2].sticky is False


def test_query_builder_pagination(sample_posts):
    """Test pagination"""
    result = (create_post_query(sample_posts)
              .paginate(offset=1, limit=1)
              .execute())
    
    assert len(result) == 1


def test_query_builder_chaining(sample_posts):
    """Test chaining multiple operations"""
    result = (create_post_query(sample_posts)
              .filter_by_tenant("infosec")
              .filter_by_tag("tag1")
              .sort_by(SortField.DATE, SortOrder.DESC)
              .paginate(offset=0, limit=1)
              .execute())
    
    assert len(result) == 1
    assert result[0].tenant == "infosec"
    assert "tag1" in result[0].tags


def test_query_builder_for_tenant(sample_posts):
    """Test QueryBuilder.for_tenant helper"""
    result = QueryBuilder.for_tenant(
        posts=sample_posts,
        tenant="quant",
        sort_field=SortField.DATE,
        sort_order=SortOrder.DESC,
        enable_sticky=False,
        limit=10
    )
    
    assert len(result) == 1
    assert result[0].tenant == "quant"


def test_query_builder_for_all_tenants(sample_posts):
    """Test QueryBuilder.for_all_tenants helper"""
    result = QueryBuilder.for_all_tenants(
        posts=sample_posts,
        tag="tag2",
        sort_field=SortField.DATE,
        sort_order=SortOrder.DESC,
        enable_sticky=False
    )
    
    assert len(result) == 2
    assert all("tag2" in post.tags for post in result)


def test_query_builder_search(sample_posts):
    """Test QueryBuilder.search helper"""
    result = QueryBuilder.search(
        posts=sample_posts,
        search_query="first",
        limit=10
    )
    
    assert len(result) == 1
    assert "first" in result[0].title.lower()


if __name__ == "__main__":
    pytest.main([__file__])