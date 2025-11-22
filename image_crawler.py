#!/usr/bin/env python3
"""
Simple Web Image Crawler

Crawls a website and downloads all images found.
Includes basic rate limiting and respectful crawling practices.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

try:
    import requests
    from bs4 import BeautifulSoup
    try:
        from PIL import Image
        PIL_AVAILABLE = True
    except ImportError:
        PIL_AVAILABLE = False
except ImportError:
    print("Error: Required packages not installed.")
    print("Install with: pip install requests beautifulsoup4 pillow")
    sys.exit(1)


class ImageCrawler:
    def __init__(
        self,
        base_url: str,
        output_dir: str = "downloaded_images",
        delay: float = 1.0,
        min_size_kb: int = 10,
        min_dimensions: tuple[int, int] = (100, 100),
        no_duplicates: bool = False,
    ):
        """
        Initialize the image crawler.

        Args:
            base_url: Starting URL to crawl
            output_dir: Directory to save images
            delay: Delay between requests in seconds (be respectful!)
            min_size_kb: Minimum file size in KB (default: 10KB)
            min_dimensions: Minimum (width, height) in pixels (default: 100x100)
            no_duplicates: Skip duplicate images in current session
        """
        self.base_url = base_url.rstrip("/")
        self.parsed_base = urlparse(self.base_url)
        self.output_dir = Path(output_dir)
        self.delay = delay
        self.min_size_kb = min_size_kb
        self.min_dimensions = min_dimensions
        self.no_duplicates = no_duplicates
        self.visited_urls = set()
        self.downloaded_images = []
        self.failed_images = []
        self.seen_image_hashes = set()  # For duplicate detection
        self.skip_stats = {
            "webp": 0,
            "too_small_size": 0,
            "too_small_dimensions": 0,
            "duplicate": 0,
            "already_exists": 0,
        }
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Check robots.txt
        self.robots_parser = self._check_robots()

    def _check_robots(self) -> RobotFileParser:
        """Check and parse robots.txt if available."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        rp = RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
            print(f"✓ Checked robots.txt: {'Allowed' if rp.can_fetch('*', self.base_url) else 'Restricted'}")
        except Exception as e:
            print(f"⚠ Could not read robots.txt: {e}")
        return rp

    def _is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        try:
            return self.robots_parser.can_fetch("*", url)
        except:
            return True  # If robots.txt check fails, proceed (but be careful!)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL (remove fragments, normalize path)."""
        parsed = urlparse(url)
        # Remove fragment and normalize
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/") or "/",
            parsed.params,
            parsed.query,
            ""  # Remove fragment
        ))
        return normalized

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL is from the same domain."""
        parsed = urlparse(url)
        return parsed.netloc == self.parsed_base.netloc or parsed.netloc == ""

    def _get_page(self, url: str) -> requests.Response | None:
        """Fetch a page with error handling."""
        if url in self.visited_urls:
            return None

        if not self._is_allowed(url):
            print(f"⚠ Skipping {url} (robots.txt disallowed)")
            return None

        try:
            time.sleep(self.delay)  # Rate limiting
            response = self.session.get(url, timeout=10, allow_redirects=True)
            response.raise_for_status()
            self.visited_urls.add(url)
            return response
        except requests.RequestException as e:
            print(f"✗ Error fetching {url}: {e}")
            return None

    def _find_images(self, html: str, page_url: str) -> list[str]:
        """Extract all image URLs from HTML (excluding webp)."""
        soup = BeautifulSoup(html, "html.parser")
        image_urls = []

        # Find <img> tags
        for img in soup.find_all("img", src=True):
            src = img.get("src")
            if src:
                # Skip webp
                if src.lower().endswith(".webp") or ".webp" in src.lower():
                    continue
                absolute_url = urljoin(page_url, src)
                image_urls.append(absolute_url)

        # Find <picture> sources
        for picture in soup.find_all("picture"):
            for source in picture.find_all("source", srcset=True):
                srcset = source.get("srcset")
                if srcset:
                    # Parse srcset (can have multiple URLs with descriptors)
                    for item in srcset.split(","):
                        url_part = item.strip().split()[0]
                        # Skip webp
                        if url_part.lower().endswith(".webp") or ".webp" in url_part.lower():
                            continue
                        absolute_url = urljoin(page_url, url_part)
                        image_urls.append(absolute_url)

        # Find CSS background images (basic regex)
        css_bg_pattern = r'url\(["\']?([^"\'()]+)["\']?\)'
        for match in re.finditer(css_bg_pattern, html):
            url = match.group(1)
            # Skip webp
            if url.lower().endswith(".webp") or ".webp" in url.lower():
                continue
            if any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg"]):
                absolute_url = urljoin(page_url, url)
                image_urls.append(absolute_url)

        # Deduplicate
        return list(set(image_urls))

    def _find_links(self, html: str, page_url: str) -> list[str]:
        """Extract all links from HTML for further crawling."""
        soup = BeautifulSoup(html, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            href = a.get("href")
            absolute_url = urljoin(page_url, href)
            normalized = self._normalize_url(absolute_url)

            # Only crawl same domain
            if self._is_same_domain(normalized):
                links.append(normalized)

        return list(set(links))

    def _get_image_hash(self, filepath: Path) -> str:
        """Get a simple hash of image file for duplicate detection."""
        import hashlib
        try:
            with open(filepath, "rb") as f:
                # Read first 64KB for hash (faster than full file)
                data = f.read(65536)
                return hashlib.md5(data).hexdigest()
        except:
            return ""

    def _check_image_dimensions(self, filepath: Path) -> tuple[int, int] | None:
        """Get image dimensions. Returns (width, height) or None if can't read."""
        if not PIL_AVAILABLE:
            return None
        try:
            with Image.open(filepath) as img:
                return img.size  # (width, height)
        except:
            return None

    def _download_image(self, image_url: str) -> bool:
        """Download a single image with filtering."""
        try:
            # Get filename from URL
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path)

            # Skip webp files
            if filename.lower().endswith(".webp") or ".webp" in image_url.lower():
                self.skip_stats["webp"] += 1
                return False

            # If no filename, generate one
            if not filename or "." not in filename:
                ext = ".jpg"  # default
                # Try to get extension from Content-Type
                try:
                    head = self.session.head(image_url, timeout=5)
                    content_type = head.headers.get("Content-Type", "")
                    if "webp" in content_type:
                        self.skip_stats["webp"] += 1
                        return False
                    if "png" in content_type:
                        ext = ".png"
                    elif "gif" in content_type:
                        ext = ".gif"
                except:
                    pass
                filename = f"image_{len(self.downloaded_images)}{ext}"

            # Sanitize filename
            filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
            filepath = self.output_dir / filename

            # Skip if already exists
            if filepath.exists():
                self.skip_stats["already_exists"] += 1
                return True

            # Download
            time.sleep(self.delay)
            response = self.session.get(image_url, timeout=10, stream=True)
            response.raise_for_status()

            # Save to temp location first to check size/dimensions
            temp_filepath = filepath.with_suffix(filepath.suffix + ".tmp")
            with open(temp_filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Check file size
            size_kb = temp_filepath.stat().st_size / 1024
            if size_kb < self.min_size_kb:
                temp_filepath.unlink()
                self.skip_stats["too_small_size"] += 1
                return False

            # Check dimensions if PIL available
            if PIL_AVAILABLE:
                dimensions = self._check_image_dimensions(temp_filepath)
                if dimensions:
                    width, height = dimensions
                    min_w, min_h = self.min_dimensions
                    if width < min_w or height < min_h:
                        temp_filepath.unlink()
                        self.skip_stats["too_small_dimensions"] += 1
                        return False

            # Check for duplicates if enabled
            if self.no_duplicates:
                img_hash = self._get_image_hash(temp_filepath)
                if img_hash and img_hash in self.seen_image_hashes:
                    temp_filepath.unlink()
                    self.skip_stats["duplicate"] += 1
                    return False
                self.seen_image_hashes.add(img_hash)

            # Move temp file to final location
            temp_filepath.rename(filepath)

            self.downloaded_images.append(image_url)
            return True

        except Exception as e:
            # Clean up temp file if it exists
            try:
                if 'temp_filepath' in locals() and temp_filepath.exists():
                    temp_filepath.unlink()
            except:
                pass
            self.failed_images.append(image_url)
            return False

    def crawl(self, max_pages: int = 10, max_depth: int = 2):
        """
        Start crawling the website.

        Args:
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth to crawl (0 = only start page)
        """
        print(f"\n🕷️  Starting crawl of: {self.base_url}")
        print(f"📁 Output directory: {self.output_dir}")
        print(f"⏱️  Delay between requests: {self.delay}s")
        print(f"📏 Min size: {self.min_size_kb}KB | Min dimensions: {self.min_dimensions[0]}x{self.min_dimensions[1]}px")
        print(f"🚫 Filters: WebP ignored | Duplicates: {'ON' if self.no_duplicates else 'OFF'}\n")

        to_visit = [(self.base_url, 0)]  # (url, depth)

        while to_visit and len(self.visited_urls) < max_pages:
            current_url, depth = to_visit.pop(0)

            if depth > max_depth:
                continue

            print(f"📄 [{depth}] {current_url}")
            response = self._get_page(current_url)
            if not response:
                continue

            # Extract and download images
            image_urls = self._find_images(response.text, current_url)
            found_count = len(image_urls)

            for img_url in image_urls:
                # Only download images from same domain or absolute URLs
                if self._is_same_domain(img_url) or img_url.startswith("http"):
                    self._download_image(img_url)

            # Show progress in table format
            downloaded = len(self.downloaded_images)
            skipped = sum(self.skip_stats.values())
            print(f"   Found: {found_count} | Downloaded: {downloaded} | Skipped: {skipped}")

            # Find links for further crawling
            if depth < max_depth:
                links = self._find_links(response.text, current_url)
                for link in links:
                    if link not in self.visited_urls and (link, depth + 1) not in to_visit:
                        to_visit.append((link, depth + 1))

        # Summary table
        print(f"\n{'='*70}")
        print(f"{'✅ CRAWL SUMMARY':^70}")
        print(f"{'='*70}")
        
        # Create table rows
        rows = [
            ("Pages visited", f"{len(self.visited_urls)}"),
            ("Images downloaded", f"{len(self.downloaded_images)}"),
            ("Failed downloads", f"{len(self.failed_images)}"),
        ]
        
        # Add skip stats if any
        if sum(self.skip_stats.values()) > 0:
            rows.append(("", ""))  # Separator
            rows.append(("Skipped (reasons):", ""))
            if self.skip_stats["webp"] > 0:
                rows.append(("  • WebP files", f"{self.skip_stats['webp']}"))
            if self.skip_stats["too_small_size"] > 0:
                rows.append(("  • Too small (size)", f"{self.skip_stats['too_small_size']}"))
            if self.skip_stats["too_small_dimensions"] > 0:
                rows.append(("  • Too small (dimensions)", f"{self.skip_stats['too_small_dimensions']}"))
            if self.skip_stats["duplicate"] > 0:
                rows.append(("  • Duplicates", f"{self.skip_stats['duplicate']}"))
            if self.skip_stats["already_exists"] > 0:
                rows.append(("  • Already exists", f"{self.skip_stats['already_exists']}"))
        
        # Print table
        max_label = max(len(row[0]) for row in rows if row[0])
        for label, value in rows:
            if label == "":
                print()
            else:
                print(f"  {label:<{max_label}}  {value:>10}")
        
        print(f"{'='*70}")
        print(f"📁 Output: {self.output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description="Crawl a website and download all images found.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python image_crawler.py https://example.com
  python image_crawler.py https://example.com --output my_images --delay 2.0
  python image_crawler.py https://example.com --max-pages 5 --max-depth 1

⚠️  WARNING: Always check website's Terms of Service and robots.txt before crawling!
        """
    )
    parser.add_argument("url", help="Starting URL to crawl")
    parser.add_argument(
        "--output", "-o",
        default="downloaded_images",
        help="Output directory for images (default: downloaded_images)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=10,
        help="Maximum number of pages to crawl (default: 10)"
    )
    parser.add_argument(
        "--max-depth", "-m",
        type=int,
        default=2,
        help="Maximum crawl depth (default: 2)"
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=10,
        help="Minimum file size in KB (default: 10)"
    )
    parser.add_argument(
        "--min-width",
        type=int,
        default=100,
        help="Minimum image width in pixels (default: 100)"
    )
    parser.add_argument(
        "--min-height",
        type=int,
        default=100,
        help="Minimum image height in pixels (default: 100)"
    )
    parser.add_argument(
        "--no-duplicates",
        action="store_true",
        help="Skip duplicate images in current session (checks image content)"
    )

    args = parser.parse_args()

    # Validate URL
    if not args.url.startswith(("http://", "https://")):
        print("Error: URL must start with http:// or https://")
        sys.exit(1)

    crawler = ImageCrawler(
        args.url,
        args.output,
        args.delay,
        min_size_kb=args.min_size,
        min_dimensions=(args.min_width, args.min_height),
        no_duplicates=args.no_duplicates,
    )
    crawler.crawl(args.max_pages, args.max_depth)


if __name__ == "__main__":
    main()

