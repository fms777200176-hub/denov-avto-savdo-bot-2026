import os
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8545646821
CHANNEL = "@denov_avto_savdo"

MODEL, YEAR, PRICE, CURRENCY, DETAILS, HIDE_PLATE, PHOTOS, CONFIRM = range(8)

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚘 Denov Avto Savdo botiga xush kelibsiz!\n\n"
        "E'lon berish uchun /elon buyrug'ini yuboring."
    )


async def elon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photos"] = []
    await update.message.reply_text("🚗 Mashina modeli va rusumini yozing:")
    return MODEL


async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model"] = update.message.text
    await update.message.reply_text("📅 Ishlab chiqarilgan yilini yozing:")
    return YEAR


async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["year"] = update.message.text
    await update.message.reply_text("💰 Narxini raqam bilan yozing:")
    return PRICE


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["price"] = update.message.text
    keyboard = [[
        InlineKeyboardButton("So'm", callback_data="UZS"),
        InlineKeyboardButton("Dollar ($)", callback_data="USD")
    ]]
    await update.message.reply_text(
        "Valyutani tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CURRENCY


async def currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["currency"] = q.data
    await q.message.reply_text("📝 Qo'shimcha ma'lumot yozing (bo'lmasa — yo'q):")
    return DETAILS


async def details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["details"] = update.message.text
    keyboard = [[
        InlineKeyboardButton("Raqamni yashirish", callback_data="hide"),
        InlineKeyboardButton("Raqam ko'rinsin", callback_data="show")
    ]]
    await update.message.reply_text(
        "🚘 Avtomobil davlat raqamini yashiramizmi?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return HIDE_PLATE


async def hide_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["hide_plate"] = q.data == "hide"
    await q.message.reply_text(
        "📸 Endi mashina rasmlarini yuboring. Tugatgach /tayyor deb yozing."
    )
    return PHOTOS


async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data["photos"].append(update.message.photo[-1].file_id)
        await update.message.reply_text("✅ Rasm qabul qilindi. Yana rasm yuboring yoki /tayyor yozing.")
    else:
        await update.message.reply_text("Iltimos, mashina rasmini yuboring yoki /tayyor yozing.")
    return PHOTOS


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data
    plate = "Yashirilgan" if d["hide_plate"] else "Ko'rsatiladi"
    currency_sign = "so'm" if d["currency"] == "UZS" else "$"
    text = (
        "🚘 YANGI AVTO E'LON\n\n"
        f"🚗 Model: {d['model']}\n"
        f"📅 Yil: {d['year']}\n"
        f"💰 Narx: {d['price']} {currency_sign}\n"
        f"📝 Ma'lumot: {d['details']}\n"
        f"🔢 Davlat raqami: {plate}\n"
        f"👤 E'lon beruvchi ID: {update.effective_user.id}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{update.effective_user.id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{update.effective_user.id}")
    ]]
    context.bot_data[f"ad:{update.effective_user.id}"] = {
        "text": text, "photos": d["photos"]
    }
    await context.bot.send_message(
        chat_id=ADMIN_ID, text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    for photo in d["photos"]:
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo)
    await update.message.reply_text("✅ E'lon adminga tekshirish uchun yuborildi!")
    return ConversationHandler.END


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.answer("Bu tugma faqat admin uchun!", show_alert=True)
        return
    action, user_id = q.data.split(":")
    ad = context.bot_data.get(f"ad:{user_id}")
    if not ad:
        await q.message.reply_text("E'lon ma'lumoti topilmadi.")
        return
    if action == "approve":
        await context.bot.send_message(CHANNEL, ad["text"])
        for photo in ad["photos"]:
            await context.bot.send_photo(CHANNEL, photo)
        await q.message.reply_text("✅ E'lon kanalga joylandi.")
        await context.bot.send_message(int(user_id), "🎉 E'loningiz tasdiqlandi!")
    else:
        await q.message.reply_text("❌ E'lon rad etildi.")
        await context.bot.send_message(int(user_id), "E'loningiz rad etildi.")
    context.bot_data.pop(f"ad:{user_id}", None)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("E'lon berish bekor qilindi.")
    return ConversationHandler.END


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN sozlamasi kiritilmagan.")
    app = Application.builder().token(TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("elon", elon)],
        states={
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, model)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, year)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price)],
            CURRENCY: [CallbackQueryHandler(currency, pattern="^(UZS|USD)$")],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, details)],
            HIDE_PLATE: [CallbackQueryHandler(hide_plate, pattern="^(hide|show)$")],
            PHOTOS: [
                MessageHandler(filters.PHOTO, photos),
                CommandHandler("tayyor", finish)
            ],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conversation)
    app.add_handler(CallbackQueryHandler(review, pattern="^(approve|reject):"))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.wait_until_closed()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
