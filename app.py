import os
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import urllib.request
import urllib.parse
import json

app = Flask(__name__)
CORS(app)

COBALT_API = "https://api.cobalt.tools"

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/download")
def get_download_link():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    quality = (data or {}).get("quality", "1080")
    audio_only = (data or {}).get("audio_only", False)

    if not url:
        return jsonify({"error": "URL не вказано"}), 400

    payload = {
        "url": url,
        "videoQuality": quality,
        "filenameStyle": "pretty",
    }

    if audio_only:
        payload["downloadMode"] = "audio"
    else:
        payload["downloadMode"] = "auto"

    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{COBALT_API}/",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # cobalt returns: {status, url} or {status, picker} or {status, error}
        status = result.get("status")

        if status in ("redirect", "stream", "tunnel"):
            return jsonify({"url": result.get("url"), "filename": result.get("filename", "video.mp4")})
        elif status == "picker":
            # multiple streams — return first
            first = result.get("picker", [{}])[0]
            return jsonify({"url": first.get("url"), "filename": "video.mp4"})
        else:
            err = result.get("error", {})
            msg = err.get("code", "Невідома помилка") if isinstance(err, dict) else str(err)
            return jsonify({"error": msg}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
