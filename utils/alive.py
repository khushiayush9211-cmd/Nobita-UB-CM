import time
import os
import json
from sys import version_info

from pyrogram import Client, filters
from pyrogram import __version__ as pyro_version

from utils import modules_help, prefix

StartTime = time.time()

version = "2.1.1"
python_version = f"{version_info.major}.{version_info.minor}.{version_info.micro}"

# Permanent JSON config aur media storage path setup
CONFIG_FILE = os.path.expanduser("~/Moon-Userbot/alive_config.json")
LOCAL_MEDIA_PATH = os.path.expanduser("~/Moon-Userbot/custom_alive_media")

# Default fallback photo (Nobita)
DEFAULT_PHOTO = "https://graph.org/file/9847fe7306fb853eec02d.jpg"

def get_saved_media():
    """Config file se saved media ka path ya link nikalne ke liye"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                path = data.get("media_path")
                if path and os.path.exists(path):
                    return path, data.get("media_type", "Photo")
        except Exception:
            pass
    return DEFAULT_PHOTO, "Photo"

def save_media_config(path, media_type):
    """Config file me permanent entry karne ke liye"""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"media_path": path, "media_type": media_type}, f)


def get_readable_time(seconds: int) -> str:
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
            
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
        
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)

    return ping_time


@Client.on_message(filters.command(["setalivepic", "sap"], prefix) & filters.me)
async def set_alive_pic(client, message):
    if not message.reply_to_message or not (message.reply_to_message.photo or message.reply_to_message.animation or message.reply_to_message.video):
        await message.edit("<b>Bhai, kisi Photo ya GIF/Video par reply karke command do!</b>")
        return

    await message.edit("<b>Media download ho raha hai, please wait... ⏳</b>")

    # Local folder check/create karo
    if not os.path.exists(LOCAL_MEDIA_PATH):
        os.makedirs(LOCAL_MEDIA_PATH)

    # Purani saved files ko clean karo taaki storage full na ho
    for file in os.listdir(LOCAL_MEDIA_PATH):
        try:
            os.remove(os.path.join(LOCAL_MEDIA_PATH, file))
        except Exception:
            pass

    try:
        # File type detect aur download logic (Direct local saving to prevent expiration)
        if message.reply_to_message.photo:
            media_type = "Photo"
            ext = ".jpg"
        elif message.reply_to_message.animation:
            media_type = "GIF"
            ext = ".mp4"
        else:
            media_type = "Video"
            ext = ".mp4"

        target_path = os.path.join(LOCAL_MEDIA_PATH, f"alive_media{ext}")
        
        # Telegram se file direct Termux me save hogi
        await client.download_media(message.reply_to_message, file_name=target_path)
        
        # Permanent save in JSON file
        save_media_config(target_path, media_type)
        
        await message.edit(f"<b>Ho Gya Mittr 👽</b>")
    except Exception as e:
        await message.edit(f"<b>Error aaya download me:</b> <code>{e}</code>")


@Client.on_message(filters.command("alive", prefix) & filters.me)
async def alive(client, message):
    uptime = get_readable_time(int(time.time() - StartTime))
    owner_name = client.me.first_name if client.me else "Master"
    
    reply_msg = (
        "<b>The Moon-Userbot...</b>\n\n"
        "Hi, I'm alive with my pro master 😎.\n\n"
        f"✯ <b>Owner</b> - <code>{owner_name} [#sunstone]</code>\n"
        f"✯ <b>UpTime</b> - <code>{uptime}</code>\n"
        f"✯ <b>Python</b> - <code>{python_version}</code>\n"
        f"✯ <b>Pyrogram</b> - <code>{pyro_version}</code>"
    )
    
    await message.delete()
    
    media, media_type = get_saved_media()
    
    try:
        # Agar default link hai
        if isinstance(media, str) and media.startswith("https"):
            await client.send_photo(
                chat_id=message.chat.id,
                photo=media,
                caption=reply_msg
            )
        else:
            # Agar local saved file hai, toh dynamic type sending bina file_id expiration ke
            if media_type == "Photo":
                await client.send_photo(chat_id=message.chat.id, photo=media, caption=reply_msg)
            elif media_type == "GIF":
                await client.send_animation(chat_id=message.chat.id, animation=media, caption=reply_msg)
            else:
                await client.send_video(chat_id=message.chat.id, video=media, caption=reply_msg)
    except Exception:
        # Ekdum safe side text fallback
        await client.send_message(
            chat_id=message.chat.id,
            text=reply_msg,
            disable_web_page_preview=True
        )


modules_help["alive"] = {
    "alive": "Check bot alive status",
    "setalivepic": "Reply to any photo/GIF/Video to permanently save it (Shortcut: .sap)",
}
