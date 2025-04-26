import os, secrets
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, Response, abort
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text
from models     import SessionLocal, init_db, Website, Scan
from crawler    import SiteCrawler
from generator  import generate_all
from emailer    import send_report
from urllib.parse import urljoin, urlparse

# ─── App & DB setup ─────────────────────────────────────────
init_db()
session = SessionLocal()
app = Flask(__name__)


# ─── Scheduler setup ────────────────────────────────────────
sched = BackgroundScheduler(timezone="Europe/Paris")

def run_scan(website_id):
    ws = session.get(Website, website_id)
    try:
        data = SiteCrawler(ws.url).crawl()
        pages, images, videos = data["pages"], data["images"], data["videos"]

        outdir = os.path.join("data", f"site_{ws.id}")
        name = urlparse(ws.url).netloc
        
        
        pf, imf, vf = generate_all(ws.id, name,  outdir, pages, images, videos)

        scan = Scan(
            website_id=ws.id,
            pages_found=len(pages), images_found=len(images), videos_found=len(videos),
            pages_included=len(pages), images_included=len(images), videos_included=len(videos),
            errors=None,
            extra_info={"pages": pf, "images": imf, "videos": vf}
        )
        session.add(scan)
        session.commit()

        body = (
            f"Scan ok for {ws.url}\n"
            f"Pages: {len(pages)}\nImages: {len(images)}\nVideos: {len(videos)}\n"
            f"Sitemaps: {outdir}"
        )
        send_report(f"[SitemapGen] Success {ws.url}", body)

    except Exception as e:
        session.rollback()
        ws.last_scan = datetime.utcnow()
        ws.last_status = "error"
        session.commit()

        scan = Scan(
            website_id=ws.id,
            pages_found=0, images_found=0, videos_found=0,
            pages_included=0, images_included=0, videos_included=0,
            errors=str(e), extra_info={}
        )
        session.add(scan); session.commit()
        send_report(f"[SitemapGen] ERROR {ws.url}", f"Error: {e}")

def schedule_all():
    sched.remove_all_jobs()
    result = session.execute(text("SELECT * FROM websites"))
    for ws in result:
        trig = CronTrigger.from_crontab(ws.cron_schedule)
        sched.add_job(run_scan, trig, args=[ws.id], id=f"site_{ws.id}")



# ─── Flask routes ────────────────────────────────────────────

# 1) UI: list sites & add new one
@app.route("/", methods=["GET"])
def index():
    result = session.execute(text("SELECT * FROM websites"))
    return render_template("index.html", sites=result)

@app.route("/add", methods=["POST"])
def add():
    url      = request.form["url"]
    schedule = request.form["schedule"]
    token    = secrets.token_urlsafe(16)
    ws = Website(url=url, cron_schedule=schedule, api_token=token)
    session.add(ws); session.commit()

    # schedule immediately
    trig = CronTrigger.from_crontab(schedule)
    sched.add_job(run_scan, trig, args=[ws.id], id=f"site_{ws.id}")

    return redirect(url_for("index"))

@app.route("/scan_now/<int:site_id>", methods=["POST"])
def scan_now(site_id):
    run_scan(site_id)
    return redirect(url_for("index"))

# 2) Serve raw sitemap files (if you ever need them)
@app.route("/reports/<path:filename>")
def reports(filename):
    return send_from_directory("data", filename)

# 3) Secure JSON/XML API for sitemaps
@app.route("/api/sitemap/<int:site_id>/<string:stype>")
def api_sitemap(site_id, stype):
    token = request.args.get("token","")
    ws = session.get(Website,).get(site_id)
    if not ws or token != ws.api_token:
        abort(403)

    basedir = os.path.join("data", f"site_{site_id}")
    files = sorted(f for f in os.listdir(basedir) if f.startswith(f"{stype}_site{site_id}_"))
    if not files:
        abort(404)

    # multiple → sitemap index
    if len(files) > 1:
        today = datetime.utcnow()
        xml  = '<?xml version="1.0"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for fn in files:
            loc = f"{os.getenv('BASE_URL')}/reports/{fn}"
            xml += f"  <sitemap>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n  </sitemap>\n"
        xml += "</sitemapindex>"
        return Response(xml, mimetype="application/xml")

    # single file
    return send_from_directory(basedir, files[0], mimetype="application/xml")

# 4) PHP fetcher download
@app.route("/download_script/<int:site_id>")
def download_script(site_id):
    ws = session.get(Website, site_id)
    if not ws:
        abort(404)
    try:
        token = ws.api_token       
    except AttributeError as e:
        token = secrets.token_urlsafe(16)
        ws.api_token = token
        session.add(ws)
        session.commit()
        
    base = os.getenv("BASE_URL")

    php = f"""<?php
// Place this file on your own webhost to fetch your sitemap securely
$token   = '{token}';
$siteId  = {site_id};
$baseUrl = '{base}';

function fetch_sitemap($type) {{
    global $token, $siteId, $baseUrl;
    $url = \"$baseUrl/api/sitemap/$siteId/$type?token=$token\";
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    $data = curl_exec($ch);
    if(curl_getinfo($ch, CURLINFO_HTTP_CODE) !== 200) {{
        http_response_code(500);
        die('Error fetching sitemap');
    }}
    header('Content-Type: application/xml');
    echo $data;
}}

// Example: to output pages sitemap, just call:
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
