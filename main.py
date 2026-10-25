import os
import uuid
import tempfile
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTasks
import yt_dlp

app = FastAPI(title="YouTube MP3 Streamer API")

def cleanup_file(filepath: str):
    """Deletes temporary file after sending response."""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

@app.get("/")
def stream_audio(
    url: str = Query(..., description="YouTube video URL"),
    background_tasks: BackgroundTasks = None
):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL format.")

    unique_id = str(uuid.uuid4())
    temp_dir = tempfile.gettempdir()
    output_template = os.path.join(temp_dir, f"{unique_id}.%(ext)s")
    target_mp3 = os.path.join(temp_dir, f"{unique_id}.mp3")

    # Base options
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': False,
    }

    # Render Secret Files are mounted at /etc/secrets/
    cookie_candidates = [
        '/etc/secrets/cookies.txt',
        'cookies.txt',
        '/app/cookies.txt'
    ]
    cookie_found = False
    for cp in cookie_candidates:
        if os.path.exists(cp):
            ydl_opts['cookiefile'] = cp
            print(f"[DEBUG] Found cookies file at: {cp}")
            cookie_found = True
            break

    if not cookie_found:
        print("[WARNING] No cookies.txt found in search paths!")

    # Optional Proxy
    proxy = os.getenv("PROXY_URL")
    if proxy:
        ydl_opts['proxy'] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename_title = info.get("title", "audio").replace("/", "_")
    except Exception as e:
        cleanup_file(target_mp3)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

    if not os.path.exists(target_mp3):
        raise HTTPException(status_code=500, detail="Audio conversion failed.")

    if background_tasks:
        background_tasks.add_task(cleanup_file, target_mp3)

    return FileResponse(
        path=target_mp3,
        media_type="audio/mpeg",
        filename=f"{filename_title}.mp3"
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}
