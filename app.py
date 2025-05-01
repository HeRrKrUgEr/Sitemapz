import os
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, send_from_directory, Response, abort
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from models import SessionLocal, init_db, Website, Scan, PageScan
from crawler import SiteCrawler
from generator import generate_all
from emailer import send_report
from urllib.parse import urlparse

# ─── Basic Auth ────────────────────────────────────────────────────
AUTH_USER = os.getenv("AUTH_USER", "admin")
AUTH_PASS = os.getenv("AUTH_PASSWORD", "password")

def check_auth(username, password):
    return username == AUTH_USER and password == AUTH_PASS

def authenticate():
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ─── App & DB setup ───────────────────────────────────────────────
init_db()
session = SessionLocal()
app = Flask(__name__)

# ─── Scheduler setup ─────────────────────────────────────────────
sched = BackgroundScheduler(timezone="Europe/Paris")

def decide_lastmod(p, prev_map, crawl_dt):
    """
    p: dict from crawler with loc, status, lastmod, redirect_to, hash
    prev_map: { url -> PageScan } from the previous scan
    crawl_dt: datetime.utcnow() of this run
    """
    # if the server gave us a Last-Modified header, use it
    if p.get("lastmod"):
        return p["lastmod"], p.get("hash")

    # fallback: use URL of the final loc for redirects, or loc for 200
    final_url = p["loc"] if p["status"] == 200 else p["redirect_to"]
    prev = prev_map.get(final_url)

    # first time ever: record this crawl date and its hash
    if not prev:
        return crawl_dt, p.get("hash")

    # content changed?
    if p.get("hash") and p["hash"] != prev.content_hash:
        return crawl_dt, p["hash"]

    # unchanged: keep old lastmod and old hash
    return prev.lastmod, prev.content_hash


def run_scan(website_id):
    ws = session.get(Website, website_id)
    try:
        data   = SiteCrawler(ws.url).crawl()
        crawl_dt = datetime.utcnow()
        pages  = data["pages"]    # list of dicts with loc/status/lastmod/redirect_to
        images = data["images"]
        videos = data["videos"]

        

        outdir = os.path.join("data", f"site_{ws.id}")
        name   = urlparse(ws.url).netloc
        
        ws.last_scan   = datetime.utcnow()
        ws.last_status = "ok"
        # summary record
        scan = Scan(
            website_id     = ws.id,
            timestamp      = datetime.utcnow(),
            pages_found    = len(pages),
            images_found   = len(images),
            videos_found   = len(videos),
            pages_included = 0,
            images_included= 0,
            videos_included= 0,
            errors         = None,
            extra_info     = {} 
        )
        session.add(scan)
        session.flush()

        last = (
        session.query(Scan)
               .filter_by(website_id=ws.id)
               .order_by(Scan.timestamp.desc())
               .offset(1)    # skip the one we just inserted
               .limit(1)
               .one_or_none()
        )
        prev_map = {}
        if last:
            prev_entries = (
                session.query(PageScan)
                    .filter_by(scan_id=last.id)
                    .all()
            )
            prev_map = { p.url: p for p in prev_entries }

        included_count = 0
            
            # detailed per-page rows
        page_urls = []    
        for p in pages:
            # decide if we include it in sitemap (200 or 301 w/ redirect_to)
            final_url = p["loc"] if p["status"] == 200 else p.get("redirect_to")
            if not final_url or p["status"] not in (200, 301):
                # still record in DB, but don’t count towards pages_included
                lm, ch = decide_lastmod(p, prev_map, crawl_dt)
                session.add(PageScan(
                scan_id     = scan.id,
                url         = p["loc"],
                status      = p["status"],
                lastmod     = lm,
                redirect_to = p.get("redirect_to"),
                content_hash= ch
                ))
                continue

            # this URL goes into sitemap
            lm, ch = decide_lastmod(p, prev_map, crawl_dt)
            toAdd = PageScan(
                scan_id     = scan.id,
                url         = final_url,
                status      = p["status"],
                lastmod     = lm,
                redirect_to = p.get("redirect_to"),
                content_hash= ch
            )
            session.add(toAdd)
            page_urls.append(toAdd)
            
        
        pf, imf, vf = generate_all(
            ws.id, name, outdir, page_urls, images, videos
        )
        scan.pages_included = len(page_urls)
        scan.images_included = len(imf)
        scan.videos_included = len(vf)
        scan.extra_info = {"images": imf, "videos": vf}
        session.commit()

        
        
        body = (
            f"Scan ok for {ws.url}\n"
            f"Pages found: {len(pages)}\n"
            f"Pages indexed: {len(page_urls)}\n"
            f"Images: {len(images)}\n"
            f"Videos: {len(videos)}\n"
            f"Sitemaps directory: {outdir}"
        )
        send_report(f"[SitemapGen] Success {ws.url}", body)

    except Exception as e:
        session.rollback()
        ws.last_scan   = datetime.utcnow()
        ws.last_status = "error"
        session.commit()

        err_scan = Scan(
            website_id     = ws.id,
            pages_found    = 0,
            images_found   = 0,
            videos_found   = 0,
            pages_included = 0,
            images_included= 0,
            videos_included= 0,
            errors         = str(e),
            extra_info     = {}
        )
        session.add(err_scan)
        session.commit()

        send_report(f"[SitemapGen] ERROR {ws.url}", f"Error: {e}")

