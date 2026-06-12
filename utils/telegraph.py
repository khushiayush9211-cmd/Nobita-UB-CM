import os
import aiohttp

from pyrogram import Client, filters
from pyrogram.types import Message

from utils import modules_help, prefix


@Client.on_message(filters.command(["tph", "telegraph", "catbox"], prefix) & filters.me)
async def telegraph_upload(_, message: Message):
    reply = message.reply_to_message

    if not reply or not (reply.photo or reply.document or reply.video):
        return await message.edit(
            f"<b>Reply to a media file with {prefix}tph</b>"
        )

    status = await message.edit("<b>Downloading...</b>")

    file_path = None
    try:
        file_path = await reply.download()

        await status.edit("<b>Uploading...</b>")

        filename = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("reqtype", "fileupload")
            form.add_field("fileToUpload", file_bytes, filename=filename)

            async with session.post("https://catbox.moe/user/api.php", data=form) as resp:
                result = (await resp.text()).strip()

        if not result.startswith("http"):
            return await status.edit(
                f"<b>Upload failed:</b>\n<code>{result}</code>"
            )

        await status.edit(
            f"<b>URL:</b>\n<code>{result}</code>"
        )

    except Exception as e:
        await status.edit(
            f"<b>Error:</b>\n<code>{e}</code>"
        )

    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


modules_help["telegraph"] = {
    "tph, telegraph, catbox [reply media]": "Upload media to Catbox",
}
