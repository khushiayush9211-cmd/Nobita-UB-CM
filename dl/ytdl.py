import asyncio
import os
import re
import shutil
import time
import uuid
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from utils import modules_help, prefix
from utils.scripts import format_exc, import_library, progress, resize_image

yt_dlp = import_library("yt_dlp", "yt-dlp")
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

BASE_DIR = "downloads/ytdl"

ydv_opts = {
    "format": "bv[height<=1440][ext=mp4]+ba/bv*[height<=1440]+ba/b[height<=1440][ext=mp4]/b[height<=1440]",
    "merge_output_format": "mp4",
    "default_search": "ytsearch",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "addmetadata": True,
    "noplaylist": True,
    "quiet": True,
}

ydm_opts = {
    "format": "bestaudio/best",
    "default_search": "ytsearch",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "addmetadata": True,
    "noplaylist": True,
    "quiet": True,
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
}

API_URL = "https://davidcyriltech.my.id/"


# ---------------------------------------------------------------- helpers
def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", str(name or "file")).strip()
    return name[:100] or "file"


def extract_video_id(url):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host == "youtu.be":
        return parsed.path[1:] or None
    if "youtube.com" in host:
        if parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            parts = parsed.path.split("/")
            return parts[2] if len(parts) > 2 else None
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


async def search_api(query, is_videoId=False, video=False):
    query = str(query)
    async with aiohttp.ClientSession() as session:
        if is_videoId:
            endpoint = "ytmp4" if video else "ytmp3"
            async with session.get(
                f"{API_URL}download/{endpoint}",
                params={"url": f"https://youtube.com/watch?v={query}"},
            ) as resp:
                data = await resp.json(content_type=None)
            if data.get("success"):
                result = data["result"]
                return result["title"], result.get("thumbnail"), result["download_url"]
        else:
            async with session.get(
                f"{API_URL}song", params={"query": query}
            ) as resp:
                data = await resp.json(content_type=None)
            if data.get("status") and data.get("result"):
                result = data["result"]
                link = (
                    result["video"]["download_url"]
                    if video
                    else result["audio"]["download_url"]
                )
                return result["title"], result.get("thumbnail"), link
    return None, None, None


async def download_file(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Download failed (HTTP {resp.status})")
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    f.write(chunk)


async def download_thumb(thumb_url, workdir):
    """Returns (resized_thumb_path, raw_bytes) or (None, None)."""
    if not thumb_url:
        return None, None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumb_url) as resp:
                if resp.status != 200:
                    return None, None
                raw = await resp.read()
        path = os.path.join(workdir, "thumb.jpg")
        with open(path, "wb") as f:
            f.write(raw)
        return resize_image(path), raw
    except Exception:
        return None, None


def _extract(opts, url):
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info and "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ExtractorError("No results found")
            info = entries[0]
        return info


def _find_file(workdir):
    for name in sorted(os.listdir(workdir)):
        if name.startswith("thumb"):
            continue
        path = os.path.join(workdir, name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("Downloaded file not found")


async def _api_fallback(url, workdir, video):
    video_id = extract_video_id(url)
    is_videoId = video_id is not None
    query = video_id if is_videoId else url
    title, thumb_url, link = await search_api(query, is_videoId, video)
    if not link:
        raise Exception("No result found (yt-dlp and API both failed)")
    img, raw = await download_thumb(thumb_url, workdir)
    ext = "mp4" if video else "mp3"
    file_path = os.path.join(workdir, f"{safe_name(title)}.{ext}")
    await download_file(link, file_path)
    return file_path, title, img, raw, {}


async def download_video(url, workdir):
    opts = {**ydv_opts, "outtmpl": f"{workdir}/%(id)s.%(ext)s"}
    try:
        info = await asyncio.to_thread(_extract, opts, url)
        title = info.get("title")
        img, raw = await download_thumb(info.get("thumbnail"), workdir)
        meta = {
            "duration": int(info.get("duration") or 0),
            "width": int(info.get("width") or 0),
            "height": int(info.get("height") or 0),
        }
        return _find_file(workdir), title, img, raw, meta
    except (DownloadError, ExtractorError):
        return await _api_fallback(url, workdir, video=True)


async def download_music(url, workdir):
    opts = {**ydm_opts, "outtmpl": f"{workdir}/%(title)s.%(ext)s"}
    try:
        info = await asyncio.to_thread(_extract, opts, url)
        title = info.get("title")
        img, _ = await download_thumb(info.get("thumbnail"), workdir)
        duration = int(info.get("duration") or 0)
        return _find_file(workdir), title, img, duration
    except (DownloadError, ExtractorError):
        file_path, title, img, _, _ = await _api_fallback(url, workdir, video=False)
        return file_path, title, img, 0


# ---------------------------------------------------------------- handler
@Client.on_message(filters.command(["ytv", "ytm"], prefix) & filters.me)
async def ytvm(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.edit_text("Please provide a YouTube URL or name.")

    cmd = message.command[0]
    url = message.text.split(maxsplit=1)[1]
    workdir = os.path.join(BASE_DIR, uuid.uuid4().hex)
    os.makedirs(workdir, exist_ok=True)

    await message.edit_text("Starting Download...")
    try:
        if cmd == "ytv":
            file_path, title, img, raw, meta = await download_video(url, workdir)

            ms = await message.edit_text("Uploading Video...")
            c = time.time()
            cover = BytesIO(raw) if raw else None

            await client.send_video(
                message.chat.id,
                video=file_path,
                thumb=img,
                cover=cover,
                duration=meta.get("duration", 0),
                width=meta.get("width", 0),
                height=meta.get("height", 0),
                supports_streaming=True,
                caption=f"<code>{title}</code>",
                progress=progress,
                progress_args=(ms, c, "<code>Uploading Video...</code>"),
            )
        else:
            file_path, title, img, duration = await download_music(url, workdir)

            ms = await message.edit_text("Uploading Audio...")
            c = time.time()

            await client.send_audio(
                message.chat.id,
                audio=file_path,
                thumb=img,
                duration=duration,
                title=title,
                caption=f"<code>{title}</code>",
                progress=progress,
                progress_args=(ms, c, "<code>Uploading Audio...</code>"),
            )
        await message.delete()
    except Exception as e:
        await message.edit_text(f"An error occurred: {format_exc(e)}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


modules_help["ytdl"] = {
    "ytv [name|link]*": "Download Video From YouTube",
    "ytm [name|link]*": "Download Music From YouTube",
}
