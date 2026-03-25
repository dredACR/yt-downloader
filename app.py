import os
import threading
import uuid

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}

BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["web_creator", "ios"],
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
}


def download_worker(job_id: str, url: str, quality: str):
    try:
        out = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")

        if quality == "audio":
            # Audio only - no FFmpeg needed, just download m4a
            fmt = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio"
        else:
            # Progressive = video+audio already merged, no FFmpeg needed
            # These go up to 720p on most videos
            height = quality.replace("p", "")
            fmt = (
                f"best[height<={height}][ext=mp4]"
                f"/best[height<={height}]"
                f"/best[ext=mp4]"
                f"/best"
            )

        def hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                jobs[job_id]["progress"] = int(done / total * 100) if total else 0
            elif d["status"] == "finished":
                jobs[job_id]["progress"] = 99

        opts = {**BASE_OPTS, "format": fmt, "outtmpl": out, "progress_hooks": [hook]}

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        # Find file
        file_path = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(job_id):
                file_path = os.path.join(DOWNLOAD_DIR, f)
                break

        if not file_path or os.path.getsize(file_path) < 1000:
            raise Exception("Файл не завантажився або пошкоджений")

        jobs[job_id].update({
            "status": "done",
            "progress": 100,
            "title": title,
            "file_path": file_path,
            "ext": os.path.splitext(file_path)[1].lstrip("."),
        })

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
        with yt_dlp.YoutubeDL(BASE_OPTS) as ydl:
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
    quality = (data or {}).get("quality", "720p")
    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "downloading", "progress": 0, "file_path": None, "error": None}

    threading.Thread(target=download_worker, args=(job_id, url, quality), daemon=True).start()
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
    if not job or job["status"] != "done":
        return jsonify({"error": "Not ready"}), 404

    path = job.get("file_path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "File missing"}), 404

    safe = "".join(c for c in job.get("title", "video") if c.isalnum() or c in " -_").strip()
    ext = job.get("ext", "mp4")
    return send_file(path, as_attachment=True, download_name=f"{safe}.{ext}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
