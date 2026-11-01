import os
import re
import sqlite3
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ChatPermissions,
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================== SOZLAMALAR ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8545646821"))

# Asosiy kanal: obunani tekshirish uchun
MAIN_CHANNEL = os.getenv("CHANNEL_ID", "@denov_avto_savdo").strip()
MAIN_CHANNEL_URL = os.getenv(
    "CHANNEL_URL", "https://t.me/denov_avto_savdo"
).strip()

# Tasdiqlangan e'lonlar to'g'ridan-to'g'ri asosiy kanalga joylanadi.
POST_CHANNEL = MAIN_CHANNEL

# Takliflar hisoblanadigan muhokama guruhi
GROUP_ID = os.getenv("GROUP_ID", "@Denov_avto_savdo_chat").strip()
GROUP_URL = os.getenv(
    "GROUP_URL", "https://t.me/Denov_avto_savdo_chat"
).strip()

# Hozircha 5 ta a’zo taklif qilish sharti o‘chirilgan; keyin qo‘shish mumkin.
INVITE_TARGET = 5
DB_PATH = os.getenv("DATABASE_PATH", "bot_data.sqlite3")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("DenovAvtoSavdo")

# Conversation holatlari
MODEL, YEAR, POSITION, MILEAGE, FUEL, COLOR, PAINT, PRICE, CURRENCY, EXTRA, LOCATION, PHONE, PHOTOS, REVIEW = range(14)

CANCEL_TEXT = "❌ Bekor qilish"
MENU_AD = "🚘 E’lon berish"
MENU_MY = "📋 Mening e’lonlarim"
MENU_INVITE = "👥 Taklif havolam"
MENU_RULES = "📜 E’lon berish shartlari"
MENU_ADMIN = "👨‍💻 Admin bilan bog‘lanish"


