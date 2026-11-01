import os
import re
import logging
import sqlite3
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputMediaPhoto,
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ChatMemberHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DenovAvtoSavdo")

# ===== SOZLAMALAR =====
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8545646821"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@denov_avto_savdotest")
CHANNEL_URL = os.getenv(
    "CHANNEL_URL", "https://t.me/denov_avto_savdotest"
)
GROUP_ID_TEXT = os.getenv("GROUP_ID", "").strip()
GROUP_ID = int(GROUP_ID_TEXT) if GROUP_ID_TEXT.lstrip("-").isdigit() else GROUP_ID_TEXT
GROUP_URL = os.getenv(
    "GROUP_URL", "https://t.me/Denov_avto_savdo_chat"
)
INVITE_TARGET = 5
DB_PATH = os.getenv("DATABASE_PATH", "bot_data.sqlite3")

# Suhbat bosqichlari
(
    MODEL, YEAR, POSITION, MILEAGE, FUEL, COLOR, PAINT,
    PRICE, CURRENCY, EXTRA, LOCATION, PHONE, PHOTOS
) = range(13)


# ===== MA'LUMOTLAR BAZASI =====
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                invite_count INTEGER DEFAULT 0,
                invite_name TEXT,
                unlocked INTEGER DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS joins_counted (
                joined_id INTEGER PRIMARY KEY,
                inviter_id INTEGER NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                model TEXT,
                year TEXT,
                position TEXT,
                mileage TEXT,
                fuel TEXT,
                color TEXT,
                paint TEXT,
                price TEXT,
                currency TEXT,
                extra TEXT,
                location TEXT,
                phone TEXT,
                photos TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)


