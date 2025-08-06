import os
import re
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Optional
import frontmatter
from bs4 import BeautifulSoup
import html2text


class BlogMirror:
    def __init__(self, posts_dir: str = "posts"):
        self.posts_dir = Path(posts_dir)
        self.posts_dir.mkdir(exist_ok=True)
        self.h2t = html2text.HTML2Text()
        self.h2t.body_width = 0  # Don't wrap lines
        self.h2t.protect_links = True
        self.h2t.wrap_lists = True
        
    def calculate_reading_time(self, text: str) -> int:
        """Calculate reading time in minutes based on ~200 words per minute"""
        words = len(text.split())
        return max(1, round(words / 200))
    
    def download_image(self, img_url: str, post_slug: str) -> str:
        """Download image and return local path"""
        assets_dir = self.posts_dir / f"{post_slug}_assets"
        assets_dir.mkdir(exist_ok=True)
        
        # Parse image filename
        parsed = urlparse(img_url)
        img_name = os.path.basename(parsed.path)
        if not img_name:
            img_name = f"image_{hash(img_url)}.jpg"
        
        local_path = assets_dir / img_name
        
        # Download image
        try:
            response = requests.get(img_url, timeout=30)
            response.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return f"{post_slug}_assets/{img_name}"
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")
            return img_url
    
    def extract_squarespace_post(self, url: str) -> Dict:
        """Extract blog post from Squarespace"""
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract metadata
        title = soup.find('h1', class_='blog-title') or soup.find('h1')
        title_text = title.get_text(strip=True) if title else "Untitled"
        
        # Author
        author_elem = soup.find('span', class_='blog-author-name') or soup.find('a', class_='blog-author-name')
        author = author_elem.get_text(strip=True) if author_elem else "Unknown"
        
        # Date
        date_elem = soup.find('time', class_='blog-date') or soup.find('span', class_='blog-date')
        if date_elem:
            date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)
            try:
                # Parse various date formats
                for fmt in ['%Y-%m-%d', '%B %d, %Y', '%b %d, %Y', '%b %d']:
                    try:
                        if 'Dec 28' in date_str:
                            date_str = f"Dec 28, {datetime.now().year}"
                        date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    date = datetime.now()
            except:
                date = datetime.now()
        else:
            date = datetime.now()
        
        # Tags/Categories
        tags = []
        tag_elements = soup.find_all('a', class_='blog-tag') or soup.find_all('span', class_='blog-meta-item--tag')
        for tag in tag_elements:
            tag_text = tag.get_text(strip=True).replace('#', '')
            if tag_text:
                tags.append(tag_text)
        
        # Content
        content_elem = soup.find('div', class_='blog-item-content') or soup.find('article') or soup.find('div', class_='content')
        
        return {
            'title': title_text,
            'author': author,
            'date': date,
            'tags': tags,
            'content_html': str(content_elem) if content_elem else "",
            'url': url
        }
    
    def mirror_post(self, url: str, custom_slug: Optional[str] = None) -> str:
        """Mirror a blog post from URL"""
        print(f"Mirroring post from: {url}")
        
        # Extract post data
        post_data = self.extract_squarespace_post(url)
        
        # Generate slug
        if custom_slug:
            slug = custom_slug
        else:
            slug = re.sub(r'[^\w\s-]', '', post_data['title'].lower())
            slug = re.sub(r'[-\s]+', '-', slug)
            slug = slug[:60]  # Limit length
        
        # Parse HTML content
        soup = BeautifulSoup(post_data['content_html'], 'html.parser')
        
        # Download images
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src')
            if img_url:
                # Make absolute URL
                img_url = urljoin(url, img_url)
                local_path = self.download_image(img_url, slug)
                # Update image src to local path
                img['src'] = f"/{local_path}"
        
        # Convert to markdown
        markdown_content = self.h2t.handle(str(soup))
        
        # Clean up markdown
        markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
        
        # Calculate reading time
        reading_time = self.calculate_reading_time(markdown_content)
        
        # Create frontmatter
        post = frontmatter.Post(markdown_content)
        post['title'] = post_data['title']
        post['author'] = post_data['author']
        post['date'] = post_data['date'].isoformat()
        post['tags'] = post_data['tags']
        post['reading_time'] = reading_time
        post['original_url'] = url
        
        # Save post
        post_path = self.posts_dir / f"{slug}.md"
        with open(post_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
        
        print(f"Saved post to: {post_path}")
        return str(post_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mirror_tool.py <url> [custom-slug]")
        sys.exit(1)
    
    url = sys.argv[1]
    custom_slug = sys.argv[2] if len(sys.argv) > 2 else None
    
    mirror = BlogMirror()
    mirror.mirror_post(url, custom_slug)