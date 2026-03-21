import os
import re
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# In-memory job store: {job_id: {status, progress, filename, error}}
jobs: dict = {}


def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def download_worker(job_id: str, url: str, quality: str):
    """Runs in a background thread; updates jobs[job_id] as it progresses."""
    import yt_dlp

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = int(downloaded / total * 100) if total else 0
            jobs[job_id]["progress"] = pct
            jobs[job_id]["status"] = "downloading"
            speed = d.get("speed")
            if speed:
                jobs[job_id]["speed"] = f"{speed/1024/1024:.1f} MB/s"
        elif d["status"] == "finished":
            jobs[job_id]["progress"] = 99
            jobs[job_id]["status"] = "processing"

    # Choose format string based on quality
    fmt_map = {
        "best": "bestvideo+bestaudio/best",
        "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "audio": "bestaudio/best",
    }
    fmt = fmt_map.get(quality, fmt_map["best"])

    out_template = str(DOWNLOAD_DIR / f"{job_id}_%(title)s.%(ext)s")

    postprocessors = []
    if quality == "audio":
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })

    ydl_opts = {
        "format": fmt,
        "outtmpl": out_template,
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "postprocessors": postprocessors,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize(info.get("title", "video"))
            ext = "mp3" if quality == "audio" else info.get("ext", "mp4")

            # Find the actual file on disk
            for f in DOWNLOAD_DIR.iterdir():
                if f.name.startswith(job_id):
                    jobs[job_id]["filename"] = f.name
                    break

        jobs[job_id]["progress"] = 100
        jobs[job_id]["status"] = "done"
        jobs[job_id]["title"] = title

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def get_info():
    """Return video title + available formats before downloading."""
    import yt_dlp

    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration_string") or str(info.get("duration", "")),
            "uploader": info.get("uploader"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/download")
def start_download():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "best")

    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "queued", "progress": 0, "filename": None, "error": None, "speed": ""}

    t = threading.Thread(target=download_worker, args=(job_id, url, quality), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.get("/api/progress/<job_id>")
def get_progress(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.get("/api/file/<job_id>")
def serve_file(job_id: str):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready"}), 404

    filepath = DOWNLOAD_DIR / job["filename"]
    if not filepath.exists():
        return jsonify({"error": "File missing"}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=job["filename"].replace(f"{job_id}_", "", 1),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