def save_user(user):
    with db() as con:
        con.execute("""
            INSERT INTO users(user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (user.id, user.username or "", user.first_name or ""))


def user_row(user_id):
    with db() as con:
        return con.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def invite_count(user_id):
    row = user_row(user_id)
    return int(row["invite_count"]) if row else 0


# ===== MENYU =====
def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🚘 E’lon berish")],
            [KeyboardButton("📋 Mening e’lonlarim")],
            [KeyboardButton("🔗 Taklif havolam")],
            [KeyboardButton("ℹ️ Shartlar"),
             KeyboardButton("👨‍💼 Admin bilan bog‘lanish")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def subscription_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📢 Asosiy kanalga obuna bo‘lish", url=CHANNEL_URL
        )],
        [InlineKeyboardButton(
            "✅ Obunani tekshirish", callback_data="check_sub"
        )],
    ])


async def subscribed(context, user_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except TelegramError as exc:
        log.warning("Obunani tekshirish xatosi: %s", exc)
        return False


async def create_invite(context, user_id):
    if not GROUP_ID:
        return None
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            name=f"ref_{user_id}",
            creates_join_request=False,
        )
        return link.invite_link
    except TelegramError:
        log.exception("Guruh havolasini yaratib bo‘lmadi")
        return None


async def check_access(update, context):
    user = update.effective_user
    if not user:
        return False

    save_user(user)

    if not await subscribed(context, user.id):
        message = (
            "🚫 Botdan foydalanish uchun avval asosiy kanalga obuna bo‘ling.\n"
            "Obuna bo‘lgach, «Obunani tekshirish» tugmasini bosing."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                message, reply_markup=subscription_buttons()
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                message, reply_markup=subscription_buttons()
            )
        return False

    count = invite_count(user.id)
    if count < INVITE_TARGET:
        link = await create_invite(context, user.id)
        message = (
            f"✅ Kanal obunasi tasdiqlandi!\n\n"
            f"💬 Guruhga {INVITE_TARGET} ta yangi a’zo taklif qiling.\n"
            f"Hisoblangan takliflar: {count}/{INVITE_TARGET}\n\n"
            "Faqat bot yaratgan shaxsiy havolangiz orqali kirgan "
            "yangi a’zolar hisoblanadi."
        )
        buttons = []
        if link:
            buttons.append([
                InlineKeyboardButton("👥 Guruhga taklif qilish", url=link)
            ])
        buttons.append([
            InlineKeyboardButton("🔄 Qayta tekshirish", callback_data="check_sub")
        ])
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                message, reply_markup=InlineKeyboardMarkup(buttons)
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                message, reply_markup=InlineKeyboardMarkup(buttons)
            )
        return False

    with db() as con:
        con.execute("UPDATE users SET unlocked=1 WHERE user_id=?", (user.id,))
    return True
    # ===== E'LON BERISH =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    save_user(user)

    if not await check_access(update, context):
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Assalomu alaykum! 🚗\n"
        "Denov Avto Savdo botiga xush kelibsiz!\n\n"
        "E’lon joylash bepul.",
        reply_markup=main_menu()
    )
    return ConversationHandler.END


async def check_sub_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    if not await subscribed(context, user.id):
        await query.message.reply_text(
            "❌ Hali asosiy kanalga obuna bo‘lmagansiz.",
            reply_markup=subscription_buttons()
        )
        return

    count = invite_count(user.id)
    if count < INVITE_TARGET:
        link = await create_invite(context, user.id)
        buttons = []
        if link:
            buttons.append([
                InlineKeyboardButton("👥 Guruhga taklif qilish", url=link)
            ])
        buttons.append([
            InlineKeyboardButton("🔄 Qayta tekshirish", callback_data="check_sub")
        ])
        await query.message.reply_text(
            f"✅ Kanal obunasi tasdiqlandi.\n"
            f"👥 Guruhga yana {INVITE_TARGET - count} ta yangi a’zo taklif qiling.\n"
            f"Hisob: {count}/{INVITE_TARGET}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    await query.message.reply_text(
        "✅ Shartlar bajarilgan. Menyudan foydalanishingiz mumkin.",
        reply_markup=main_menu()
    )


async def begin_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return ConversationHandler.END

    context.user_data["ad"] = {"photos": []}

    await update.effective_message.reply_text(
        "🚘 Avtomobil markasi va modelini yozing.\n"
        "Masalan: Opel Vectra",
        reply_markup=ReplyKeyboardMarkup(
            [[CANCEL_TEXT]], resize_keyboard=True
        )
    )
    return MODEL


async def get_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["model"] = update.message.text.strip()
    await update.message.reply_text("📅 Ishlab chiqarilgan yili?")
    return YEAR


async def get_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["year"] = update.message.text.strip()
    await update.message.reply_text("🔢 Pozitsiyasi yoki turi?")
    return POSITION


async def get_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["position"] = update.message.text.strip()
    await update.message.reply_text("🛣 Yurgan masofasi (km)?")
    return MILEAGE


async def get_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["mileage"] = update.message.text.strip()
    await update.message.reply_text("⛽️ Yoqilg‘i turi?")
    return FUEL


async def get_fuel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["fuel"] = update.message.text.strip()
    await update.message.reply_text("🎨 Avtomobil rangi?")
    return COLOR


async def get_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["color"] = update.message.text.strip()
    await update.message.reply_text("🎨 Kraska holati qanday?")
    return PAINT


async def get_paint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["paint"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 Narxini yozing.\nMasalan: 10 mln yoki 1500"
    )
    return PRICE


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["price"] = update.message.text.strip()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇿 So‘m", callback_data="currency_UZS"),
            InlineKeyboardButton("🇺🇸 Dollar", callback_data="currency_USD"),
        ]
    ])
    await update.message.reply_text(
        "Valyutani tanlang:", reply_markup=keyboard
    )
    return CURRENCY


async def get_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency = query.data.replace("currency_", "")
    context.user_data["ad"]["currency"] = (
        "so‘m" if currency == "UZS" else "dollar"
    )

    await query.message.reply_text("✏️ Qo‘shimcha ma’lumot yozing.\n"
                                   "Bo‘lmasa: Yo‘q deb yozing.")
    return EXTRA


async def get_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["ad"]["extra"] = (
        "" if text.lower() in ("yo‘q", "yo'q", "yoq", "-") else text
    )
    await update.message.reply_text("📍 Viloyat va tumanini yozing.")
    return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad"]["location"] = update.message.text.strip()
    await update.message.reply_text(
        "📞 Aloqa telefon raqamini yozing.\n"
        "Masalan: +998901234567"
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if len(re.sub(r"\D", "", phone)) < 9:
        await update.message.reply_text(
            "❌ Telefon raqami noto‘g‘ri ko‘rinadi. Qayta yozing."
        )
        return PHONE

    context.user_data["ad"]["phone"] = phone
    await update.message.reply_text(
        "📸 Avtomobil rasmlarini yuboring.\n"
        "Bir nechta rasm yuborishingiz mumkin.\n"
        "Tugatgach, «✅ Rasmlar tayyor» tugmasini bosing.",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Rasmlar tayyor"], [CANCEL_TEXT]],
            resize_keyboard=True
        )
    )
    return PHOTOS


async def get_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photos = context.user_data["ad"].setdefault("photos", [])
        photos.append(update.message.photo[-1].file_id)

        await update.message.reply_text(
            f"✅ Rasm qabul qilindi. Jami: {len(photos)} ta.\n"
            "Yana rasm yuboring yoki «✅ Rasmlar tayyor» tugmasini bosing."
        )
        return PHOTOS

    if update.message.text == "✅ Rasmlar tayyor":
        photos = context.user_data["ad"].get("photos", [])
        if not photos:
            await update.message.reply_text(
                "❗ Kamida bitta avtomobil rasmi yuboring."
            )
            return PHOTOS

        ad = context.user_data["ad"]
        ad["user_id"] = update.effective_user.id
        ad["username"] = update.effective_user.username or ""
        ad["first_name"] = update.effective_user.first_name or ""

        with db() as con:
            cur = con.execute("""
                INSERT INTO ads (
                    user_id, username, model, year, position, mileage,
                    fuel, color, paint, price, currency, extra,
                    location, phone, photos
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ad["user_id"], ad["username"], ad["model"], ad["year"],
                ad["position"], ad["mileage"], ad["fuel"], ad["color"],
                ad["paint"], ad["price"], ad["currency"], ad["extra"],
                ad["location"], ad["phone"], ",".join(photos)
            ))
            ad_id = cur.lastrowid

        caption = format_ad(ad, ad_id)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Tasdiqlash", callback_data=f"approve_{ad_id}"
            ),
            InlineKeyboardButton(
                "❌ Rad etish", callback_data=f"reject_{ad_id}"
            )
        ]])

        try:
            if len(photos) == 1:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photos[0],
                    caption=caption,
                    reply_markup=keyboard
                )
            else:
                media = [
                    InputMediaPhoto(
                        media=photo,
                        caption=caption if i == 0 else None
                    )
                    for i, photo in enumerate(photos[:10])
                ]
                sent = await context.bot.send_media_group(
                    chat_id=ADMIN_ID, media=media
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📥 E’lon #{ad_id} — tasdiqlash yoki rad etish:",
                    reply_markup=keyboard
                )
        except TelegramError:
            log.exception("Adminga e’lon yuborilmadi")
            await update.message.reply_text(
                "❌ E’lon admin uchun yuborilmadi. Keyinroq qayta urinib ko‘ring."
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "✅ E’loningiz adminga tekshiruv uchun yuborildi.\n"
            "Tasdiqlangach, kanalga joylanadi.",
            reply_markup=main_menu()
        )
        context.user_data.pop("ad", None)
        return ConversationHandler.END

    await update.message.reply_text(
        "📸 Iltimos, rasm yuboring yoki «✅ Rasmlar tayyor» tugmasini bosing."
    )
    return PHOTOS


