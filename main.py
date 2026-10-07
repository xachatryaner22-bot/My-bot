)import os
import re
import logging
import asyncio
import imageio_ffmpeg
from langdetect import detect, DetectorFactory
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

DetectorFactory.seed = 0

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# Новый токен:
TOKEN = "8733776616:AAEDPLDwuxLrm_1FoakNny48nvB6R03fiec" 

BANNED_USERS = set()
FORBIDDEN_CHARS = re.compile(r'[ğĞıƏə]')

def is_forbidden_language(text: str) -> bool:
    if FORBIDDEN_CHARS.search(text):
        return True
    
    clean_text = re.sub(r'http\S+|[^\w\s]', '', text).strip()
    if len(clean_text) > 3:
        try:
            lang = detect(clean_text)
            if lang in ['tr', 'az']:
                return True
        except Exception:
            pass
            
    return False

async def check_banned(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id in BANNED_USERS:
        return True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_banned(update):
        return

    keyboard = [[KeyboardButton("Help")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я бот для скачивания музыки.\n\n"
        "1. Отправь мне ссылку на YouTube или TikTok.\n"
        "2. Или напиши название песни (например: EMIN JONY Камин).",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_banned(update):
        return

    await update.message.reply_text(
        "Инструкция:\n"
        "• Отправь прямую ссылку на видео из TikTok или YouTube.\n"
        "• Или отправь название песни текстом."
    )

def download_audio(query_or_url: str) -> tuple[str, str]:
    is_url = bool(re.match(r'https?://', query_or_url))
    search_query = query_or_url if is_url else f"ytsearch1:{query_or_url}"

    ydl_opts = {
        'format': 'ba/b',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 15,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        }
    }

    os.makedirs('downloads', exist_ok=True)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_query, download=True)
        if 'entries' in info and info['entries']:
            info = info['entries'][0]
        
        title = info.get('title', 'audio')
        filename = ydl.prepare_filename(info)
        mp3_filename = os.path.splitext(filename)[0] + '.mp3'
        return mp3_filename, title

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in BANNED_USERS:
        return

    text = update.message.text.strip()

    if is_forbidden_language(text):
        BANNED_USERS.add(user_id)
        await update.message.reply_text("⛔ You have been banned for using a forbidden language.")
        return

    if text.lower() in ["help", "/help"]:
        await help_command(update, context)
        return

    clean_math = text.replace('x', '*').replace('Х', '*').replace('х', '*')
    if re.match(r'^\d+\s*[\+\-\*/]\s*\d+$', clean_math):
        try:
            result = eval(clean_math)
            await update.message.reply_text(f"Результат / Result: {result}")
            return
        except Exception:
            pass

    msg = await update.message.reply_text("🔎 Ищу и скачиваю трек, подождите...")

    try:
        loop = asyncio.get_event_loop()
        file_path, title = await asyncio.wait_for(
            loop.run_in_executor(None, download_audio, text),
            timeout=60.0
        )

        if os.path.exists(file_path):
            await update.message.reply_audio(
                audio=open(file_path, 'rb'),
                title=title,
                caption="Вот ваш трек! 🎵 / Here is your track!"
            )
            await msg.delete()
            os.remove(file_path)
        else:
            await msg.edit_text("❌ Ошибка при сохранении файла.")

    except asyncio.TimeoutError:
        await msg.edit_text("⏱ Время ожидания истекло. Попробуйте ссылку из TikTok!")
    except Exception as e:
        logging.error(f"Error downloading: {e}")
        await msg.edit_text("❌ Не удалось скачать трек. Попробуйте другую ссылку.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

