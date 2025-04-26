import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from models import SessionLocal, init_db, Website, Scan
from crawler import SiteCrawler
from generator import generate_all
from emailer import send_report
from datetime import datetime

init_db()
session = SessionLocal()
sched = BackgroundScheduler(timezone="Europe/Paris")

def run_scan(website_id):
    ws = session.query(Website).get(website_id)
    try:
        crawler = SiteCrawler(ws.url)
        result = crawler.crawl()
        pages, images, videos = result["pages"], result["images"], result["videos"]

        output_dir = os.path.join("data", f"site_{ws.id}")
        pages_files, img_files, vid_files = generate_all(ws.id, output_dir, pages, images, videos)

        scan = Scan(
            website_id=ws.id,
            pages_found=len(pages),
            images_found=len(images),
            videos_found=len(videos),
            pages_included=sum(len(chunk) for chunk in [pages]),
            images_included=sum(len(chunk) for chunk in [images]),
            videos_included=sum(len(chunk) for chunk in [videos]),
            errors=None,
            extra_info={
                "pages_sitemaps": pages_files,
                "images_sitemaps": img_files,
                "videos_sitemaps": vid_files
            }
        )
        ws.last_scan = datetime.utcnow()
        ws.last_status = "success"
        session.add(scan)
        session.commit()

        body = (
            f"Scan successful for {ws.url}\n\n"
            f"Pages: {len(pages)} → {sum(len(chunk) for chunk in [pages])}\n"
            f"Images: {len(images)} → {sum(len(chunk) for chunk in [images])}\n"
            f"Videos: {len(videos)} → {sum(len(chunk) for chunk in [videos])}\n"
            f"Sitemaps: {output_dir}\n"
        )
        send_report(f"[SitemapGen] Success: {ws.url}", body)

    except Exception as e:
        session.rollback()
        ws.last_status = "error"
        ws.last_scan = datetime.utcnow()
        session.commit()

        scan = Scan(
            website_id=ws.id,
            pages_found=0, images_found=0, videos_found=0,
            pages_included=0, images_included=0, videos_included=0,
            errors=str(e),
            extra_info={}
        )
        session.add(scan)
        session.commit()

        send_report(f"[SitemapGen] ERROR: {ws.url}", f"Error scanning {ws.url}:\n{e}")

def schedule_all():
    # clear existing jobs
    sched.remove_all_jobs()
    for ws in session.query(Website).all():
        trigger = CronTrigger.from_crontab(ws.cron_schedule)
        sched.add_job(run_scan, trigger, args=[ws.id], id=f"site_{ws.id}")
    sched.start()

if __name__ == "__main__":
    schedule_all()
    # keep alive
    import time
    while True:
        time.sleep(60)