def format_ad(ad, ad_id=None):
    model = ad.get("model", "—")
    hashtags = " ".join(
        "#" + re.sub(r"[^A-Za-zА-Яа-яЁё0-9_]", "", word)
        for word in model.split() if word
    )

    text = (
        f"🚗❤️‍🔥 {hashtags} SOTILADI!\n"
        f"📅 Ishlab chiqarilgan yili: {ad.get('year', '—')}-yil\n"
        f"🔢 Pozitsiya / Turi: {ad.get('position', '—')}\n"
        f"🛣 Yurgan masofasi: {ad.get('mileage', '—')} km\n"
        f"⛽️ Yoqilg‘i turi: {ad.get('fuel', '—')}\n"
        f"🎨 Rangi: {ad.get('color', '—')}\n"
        f"🎨 Kraska holati: {ad.get('paint', '—')}\n"
        f"💰 Narxi: {ad.get('price', '—')} {ad.get('currency', '')}\n"
    )

    extra = ad.get("extra", "")
    if extra:
        text += f"\n✏️ Qo‘shimcha ma’lumot:\n{extra}\n"

    text += (
        f"\n📍 Manzil: {ad.get('location', '—')}\n"
        f"\n📞 Aloqa uchun: {ad.get('phone', '—')}\n"
        "\n📌 Biz bilan tez va oson soting❗️"
        "\n👇👇👇👇👇 (E’lon berish bepul!)"
        "\n\n📱@Denov_avto_savdo"
        "\n💬@Denov_avto_savdo_chat"
    )
    return text
    # ===== BEKOR QILISH =====
