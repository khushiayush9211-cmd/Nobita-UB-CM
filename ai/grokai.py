import os
import json
import html
import aiohttp

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram import enums

from utils import modules_help, prefix


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
CONFIG_FILE = "grok_config.json"


# =========================
# 💾 API STORAGE
# =========================
def load_key():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get("api_key")
    return None


def save_key(key):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"api_key": key}, f)


GROQ_API_KEY = load_key()


def get_key():
    return GROQ_API_KEY


# =========================
# ✂️ TEXT SPLITTER
# =========================
def split_text(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)]


# =========================
# 🤖 AI REQUEST
# =========================
async def fetch_free_ai_response(query: str, message: Message):
    api_key = get_key()

    if not api_key:
        return await message.edit("❌ Groq API key not set. Use .set_grok api <key>")

    await message.edit("🧠 Thinking...")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": query},
        ],
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_API_URL,
                headers=headers,
                json=payload,
            ) as resp:

                if resp.status == 401:
                    return await message.edit("❌ Invalid Groq API Key!")

                resp.raise_for_status()
                data = await resp.json()

        response_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "No response received.")
        )

        # =========================
        # 🔐 HTML SAFE ESCAPE
        # =========================
        query = html.escape(query)
        response_text = html.escape(response_text)

        full_text = f"🧠 Question:\n\n{query}\n\n💬 Answer:\n\n{response_text}"

        # =========================
        # 📏 HANDLE LIMIT
        # =========================
        parts = split_text(full_text)

        await message.edit(parts[0], parse_mode=enums.ParseMode.HTML)

        for part in parts[1:]:
            await message.reply(part, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await message.edit(f"❌ Error:\n\n{str(e)}")


# =========================
# 🤖 MAIN COMMAND
# =========================
@Client.on_message(filters.command("grok", prefix) & filters.me)
async def grok(_, message: Message):

    if len(message.command) < 2:
        return await message.edit(f"Usage: {prefix}grok <query>")

    query = " ".join(message.command[1:]).strip()

    await fetch_free_ai_response(query, message)


# =========================
# 🔑 SET API COMMAND
# =========================
@Client.on_message(filters.command("set_grok", prefix) & filters.me)
async def set_grok(_, message: Message):
    global GROQ_API_KEY

    if len(message.command) < 3 or message.command[1] != "api":
        return await message.edit(f"Usage: {prefix}set_grok api <key>")

    key = message.command[2]

    GROQ_API_KEY = key
    save_key(key)

    await message.edit("Save Ho Gya Mittr ✅!")


# =========================
# 📦 HELP
# =========================
modules_help["grokai"] = {
    "grok [query]": "Ask Groq AI (Llama 3.3 70B)",
    "set_grok api <key>": "Save Groq API key permanently",
}