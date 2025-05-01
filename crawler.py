import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib

class SiteCrawler:
    def __init__(self, base_url, max_pages=10000, delay=0.5):
        self.base_url   = base_url.rstrip('/')
        self.parsed_base = urlparse(self.base_url)
        self.visited    = set()
        self.to_visit   = [self.base_url]
        self.pages      = []    # will hold dicts
        self.images     = set()
        self.videos     = set()
        self.max_pages  = max_pages
        self.delay      = delay

    def is_internal(self, link):
        p = urlparse(link)
        return (p.netloc == "" or self.parsed_base.netloc in p.netloc)

    def normalize(self, link):
        # strip hashes, make absolute, strip trailing slash
        return urljoin(self.base_url, link.split('#')[0]).rstrip('/')

    def crawl(self):
        results = []

        while self.to_visit and len(results) < self.max_pages:
            url = self.to_visit.pop(0)
            if url in self.visited:
                continue
            self.visited.add(url)

            try:
                # no auto-redirects so we can catch 301/302
                r = requests.get(url, timeout=10, allow_redirects=False)
                code = r.status_code

                # 404 → record broken, skip indexing
                if code == 404:
                    results.append({
                        "loc": url,
                        "status": 404,
                        "lastmod": None,
                        "redirect_to": None
                    })
                    continue

                # redirects → enqueue target, record original as redirect
                if 300 <= code < 400 and "Location" in r.headers:
                    target = self.normalize(r.headers["Location"])
                    if self.is_internal(target) and target not in self.visited:
                        self.to_visit.append(target)
                    results.append({
                        "loc": url,
                        "status": code,
                        "lastmod": None,
                        "redirect_to": target
                    })
                    continue

                # 200 OK (or other 2xx)
                r.raise_for_status()
                body_hash = hashlib.sha256(r.content).hexdigest()
                # parse Last-Modified header if present
                lm = r.headers.get("Last-Modified")
                dt = None
                if lm:
                    try:
                        dt = parsedate_to_datetime(lm).astimezone(timezone.utc)
                    except Exception:
                        dt = None

                # record this page
                results.append({
                    "loc": url,
                    "status": code,
                    "lastmod": dt,
                    "redirect_to": None,
                    "hash": body_hash
                })

                # extract further internal links
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all('a', href=True):
                    link = self.normalize(a['href'])
                    if link not in self.visited and self.is_internal(link):
                        self.to_visit.append(link)

                # images
                for img in soup.find_all('img', src=True):
                    self.images.add(self.normalize(img['src']))
                # videos/sources
                for vid in soup.find_all(['video', 'source'], src=True):
                    self.videos.add(self.normalize(vid['src']))

                time.sleep(self.delay)
            except Exception:
                # network errors, parse errors, etc.
                continue

        return {
            "pages": results,
            "images": list(self.images),
            "videos": list(self.videos)
        }