CANCEL_TEXT = "❌ Bekor qilish"


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("ad", None)
    await update.effective_message.reply_text(
        "❌ E’lon berish bekor qilindi.",
        reply_markup=main_menu()
    )
    return ConversationHandler.END


# ===== GURUHGA TAKLIFLARNI SANASH =====
async def track_group_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    member_update = update.chat_member
    if not member_update:
        return

    chat = member_update.chat
    if GROUP_ID and str(chat.id) != str(GROUP_ID):
        return

    old_status = member_update.old_chat_member.status
    new_status = member_update.new_chat_member.status

    # Faqat guruhga yangi kirgan haqiqiy a'zolar sanaladi.
    was_member = old_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )
    is_member = new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )

    if was_member or not is_member:
        return

    invite = member_update.invite_link
    if not invite:
        return

    invite_url = invite.invite_link
    with db() as con:
        inviter = con.execute(
            "SELECT user_id FROM users WHERE invite_name=?",
            (invite_url,)
        ).fetchone()

        if not inviter:
            return

        inviter_id = inviter["user_id"]
        joined_id = member_update.new_chat_member.user.id

        if joined_id == inviter_id:
            return

        try:
            con.execute(
                "INSERT INTO joins_counted(joined_id, inviter_id) VALUES (?, ?)",
                (joined_id, inviter_id)
            )
        except sqlite3.IntegrityError:
            return

        con.execute("""
            UPDATE users
            SET invite_count = invite_count + 1
            WHERE user_id=?
        """, (inviter_id,))

    try:
        await context.bot.send_message(
            inviter_id,
            f"👥 Yangi a’zo taklifingiz orqali guruhga qo‘shildi!\n"
            f"Hisob: {invite_count(inviter_id)}/{INVITE_TARGET}"
        )
    except TelegramError:
        pass


# Shaxsiy havolani yaratish va saqlash
async def create_invite(context, user_id):
    if not GROUP_ID:
        return None

    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            name=f"ref_{user_id}",
            creates_join_request=False
        )
        with db() as con:
            con.execute(
                "UPDATE users SET invite_name=? WHERE user_id=?",
                (link.invite_link, user_id)
            )
        return link.invite_link
    except TelegramError:
        log.exception("Taklif havolasi yaratilmadi")
        return None


# ===== ADMIN TASDIG'I =====
async def admin_decision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        await query.answer("Bu tugma faqat admin uchun.", show_alert=True)
        return

    action, ad_id_text = query.data.split("_", 1)
    ad_id = int(ad_id_text)

    with db() as con:
        ad = con.execute(
            "SELECT * FROM ads WHERE id=?", (ad_id,)
        ).fetchone()

        if not ad:
            await query.message.reply_text("❌ E’lon topilmadi.")
            return

        if ad["status"] != "pending":
            await query.message.reply_text(
                "ℹ️ Bu e’lon bo‘yicha qaror allaqachon qabul qilingan."
            )
            return

        if action == "reject":
            con.execute(
                "UPDATE ads SET status='rejected' WHERE id=?", (ad_id,)
            )

    if action == "reject":
        try:
            await context.bot.send_message(
                ad["user_id"],
                f"❌ E’loningiz admin tomonidan rad etildi. E’lon ID: {ad_id}"
            )
        except TelegramError:
            pass

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ E’lon #{ad_id} rad etildi.")
        return

    photos = ad["photos"].split(",") if ad["photos"] else []
    ad_data = dict(ad)
    caption = format_ad(ad_data, ad_id)

    try:
        if not photos:
            await query.message.reply_text(
                "❌ E’londa rasm yo‘q. Kanalga yuborilmadi."
            )
            return

        if len(photos) == 1:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photos[0],
                caption=caption
            )
        else:
            media = [
                InputMediaPhoto(
                    media=photo,
                    caption=caption if i == 0 else None
                )
                for i, photo in enumerate(photos[:10])
            ]
            await context.bot.send_media_group(
                chat_id=CHANNEL_ID,
                media=media
            )

        with db() as con:
            con.execute(
                "UPDATE ads SET status='approved' WHERE id=?", (ad_id,)
            )

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ E’lon #{ad_id} kanalga joylandi."
        )

        try:
            await context.bot.send_message(
                ad["user_id"],
                "🎉 E’loningiz admin tomonidan tasdiqlandi va kanalga joylandi!"
            )
        except TelegramError:
            pass

    except TelegramError:
        log.exception("E'lonni kanalga yuborishda xato")
        await query.message.reply_text(
            "❌ Kanalga yuborilmadi. Botning kanal admin huquqlarini tekshiring."
        )


