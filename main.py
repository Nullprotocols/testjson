import asyncio
import aiohttp
import json
import html
from io import BytesIO
from typing import Dict, Any, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from telegram.constants import ParseMode

import config

# ---------- Helper: Force channel check ----------
async def is_user_joined_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user has joined ALL force channels."""
    for channel_id in config.FORCE_CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

async def force_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send join buttons for all force channels."""
    buttons = []
    for idx, username in enumerate(config.FORCE_CHANNEL_USERNAMES):
        if username:
            buttons.append([InlineKeyboardButton(f"📢 चैनल {idx+1} जॉइन करें", url=f"https://t.me/{username}")])
    buttons.append([InlineKeyboardButton("✅ मैं जॉइन कर चुका हूँ", callback_data="check_join")])
    await update.message.reply_text(
        "🤝 *स्वागत है!*\n\n"
        "बॉट का उपयोग करने के लिए आपको नीचे दिए गए सभी चैनल जॉइन करने होंगे।\n"
        "जॉइन करने के बाद 'मैं जॉइन कर चुका हूँ' बटन दबाएँ।",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if await is_user_joined_channels(user_id, context):
        await query.edit_message_text(
            "✅ अब आप बॉट का उपयोग कर सकते हैं।\n"
            "कृपया कोई फ़ोन नंबर भेजें (जैसे +919876543210 या 9876543210)"
        )
    else:
        await query.edit_message_text(
            "❌ आपने सभी चैनल जॉइन नहीं किए हैं। कृपया ऊपर दिए लिंक से जॉइन करें और फिर से दबाएँ।"
        )

# ---------- API call ----------
async def fetch_number_info(phone_number: str) -> Dict[str, Any]:
    """Call your API and return JSON."""
    params = {config.API_PARAM_NAME: phone_number}
    if config.API_KEY:
        params["apikey"] = config.API_KEY
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(config.API_URL, params=params, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"API returned {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

# ---------- Formatting (remove branding, add emoji) ----------
def format_number_info(data: Dict[str, Any], queried_number: str = "") -> str:
    """Convert JSON to human readable Hinglish text with emojis."""
    # Remove branding fields
    clean_data = {k: v for k, v in data.items() 
                  if k not in ["API_Developer", "channel_name", "channel_link"]}
    
    total = clean_data.get("total_records", 0)
    results = clean_data.get("result", [])
    
    header = f"📞 *नंबर जानकारी*"
    if queried_number:
        header += f" : `{queried_number}`"
    header += f"\n\n🔍 *कुल रिकॉर्ड्स:* {total}\n"
    
    if total == 0:
        return header + "\n❌ कोई रिकॉर्ड नहीं मिला।"
    
    msg = header + "\n" + "─" * 30 + "\n"
    
    for idx, rec in enumerate(results, 1):
        msg += f"\n*रिकॉर्ड #{idx}*\n"
        msg += f"👤 नाम: {rec.get('name', 'N/A')}\n"
        msg += f"👨 पिता का नाम: {rec.get('father_name', 'N/A')}\n"
        msg += f"🏠 पता: {rec.get('address', 'N/A')}\n"
        msg += f"📡 सर्कल: {rec.get('circle', 'N/A')}\n"
        msg += f"📱 मोबाइल: {rec.get('mobile', 'N/A')}\n"
        if rec.get('alternate'):
            msg += f"📞 वैकल्पिक: {rec.get('alternate')}\n"
        if rec.get('email'):
            msg += f"📧 ईमेल: {rec.get('email')}\n"
        msg += f"🆔 ID: {rec.get('id', 'N/A')}\n"
        msg += "─" * 30 + "\n"
    
    return msg

# ---------- File helper for long messages ----------
async def send_as_file(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, filename: str = "result.txt"):
    """Send long text as a .txt file."""
    file_obj = BytesIO(text.encode('utf-8'))
    file_obj.name = filename
    await context.bot.send_document(chat_id=chat_id, document=file_obj)

# ---------- Log to channel ----------
async def log_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    name: str,
    query_number: str,
    output_text: str,
    is_long: bool = False,
    file_bytes: Optional[BytesIO] = None
):
    """Send user search details + output to log channel."""
    user_info = f"👤 *User:* {html.escape(name)} (@{html.escape(username)}) | ID: `{user_id}`"
    search_info = f"🔎 *Searched number:* `{html.escape(query_number)}`"
    log_header = f"{user_info}\n{search_info}\n\n📄 *Output:*\n"
    
    if is_long and file_bytes:
        # Send file to log channel
        file_bytes.seek(0)
        caption = f"{log_header}\n(Output too long, attached as file)"
        await context.bot.send_document(
            chat_id=config.LOG_CHANNEL_ID,
            document=file_bytes,
            caption=caption[:1024],
            parse_mode=ParseMode.HTML
        )
    else:
        # Send text (trim if needed)
        full_log = log_header + output_text
        if len(full_log) > 4096:
            # Still send as file for safety
            file_bytes = BytesIO(full_log.encode('utf-8'))
            file_bytes.name = "log_output.txt"
            await context.bot.send_document(
                chat_id=config.LOG_CHANNEL_ID,
                document=file_bytes,
                caption=f"Log for {user_id}",
                parse_mode=ParseMode.HTML
            )
        else:
            await context.bot.send_message(
                chat_id=config.LOG_CHANNEL_ID,
                text=full_log,
                parse_mode=ParseMode.HTML
            )

# ---------- Bot command handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_user_joined_channels(user_id, context):
        await update.message.reply_text(
            "🙏 नमस्ते! मैं एक नंबर इन्फो बॉट हूँ।\n"
            "मुझे कोई भी फ़ोन नंबर भेजें (जैसे +919876543210) और मैं API से जानकारी लाऊंगा।\n"
            "लंबे आउटपुट के लिए फाइल भेजी जाएगी।"
        )
    else:
        await force_channel_message(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔹 *निर्देश:*\n"
        "• कोई भी फ़ोन नंबर भेजें (देश कोड के साथ या बिना)\n"
        "• उदाहरण: `+919876543210` या `9876543210`\n"
        "• बॉट आपको नंबर से जुड़े रिकॉर्ड दिखाएगा\n\n"
        "🔸 *सीमा:* एक बार में एक नंबर\n"
        "🔹 *सहायता:* @YourSupport (optional)",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or "NoUsername"
    name = user.first_name or ""
    
    # Force channel check
    if not await is_user_joined_channels(user_id, context):
        await force_channel_message(update, context)
        return
    
    phone_number = update.message.text.strip()
    # Simple validation
    if not (phone_number.startswith('+') or phone_number.isdigit()):
        await update.message.reply_text("⚠️ कृपया सही फ़ोन नंबर भेजें। (जैसे +919876543210 या 9876543210)")
        return
    
    await update.message.reply_text("⏳ जानकारी लाई जा रही है, कृपया प्रतीक्षा करें...")
    
    # Call API
    raw_data = await fetch_number_info(phone_number)
    if "error" in raw_data:
        error_msg = f"❌ API त्रुटि: {raw_data['error']}"
        await update.message.reply_text(error_msg)
        await log_to_channel(context, user_id, username, name, phone_number, error_msg, is_long=False)
        return
    
    formatted_output = format_number_info(raw_data, queried_number=phone_number)
    
    # Send to user (as file if too long)
    is_long = len(formatted_output) > 4096
    file_obj = None
    if is_long:
        file_obj = BytesIO(formatted_output.encode('utf-8'))
        file_obj.name = "number_info.txt"
        await context.bot.send_document(
            chat_id=user_id,
            document=file_obj,
            caption="📄 आपका रिजल्ट (लंबा आउटपुट)"
        )
    else:
        await update.message.reply_text(formatted_output, parse_mode=ParseMode.MARKDOWN)
    
    # Log to channel with same file if any
    await log_to_channel(
        context, user_id, username, name, phone_number,
        formatted_output, is_long=is_long, file_bytes=file_obj
    )

# ---------- Error handler ----------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")
    try:
        await update.message.reply_text("⚠️ कोई आंतरिक त्रुटि हुई। कृपया बाद में प्रयास करें।")
    except:
        pass

# ---------- Main webhook setup ----------
def main():
    if not config.TOKEN or not config.API_URL:
        raise ValueError("Missing BOT_TOKEN or API_URL in environment variables")
    
    app = Application.builder().token(config.TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
    app.add_error_handler(error_handler)
    
    # Webhook
    if config.WEBHOOK_URL:
        webhook_url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH}"
        app.run_webhook(
            listen="0.0.0.0",
            port=config.PORT,
            url_path=config.WEBHOOK_PATH,
            webhook_url=webhook_url
        )
    else:
        # Fallback to polling (for local testing)
        print("No WEBHOOK_URL set, using polling...")
        app.run_polling()

if __name__ == "__main__":
    main()