# ================== MA'LUMOTLAR BAZASI ==================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                invite_link TEXT,
                invite_count INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS counted_joins (
                user_id INTEGER NOT NULL,
                new_member_id INTEGER NOT NULL UNIQUE,
                joined_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                model TEXT, year TEXT, position TEXT, mileage TEXT,
                fuel TEXT, color TEXT, paint TEXT, price TEXT,
                currency TEXT, extra TEXT, location TEXT, phone TEXT,
                photos TEXT, status TEXT DEFAULT 'draft',
                channel_message_id INTEGER,
                created_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ad_photos (
                ad_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                PRIMARY KEY (ad_id, file_id)
            )
        """)


def ensure_user(user_id):
    with db() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(user_id, joined_at) VALUES(?, ?)",
            (user_id, datetime.utcnow().isoformat()),
        )


def get_user(user_id):
    with db() as con:
        return con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def set_invite(user_id, link):
    with db() as con:
        con.execute("UPDATE users SET invite_link=? WHERE user_id=?", (link, user_id))


def add_join(inviter_id, new_member_id):
    if inviter_id == new_member_id:
        return False
    with db() as con:
        try:
            con.execute(
                "INSERT INTO counted_joins(user_id, new_member_id, joined_at) VALUES(?,?,?)",
                (inviter_id, new_member_id, datetime.utcnow().isoformat()),
            )
            con.execute(
                "UPDATE users SET invite_count=invite_count+1 WHERE user_id=?",
                (inviter_id,),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def create_ad_row(user_id, data):
    with db() as con:
        cur = con.execute("""
            INSERT INTO ads(
                user_id, model, year, position, mileage, fuel, color, paint,
                price, currency, extra, location, phone, status, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)
        """, (
            user_id, data["model"], data["year"], data["position"],
            data["mileage"], data["fuel"], data["color"], data["paint"],
            data["price"], data["currency"], data["extra"], data["location"],
            data["phone"], datetime.utcnow().isoformat()
        ))
        ad_id = cur.lastrowid
        for file_id in data["photos"]:
            con.execute(
                "INSERT OR IGNORE INTO ad_photos(ad_id, file_id) VALUES(?,?)",
                (ad_id, file_id),
            )
        return ad_id


def get_ad(ad_id):
    with db() as con:
        ad = con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
        photos = con.execute(
            "SELECT file_id FROM ad_photos WHERE ad_id=? ORDER BY rowid", (ad_id,)
        ).fetchall()
    return ad, [p["file_id"] for p in photos]


# ================== MENYU VA MATNLAR ==================
def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MENU_AD)],
            [KeyboardButton(MENU_MY)],
            [KeyboardButton(MENU_RULES)],
            [KeyboardButton(MENU_ADMIN)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def rules_text():
    return (
        "📜 E’LON BERISH SHARTLARI\n\n"
        "✅ Asosiy kanalga obuna bo‘ling.\n"
        "🚘 E’lon joylashtirish bepul.\n"
        "🛡 E’lon avval administrator tekshiruvidan o‘tadi.\n"
        "📸 Rasmda davlat raqamini berkitmoqchi bo‘lsangiz, yuborishdan oldin uni telefonda xiralashtiring yoki yoping. Bot raqamni avtomatik aniqlab berkitmaydi.\n"
        "⚠️ Faqat to‘g‘ri ma’lumot yuboring."
    )


def access_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga obuna bo‘lish", url=MAIN_CHANNEL_URL)],
        [InlineKeyboardButton("💬 Muhokama guruhiga kirish", url=GROUP_URL)],
        [InlineKeyboardButton("🔄 Qayta tekshirish", callback_data="check_access")],
    ])


async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(MAIN_CHANNEL, user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except TelegramError as e:
        log.warning("Kanal obunasi tekshirilmadi: %s", e)
        return False


async def has_access(bot, user_id):
    # Hozircha faqat asosiy kanalga obuna tekshiriladi.
    # 5 ta a’zo taklif qilish sharti keyin alohida qo‘shiladi.
    subscribed = await is_subscribed(bot, user_id)
    return subscribed, True


async def show_gate(update, context, greeting=False):
    user_id = update.effective_user.id
    ensure_user(user_id)
    user = get_user(user_id)
    subscribed, invited = await has_access(context.bot, user_id)
    greeting_text = (
        f"👋 Assalomu alaykum, {update.effective_user.first_name}!\n"
        "Denov Avto Savdo botiga xush kelibsiz! 🚘❤️‍🔥\n\n"
        "🚗 Avtomobilingizni kanalimizda bepul e’lon qiling.\n\n"
    ) if greeting else ""
    if not subscribed:
        status = "📢 Avval asosiy kanalga obuna bo‘ling.\n\n"
        status += "Obuna bo‘lgach, “🔄 Qayta tekshirish” tugmasini bosing."
        await update.effective_message.reply_text(
            greeting_text + status,
            reply_markup=access_buttons(),
        )
    else:
        await update.effective_message.reply_text(
            greeting_text + "Asosiy menyudan kerakli bo‘limni tanlang 👇",
            reply_markup=main_menu(),
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_gate(update, context, greeting=True)


async def check_access_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ensure_user(query.from_user.id)
    user = get_user(query.from_user.id)
    subscribed, _ = await has_access(context.bot, query.from_user.id)
    if subscribed:
        await query.message.reply_text(
            "🎉 Kanal obunasi tasdiqlandi! Menyudan foydalanishingiz mumkin.",
            reply_markup=main_menu(),
        )
    else:
        await query.message.reply_text(
            "❌ Kanalga obuna aniqlanmadi. Obuna bo‘ling, so‘ng qayta tekshiring.",
            reply_markup=access_buttons(),
        )


async def get_personal_invite(update, context):
    user_id = update.effective_user.id
    ensure_user(user_id)
    user = get_user(user_id)
    if user["invite_link"]:
        link = user["invite_link"]
    else:
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=GROUP_ID,
                name=f"taklif-{user_id}",
                creates_join_request=False,
            )
            link = invite.invite_link
            set_invite(user_id, link)
        except TelegramError as e:
            log.exception("Taklif havolasi yaratilmadi: %s", e)
            await update.effective_message.reply_text(
                "❌ Shaxsiy havola yaratilmadi. Botni muhokama guruhiga administrator qilib qo‘ying va qayta urinib ko‘ring.",
                reply_markup=main_menu(),
            )
            return
    user = get_user(user_id)
    await update.effective_message.reply_text(
        f"👥 Sizning shaxsiy taklif havolangiz:\n{link}\n\n"
        f"Hisoblangan yangi a’zolar: {user['invite_count']}/{INVITE_TARGET}\n"
        "Faqat shu havola orqali guruhga yangi kirgan a’zolar hisoblanadi.",
        reply_markup=main_menu(),
    )


async def track_group_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm or cm.chat.id != int(GROUP_ID) if str(GROUP_ID).lstrip("-").isdigit() else False:
        # Username bilan sozlangan guruhda ham update'ni quyida tekshiramiz.
        pass
    if not cm:
        return
    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status
    joined = old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and new_status in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER
    )
    if not joined or not cm.invite_link:
        return
    invite_link = cm.invite_link.invite_link
    with db() as con:
        inviter = con.execute(
            "SELECT user_id FROM users WHERE invite_link=?", (invite_link,)
        ).fetchone()
        if inviter:
            add_join(inviter["user_id"], cm.new_chat_member.user.id)



# ================== GURUHDA OBUNANI MAJBURIY QILISH ==================
async def group_message_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruhda yozayotgan foydalanuvchi asosiy kanalga obuna ekanini tekshiradi."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or chat.type not in ("group", "supergroup"):
        return
    if user.is_bot:
        return

    try:
        subscribed = await is_subscribed(context.bot, user.id)
        if subscribed:
            # Obuna bo‘lsa, avvalgi cheklovni olib tashlashga urinib ko‘ramiz.
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            return

        try:
            await message.delete()
        except TelegramError:
            pass

        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"📢 {user.mention_html()} guruhda yozish uchun avval "
                    f'<a href="{MAIN_CHANNEL_URL}">asosiy kanalga obuna bo‘ling</a>.\n'
                    "Obuna bo‘lgach, guruhga qayta yozishingiz mumkin."
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError:
            pass
    except TelegramError as e:
        log.warning(
            "Guruh obuna cheklovi bajarilmadi. Bot guruhda administrator va "
            "a'zolarni cheklash huquqiga ega ekanini tekshiring: %s", e
        )


async def channel_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalga a'zo bo‘lganda guruhdagi yozish cheklovini olib tashlaydi."""
    cm = update.chat_member
    if not cm:
        return

    chat_username = getattr(cm.chat, "username", None)
    if chat_username and chat_username.lower() != MAIN_CHANNEL.lstrip("@").lower():
        return

    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status
    now_subscribed = new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )
    was_subscribed = old_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )
    if now_subscribed and not was_subscribed:
        try:
            await context.bot.restrict_chat_member(
                chat_id=GROUP_ID,
                user_id=cm.new_chat_member.user.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
        except TelegramError as e:
            log.warning("Obuna bo‘lgach guruh cheklovi yechilmadi: %s", e)


# ================== E'LON YIG'ISH ==================
def current_ad(context):
    return context.user_data.setdefault("ad", {"photos": []})


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("ad", None)
    await update.effective_message.reply_text(
        "❌ E’lon kiritish bekor qilindi.", reply_markup=main_menu()
    )
    return ConversationHandler.END


async def begin_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    subscribed, _ = await has_access(context.bot, user_id)
    if not subscribed:
        await show_gate(update, context)
        return ConversationHandler.END
    context.user_data["ad"] = {"photos": []}
    await update.effective_message.reply_text(
        "🚘 Avtomobil markasi va modelini yozing.\nMasalan: Chevrolet Cobalt\nBekor qilish uchun /cancel",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(CANCEL_TEXT)]], resize_keyboard=True),
    )
    return MODEL


