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
    """Generates mystical main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🔮 Buka Tabir Takdir (3 Kartu)", callback_data="spread_3")
        ],
        [
            InlineKeyboardButton("🌙 Bisikan Kartu Harian", callback_data="daily_card")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reading_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after reading - returns to altar."""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Kembali ke Altar", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_daily_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after daily card - strictly altar return only."""
    keyboard = [
        [
            InlineKeyboardButton("🏠 Kembali ke Altar", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the seeker with an atmospheric mystical aura."""
    user = update.effective_user
    user_name = user.first_name if user else "Pengelana Jiwa"

    welcome_text = (
        f"🕯️ *Salam dari Balik Tabir Rahasia, {user_name}...*\n\n"
        "Selamat datang di *Sanctum Tarot Takdir*.\n"
        "Asap dupa kemenyan telah membumbung tinggi, dan tirai antara alam nyata "
        "serta ruang batinmu kini perlahan tersingkap.\n\n"
        "Tujuh puluh delapan kartu purba telah dibersihkan di bawah sinar bulan purnama, "
        "menanti niat dan getaran batinmu.\n\n"
        "✨ *Apakah yang ingin kau tanyakan kepada semesta hari ini?*\n"
        "Pusatkan kesadaranmu, hembuskan keraguanmu, dan pilih jalanmu di bawah ini."
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
    """Draws 3 unique cards and presents the reading step by step."""
    query = update.callback_query
    if query:
        await query.answer()
        chat_id = query.message.chat_id
    else:
        chat_id = update.message.chat_id

    # Ritual initiation message
    init_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✨ *Ritual Pengocokan Kartu Dimulai...*\n\n"
            "🌀 _Tutup matamu sejenak._\n"
            "🌬️ _Tarik napas dalam, hembuskan perlahan._\n"
            "🕯️ _Pusatkan pertanyaan dan getaran batinmu ke dalam keheningan..._"
        ),
        parse_mode=constants.ParseMode.MARKDOWN
    )

    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    await asyncio.sleep(2.5)

    # Pick 3 unique cards
    drawn_cards = random.sample(CARDS_LIST, 3)

    positions = [
        {
            "roman": "I",
            "title": "MASA LALU (Akar Energi & Pelajaran Batin)",
            "key": "past"
        },
        {
            "roman": "II",
            "title": "MASA KINI (Realitas & Ujian Saat Ini)",
            "key": "present"
        },
        {
            "roman": "III",
            "title": "MASA DEPAN (Arah Takdir & Konsekuensi)",
            "key": "future"
        }
    ]

    card_summaries = []

    for i, (card, pos) in enumerate(zip(drawn_cards, positions)):
        # 50% chance upright or reversed
        is_reversed = random.choice([True, False])
        orientation_label = "⬇️ TERBALIK (Reversed)" if is_reversed else "⬆️ TEGAK (Upright)"
        state_data = card["reversed"] if is_reversed else card["upright"]

        keywords_str = ", ".join(state_data["keywords"])
        interpretation = state_data[pos["key"]]

        caption = (
            f"🔮 *KARTU {pos['roman']} — {pos['title']}*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎴 *{card['name_id']}*\n"
            f"✨ *Elemen/Domain:* _{card['element']}_\n"
            f"🔑 *Kata Kunci:* _{keywords_str}_\n\n"
            f"📖 *Makna Takdir:*\n{interpretation}\n\n"
            f"🕯️ *Bisikan Gaib:*\n_{state_data['whisper']}_"
        )

        card_summaries.append({
            "name": card["name_en"],
            "pos": pos["title"],
            "whisper": state_data["whisper"]
        })

        # Send chat action uploading photo
        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)

        # Get image bytes with rotation if reversed
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
        "📜 *IKATAN TIGA BENANG TAKDIR (Sintesis Gaib)*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"• *Akar (Masa Lalu):* `{card_summaries[0]['name']}`\n"
        f"• *Titik Pijak (Masa Kini):* `{card_summaries[1]['name']}`\n"
        f"• *Cakrawala (Masa Depan):* `{card_summaries[2]['name']}`\n\n"
        "🌌 *Renungan Penutup:*\n"
        "_Masa lalu telah menabur benihnya, dan masa kinimu adalah tanah tempat benih itu diuji. "
        "Masa depan yang terpampang di hadapanmu bukanlah garis mati yang tak terelakkan, melainkan seruan agar "
        "kamu bertindak dengan kesadaran penuh._\n\n"
        "🕯️ *Dengarkan bisikan batinmu sebelum melangkah kembali ke riuh dunia.*"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=synthesis_text,
        reply_markup=get_reading_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def perform_daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Draws 1 card for daily meditation with strict 1-per-day limit."""
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
            "🌙 *Tabir Harian Telah Tertutup...*\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Engkau telah mengambil satu helai bisikan takdir untuk hari ini.\n\n"
            "🕯️ _Pusatkan batinmu dan resapilah energi kartu yang telah kau peroleh hari ini. "
            "Altar harian baru akan terbuka kembali esok hari saat fajar menyingsing._"
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
        f"🌙 *BISIKAN KARTU HARIAN (Daily Meditation)*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎴 *{card['name_id']}*\n"
        f"✨ *Elemen:* _{card['element']}_\n"
        f"🔑 *Energi Hari Ini:* _{keywords_str}_\n\n"
        f"📖 *Pesan Hari Ini:*\n{state_data['overview']}\n\n"
        f"🕯️ *Nasihat Gaib:*\n_{state_data['whisper']}_\n\n"
        f"_Bawalah energi kartu ini dalam renungan hening sepanjang harimu._"
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
    """If user types anything into chat, cleanly summon the Altar with interactive buttons."""
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
        user = update.effective_user
        user_name = user.first_name if user else "Pengelana Jiwa"
        welcome_text = (
            f"🕯️ *Salam dari Balik Tabir Rahasia, {user_name}...*\n\n"
            "Selamat datang di *Sanctum Tarot Takdir*.\n"
            "Asap dupa kemenyan telah membumbung tinggi, dan tirai antara alam nyata "
            "serta ruang batinmu kini perlahan tersingkap.\n\n"
            "Tujuh puluh delapan kartu purba telah dibersihkan di bawah sinar bulan purnama, "
            "menanti niat dan getaran batinmu.\n\n"
            "✨ *Apakah yang ingin kau tanyakan kepada semesta hari ini?*\n"
            "Pusatkan kesadaranmu, hembuskan keraguanmu, dan pilih jalanmu di bawah ini."
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
        BotCommand("start", "🔮 Masuk ke Altar Takdir"),
        BotCommand("tarot", "🔮 Buka Tabir Takdir (3 Kartu)"),
        BotCommand("daily", "🌙 Bisikan Kartu Harian")
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