# ===== MENYU TUGMALARI =====
async def menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🚘 E’lon berish":
        if not await check_access(update, context):
            return
        await begin_ad(update, context)
        return

    if text == "📋 Mening e’lonlarim":
        with db() as con:
            rows = con.execute("""
                SELECT id, model, status FROM ads
                WHERE user_id=? ORDER BY id DESC LIMIT 10
            """, (user_id,)).fetchall()

        if not rows:
            await update.message.reply_text("Sizda hali e’lon yo‘q.")
            return

        labels = {
            "pending": "⏳ Tekshiruvda",
            "approved": "✅ Tasdiqlangan",
            "rejected": "❌ Rad etilgan",
        }
        result = ["📋 Oxirgi e’lonlaringiz:"]
        for row in rows:
            result.append(
                f"#{row['id']} — {row['model']} — "
                f"{labels.get(row['status'], row['status'])}"
            )
        await update.message.reply_text("\n".join(result))
        return

    if text == "🔗 Taklif havolam":
        link = await create_invite(context, user_id)
        if not link:
            await update.message.reply_text(
                "❌ Havola yaratilmadi. Guruh ID va admin huquqlarini tekshirish kerak."
            )
            return

        await update.message.reply_text(
            f"👥 Guruhga yangi a’zolarni taklif qiling.\n"
            f"Hisob: {invite_count(user_id)}/{INVITE_TARGET}\n\n"
            f"Shaxsiy havolangiz:\n{link}"
        )
        return

    if text == "ℹ️ Shartlar":
        await update.message.reply_text(
            "📌 E’lon berish bepul.\n"
            "1. Asosiy kanalga obuna bo‘ling.\n"
            "2. Guruhga shaxsiy havolangiz orqali 5 ta yangi a’zo taklif qiling.\n"
            "3. Avtomobil ma’lumotlarini to‘ldiring.\n"
            "4. E’lon admin tekshiruvidan keyin kanalga chiqariladi."
        )
        return

    if text == "👨‍💼 Admin bilan bog‘lanish":
        await update.message.reply_text(
            "👨‍💼 Admin: @DAS_Admin"
        )
        return


# ===== XATOLARNI QAYD ETISH =====
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    log.error("Bot xatosi:", exc_info=context.error)


# ===== BOTNI ISHGA TUSHIRISH =====
def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi. Render Environment Variables bo‘limiga kiriting."
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^🚘 E’lon berish$"),
                begin_ad
            )
        ],
        states={
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_model)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)],
            POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_position)],
            MILEAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mileage)],
            FUEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fuel)],
            COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_color)],
            PAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_paint)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            CURRENCY: [CallbackQueryHandler(get_currency, pattern=r"^currency_(UZS|USD)$")],
            EXTRA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_extra)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, get_photos),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_photos),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(r"^❌ Bekor qilish$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conversation)
    app.add_handler(CallbackQueryHandler(check_sub_button, pattern=r"^check_sub$"))
    app.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^(approve|reject)_\d+$"))
    app.add_handler(
        ChatMemberHandler(track_group_member, ChatMemberHandler.CHAT_MEMBER)
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            menu_handler
        )
    )
    app.add_error_handler(error_handler)

    log.info("Denov Avto Savdo bot ishga tushmoqda...")
    app.run_polling(
        allowed_updates=[
            "message", "callback_query", "chat_member"
        ]
    )


if __name__ == "__main__":
    main()
