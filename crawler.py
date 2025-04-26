import re
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

class SiteCrawler:
    def __init__(self, base_url, max_pages=10000, delay=0.5):
        self.base_url = base_url.rstrip('/')
        self.parsed_base = urlparse(self.base_url)
        self.visited = set()
        self.to_visit = [self.base_url]
        self.pages = []
        self.images = set()
        self.videos = set()
        self.max_pages = max_pages
        self.delay = delay

    def is_internal(self, link):
        p = urlparse(link)
        return (p.netloc == "" or self.parsed_base.netloc in p.netloc) 
                
    def normalize(self, link):
        return urljoin(self.base_url, link.split('#')[0]).rstrip('/')

    def crawl(self):
        while self.to_visit and len(self.pages) < self.max_pages:
            url = self.to_visit.pop(0)
            if url in self.visited:
                continue
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                self.visited.add(url)
                self.pages.append(url)

                # extract links
                for a in soup.find_all('a', href=True):
                    link = self.normalize(a['href'])
                    if link not in self.visited and self.is_internal(link):
                        self.to_visit.append(link)

                # extract images
                for img in soup.find_all('img', src=True):
                    self.images.add(self.normalize(img['src']))

                # extract videos
                for vid in soup.find_all(['video', 'source'], src=True):
                    self.videos.add(self.normalize(vid['src']))

                time.sleep(self.delay)
            except Exception as e:
                # skip on errors
                continue

        return {
            "pages": self.pages,
            "images": list(self.images),
            "videos": list(self.videos)
        }