async def get_model(update, context):
    current_ad(context)["model"] = update.message.text.strip()
    await update.message.reply_text("📅 Ishlab chiqarilgan yilini yozing. Masalan: 2018")
    return YEAR


async def get_year(update, context):
    text = update.message.text.strip()
    if not re.fullmatch(r"\d{4}", text):
        await update.message.reply_text("Yilni 4 ta raqam bilan yozing. Masalan: 2018")
        return YEAR
    current_ad(context)["year"] = text
    await update.message.reply_text("🔢 Pozitsiyasi yoki turini yozing. Masalan: 2-pozitsiya")
    return POSITION


async def get_position(update, context):
    current_ad(context)["position"] = update.message.text.strip()
    await update.message.reply_text("🛣 Yurgan masofasi. Masalan: 120 000 km yoki noma’lum")
    return MILEAGE


async def get_mileage(update, context):
    current_ad(context)["mileage"] = update.message.text.strip()
    await update.message.reply_text("⛽️ Yoqilg‘i turi. Masalan: Benzin / Metan")
    return FUEL


async def get_fuel(update, context):
    current_ad(context)["fuel"] = update.message.text.strip()
    await update.message.reply_text("🎨 Rangi qanday?")
    return COLOR


async def get_color(update, context):
    current_ad(context)["color"] = update.message.text.strip()
    await update.message.reply_text("🎨 Kraska holati qanday? Masalan: Toza, 2 ta detal bo‘yalgan")
    return PAINT


