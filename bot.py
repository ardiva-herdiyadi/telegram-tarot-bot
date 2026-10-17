import os
import sys
import io
import json
import random
import asyncio
import logging
from typing import Dict, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image

# Reconfigure stdout/stderr for Unicode/Windows terminal
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    constants
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN belum diset di file .env!")

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lightweight health-check HTTP server for Cloud Hosting (e.g. Render.com Free Tier)
port_env = os.getenv("PORT")
if port_env:
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Sanctum Tarot Bot is online and healthy.")

        def log_message(self, format, *args):
            pass

    def start_health_check_server():
        port = int(port_env)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health-check server running on port {port}")
        server.serve_forever()

    threading.Thread(target=start_health_check_server, daemon=True).start()

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "tarot_cards.json")
CARDS_DIR = os.path.join(BASE_DIR, "assets", "cards")
DAILY_DRAWS_PATH = os.path.join(BASE_DIR, "data", "daily_draws.json")

# Load Tarot Cards Data
with open(DATA_PATH, "r", encoding="utf-8") as f:
    TAROT_DB = json.load(f)
    CARDS_LIST = TAROT_DB["cards"]

logger.info(f"Loaded {len(CARDS_LIST)} tarot cards into memory.")


def load_daily_draws() -> dict:
    """Loads daily draw records from disk."""
    if os.path.exists(DAILY_DRAWS_PATH):
        try:
            with open(DAILY_DRAWS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def has_drawn_today(user_id: int) -> bool:
    """Checks if user has already drawn a daily card today."""
    records = load_daily_draws()
    user_record = records.get(str(user_id))
    if not user_record:
        return False
    today_str = datetime.now().strftime("%Y-%m-%d")
    return user_record.get("date") == today_str


def save_daily_draw(user_id: int, card_id: str) -> None:
    """Saves the user's daily card draw date."""
    records = load_daily_draws()
    today_str = datetime.now().strftime("%Y-%m-%d")
    records[str(user_id)] = {
        "date": today_str,
        "card_id": card_id
    }
    with open(DAILY_DRAWS_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def get_card_image_bytes(filename: str, is_reversed: bool = False) -> bytes:
    """Reads card image in standard upright orientation."""
    image_path = os.path.join(CARDS_DIR, filename)
    with open(image_path, "rb") as f:
        return f.read()


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Generates casual & friendly main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🔮 Cek 3 Kartu (Past, Now, Future)", callback_data="spread_3")
        ],
        [
            InlineKeyboardButton("✨ Kartu Harian Kamu (1x/hari)", callback_data="daily_card")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reading_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after reading - returns to main menu."""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Balik ke Menu Utama", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_daily_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after daily card - returns to main menu."""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Balik ke Menu Utama", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the user with a friendly, casual, and supportive vibe."""
    user = update.effective_user
    user_name = user.first_name if user else "Bestie"

    welcome_text = (
        f"✨ *Halo {user_name}! Welcome to Sanctum Tarot!* 🔮\n\n"
        "Lagi overthinking, penasaran sama masa depan, atau butuh insight buat langkah hidupmu? "
        "Santai aja, kamu ada di tempat yang tepat!\n\n"
        "Di sini, kita bakal baca energi dan arah langkahmu lewat 78 kartu Tarot Rider-Waite "
        "dengan gaya yang santai, positif, dan gampang banget dipahami. "
        "Nggak perlu tegang atau pusing, anggap aja lagi ngobrol bareng teman curhatmu. 😉\n\n"
        "👇 *Yuk, pilih mau cek apa hari ini:*"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text=welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )




async def perform_3_card_spread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Draws 3 unique cards and presents the reading step by step in casual style."""
    query = update.callback_query
    if query:
        await query.answer()
        chat_id = query.message.chat_id
    else:
        chat_id = update.message.chat_id

    # Initiation message
    init_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🃏 *Kartu lagi dikocok nih, bentar ya...* ✨\n\n"
            "Tarik napas santai dulu, buang overthinking-nya... "
            "Biar kartunya bisa ngasih sinyal & insight paling pas buat kamu! 🔮"
        ),
        parse_mode=constants.ParseMode.MARKDOWN
    )

    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(2.5)

    # Pick 3 unique cards
    drawn_cards = random.sample(CARDS_LIST, 3)

    positions = [
        {
            "roman": "1",
            "title": "1️⃣ KARTU 1 — MASA LALU",
            "subtitle": "Apa yang Udah Lewat & Membentuk Kamu",
            "key": "past"
        },
        {
            "roman": "2",
            "title": "2️⃣ KARTU 2 — MASA SEKARANG",
            "subtitle": "Situasi & Kondisi Kamu Saat Ini",
            "key": "present"
        },
        {
            "roman": "3",
            "title": "3️⃣ KARTU 3 — MASA DEPAN",
            "subtitle": "Peluang & Arah Langkah ke Depan",
            "key": "future"
        }
    ]

    card_summaries = []

    for i, (card, pos) in enumerate(zip(drawn_cards, positions)):
        # 50% chance upright or reversed
        is_reversed = random.choice([True, False])
        state_data = card["reversed"] if is_reversed else card["upright"]

        keywords_str = ", ".join(state_data["keywords"])
        interpretation = state_data[pos["key"]]

        caption = (
            f"🔮 *{pos['title']}*\n"
            f"_{pos['subtitle']}_\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎴 *{card['name_id']}*\n"
            f"🌈 *Vibes / Energi:* _{card['element']}_\n"
            f"🔑 *Kata Kunci:* _{keywords_str}_\n\n"
            f"💡 *Artinya Buat Kamu:*\n{interpretation}\n\n"
            f"💬 *Pesan Buat Kamu:*\n_{state_data['whisper']}_"
        )

        card_summaries.append({
            "name": card["name_id"].split(" (")[0],
            "pos": pos["title"],
            "whisper": state_data["whisper"]
        })

        # Send chat action uploading photo
        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)

        # Get image bytes (always upright as per clean aesthetics)
        photo_bytes = get_card_image_bytes(card["image"], is_reversed)

        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_bytes,
            caption=caption,
            parse_mode=constants.ParseMode.MARKDOWN
        )

        await asyncio.sleep(1.5)

    # Concluding synthesis message
    synthesis_text = (
        "✨ *BENANG MERAH BACAAN KAMU (Takeaway)*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🔙 *Masa Lalu:* `{card_summaries[0]['name']}`\n"
        f"⚡ *Masa Sekarang:* `{card_summaries[1]['name']}`\n"
        f"🚀 *Masa Depan:* `{card_summaries[2]['name']}`\n\n"
        "💡 *Rangkuman Santai:*\n"
        "_Semua yang udah lewat jadi pengalaman berharga yang bikin kamu makin kuat. "
        "Kondisi kamu saat ini butuh fokus, kejernihan pikiran, dan tindakan nyata. "
        "Dan ingat ya, masa depan itu bukan sesuatu yang kaku atau nakutin, "
        "tapi peluang terbuka yang bisa kamu bentuk sendiri lewat pilihanmu hari ini!_\n\n"
        "Tetap semangat, percaya sama intuisimu, and keep moving forward! 💪✨"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=synthesis_text,
        reply_markup=get_reading_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def perform_daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Draws 1 card for daily inspiration with strict 1-per-day limit."""
    query = update.callback_query
    user = update.effective_user
    user_id = user.id if user else 0

    if query:
        await query.answer()
        chat_id = query.message.chat_id
    else:
        chat_id = update.message.chat_id

    # Check if user already pulled daily card today
    if has_drawn_today(user_id):
        already_drawn_text = (
            "⏰ *Eits, Kuota Kartu Harianmu Udah Kepake Hari Ini!* 😉\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Kamu udah ambil 1 kartu harian buat hari ini ya.\n\n"
            "Biar fokus dan nggak kebanyakan mikir, resapi dulu pesan positif dari kartu yang tadi. "
            "Kartu harian baru bakal siap kamu ambil lagi besok pas ganti hari ya.\n\n"
            "Have a great and productive day! ✨"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=already_drawn_text,
            reply_markup=get_daily_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)

    card = random.choice(CARDS_LIST)
    is_reversed = random.choice([True, False])
    state_data = card["reversed"] if is_reversed else card["upright"]

    keywords_str = ", ".join(state_data["keywords"])

    caption = (
        f"✨ *KARTU HARIAN KAMU (Daily Vibes)*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎴 *{card['name_id']}*\n"
        f"🌈 *Vibes Hari Ini:* _{card['element']}_\n"
        f"🔑 *Kata Kunci:* _{keywords_str}_\n\n"
        f"💡 *Insight Buat Kamu:*\n{state_data['overview']}\n\n"
        f"💬 *Tips / Pesan Hari Ini:*\n_{state_data['whisper']}_\n\n"
        f"_Jadikan pesan positif ini buat nemenin dan semangatin harimu ya!_ ✨"
    )

    photo_bytes = get_card_image_bytes(card["image"], is_reversed)

    # Save today's draw
    save_daily_draw(user_id, card["id"])

    await context.bot.send_photo(
        chat_id=chat_id,
        photo=photo_bytes,
        caption=caption,
        reply_markup=get_daily_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button clicks."""
    query = update.callback_query
    data = query.data

    if data == "spread_3":
        await perform_3_card_spread(update, context)
    elif data == "daily_card":
        await perform_daily_card(update, context)
    elif data == "main_menu":
        await query.answer()
        await start_command(update, context)


async def handle_unwanted_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """If user types anything into chat, cleanly delete it and summon the main menu."""
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
        user = update.effective_user
        user_name = user.first_name if user else "Bestie"
        welcome_text = (
            f"✨ *Halo {user_name}!* Biar praktis dan nggak ribet, kita pakainya tombol interaktif di bawah ya. "
            "Yuk pilih mau cek apa hari ini:"
        )
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=welcome_text,
            reply_markup=get_main_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN
        )


async def post_init(application) -> None:
    """Registers commands in Telegram's Menu button so users always see the start menu."""
    await application.bot.set_my_commands([
        BotCommand("start", "🏠 Buka Menu Utama"),
        BotCommand("tarot", "🔮 Cek 3 Kartu (Past, Now, Future)"),
        BotCommand("daily", "✨ Ambil Kartu Harian Kamu")
    ])


def main() -> None:
    """Launches the Telegram Tarot Bot."""
    print("==========================================")
    print("[*] Menginisialisasi Bot Telegram Tarot...")
    print(f"[*] Koleksi Kartu: {len(CARDS_LIST)} kartu termuat.")
    print("==========================================")

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("tarot", perform_3_card_spread))
    application.add_handler(CommandHandler("baca", perform_3_card_spread))
    application.add_handler(CommandHandler("daily", perform_daily_card))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_unwanted_input))

    print("[+] Bot sedang berjalan (Polling aktif)...")
    print("[+] Tekan Ctrl+C untuk menghentikan bot.")
    application.run_polling()


if __name__ == "__main__":
    main()
