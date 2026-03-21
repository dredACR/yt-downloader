import os
import io
import threading
import uuid
import json

from flask import Flask, jsonify, render_template, request, send_file, Response
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}  # job_id -> {status, file_path, error, title}

# yt-dlp options that bypass bot detection without cookies
BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["web_creator", "ios"],
            "player_skip": ["webpage"],
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
}


def get_ydl_opts(quality: str, job_id: str) -> dict:
    out = str(os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s"))

    fmt_map = {
        "720": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
        "480": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "360": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }
    fmt = fmt_map.get(quality, fmt_map["720"])

    postprocessors = []
    if quality == "audio":
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })
    else:
        postprocessors.append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            jobs[job_id]["progress"] = int(done / total * 100) if total else 0
        elif d["status"] == "finished":
            jobs[job_id]["progress"] = 95

    opts = {**BASE_OPTS}
    opts.update({
        "format": fmt,
        "outtmpl": out,
        "merge_output_format": "mp4",
        "postprocessors": postprocessors,
        "progress_hooks": [progress_hook],
    })
    return opts


def download_worker(job_id: str, url: str, quality: str):
    try:
        opts = get_ydl_opts(quality, job_id)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            ext = "mp3" if quality == "audio" else "mp4"

        # Find downloaded file
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(job_id):
                jobs[job_id]["file_path"] = os.path.join(DOWNLOAD_DIR, f)
                break

        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["title"] = title
        jobs[job_id]["ext"] = ext

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def get_info():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL не вказано"}), 400
    try:
        opts = {**BASE_OPTS}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration_string", ""),
            "uploader": info.get("uploader", ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/download")
def start_download():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "720")

    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "downloading", "progress": 0, "file_path": None, "error": None}

    t = threading.Thread(target=download_worker, args=(job_id, url, quality), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.get("/api/progress/<job_id>")
def get_progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    return jsonify(job)


@app.get("/api/file/<job_id>")
def serve_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job.get("file_path"):
        return jsonify({"error": "File not ready"}), 404

    path = job["file_path"]
    if not os.path.exists(path):
        return jsonify({"error": "File missing"}), 404

    title = job.get("title", "video")
    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    ext = job.get("ext", "mp4")

    return send_file(path, as_attachment=True, download_name=f"{safe}.{ext}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
