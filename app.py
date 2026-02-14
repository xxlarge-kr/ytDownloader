import os
import re
import uuid
import glob
import threading

from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/.+"
)


def cleanup_file(path, delay=60):
    """Delete file after a delay (seconds)."""
    def _delete():
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    timer = threading.Timer(delay, _delete)
    timer.daemon = True
    timer.start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "요청 데이터가 없습니다."}), 400

    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")

    if not url:
        return jsonify({"error": "URL을 입력해주세요."}), 400

    if not YOUTUBE_URL_PATTERN.match(url):
        return jsonify({"error": "유효한 YouTube URL이 아닙니다."}), 400

    if fmt not in ("mp4", "mp3"):
        return jsonify({"error": "지원하지 않는 포맷입니다."}), 400

    file_id = uuid.uuid4().hex
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}_YT-%(uploader)s-%(title)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["web"]}},
        "js_runtimes": {"node": {}},
    }

    if fmt == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts.update({
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"다운로드 실패: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"오류 발생: {str(e)}"}), 500

    # Find the downloaded file
    ext = "mp3" if fmt == "mp3" else "mp4"
    pattern = os.path.join(DOWNLOAD_DIR, f"{file_id}_*.{ext}")
    files = glob.glob(pattern)

    if not files:
        return jsonify({"error": "다운로드된 파일을 찾을 수 없습니다."}), 500

    filepath = files[0]
    filename = os.path.basename(filepath).replace(f"{file_id}_", "", 1)

    # Schedule cleanup after sending
    cleanup_file(filepath, delay=60)

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
