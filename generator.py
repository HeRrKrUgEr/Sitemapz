import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATES_PATH), autoescape=True)

def split_urls(urls):
    # Google allows max 50k URLs per sitemap
    chunk_size = 50000
    for i in range(0, len(urls), chunk_size):
        yield urls[i:i+chunk_size]

def write_sitemaps(site_id, site_name, base_output, urls, tpl_name, prefix):
    """
    Generates one or more sitemap files for a given list of URLs.
    """
    tpl = env.get_template(tpl_name)
    files = []
    for idx, chunk in enumerate(split_urls(urls), start=1):       
        filename = f"{prefix}_site{site_id}_{idx}.xml"
        path = os.path.join(base_output, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(tpl.render(urls=chunk, now=datetime.utcnow()))
        files.append(filename)
    return files

def generate_all(site_id, site_name, output_dir, pages, images, videos):
    os.makedirs(output_dir, exist_ok=True)
    pages_files = write_sitemaps(site_id, site_name, output_dir, pages, "pages_sitemap.xml.j2", "pages")
    image_files = write_sitemaps(site_id, site_name, output_dir, images, "images_sitemap.xml.j2", "images")
    video_files = write_sitemaps(site_id, site_name, output_dir, videos, "videos_sitemap.xml.j2", "videos")
    return pages_files, image_files, video_files