async def get_paint(update, context):
    current_ad(context)["paint"] = update.message.text.strip()
    await update.message.reply_text("💰 Narxini yozing. Masalan: 85 mln")
    return PRICE


async def get_price(update, context):
    current_ad(context)["price"] = update.message.text.strip()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 So‘m", callback_data="currency_UZS"),
        InlineKeyboardButton("🇺🇸 Dollar", callback_data="currency_USD"),
    ]])
    await update.message.reply_text("Valyutani tanlang:", reply_markup=keyboard)
    return CURRENCY


async def get_currency(update, context):
    query = update.callback_query
    await query.answer()
    current_ad(context)["currency"] = "so‘m" if query.data == "currency_UZS" else "dollar"
    await query.message.reply_text("✏️ Qo‘shimcha ma’lumot yozing yoki “Yo‘q” deb yuboring.")
    return EXTRA


async def get_extra(update, context):
    text = update.message.text.strip()
    current_ad(context)["extra"] = "" if text.lower() in ("yo‘q", "yoq", "yo'q", "-") else text
    await update.message.reply_text("📍 Manzilni yozing. Masalan: Denov, Surxondaryo")
    return LOCATION


async def get_location(update, context):
    current_ad(context)["location"] = update.message.text.strip()
    await update.message.reply_text("📞 Telefon raqamingizni yozing. Masalan: +998901234567")
    return PHONE


async def get_phone(update, context):
    phone = update.message.text.strip()
    if len(re.sub(r"\D", "", phone)) < 9:
        await update.message.reply_text("Telefon raqam to‘liq ko‘rinmayapti. Qayta yozing.")
        return PHONE
    current_ad(context)["phone"] = phone
    await update.message.reply_text(
        "🖼 Avtomobil rasmlarini yuboring.\n"
        "Bir nechta rasm yuborishingiz mumkin. Tugatgach “✅ Rasmlar tayyor” tugmasini bosing.\n"
        "Eslatma: davlat raqamini yashirmoqchi bo‘lsangiz, rasmning o‘zida oldindan berkitib yuboring.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("✅ Rasmlar tayyor")], [KeyboardButton(CANCEL_TEXT)],
            ],
            resize_keyboard=True,
        ),
    )
    return PHOTOS


async def get_photos(update, context):
    ad = current_ad(context)
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        if file_id not in ad["photos"]:
            ad["photos"].append(file_id)
        await update.message.reply_text(
            f"✅ Rasm qabul qilindi ({len(ad['photos'])}). Yana rasm yuboring yoki “✅ Rasmlar tayyor” bosing."
        )
        return PHOTOS
    if update.message.text == "✅ Rasmlar tayyor":
        if not ad["photos"]:
            await update.message.reply_text("Kamida bitta rasm yuboring.")
            return PHOTOS
        ad_id = create_ad_row(update.effective_user.id, ad)
        context.user_data["pending_ad_id"] = ad_id
        preview = format_ad(ad)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Tasdiqlash va adminga yuborish", callback_data=f"userconfirm_{ad_id}")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"usercancel_{ad_id}")],
        ])
        await update.message.reply_text(
            "📋 E’loningizni tekshiring:\n\n" + preview + "\n\nTasdiqlaysizmi?",
            reply_markup=keyboard,
        )
        return REVIEW
    await update.message.reply_text("Rasm yuboring yoki “✅ Rasmlar tayyor” tugmasini bosing.")
    return PHOTOS


