import os
import io
from flask import Flask, jsonify, render_template, request, Response
from flask_cors import CORS
from pytubefix import YouTube
from pytubefix.cli import on_progress

app = Flask(__name__)
CORS(app)

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
        yt = YouTube(url, use_po_token=True)
        return jsonify({
            "title": yt.title,
            "thumbnail": yt.thumbnail_url,
            "duration": str(yt.length) + " сек",
            "author": yt.author,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/download")
def download():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "720p")
    audio_only = (data or {}).get("audio_only", False)

    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    try:
        yt = YouTube(url, use_po_token=True)

        if audio_only:
            stream = yt.streams.get_audio_only()
            ext = "mp3"
            mime = "audio/mpeg"
        else:
            # Try to get progressive stream (video+audio in one file)
            res = quality if quality != "best" else None
            if res:
                stream = yt.streams.filter(progressive=True, res=res).first()
            if not stream:
                stream = yt.streams.filter(progressive=True).order_by("resolution").last()
            ext = "mp4"
            mime = "video/mp4"

        if not stream:
            return jsonify({"error": "Потрібний формат недоступний"}), 400

        # Stream file directly to browser
        buf = io.BytesIO()
        stream.stream_to_buffer(buf)
        buf.seek(0)

        safe_title = "".join(c for c in yt.title if c.isalnum() or c in " -_").strip()
        filename = f"{safe_title}.{ext}"

        return Response(
            buf,
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": buf.getbuffer().nbytes,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
