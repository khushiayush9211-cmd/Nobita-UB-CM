import os
import aiohttp

from pyrogram import Client, filters
from pyrogram.types import Message

from utils import modules_help, prefix


@Client.on_message(filters.command(["tph", "telegraph"], prefix) & filters.me)
async def telegraph_upload(_, message: Message):
    reply = message.reply_to_message

    if not reply or not (reply.photo or reply.document):
        return await message.edit(
            f"<b>Reply to an image with {prefix}tph</b>"
        )

    status = await message.edit("<b>Downloading...</b>")

    file_path = None
    try:
        file_path = await reply.download()

        await status.edit("<b>Uploading to Telegraph...</b>")

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        filename = os.path.basename(file_path)

        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("file", file_bytes, filename=filename)

            async with session.post("https://telegra.ph/upload", data=form) as resp:
                result = await resp.json()

        if not isinstance(result, list):
            return await status.edit(
                f"<b>Upload failed:</b>\n<code>{result}</code>"
            )

        url = "https://telegra.ph" + result[0]["src"]

        await status.edit(
            f"<b>Telegraph URL:</b>\n<code>{url}</code>"
        )

    except Exception as e:
        await status.edit(
            f"<b>Error:</b>\n<code>{e}</code>"
        )

    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


modules_help["telegraph"] = {
    "tph, telegraph [reply image]": "Upload image to Telegraph",
}