def format_ad(ad):
    extra = ad.get("extra", "")
    text = (
        f"🚗❤️‍🔥 #{re.sub(r'[^A-Za-zА-Яа-яЁё0-9]', '', ad['model'].split()[0])} "
        f"{ad['model']} SOTILADI!\n"
        f"📅 Ishlab chiqarilgan yili: {ad['year']}-yil\n"
        f"🔢 Pozitsiya / Turi: {ad['position']}\n"
        f"🛣 Yurgan masofasi: {ad['mileage']}\n"
        f"⛽️ Yoqilg‘i turi: {ad['fuel']}\n"
        f"🎨 Rangi: {ad['color']}\n"
        f"🎨 Kraska holati: {ad['paint']}\n"
        f"💰 Narxi: {ad['price']} {ad['currency']}\n"
    )
    if extra:
        text += f"\n✏️ Qo‘shimcha ma’lumot:\n{extra}\n"
    text += (
        f"\n📍 Manzil: {ad['location']}\n\n"
        f"📞 Aloqa uchun: {ad['phone']}\n\n"
        "📌 Biz bilan tez va oson soting❗️\n"
        "👇👇👇👇👇 (E’lon berish bepul!)\n\n"
        "📱 @Denov_avto_savdo\n"
        "💬 @Denov_avto_savdo_chat"
    )
    return text


async def user_ad_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, ad_id_str = query.data.split("_", 1)
    ad_id = int(ad_id_str)
    ad, photos = get_ad(ad_id)
    if not ad or ad["user_id"] != query.from_user.id:
        await query.message.reply_text("Bu e’lon sizga tegishli emas.")
        return ConversationHandler.END
    if action == "usercancel":
        with db() as con:
            con.execute("UPDATE ads SET status='cancelled' WHERE id=?", (ad_id,))
        await query.message.reply_text("E’lon bekor qilindi.", reply_markup=main_menu())
        context.user_data.pop("ad", None)
        return ConversationHandler.END

    caption = (
        f"🆕 Yangi e’lon #{ad_id}\n"
        f"Yuboruvchi ID: {ad['user_id']}\n\n"
        + format_ad(dict(ad))
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"adminapprove_{ad_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"adminreject_{ad_id}"),
    ]])
    try:
        if len(photos) == 1:
            await context.bot.send_photo(
                ADMIN_ID, photos[0], caption=caption[:1024], reply_markup=keyboard
            )
        else:
            media = []
            from telegram import InputMediaPhoto
            for i, file_id in enumerate(photos[:10]):
                media.append(InputMediaPhoto(
                    media=file_id,
                    caption=caption[:1024] if i == 0 else None,
                ))
            await context.bot.send_media_group(ADMIN_ID, media)
            await context.bot.send_message(ADMIN_ID, f"E’lon #{ad_id} uchun qaror:", reply_markup=keyboard)
        with db() as con:
            con.execute("UPDATE ads SET status='waiting_admin' WHERE id=?", (ad_id,))
        await query.message.reply_text(
            "✅ E’lon adminga tekshiruv uchun yuborildi. Tasdiqlansa kanalga joylanadi.",
            reply_markup=main_menu(),
        )
    except TelegramError as e:
        log.exception("Adminga yuborishda xato: %s", e)
        await query.message.reply_text("❌ E’lonni adminga yuborib bo‘lmadi. Keyinroq urinib ko‘ring.")
    context.user_data.pop("ad", None)
    return ConversationHandler.END


async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Bu tugma faqat administrator uchun.", show_alert=True)
        return
    await query.answer()
    action, ad_id_str = query.data.split("_", 1)
    ad_id = int(ad_id_str)
    ad, photos = get_ad(ad_id)
    if not ad:
        await query.message.reply_text("E’lon topilmadi.")
        return
    if action == "adminreject":
        with db() as con:
            con.execute("UPDATE ads SET status='rejected' WHERE id=?", (ad_id,))
        await query.message.reply_text(f"❌ E’lon #{ad_id} rad etildi.")
        try:
            await context.bot.send_message(ad["user_id"], f"❌ E’loningiz (#{ad_id}) administrator tomonidan rad etildi.")
        except TelegramError:
            pass
        return

    caption = format_ad(dict(ad))
    try:
        if len(photos) == 1:
            sent = await context.bot.send_photo(POST_CHANNEL, photos[0], caption=caption[:1024])
            msg_id = sent.message_id
        else:
            media = []
            from telegram import InputMediaPhoto
            for i, file_id in enumerate(photos[:10]):
                media.append(InputMediaPhoto(media=file_id, caption=caption[:1024] if i == 0 else None))
            sent_media = await context.bot.send_media_group(POST_CHANNEL, media)
            msg_id = sent_media[0].message_id
        with db() as con:
            con.execute(
                "UPDATE ads SET status='posted_test', channel_message_id=? WHERE id=?",
                (msg_id, ad_id),
            )
        await query.message.reply_text(f"✅ E’lon #{ad_id} kanalimizga joylandi.")
        try:
            await context.bot.send_message(
                ad["user_id"],
                f"🎉 E’loningiz tasdiqlandi va kanalimizga joylandi!\n{MAIN_CHANNEL_URL}"
            )
        except TelegramError:
            pass
    except TelegramError as e:
        log.exception("Kanalga joylashda xato: %s", e)
        await query.message.reply_text(
            "❌ Kanalga joylab bo‘lmadi. Bot asosiy kanalda administrator ekanini va POST_CHANNEL_ID sozlamasini tekshiring."
        )


