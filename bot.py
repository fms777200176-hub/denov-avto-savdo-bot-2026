
import os
import asyncio
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8545646821
CHANNEL = "@denov_avto_savdotest"

MODEL, YEAR, PRICE, CURRENCY, DETAILS, HIDE_PLATE, PHONE, PHOTOS, CONFIRM = range(9)

CANCEL_TEXT = "❌ Bekor qilish"
CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [[CANCEL_TEXT]],
    resize_keyboard=True,
    persistent=True,
)

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🚘 Denov Avto Savdo botiga xush kelibsiz!\n\n"
        "🎉 E'LON BERISH MUTLAQO BEPUL! 🎉\n\n"
        "💰 Hech qanday to'lov yo'q!\n"
        "📸 Mashina rasmlari va ma'lumotlarini yuboring.\n"
        "👨‍💼 E'lon admin tasdiqlagandan keyin kanalga chiqadi.\n\n"
        "👇 E'lon berishni boshlash uchun /elon yuboring.",
        reply_markup=CANCEL_KEYBOARD,
    )


async def elon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["photos"] = []
    await update.effective_message.reply_text(
        "🚗 Mashina modeli va rusumini yozing:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return MODEL


async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 Ishlab chiqarilgan yilini yozing:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return YEAR


async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["year"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 Narxini raqam bilan yozing:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return PRICE


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["price"] = update.message.text.strip()
    keyboard = [[
        InlineKeyboardButton("So'm", callback_data="UZS"),
        InlineKeyboardButton("Dollar ($)", callback_data="USD"),
    ]]
    await update.message.reply_text(
        "💵 Valyutani tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CURRENCY


async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["currency"] = q.data
    await q.message.reply_text(
        "📝 Qo'shimcha ma'lumot yozing. Bo'lmasa, «Yo'q» deb yozing:",
        reply_markup=CANCEL_KEYBOARD,
    )
    return DETAILS


async def details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["details"] = update.message.text.strip()
    keyboard = [[
        InlineKeyboardButton("🙈 Raqamni yashirish", callback_data="hide"),
        InlineKeyboardButton("👁 Raqam ko'rinsin", callback_data="show"),
    ]]
    await update.message.reply_text(
        "🚘 Davlat raqamini e'londa yashiramizmi?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return HIDE_PLATE


async def hide_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["hide_plate"] = q.data == "hide"
    await q.message.reply_text(
        "📞 Telefon raqamingizni yozing.\nMasalan: +998901234567",
        reply_markup=CANCEL_KEYBOARD,
    )
    return PHONE


async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text(
        "📸 Mashina rasmlarini yuboring.\n"
        "Kamida bitta rasm yuboring. Tugatgach /tayyor yozing.",
        reply_markup=CANCEL_KEYBOARD,
    )
    return PHOTOS


async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data.setdefault("photos", []).append(
            update.message.photo[-1].file_id
        )
        await update.message.reply_text(
            "✅ Rasm qabul qilindi. Yana rasm yuboring yoki /tayyor yozing.",
            reply_markup=CANCEL_KEYBOARD,
        )
    else:
        await update.message.reply_text(
            "Rasm yuboring yoki /tayyor yozing.",
            reply_markup=CANCEL_KEYBOARD,
        )
    return PHOTOS


def make_ad_text(data):
    currency_sign = "so'm" if data["currency"] == "UZS" else "$"
    plate = "Yashirilgan" if data["hide_plate"] else "Ko'rsatiladi"
    return (
        "🚘 AVTO E'LON\n\n"
        f"🚗 Model: {data['model']}\n"
        f"📅 Yil: {data['year']}\n"
        f"💰 Narx: {data['price']} {currency_sign}\n"
        f"📝 Ma'lumot: {data['details']}\n"
        f"🔢 Davlat raqami: {plate}\n"
        f"📞 Telefon: {data['phone']}"
    )


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data

    if not data.get("photos"):
        await update.message.reply_text(
            "⚠️ Avval kamida bitta rasm yuboring.",
            reply_markup=CANCEL_KEYBOARD,
        )
        return PHOTOS

    data["preview_text"] = make_ad_text(data)

    await update.message.reply_text(
        "👀 E'loningizni tekshirib chiqing:\n\n" + data["preview_text"],
        reply_markup=CANCEL_KEYBOARD,
    )

    for photo_id in data["photos"]:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo_id,
        )

    keyboard = [[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm:yes"),
        InlineKeyboardButton("🔄 Qaytadan kiritish", callback_data="confirm:restart"),
    ]]
    await update.message.reply_text(
        "Ma'lumotlar to'g'rimi?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "confirm:restart":
        context.user_data.clear()
        context.user_data["photos"] = []
        await q.message.reply_text(
            "🔄 Boshidan boshlaymiz.\n🚗 Mashina modeli va rusumini yozing:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return MODEL

    data = context.user_data
    user_id = q.from_user.id
    ad_key = f"ad:{user_id}"

    # Admin tasdiqlashi uchun e'lon va rasmlarni saqlaymiz.
    context.bot_data[ad_key] = {
        "text": data["preview_text"],
        "photos": list(data["photos"]),
    }

    keyboard = [[
        InlineKeyboardButton(
            "✅ Tasdiqlash va kanalga chiqarish",
            callback_data=f"approve:{user_id}",
        ),
        InlineKeyboardButton(
            "❌ Rad etish",
            callback_data=f"reject:{user_id}",
        ),
    ]]

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="🆕 YANGI E'LON — TEKSHIRING\n\n" + data["preview_text"],
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        for photo_id in data["photos"]:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo_id,
            )
    except Exception:
        context.bot_data.pop(ad_key, None)
        logging.exception("E'lonni adminga yuborishda xato")
        await q.message.reply_text(
            "⚠️ E'lon adminga yuborilmadi. Keyinroq qayta urinib ko'ring."
        )
        return ConversationHandler.END

    await q.message.reply_text(
        "✅ E'loningiz adminga tekshirish uchun yuborildi.\n"
        "Tasdiqlansa, kanalga joylanadi.",
        reply_markup=CANCEL_KEYBOARD,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if q.from_user.id != ADMIN_ID:
        await q.answer("Bu tugma faqat admin uchun!", show_alert=True)
        return

    await q.answer()
    action, user_id = q.data.split(":", 1)
    ad_key = f"ad:{user_id}"
    ad = context.bot_data.get(ad_key)

    if not ad:
        await q.message.reply_text(
            "⚠️ E'lon topilmadi yoki u allaqachon ko'rib chiqilgan."
        )
        return

    try:
        if action == "approve":
            await context.bot.send_message(
                chat_id=CHANNEL,
                text=ad["text"],
            )
            for photo_id in ad["photos"]:
                await context.bot.send_photo(
                    chat_id=CHANNEL,
                    photo=photo_id,
                )

            await q.message.reply_text("✅ E'lon test kanalga joylandi.")
            await context.bot.send_message(
                chat_id=int(user_id),
                text="🎉 E'loningiz admin tomonidan tasdiqlandi!",
            )
        else:
            await q.message.reply_text("❌ E'lon rad etildi.")
            await context.bot.send_message(
                chat_id=int(user_id),
                text="❌ Afsuski, e'loningiz rad etildi.",
            )

        context.bot_data.pop(ad_key, None)

    except Exception:
        logging.exception("Admin qarorini bajarishda xato")
        await q.message.reply_text(
            "⚠️ Amal bajarilmadi. Kanal ruxsatlari va bot loglarini tekshiring."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        "❌ E'lon berish bekor qilindi. Ma'lumotlar tozalandi.\n"
        "Qayta boshlash uchun /elon yuboring.",
        reply_markup=CANCEL_KEYBOARD,
    )
    return ConversationHandler.END


def make_cancel_handlers():
    return [
        CommandHandler("bekor", cancel),
        MessageHandler(filters.Regex(r"^❌ Bekor qilish$"), cancel),
    ]


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN sozlamasi kiritilmagan!")

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("elon", elon)],
        states={
            MODEL: make_cancel_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, model)
            ],
            YEAR: make_cancel_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, year)
            ],
            PRICE: make_cancel_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, price)
            ],
            CURRENCY: make_cancel_handlers() + [
                CallbackQueryHandler(currency, pattern=r"^(UZS|USD)$")
            ],
            DETAILS: make_cancel_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, details)
            ],
            HIDE_PLATE: make_cancel_handlers() + [
                CallbackQueryHandler(hide_plate, pattern=r"^(hide|show)$")
            ],
            PHONE: make_cancel_handlers() + [
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone)
            ],
            PHOTOS: make_cancel_handlers() + [
                CommandHandler("tayyor", finish),
                MessageHandler(filters.PHOTO, photos),
            ],
            CONFIRM: make_cancel_handlers() + [
                CallbackQueryHandler(confirm, pattern=r"^confirm:")
            ],
        },
        fallbacks=make_cancel_handlers(),
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conversation)
    app.add_handler(
        CallbackQueryHandler(review, pattern=r"^(approve|reject):")
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logging.info("Bot ishga tushdi.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
