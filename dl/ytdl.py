import base64
import glob
import os
import time
from io import BytesIO

import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.scripts import import_library

yt_dlp = import_library("yt_dlp", "yt-dlp")

from urllib.parse import parse_qs, urlparse

from utils.scripts import format_exc, progress, resize_image
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from utils import modules_help, prefix

COOKIES_PATH = "downloads/ytdl/cookies.txt"
VIDEO_DIR = "downloads/ytdl/videos"
AUDIO_DIR = "downloads/ytdl/audios"

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

ydv_opts = {
    "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "addmetadata": True,
    "noplaylist": True,
    "merge_output_format": "mp4",
    "outtmpl": f"{VIDEO_DIR}/%(id)s.%(ext)s",
}

ydm_opts = {
    "format": "bestaudio/best",
    "default_search": "ytsearch",
    "geo_bypass": True,
    "nocheckcertificate": True,
    "noplaylist": True,
    "outtmpl": f"{AUDIO_DIR}/%(id)s.%(ext)s",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
}

API_URL = "https://apis.davidcyriltech.my.id/"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=120)


def restore_cookies_from_env():
    b64 = os.environ.get("COOKIES_B64")
    if b64:
        try:
            os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
            with open(COOKIES_PATH, "wb") as f:
                f.write(base64.b64decode(b64))
        except Exception:
            pass


# Bot start hote hi cookies restore karo (agar env var set hai)
restore_cookies_from_env()


def get_opts(base_opts: dict) -> dict:
    """Return a copy of opts, adding cookiefile if cookies.txt exists."""
    opts = dict(base_opts)
    if os.path.exists(COOKIES_PATH):
        opts["cookiefile"] = COOKIES_PATH
    return opts


def extract_video_id(url):
    try:
        parsed_url = urlparse(url)
        if parsed_url.hostname == "youtu.be":
            video_id = parsed_url.path[1:]
        else:
            query_params = parse_qs(parsed_url.query)
            video_id = query_params.get("v", [None])[0]
        return video_id
    except Exception:
        return None


async def search_api(query, is_videoId=False, video=False):
    query = str(query)
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        try:
            if is_videoId:
                async with session.get(
                    f"{API_URL}download/{'ytmp4' if video else 'ytmp3'}?url=https://youtube.com/watch?v="
                    + query
                ) as resp:
                    if resp.status != 200:
                        return None, None, None
                    data = await resp.json(content_type=None)
                    if data and data.get("success"):
                        result = data.get("result") or {}
                        title = result.get("title")
                        thumb_url = result.get("thumbnail")
                        link = result.get("download_url")
                        if title and link:
                            return title, thumb_url, link
            else:
                async with session.get(f"{API_URL}song?query=" + query) as resp:
                    if resp.status != 200:
                        return None, None, None
                    data = await resp.json(content_type=None)
                    if data and data.get("status"):
                        result = data.get("result")
                        if result:
                            title = result.get("title")
                            thumb_url = result.get("thumbnail")
                            sub = result.get("video") if video else result.get("audio")
                            link = (sub or {}).get("download_url")
                            if title and link:
                                return title, thumb_url, link
        except Exception:
            pass
    return None, None, None


async def download_thumb(thumb_url):
    if not thumb_url:
        return None
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(thumb_url) as resp:
                if resp.status != 200:
                    return None
                with open("thumbyt.jpg", "wb") as f:
                    f.write(await resp.read())
        return resize_image("thumbyt.jpg")
    except Exception:
        return None


async def download_file(url, path):
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download file (status {resp.status})")
            with open(path, "wb") as f:
                f.write(await resp.read())


def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def find_downloaded_file(directory, video_id, fallback_title=None):
    """Find the actual downloaded file by id, ignoring extension/postprocessing differences."""
    matches = glob.glob(os.path.join(directory, f"{video_id}.*"))
    # Ignore part files / temp files
    matches = [m for m in matches if not m.endswith((".part", ".ytdl", ".tmp"))]
    if matches:
        return matches[0]
    if fallback_title:
        matches = glob.glob(os.path.join(directory, f"{fallback_title}.*"))
        matches = [m for m in matches if not m.endswith((".part", ".ytdl", ".tmp"))]
        if matches:
            return matches[0]
    return None