# ================== MENYU HANDLERLARI ==================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    ensure_user(user_id)

    if text == CANCEL_TEXT:
        return await cancel(update, context)

    if text == MENU_AD:
        return await begin_ad(update, context)
    if text == MENU_INVITE:
        await update.message.reply_text(
            "👥 Taklif havolasi va 5 ta a’zo sharti hozircha o‘chirilgan. Keyinroq qo‘shamiz.",
            reply_markup=main_menu(),
        )
        return
    if text == MENU_RULES:
        context.user_data.pop("ad", None)
        await update.message.reply_text(rules_text(), reply_markup=main_menu())
        return ConversationHandler.END
    if text == MENU_MY:
        with db() as con:
            rows = con.execute(
                "SELECT id, model, status, created_at FROM ads WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,),
            ).fetchall()
        if not rows:
            await update.message.reply_text("Hozircha e’lonlaringiz yo‘q.", reply_markup=main_menu())
        else:
            lines = ["📋 Mening e’lonlarim:"]
            for row in rows:
                lines.append(f"#{row['id']} — {row['model']} — {row['status']}")
            await update.message.reply_text("\n".join(lines), reply_markup=main_menu())
        context.user_data.pop("ad", None)
        return ConversationHandler.END
    if text == MENU_ADMIN:
        context.user_data.pop("ad", None)
        await update.message.reply_text(
            "👨‍💻 Administrator bilan bog‘lanish: @DAS_Admin",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    # Menyu tashqarisidagi oddiy xabarlar uchun foydalanuvchini yo'naltiramiz.
    context.user_data.pop("ad", None)
    await update.message.reply_text(
        "👇 Kerakli bo‘limni menyudan tanlang.", reply_markup=main_menu()
    )
    return ConversationHandler.END


async def error_handler(update, context):
    log.exception("Bot xatosi:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable kiritilmagan.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Menyu tugmalari suhbatning har qanday bosqichida ishlasin.
    active_menu = filters.Regex(r"^(❌ Bekor qilish|🚘 E’lon berish|📋 Mening e’lonlarim|📜 E’lon berish shartlari|👨‍💻 Admin bilan bog‘lanish)$")
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^🚘 E’lon berish$"), begin_ad)],
        states={
            MODEL: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_model)],
            YEAR: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)],
            POSITION: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_position)],
            MILEAGE: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_mileage)],
            FUEL: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_fuel)],
            COLOR: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_color)],
            PAINT: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_paint)],
            PRICE: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            CURRENCY: [MessageHandler(active_menu, menu_handler), CallbackQueryHandler(get_currency, pattern=r"^currency_(UZS|USD)$")],
            EXTRA: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_extra)],
            LOCATION: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            PHONE: [MessageHandler(active_menu, menu_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PHOTOS: [
                MessageHandler(active_menu, menu_handler),
                MessageHandler(filters.PHOTO, get_photos),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_photos),
            ],
            REVIEW: [MessageHandler(active_menu, menu_handler), CallbackQueryHandler(user_ad_decision, pattern=r"^user(confirm|cancel)_\d+$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(r"^❌ Bekor qilish$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(check_access_button, pattern=r"^check_access$"))
    app.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^admin(approve|reject)_\d+$"))
    app.add_handler(ChatMemberHandler(track_group_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(channel_member_update, ChatMemberHandler.CHAT_MEMBER), group=1)
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_message_gate),
        group=0,
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    app.add_error_handler(error_handler)

    log.info("Denov Avto Savdo bot ishga tushmoqda.")
    app.run_polling(
        allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"]
    )


if __name__ == "__main__":
    main()