def schedule_all():
    sched.remove_all_jobs()
    result = session.execute(text("SELECT * FROM websites"))
    for ws in result:
        trig = CronTrigger.from_crontab(ws.cron_schedule)
        sched.add_job(run_scan, trig, args=[ws.id], id=f"site_{ws.id}")

# ─── Routes ───────────────────────────────────────────────────────–

@app.route("/", methods=["GET"])
@requires_auth
def index():
    sites = session.query(Website).all()
    # attach last scan summary to each for the UI
    return render_template("index.html", sites=sites)

@app.route("/add", methods=["POST"])
@requires_auth
def add():
    url      = request.form["url"]
    schedule = request.form["schedule"]
    token    = secrets.token_urlsafe(16)

    ws = Website(
        url          = url,
        cron_schedule= schedule,
        api_token    = token
    )
    session.add(ws)
    session.commit()

    # schedule immediately
    trig = CronTrigger.from_crontab(schedule)
    sched.add_job(run_scan, trig, args=[ws.id], id=f"site_{ws.id}")

    return redirect(url_for("index"))

@app.route("/scan_now/<int:site_id>", methods=["POST"])
@requires_auth
def scan_now(site_id):
    run_scan(site_id)
    return redirect(url_for("index"))

@app.route("/reports/<path:filename>")
@requires_auth
def reports(filename):
    return send_from_directory("data", filename)

@app.route("/broken/<int:site_id>")
@requires_auth
def broken(site_id):
    last = (
        session.query(Scan)
               .filter_by(website_id=site_id)
               .order_by(Scan.timestamp.desc())
               .first()
    )
    broken_pages = []
    if last:
        broken_pages = (
            session.query(PageScan)
                   .filter_by(scan_id=last.id, status=404)
                   .all()
        )
    return render_template("broken.html", broken=broken_pages, site_id=site_id)

@app.route("/api/sitemap/<int:site_id>/<string:stype>")
def api_sitemap(site_id, stype):
    token = request.args.get("token", "")
    ws    = session.get(Website, site_id)
    if not ws or token != ws.api_token:
        abort(403)

    basedir = os.path.join("data", f"site_{site_id}")
    files   = sorted(
        f for f in os.listdir(basedir)
        if f.startswith(f"{stype}_site{site_id}_")
    )
    if not files:
        abort(404)

    # sitemap index
    if len(files) > 1:
        today = datetime.utcnow()
        xml   = '<?xml version="1.0"?>\n'
        xml  += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for fn in files:
            loc = f"{os.getenv('BASE_URL')}/reports/{fn}"
            xml+= (f"  <sitemap>\n"
                   f"    <loc>{loc}</loc>\n"
                   f"    <lastmod>{today}</lastmod>\n"
                   f"  </sitemap>\n")
        xml += "</sitemapindex>"
        return Response(xml, mimetype="application/xml")

    # single file
    return send_from_directory(basedir, files[0], mimetype="application/xml")

@app.route("/download_script/<int:site_id>")
@requires_auth
def download_script(site_id):
    ws = session.get(Website, site_id)
    if not ws:
        abort(404)

    token = ws.api_token or secrets.token_urlsafe(16)
    if not ws.api_token:
        ws.api_token = token
        session.add(ws)
        session.commit()

    base = os.getenv("BASE_URL")
    php  = f"""<?php
// Secure PHP fetcher
$token  = '{token}';
$siteId = {site_id};
$baseUrl= '{base}';
function fetch_sitemap($type) {{
    global $token, $siteId, $baseUrl;
    $url = "$baseUrl/api/sitemap/$siteId/$type?token=$token";
    $ch  = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    $data = curl_exec($ch);
    if(curl_getinfo($ch, CURLINFO_HTTP_CODE) !== 200) {{
        http_response_code(500);
        die('Error fetching sitemap');
    }}
    header('Content-Type: application/xml');
    echo $data;
}}
// fetch_sitemap('pages');
fetch_sitemap('pages');
?>"""

    return Response(
        php,
        mimetype="application/octet-stream",
        headers={"Content-Disposition":f"attachment;filename=sitemap_fetcher_{site_id}.php"}
    )

if __name__ == "__main__":
    schedule_all()
    sched.start()
    app.run(host="0.0.0.0", port=8000)