async def download_video(url):
    try:
        with YoutubeDL(get_opts(ydv_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ExtractorError("Could not fetch video info.")
            i_d = info.get("id")
            title = info.get("title") or i_d
            thumb_url = info.get("thumbnail")
            img = await download_thumb(thumb_url)
            ydl.download([url])

        file_path = find_downloaded_file(VIDEO_DIR, i_d)
        if not file_path:
            raise FileNotFoundError("Downloaded video file not found.")
        return file_path, title, img, thumb_url

    except (DownloadError, ExtractorError, FileNotFoundError):
        video_id = extract_video_id(url)
        is_videoId = video_id is not None
        query = video_id if is_videoId else url
        title, thumb_url, songlink = await search_api(query, is_videoId, True)
        if not songlink or not title:
            raise Exception("yt-dlp failed and fallback API also unavailable.")
        img = await download_thumb(thumb_url)
        safe_title = "".join(c for c in title if c not in '<>:"/\\|?*')
        out_path = os.path.join(VIDEO_DIR, safe_title + ".mp4")
        await download_file(songlink, out_path)
        return out_path, title, img, thumb_url


async def download_music(url):
    try:
        with YoutubeDL(get_opts(ydm_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ExtractorError("Could not fetch audio info.")
            i_d = info.get("id")
            title = info.get("title") or i_d
            thumb_url = info.get("thumbnail")
            img = await download_thumb(thumb_url)
            ydl.download([url])

        file_path = find_downloaded_file(AUDIO_DIR, i_d)
        if not file_path:
            raise FileNotFoundError("Downloaded audio file not found.")
        return file_path, title, img

    except (DownloadError, ExtractorError, FileNotFoundError):
        video_id = extract_video_id(url)
        is_videoId = video_id is not None
        query = video_id if is_videoId else url
        title, thumb_url, songlink = await search_api(query, is_videoId)
        if not songlink or not title:
            raise Exception("yt-dlp failed and fallback API also unavailable.")
        img = await download_thumb(thumb_url)
        safe_title = "".join(c for c in title if c not in '<>:"/\\|?*')
        out_path = os.path.join(AUDIO_DIR, safe_title + ".mp3")
        await download_file(songlink, out_path)
        return out_path, title, img


@Client.on_message(filters.command(["ytv", "ytm"], prefix) & filters.me)
async def ytvm(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Please provide a YouTube URL to download.")

    if message.command[0] == "ytv":
        await message.edit_text("Starting Download...")
        file_path = None
        try:
            url = message.text.split(maxsplit=1)[1]
            file_path, title, img, thumb_url = await download_video(url)

            ms = await message.edit_text("Uploading Video...")
            c = time.time()

            cover = None
            if thumb_url:
                try:
                    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                        async with session.get(thumb_url) as resp:
                            if resp.status == 200:
                                cover = BytesIO(await resp.read())
                except Exception:
                    cover = None

            await client.send_video(
                message.chat.id,
                video=file_path,
                thumb=img,
                cover=cover,
                caption=f"<code>{title}</code>",
                progress=progress,
                progress_args=(ms, c, "<code>Uploading Video...</code>"),
            )
            await message.delete()
        except Exception as e:
            await message.edit_text(f"An error occurred: {format_exc(e)}")
        finally:
            safe_remove(file_path)
            safe_remove("thumbyt.jpg")

    elif message.command[0] == "ytm":
        await message.edit_text("Starting Download...")
        file_path = None
        try:
            url = message.text.split(None, 1)[1]
            file_path, title, img = await download_music(url)

            ms = await message.edit_text("Uploading Audio...")
            c = time.time()

            await client.send_audio(
                message.chat.id,
                audio=file_path,
                thumb=img,
                caption=f"<code>{title}</code>",
                progress=progress,
                progress_args=(ms, c, "<code>Uploading Audio...</code>"),
            )
            await message.delete()
        except Exception as e:
            await message.edit_text(f"An error occurred: {format_exc(e)}")
        finally:
            safe_remove(file_path)
            safe_remove("thumbyt.jpg")
    else:
        return await message.edit_text("Oh Damn Lol")


@Client.on_message(filters.command(["ytdlc"], prefix) & filters.me)
async def ytdlc(client: Client, message: Message):
    # .ytdlc delete -> remove saved cookies
    if len(message.command) > 1 and message.command[1].lower() == "delete":
        if os.path.exists(COOKIES_PATH):
            os.remove(COOKIES_PATH)
            return await message.edit_text("Cookies file deleted. yt-dlp will no longer use cookies.")
        else:
            return await message.edit_text("No cookies file found.")

    # .ytdlc as a reply to a document -> save cookies
    reply = message.reply_to_message
    if not reply or not reply.document:
        return await message.edit_text(
            "Reply to a `cookies.txt` file with `.ytdlc` to set it, "
            "or use `.ytdlc delete` to remove the saved cookies."
        )

    await message.edit_text("Saving cookies file...")
    try:
        os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
        await client.download_media(reply, file_name=COOKIES_PATH)
        await message.edit_text(
            "Cookies saved! yt-dlp will use this file for `.ytv` and `.ytm` "
            "until you run `.ytdlc delete`."
        )
    except Exception as e:
        await message.edit_text(f"An error occurred: {format_exc(e)}")


modules_help["ytdl"] = {
    "ytv [name|link]*": "Download Video From YouTube",
    "ytm [name|link]*": "Download Music From YouTube",
    "ytdlc": "Reply to a cookies.txt file to set cookies for yt-dlp",
    "ytdlc delete": "Delete the saved cookies file",
}