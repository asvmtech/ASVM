import os
import uuid
import shutil
import tempfile
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTasks
import yt_dlp

app = FastAPI(title="YouTube MP3 Streamer API")

def cleanup_files(*filepaths):
    """Deletes temporary files after sending the HTTP response."""
    for path in filepaths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def get_writable_cookie_file() -> str | None:
    """
    Finds cookies.txt in the repo and copies it to /tmp so yt-dlp
    has write access without throwing read-only filesystem errors.
    """
    source_cookie = "cookies.txt"
    if os.path.exists(source_cookie):
        temp_dir = tempfile.gettempdir()
        temp_cookie_path = os.path.join(temp_dir, f"session_cookies_{uuid.uuid4().hex[:8]}.txt")
        shutil.copyfile(source_cookie, temp_cookie_path)
        return temp_cookie_path
    return None

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

    active_cookie_file = get_writable_cookie_file()

    ydl_opts = {
        # Fallback to full video+audio stream if standalone audio is unavailable
        'format': 'bestaudio/bestvideo+bestaudio/best',
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

    if active_cookie_file:
        ydl_opts['cookiefile'] = active_cookie_file

    proxy = os.getenv("PROXY_URL")
    if proxy:
        ydl_opts['proxy'] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename_title = info.get("title", "audio").replace("/", "_")
    except Exception as e:
        cleanup_files(target_mp3, active_cookie_file)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

    if not os.path.exists(target_mp3):
        cleanup_files(active_cookie_file)
        raise HTTPException(status_code=500, detail="Audio conversion failed.")

    # Safely delete the temporary MP3 and cookie clone after the file is streamed
    if background_tasks:
        background_tasks.add_task(cleanup_files, target_mp3, active_cookie_file)

    return FileResponse(
        path=target_mp3,
        media_type="audio/mpeg",
        filename=f"{filename_title}.mp3"
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}
