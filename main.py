# main.py – Complete Number Info Bot (Webhook + Self-Ping + Pagination + Full Admin + PDF/TXT Output)

import logging
import os
import json
import asyncio
import httpx
import secrets
import csv
import tempfile
from datetime import datetime, timedelta
from aiohttp import web
from fpdf import FPDF

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from dotenv import load_dotenv

import config
from database import *

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable not set!")

# ---------- Bot Initialization ----------
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# ---------- Force Join Channels ----------
FORCE_JOIN_CHANNELS = config.FORCE_JOIN_CHANNELS

# ---------- Helper Functions ----------
def clean_api_response(data, extra_blacklist=None):
    if extra_blacklist is None:
        extra_blacklist = []
    blacklist = [item.lower() for item in extra_blacklist]
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            if key.lower() in blacklist:
                continue
            if isinstance(value, dict):
                cleaned[key] = clean_api_response(value, extra_blacklist)
            elif isinstance(value, list):
                cleaned[key] = [clean_api_response(item, extra_blacklist) if isinstance(item, dict) else item for item in value]
            else:
                cleaned[key] = value
        return cleaned
    elif isinstance(data, list):
        return [clean_api_response(item, extra_blacklist) if isinstance(item, dict) else item for item in data]
    return data

def format_number_info(raw_data: dict, queried_number: str = "") -> str:
    clean_data = clean_api_response(raw_data, config.NUM_API.get('extra_blacklist', []))
    total = clean_data.get("total_records", 0)
    results = clean_data.get("result", [])
    header = f"📞 *Number Info*"
    if queried_number:
        header += f" : `{queried_number}`"
    header += f"\n\n🔍 *Total Records:* {total}\n"
    if total == 0:
        return header + "\n❌ No records found."
    msg = header + "\n" + "─" * 30 + "\n"
    for idx, rec in enumerate(results, 1):
        msg += f"\n*Record #{idx}*\n"
        msg += f"👤 Name: {rec.get('name', 'N/A')}\n"
        msg += f"👨 Father's Name: {rec.get('father_name', 'N/A')}\n"
        msg += f"🏠 Address: {rec.get('address', 'N/A')}\n"
        msg += f"📡 Circle: {rec.get('circle', 'N/A')}\n"
        msg += f"📱 Mobile: {rec.get('mobile', 'N/A')}\n"
        if rec.get('alternate'):
            msg += f"📞 Alternate: {rec.get('alternate')}\n"
        if rec.get('email'):
            msg += f"📧 Email: {rec.get('email')}\n"
        msg += f"🆔 ID: {rec.get('id', 'N/A')}\n"
        msg += "─" * 30 + "\n"
    msg += f"\n👨‍💻 Developer: {config.DEV_USERNAME}\n"
    msg += f"⚡ Powered by: {config.POWERED_BY}"
    return msg

def generate_pdf_report(data: dict, queried_number: str) -> bytes:
    """Generate professional PDF report for number info."""
    clean_data = clean_api_response(data, config.NUM_API.get('extra_blacklist', []))
    total = clean_data.get("total_records", 0)
    results = clean_data.get("result", [])
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Number Information Report", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Query: {queried_number}", ln=True, align="C")
    pdf.cell(0, 6, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Total Records Found: {total}", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    if total == 0:
        pdf.set_font("Arial", "I", 11)
        pdf.cell(0, 8, "No records found.", ln=True)
    else:
        for idx, rec in enumerate(results, 1):
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 8, f"Record #{idx}", ln=True)
            pdf.set_font("Arial", "", 10)
            pdf.cell(40, 6, "Name:", border=0)
            pdf.cell(0, 6, rec.get('name', 'N/A'), ln=True)
            pdf.cell(40, 6, "Father's Name:", border=0)
            pdf.cell(0, 6, rec.get('father_name', 'N/A'), ln=True)
            pdf.cell(40, 6, "Address:", border=0)
            pdf.multi_cell(0, 6, rec.get('address', 'N/A'))
            pdf.cell(40, 6, "Circle:", border=0)
            pdf.cell(0, 6, rec.get('circle', 'N/A'), ln=True)
            pdf.cell(40, 6, "Mobile:", border=0)
            pdf.cell(0, 6, rec.get('mobile', 'N/A'), ln=True)
            if rec.get('alternate'):
                pdf.cell(40, 6, "Alternate:", border=0)
                pdf.cell(0, 6, rec.get('alternate'), ln=True)
            if rec.get('email'):
                pdf.cell(40, 6, "Email:", border=0)
                pdf.cell(0, 6, rec.get('email'), ln=True)
            pdf.cell(40, 6, "ID:", border=0)
            pdf.cell(0, 6, rec.get('id', 'N/A'), ln=True)
            pdf.ln(4)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)
    
    # Footer branding
    pdf.set_y(-20)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Developer: {config.DEV_USERNAME} | Powered by: {config.POWERED_BY}", ln=True, align="C")
    
    return pdf.output(dest='S').encode('latin1')

async def fetch_number_api(phone_number: str):
    url = config.NUM_API['url'].format(phone_number)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30)
            if resp.status_code != 200:
                return {"error": f"API Error {resp.status_code}"}
            return resp.json()
    except Exception as e:
        return {"error": str(e)}

async def log_to_channel(user_id: int, username: str, name: str, query_number: str, output_text: str, is_long: bool = False, file_bytes=None):
    user_info = f"👤 User: {user_id} (@{username or 'N/A'})"
    search_info = f"🔎 Searched number: {query_number}"
    log_header = f"{user_info}\n{search_info}\n\n📄 Output:\n"
    if is_long and file_bytes:
        file_bytes.seek(0)
        caption = f"{log_header}\n(Output too long, attached as file)"
        await bot.send_document(config.LOG_CHANNEL_NUM, document=file_bytes, caption=caption[:1024])
    else:
        full_log = log_header + output_text
        if len(full_log) > 4096:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(full_log)
                f.flush()
                await bot.send_document(config.LOG_CHANNEL_NUM, FSInputFile(f.name), caption=f"Log for {user_id}")
                os.unlink(f.name)
        else:
            await bot.send_message(config.LOG_CHANNEL_NUM, full_log, parse_mode="HTML")

# ---------- Membership & Force Join ----------
async def is_user_joined_channels(user_id: int) -> bool:
    for channel in FORCE_JOIN_CHANNELS:
        channel_id = channel["id"]
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def get_join_keyboard():
    buttons = []
    for idx, channel in enumerate(FORCE_JOIN_CHANNELS, 1):
        buttons.append([InlineKeyboardButton(text=f"📢 Join {channel['name']}", url=channel['link'])])
    buttons.append([InlineKeyboardButton(text="✅ Verify Join", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def check_membership(user_id):
    admin_level = await is_admin(user_id) or user_id == config.OWNER_ID or user_id in config.ADMIN_IDS
    if admin_level:
        return True
    if await is_user_premium(user_id):
        return True
    return await is_user_joined_channels(user_id)

# ---------- Main Menu ----------
def get_main_menu(user_id):
    keyboard = [
        [InlineKeyboardButton(text="📱 Number Info", callback_data="api_num")],
        [InlineKeyboardButton(text="🎁 Redeem", callback_data="redeem"), InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="refer_earn")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile"), InlineKeyboardButton(text="💳 Buy Credits", url="https://t.me/Nullprotocol_X")],
        [InlineKeyboardButton(text="⭐ Premium Plans", callback_data="premium_plans")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ---------- Start Command ----------
@dp.message(CommandStart())
async def start_command(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("🚫 <b>You are BANNED from using this bot.</b>", parse_mode="HTML")
        return
    existing = await get_user(user_id)
    if not existing:
        referrer = None
        args = command.args
        if args and args.startswith("ref_"):
            try:
                referrer = int(args.split("_")[1])
                if referrer == user_id:
                    referrer = None
            except:
                pass
        await add_user(user_id, message.from_user.username, referrer)
        if referrer:
            await update_credits(referrer, 3)
            try:
                await bot.send_message(referrer, "🎉 <b>Referral +3 Credits!</b>", parse_mode="HTML")
            except:
                pass
    if not await check_membership(user_id):
        channel_list = "\n".join([f"• {ch['name']}" for ch in FORCE_JOIN_CHANNELS])
        await message.answer(
            f"👋 <b>Welcome to Number Info Bot</b>\n\n⚠️ <b>Bot use karne ke liye ye channels join karein:</b>\n{channel_list}",
            reply_markup=get_join_keyboard(),
            parse_mode="HTML"
        )
        return
    welcome_msg = (
        f"🔓 <b>Access Granted!</b>\n\n"
        f"Welcome <b>{message.from_user.first_name}</b>,\n\n"
        f"<b>Number Info Bot</b> – Get detailed information about any mobile number.\n"
        f"Select an option from the menu below:"
    )
    await message.answer(welcome_msg, reply_markup=get_main_menu(user_id), parse_mode="HTML")
    await update_last_active(user_id)

@dp.callback_query(F.data == "check_join")
async def verify_join(callback: types.CallbackQuery):
    if await check_membership(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ <b>Verified!</b>", reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")
    else:
        await callback.answer("❌ Abhi bhi kuch channels join nahi kiye!", show_alert=True)

# ---------- Profile (Professional Format) ----------
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_data = await get_user(callback.from_user.id)
    if not user_data:
        return
    admin_level = await is_admin(callback.from_user.id) or callback.from_user.id == config.OWNER_ID
    is_premium = await is_user_premium(callback.from_user.id)
    credits = "♾️ Unlimited" if (admin_level or is_premium) else user_data['credits']
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_data['user_id']}"
    stats = await get_user_stats(callback.from_user.id)
    referrals = stats['referrals'] if stats else 0
    codes_claimed = stats['codes_claimed'] if stats else 0
    total_from_codes = stats['total_from_codes'] if stats else 0
    lookups = await get_user_lookups(callback.from_user.id, limit=5)

    msg = (
        f"👤 <b>User Profile</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_data['user_id']}</code>\n"
        f"👤 <b>Username:</b> @{user_data['username'] or 'N/A'}\n"
        f"💰 <b>Credits:</b> {credits}\n"
        f"📊 <b>Total Earned:</b> {user_data['total_earned']}\n"
        f"👥 <b>Referrals:</b> {referrals}\n"
        f"🎫 <b>Codes Claimed:</b> {codes_claimed}\n"
        f"📅 <b>Joined:</b> {datetime.fromtimestamp(float(user_data['joined_date'])).strftime('%d-%m-%Y')}\n"
        f"🔗 <b>Referral Link:</b>\n<code>{link}</code>\n\n"
        f"📋 <b>Recent Lookups:</b>\n"
    )
    if lookups:
        for i, (api_type, inp, date) in enumerate(lookups, 1):
            dstr = datetime.fromisoformat(date).strftime('%d/%m %H:%M')
            msg += f"{i}. Number: <code>{inp}</code> - {dstr}\n"
    else:
        msg += "No lookups yet."
    await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=get_main_menu(callback.from_user.id))

# ---------- Refer & Earn ----------
@dp.callback_query(F.data == "refer_earn")
async def refer_earn_handler(callback: types.CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    msg = (
        "🔗 <b>Refer & Earn Program</b>\n\n"
        "Apne dosto ko invite karein aur free credits paayein!\n"
        "Per Referral: <b>+3 Credits</b>\n\n"
        "👇 <b>Your Link:</b>\n"
        f"<code>{link}</code>\n\n"
        "📊 <b>How it works:</b>\n"
        "1. Apna link share karein\n"
        "2. Jo bhi is link se join karega\n"
        "3. Aapko milenge <b>3 credits</b>"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_home")]])
    await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=back_kb)

@dp.callback_query(F.data == "back_home")
async def go_home(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(discount_percent=0, discount_code=None)
    await callback.message.edit_text("🔓 <b>Main Menu</b>", reply_markup=get_main_menu(callback.from_user.id), parse_mode="HTML")

# ---------- Redeem Code ----------
@dp.callback_query(F.data == "redeem")
async def redeem_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎁 <b>Redeem Code</b>\n\n"
        "Enter your redeem code below:\n\n"
        "📌 <i>Note: Each code can be used only once per user</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_redeem")]]),
        parse_mode="HTML"
    )
    await state.set_state(Form.waiting_for_redeem)
    await callback.answer()

@dp.callback_query(F.data == "cancel_redeem")
async def cancel_redeem(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("❌ Operation Cancelled.", reply_markup=get_main_menu(callback.from_user.id))

# ---------- FSM States ----------
class Form(StatesGroup):
    waiting_for_redeem = State()
    waiting_for_broadcast = State()
    waiting_for_dm_user = State()
    waiting_for_dm_content = State()
    waiting_for_custom_code = State()
    waiting_for_stats_range = State()
    waiting_for_code_deactivate = State()
    waiting_for_api_input = State()
    waiting_for_username = State()
    waiting_for_delete_user = State()
    waiting_for_reset_credits = State()
    waiting_for_bulk_gift = State()
    waiting_for_user_search = State()
    waiting_for_settings = State()
    waiting_for_offer_code = State()
    waiting_for_bulk_dm_users = State()
    waiting_for_bulk_dm_content = State()
    waiting_for_add_premium = State()
    waiting_for_remove_premium = State()
    waiting_for_plan_price = State()
    waiting_for_offer_details = State()
    waiting_for_bulk_file = State()
    waiting_for_code_stats = State()
    waiting_for_user_lookups = State()
    waiting_for_gift_user = State()
    waiting_for_gift_amount = State()
    waiting_for_removecredits_user = State()
    waiting_for_removecredits_amount = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_recent_days = State()
    waiting_for_inactive_days = State()
    waiting_for_gencode_amount = State()
    waiting_for_gencode_uses = State()
    waiting_for_gencode_expiry = State()
    waiting_for_dailystats_days = State()
    waiting_for_topref_limit = State()
    waiting_for_addadmin_id = State()
    waiting_for_removeadmin_id = State()

@dp.message(Form.waiting_for_redeem)
async def process_redeem(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    result = await redeem_code_db(message.from_user.id, code)
    user_data = await get_user(message.from_user.id)
    if isinstance(result, int):
        new_balance = user_data['credits'] + result if user_data else result
        await message.answer(
            f"✅ <b>Code Redeemed Successfully!</b>\n"
            f"➕ <b>{result} Credits</b> added to your account.\n\n"
            f"💰 <b>New Balance:</b> {new_balance}",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    elif result == "already_claimed":
        await message.answer(
            "❌ <b>You have already claimed this code!</b>\nEach user can claim a code only once.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    elif result == "invalid":
        await message.answer(
            "❌ <b>Invalid Code!</b>\nPlease check the code and try again.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    elif result == "inactive":
        await message.answer(
            "❌ <b>Code is Inactive!</b>\nThis code has been deactivated by admin.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    elif result == "limit_reached":
        await message.answer(
            "❌ <b>Code Limit Reached!</b>\nThis code has been used by maximum users.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    elif result == "expired":
        await message.answer(
            "❌ <b>Code Expired!</b>\nThis code is no longer valid.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    else:
        await message.answer(
            "❌ <b>Error processing code!</b>\nPlease try again later.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
    await state.clear()

# ---------- Number Info Handler (with PDF + TXT for long output) ----------
@dp.callback_query(F.data == "api_num")
async def ask_number_input(callback: types.CallbackQuery, state: FSMContext):
    if await is_user_banned(callback.from_user.id):
        return
    if not await check_membership(callback.from_user.id):
        await callback.answer("❌ Join channels first!", show_alert=True)
        return
    await state.set_state(Form.waiting_for_api_input)
    await state.update_data(api_type="num")
    await callback.message.answer(
        "📱 <b>Enter Mobile Number</b> (with country code, e.g., +919876543210 or 9876543210):\n\n"
        "<i>Type /cancel to cancel</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_api")]])
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_api")
async def cancel_api(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("❌ Operation Cancelled.", reply_markup=get_main_menu(callback.from_user.id))

@dp.message(Form.waiting_for_api_input)
async def handle_number_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone_number = message.text.strip()
    if not (phone_number.startswith('+') or phone_number.isdigit()):
        await message.answer("⚠️ Kripya sahi phone number bhejein (jaise +919876543210 ya 9876543210)")
        return
    admin_level = await is_admin(user_id) or user_id == config.OWNER_ID or user_id in config.ADMIN_IDS
    is_premium = await is_user_premium(user_id)
    if not admin_level and not is_premium:
        user = await get_user(user_id)
        if not user or user['credits'] < 1:
            await message.answer("❌ <b>Insufficient Credits!</b>\n\nUse /start to see your balance.", parse_mode="HTML")
            await state.clear()
            return
        else:
            await update_credits(user_id, -1)
    status_msg = await message.answer("🔄 <b>Fetching number information...</b>", parse_mode="HTML")
    raw_data = await fetch_number_api(phone_number)
    await status_msg.delete()
    if "error" in raw_data:
        error_msg = f"❌ API Error: {raw_data['error']}"
        await message.answer(error_msg)
        await log_to_channel(user_id, message.from_user.username, message.from_user.first_name, phone_number, error_msg)
        await state.clear()
        return
    
    formatted_output = format_number_info(raw_data, queried_number=phone_number)
    is_long = len(formatted_output) > 3500  # threshold for file output
    
    if is_long:
        # Generate PDF
        pdf_bytes = generate_pdf_report(raw_data, phone_number)
        pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        pdf_file.write(pdf_bytes)
        pdf_file.close()
        
        # Generate TXT (readable text)
        txt_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
        txt_file.write(formatted_output)
        txt_file.close()
        
        # Send both to user
        await bot.send_document(
            chat_id=user_id,
            document=FSInputFile(pdf_file.name, filename=f"number_report_{phone_number}.pdf"),
            caption="📄 <b>Professional PDF Report</b>",
            parse_mode="HTML"
        )
        await bot.send_document(
            chat_id=user_id,
            document=FSInputFile(txt_file.name, filename=f"number_info_{phone_number}.txt"),
            caption="📝 <b>Text Format (Readable)</b>",
            parse_mode="HTML"
        )
        # Log to channel
        with open(pdf_file.name, 'rb') as f:
            pdf_log = f.read()
        with open(txt_file.name, 'rb') as f:
            txt_log = f.read()
        
        await bot.send_document(
            chat_id=config.LOG_CHANNEL_NUM,
            document=FSInputFile(pdf_file.name, filename=f"log_{phone_number}.pdf"),
            caption=f"👤 User: {user_id} (@{message.from_user.username or 'N/A'})\n🔎 Number: {phone_number}\n📄 PDF Report"
        )
        await bot.send_document(
            chat_id=config.LOG_CHANNEL_NUM,
            document=FSInputFile(txt_file.name, filename=f"log_{phone_number}.txt"),
            caption=f"Text format for {phone_number}"
        )
        
        os.unlink(pdf_file.name)
        os.unlink(txt_file.name)
    else:
        await message.answer(formatted_output, parse_mode="Markdown")
        await log_to_channel(user_id, message.from_user.username, message.from_user.first_name, phone_number, formatted_output)
    
    await log_lookup(user_id, "num", phone_number, formatted_output[:1000])
    await update_last_active(user_id)
    await state.clear()

# ---------- Premium Plans ----------
@dp.callback_query(F.data == "premium_plans")
async def show_premium_plans(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    discount = data.get('discount_percent', 0)
    discount_code = data.get('discount_code', None)
    if await is_user_premium(user_id):
        await callback.message.edit_text(
            "⭐ <b>You are already a Premium User!</b>\n\n✅ Unlimited searches\n✅ No channel join",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_home")]])
        )
        return
    weekly_price = await get_plan_price('weekly') or 69
    monthly_price = await get_plan_price('monthly') or 199
    weekly_discounted = int(weekly_price * (100 - discount) / 100)
    monthly_discounted = int(monthly_price * (100 - discount) / 100)
    if discount > 0:
        price_text = (
            f"📅 Weekly Plan: ~~₹{weekly_price}~~ ➜ **₹{weekly_discounted}** ({discount}% off)\n"
            f"📆 Monthly Plan: ~~₹{monthly_price}~~ ➜ **₹{monthly_discounted}** ({discount}% off)\n\n"
            f"🎟️ Applied code: <code>{discount_code}</code>"
        )
        extra_buttons = [[InlineKeyboardButton(text="❌ Remove Discount", callback_data="remove_discount")]]
    else:
        price_text = f"📅 Weekly Plan – ₹{weekly_price}\n📆 Monthly Plan – ₹{monthly_price}\n\n"
        extra_buttons = []
    text = (
        f"⭐ <b>Premium Plans</b>\n\n"
        f"{price_text}"
        f"💳 <b>How to Buy:</b>\n"
        f"Contact @Nullprotocol_X to purchase.\n"
        f"After payment, admin will activate your premium."
    )
    keyboard = [
        [InlineKeyboardButton(text=f"📅 Buy Weekly (₹{weekly_discounted})", callback_data="buy_weekly")],
        [InlineKeyboardButton(text=f"📆 Buy Monthly (₹{monthly_discounted})", callback_data="buy_monthly")],
        [InlineKeyboardButton(text="🎟️ Redeem Offer Code", callback_data="redeem_offer")],
    ] + extra_buttons + [[InlineKeyboardButton(text="🔙 Back", callback_data="back_home")]]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(F.data.startswith("buy_"))
async def buy_plan_handler(callback: types.CallbackQuery, state: FSMContext):
    plan = callback.data.split("_")[1]
    data = await state.get_data()
    discount = data.get('discount_percent', 0)
    base_price = await get_plan_price(plan) or (69 if plan == "weekly" else 199)
    final_price = int(base_price * (100 - discount) / 100)
    text = (
        f"🛒 <b>Purchase {plan.capitalize()} Plan</b>\n\n"
        f"{'Original Price: ₹' + str(base_price) + '\n' if discount > 0 else ''}"
        f"Final Amount: ₹{final_price}\n\n"
        "📲 <b>Payment Instructions:</b>\n"
        "1. Send payment to [UPI ID / QR code]\n"
        "2. Take a screenshot\n"
        "3. Forward screenshot to @Nullprotocol_X\n"
        "4. Your premium will be activated within 24 hours\n\n"
        "Or click below to contact admin directly:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Contact Admin", url="https://t.me/Nullprotocol_X")],
        [InlineKeyboardButton(text="🔙 Back to Plans", callback_data="premium_plans")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data == "redeem_offer")
async def redeem_offer_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎟️ <b>Redeem Offer Code</b>\n\n"
        "Enter your discount code:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_redeem_offer")]]),
        parse_mode="HTML"
    )
    await state.set_state(Form.waiting_for_offer_code)
    await callback.answer()

@dp.callback_query(F.data == "cancel_redeem_offer")
async def cancel_offer_redeem(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Offer redemption cancelled.", reply_markup=get_main_menu(callback.from_user.id))

@dp.message(Form.waiting_for_offer_code)
async def process_offer_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    discount_info = await get_discount_by_code(code)
    if not discount_info:
        await message.answer("❌ Invalid or expired offer code.")
        await state.clear()
        return
    discount_percent, plan_id, max_uses, current_uses, expiry_minutes, created_date, is_active = discount_info
    if not is_active or current_uses >= max_uses:
        await message.answer("❌ Offer code is no longer valid.")
        await state.clear()
        return
    if expiry_minutes:
        created_dt = datetime.fromisoformat(created_date)
        if datetime.now() > created_dt + timedelta(minutes=expiry_minutes):
            await message.answer("❌ Offer code has expired.")
            await state.clear()
            return
    await state.update_data(discount_percent=discount_percent, discount_code=code)
    await message.answer(
        f"✅ Offer code accepted! You got {discount_percent}% discount.\n"
        f"Click below to view discounted plans.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ View Premium Plans", callback_data="premium_plans")]])
    )
    await state.set_state(None)

@dp.callback_query(F.data == "remove_discount")
async def remove_discount(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(discount_percent=0, discount_code=None)
    await callback.answer("Discount removed.")
    await show_premium_plans(callback, state)

# ---------- ADMIN PANEL (Full, with pagination) ----------
async def show_admin_panel(chat_id, message_id=None):
    admin_level = await is_admin(chat_id) or chat_id == config.OWNER_ID or chat_id in config.ADMIN_IDS
    text = "🛠 <b>ADMIN CONTROL PANEL</b>\n\nChoose a category:"
    buttons = [
        [InlineKeyboardButton(text="📊 User Management", callback_data="admin_user_mgmt")],
        [InlineKeyboardButton(text="🎫 Code Management", callback_data="admin_code_mgmt")],
        [InlineKeyboardButton(text="📈 Statistics", callback_data="admin_stats")],
    ]
    if admin_level == 'owner' or chat_id == config.OWNER_ID:
        buttons.append([InlineKeyboardButton(text="👑 Owner Commands", callback_data="admin_owner")])
    buttons.append([InlineKeyboardButton(text="❌ Close", callback_data="close_panel")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if message_id:
        await bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not (await is_admin(message.from_user.id) or message.from_user.id == config.OWNER_ID or message.from_user.id in config.ADMIN_IDS):
        await message.answer("❌ Unauthorized.")
        return
    await show_admin_panel(message.from_user.id)

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await show_admin_panel(callback.from_user.id, callback.message.message_id)
    await callback.answer()

@dp.callback_query(F.data == "close_panel")
async def close_panel(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data == "admin_user_mgmt")
async def admin_user_mgmt(callback: types.CallbackQuery):
    if not (await is_admin(callback.from_user.id) or callback.from_user.id == config.OWNER_ID or callback.from_user.id in config.ADMIN_IDS):
        await callback.answer("Unauthorized", show_alert=True)
        return
    text = "📊 <b>User Management</b>\n\nSelect an action:"
    buttons = [
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast_now"), InlineKeyboardButton(text="📨 Direct Message", callback_data="dm_now")],
        [InlineKeyboardButton(text="🎁 Gift Credits", callback_data="admin_gift"), InlineKeyboardButton(text="🎁 Bulk Gift", callback_data="bulk_gift")],
        [InlineKeyboardButton(text="📉 Remove Credits", callback_data="admin_removecredits"), InlineKeyboardButton(text="🔄 Reset Credits", callback_data="admin_resetcredits")],
        [InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban"), InlineKeyboardButton(text="🟢 Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton(text="🗑 Delete User", callback_data="admin_deleteuser"), InlineKeyboardButton(text="🔍 Search User", callback_data="admin_searchuser")],
        [InlineKeyboardButton(text="👥 List Users", callback_data="admin_users"), InlineKeyboardButton(text="📈 Recent Users", callback_data="admin_recentusers")],
        [InlineKeyboardButton(text="📊 User Lookups", callback_data="admin_userlookups"), InlineKeyboardButton(text="🏆 Leaderboard", callback_data="admin_leaderboard")],
        [InlineKeyboardButton(text="⭐ All Premium Users", callback_data="admin_premiumusers"), InlineKeyboardButton(text="📉 Low Credit Users", callback_data="admin_lowcredit")],
        [InlineKeyboardButton(text="⏰ Inactive Users", callback_data="admin_inactiveusers"), InlineKeyboardButton(text="⭐ Add Premium", callback_data="add_premium")],
        [InlineKeyboardButton(text="➖ Remove Premium", callback_data="remove_premium")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_code_mgmt")
async def admin_code_mgmt(callback: types.CallbackQuery):
    if not (await is_admin(callback.from_user.id) or callback.from_user.id == config.OWNER_ID or callback.from_user.id in config.ADMIN_IDS):
        await callback.answer("Unauthorized", show_alert=True)
        return
    text = "🎫 <b>Code Management</b>\n\nSelect an action:"
    buttons = [
        [InlineKeyboardButton(text="🎲 Generate Random Code", callback_data="admin_gencode"), InlineKeyboardButton(text="🎫 Custom Code", callback_data="admin_customcode")],
        [InlineKeyboardButton(text="📋 List All Codes", callback_data="admin_listcodes"), InlineKeyboardButton(text="✅ Active Codes", callback_data="admin_activecodes")],
        [InlineKeyboardButton(text="❌ Inactive Codes", callback_data="admin_inactivecodes"), InlineKeyboardButton(text="🚫 Deactivate Code", callback_data="admin_deactivatecode")],
        [InlineKeyboardButton(text="📊 Code Stats", callback_data="admin_codestats"), InlineKeyboardButton(text="⌛️ Check Expired", callback_data="admin_checkexpired")],
        [InlineKeyboardButton(text="🧹 Clean Expired", callback_data="admin_cleanexpired")],
        [InlineKeyboardButton(text="💰 Set Plan Price", callback_data="set_plan_price"), InlineKeyboardButton(text="🎟️ Create Offer", callback_data="create_offer")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not (await is_admin(callback.from_user.id) or callback.from_user.id == config.OWNER_ID or callback.from_user.id in config.ADMIN_IDS):
        await callback.answer("Unauthorized", show_alert=True)
        return
    text = "📈 <b>Statistics</b>\n\nSelect an action:"
    buttons = [
        [InlineKeyboardButton(text="📊 Bot Stats", callback_data="admin_stats_general"), InlineKeyboardButton(text="📅 Daily Stats", callback_data="admin_dailystats")],
        [InlineKeyboardButton(text="🔍 Lookup Stats", callback_data="admin_lookupstats"), InlineKeyboardButton(text="💾 Backup User Data", callback_data="admin_backup")],
        [InlineKeyboardButton(text="🏆 Top Referrers", callback_data="admin_topref")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_owner")
async def admin_owner(callback: types.CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    text = "👑 <b>Owner Commands</b>\n\nSelect an action:"
    buttons = [
        [InlineKeyboardButton(text="➕ Add Admin", callback_data="admin_addadmin"), InlineKeyboardButton(text="➖ Remove Admin", callback_data="admin_removeadmin")],
        [InlineKeyboardButton(text="👥 List Admins", callback_data="admin_listadmins"), InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="💾 Full DB Backup", callback_data="admin_fulldbbackup")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ---------- Broadcast, DM, Gift, etc. ----------
@dp.callback_query(F.data == "broadcast_now")
async def broadcast_now(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 <b>Send message to broadcast</b> (text, photo, video, etc.):", parse_mode="HTML")
    await state.set_state(Form.waiting_for_broadcast)
    await callback.answer()

@dp.message(Form.waiting_for_broadcast)
async def broadcast_handler(message: types.Message, state: FSMContext):
    users = await get_all_users()
    sent = 0
    failed = 0
    total = len(users)
    status = await message.answer(f"🚀 Broadcasting to {total} users...\n\nSent: 0\nFailed: 0")
    for uid in users:
        try:
            await message.copy_to(uid)
            sent += 1
            if sent % 20 == 0:
                await status.edit_text(f"🚀 Broadcasting...\n✅ Sent: {sent}\n❌ Failed: {failed}\n📊 Progress: {((sent+failed)/total*100):.1f}%")
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await status.edit_text(f"✅ <b>Broadcast Complete!</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}\n👥 Total: {total}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "dm_now")
async def dm_now(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 <b>Enter user ID to send message:</b>", parse_mode="HTML")
    await state.set_state(Form.waiting_for_dm_user)
    await callback.answer()

@dp.message(Form.waiting_for_dm_user)
async def dm_user_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(dm_user_id=uid)
        await message.answer("📨 Now send the message:")
        await state.set_state(Form.waiting_for_dm_content)
    except:
        await message.answer("❌ Invalid user ID. Please enter a numeric ID.")

@dp.message(Form.waiting_for_dm_content)
async def dm_content_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get('dm_user_id')
    try:
        await message.copy_to(uid)
        await message.answer(f"✅ Message sent to user {uid}")
    except Exception as e:
        await message.answer(f"❌ Failed: {str(e)}")
    await state.clear()

@dp.callback_query(F.data == "admin_gift")
async def admin_gift_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎁 <b>Gift Credits</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_gift_user)
    await callback.answer()

@dp.message(Form.waiting_for_gift_user)
async def gift_user_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(gift_user_id=uid)
        await message.answer("Enter amount of credits to add:")
        await state.set_state(Form.waiting_for_gift_amount)
    except:
        await message.answer("❌ Invalid user ID.")

@dp.message(Form.waiting_for_gift_amount)
async def gift_amount_handler(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['gift_user_id']
        await update_credits(uid, amount)
        await message.answer(f"✅ Added {amount} credits to user {uid}")
        try:
            await bot.send_message(uid, f"🎁 <b>Admin Gifted You {amount} Credits!</b>", parse_mode="HTML")
        except:
            pass
    except:
        await message.answer("❌ Invalid amount.")
    await state.clear()

@dp.callback_query(F.data == "bulk_gift")
async def bulk_gift_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎁 <b>Bulk Gift Credits</b>\n\n"
        "Send in format: <code>AMOUNT USERID1 USERID2 ...</code>\n"
        "Example: <code>50 123456 789012 345678</code>",
        parse_mode="HTML"
    )
    await state.set_state(Form.waiting_for_bulk_gift)
    await callback.answer()

@dp.message(Form.waiting_for_bulk_gift)
async def bulk_gift_handler(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        amount = int(parts[0])
        user_ids = [int(uid) for uid in parts[1:]]
        await bulk_update_credits(user_ids, amount)
        msg = f"✅ Gifted {amount} credits to {len(user_ids)} users:\n"
        for uid in user_ids[:10]:
            msg += f"• <code>{uid}</code>\n"
        if len(user_ids) > 10:
            msg += f"... and {len(user_ids)-10} more"
        await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "admin_removecredits")
async def admin_removecredits_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📉 <b>Remove Credits</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_removecredits_user)
    await callback.answer()

@dp.message(Form.waiting_for_removecredits_user)
async def removecredits_user_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await state.update_data(removecredits_user_id=uid)
        await message.answer("Enter amount of credits to remove:")
        await state.set_state(Form.waiting_for_removecredits_amount)
    except:
        await message.answer("❌ Invalid user ID.")

@dp.message(Form.waiting_for_removecredits_amount)
async def removecredits_amount_handler(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        uid = data['removecredits_user_id']
        await update_credits(uid, -amount)
        await message.answer(f"✅ Removed {amount} credits from user {uid}")
        try:
            await bot.send_message(uid, f"⚠️ <b>Admin Removed {amount} Credits From Your Account!</b>", parse_mode="HTML")
        except:
            pass
    except:
        await message.answer("❌ Invalid amount.")
    await state.clear()

@dp.callback_query(F.data == "admin_resetcredits")
async def admin_resetcredits_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔄 <b>Reset Credits</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_reset_credits)
    await callback.answer()

@dp.message(Form.waiting_for_reset_credits)
async def reset_credits_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await reset_user_credits(uid)
        await message.answer(f"✅ Credits reset for user {uid}")
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_ban")
async def admin_ban_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🚫 <b>Ban User</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_ban_id)
    await callback.answer()

@dp.message(Form.waiting_for_ban_id)
async def ban_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await set_ban_status(uid, 1)
        await message.answer(f"🚫 User {uid} banned.")
        try:
            await bot.send_message(uid, "🚫 <b>You have been banned from using this bot.</b>", parse_mode="HTML")
        except:
            pass
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_unban")
async def admin_unban_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🟢 <b>Unban User</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_unban_id)
    await callback.answer()

@dp.message(Form.waiting_for_unban_id)
async def unban_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await set_ban_status(uid, 0)
        await message.answer(f"🟢 User {uid} unbanned.")
        try:
            await bot.send_message(uid, "✅ <b>You have been unbanned. You can now use the bot again.</b>", parse_mode="HTML")
        except:
            pass
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_deleteuser")
async def admin_deleteuser_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🗑 <b>Delete User</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_delete_user)
    await callback.answer()

@dp.message(Form.waiting_for_delete_user)
async def delete_user_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await delete_user(uid)
        await message.answer(f"✅ User {uid} deleted.")
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_searchuser")
async def admin_searchuser_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔍 <b>Search User</b>\n\nEnter username or user ID to search:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_user_search)
    await callback.answer()

@dp.message(Form.waiting_for_user_search)
async def search_user_handler(message: types.Message, state: FSMContext):
    query = message.text.strip()
    users = await search_users(query)
    if not users:
        await message.answer("❌ No users found.")
    else:
        text = f"🔍 <b>Search Results for '{query}'</b>\n\n"
        for uid, username, credits in users[:15]:
            text += f"🆔 <code>{uid}</code> - @{username or 'N/A'} - {credits} credits\n"
        if len(users) > 15:
            text += f"\n... and {len(users)-15} more results"
        await message.answer(text, parse_mode="HTML")
    await state.clear()

# ---------- Users List with Pagination ----------
users_cache = {}
@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    users = await get_all_users()
    if not users:
        await callback.message.answer("❌ No users found.")
        return
    users_cache[callback.from_user.id] = users
    await show_users_page(callback, page=0)

async def show_users_page(callback: types.CallbackQuery, page: int, edit: bool = True):
    users = users_cache.get(callback.from_user.id, [])
    if not users:
        await callback.answer("Session expired.")
        return
    per_page = 10
    total_pages = (len(users) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    text = f"👥 <b>Users List (Page {page+1}/{total_pages})</b>\n\n"
    for i, user_id in enumerate(page_users, start=start+1):
        user_data = await get_user(user_id)
        if user_data:
            text += f"{i}. <code>{user_data['user_id']}</code> - @{user_data['username'] or 'N/A'} - {user_data['credits']} credits\n"
    text += f"\nTotal Users: {len(users)}"
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"users_page_{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"users_page_{page+1}"))
    buttons.append(InlineKeyboardButton(text="🔙 Back", callback_data="admin_back"))
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    if edit:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

@dp.callback_query(F.data.startswith("users_page_"))
async def users_page_nav(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_users_page(callback, page)
    await callback.answer()

# ---------- Recent Users (paginated) ----------
recent_users_cache = {}
@dp.callback_query(F.data == "admin_recentusers")
async def admin_recentusers(callback: types.CallbackQuery):
    users = await get_recent_users(limit=50)
    if not users:
        await callback.message.answer("❌ No users found.")
        return
    recent_users_cache[callback.from_user.id] = users
    await show_recent_users_page(callback, page=0)

async def show_recent_users_page(callback: types.CallbackQuery, page: int, edit: bool = True):
    users = recent_users_cache.get(callback.from_user.id, [])
    if not users:
        await callback.answer("Session expired.")
        return
    per_page = 10
    total_pages = (len(users) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    text = f"📅 <b>Recent Users (Last {len(users)} users)</b>\n\n"
    for user in page_users:
        join_date = datetime.fromisoformat(user['joined_date']).strftime('%d-%m-%Y')
        text += f"• <code>{user['user_id']}</code> - @{user['username'] or 'N/A'} - Joined: {join_date}\n"
    text += f"\nPage {page+1}/{total_pages}"
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"recent_page_{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"recent_page_{page+1}"))
    buttons.append(InlineKeyboardButton(text="🔙 Back", callback_data="admin_back"))
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    if edit:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

@dp.callback_query(F.data.startswith("recent_page_"))
async def recent_page_nav(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_recent_users_page(callback, page)
    await callback.answer()

# ---------- All Premium Users (paginated) ----------
premium_users_cache = {}
@dp.callback_query(F.data == "admin_premiumusers")
async def admin_all_premium_users(callback: types.CallbackQuery):
    users = await get_all_premium_users()
    if not users:
        await callback.message.answer("❌ No premium users found.")
        return
    premium_users_cache[callback.from_user.id] = users
    await show_premium_users_page(callback, page=0)

async def show_premium_users_page(callback: types.CallbackQuery, page: int, edit: bool = True):
    users = premium_users_cache.get(callback.from_user.id, [])
    if not users:
        await callback.answer("Session expired.")
        return
    per_page = 10
    total_pages = (len(users) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    text = f"⭐ <b>All Premium Users</b>\n\n"
    for user in page_users:
        expiry = user['premium_expiry']
        if expiry:
            expiry_dt = datetime.fromisoformat(expiry)
            if expiry_dt > datetime.now():
                expiry_str = expiry_dt.strftime('%d-%m-%Y')
            else:
                expiry_str = "Expired"
        else:
            expiry_str = "Permanent"
        text += f"• <code>{user['user_id']}</code> - @{user['username'] or 'N/A'} - Expiry: {expiry_str}\n"
    text += f"\nPage {page+1}/{total_pages}"
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"premium_page_{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"premium_page_{page+1}"))
    buttons.append(InlineKeyboardButton(text="🔙 Back", callback_data="admin_back"))
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
    if edit:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

@dp.callback_query(F.data.startswith("premium_page_"))
async def premium_page_nav(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_premium_users_page(callback, page)
    await callback.answer()

# ---------- User Lookups ----------
@dp.callback_query(F.data == "admin_userlookups")
async def admin_userlookups_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📊 <b>User Lookup History</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_user_lookups)
    await callback.answer()

@dp.message(Form.waiting_for_user_lookups)
async def user_lookups_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        lookups = await get_user_lookups(uid, 20)
        if not lookups:
            await message.answer(f"❌ No lookups found for user {uid}.")
            return
        text = f"📊 <b>Recent Lookups for User {uid}</b>\n\n"
        for i, (api_type, input_data, lookup_date) in enumerate(lookups, 1):
            date_str = datetime.fromisoformat(lookup_date).strftime('%d/%m %H:%M')
            text += f"{i}. Number: {input_data} - {date_str}\n"
        if len(text) > 4000:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(text)
                temp_file = f.name
            await message.reply_document(FSInputFile(temp_file), caption=f"Lookup history for user {uid}")
            os.unlink(temp_file)
        else:
            await message.answer(text, parse_mode="HTML")
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_leaderboard")
async def admin_leaderboard(callback: types.CallbackQuery):
    leaderboard = await get_leaderboard(10)
    if not leaderboard:
        await callback.message.answer("❌ No users found.")
        return
    text = "🏆 <b>Credits Leaderboard</b>\n\n"
    for i, (uid, username, credits) in enumerate(leaderboard, 1):
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
        text += f"{medal} <code>{uid}</code> - @{username or 'N/A'} - {credits} credits\n"
    await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_lowcredit")
async def admin_lowcredit(callback: types.CallbackQuery):
    users = await get_low_credit_users()
    if not users:
        await callback.message.answer("✅ No users with low credits.")
        return
    text = "📉 <b>Users with Low Credits (≤5 credits)</b>\n\n"
    for uid, username, credits in users[:20]:
        text += f"• <code>{uid}</code> - @{username or 'N/A'} - {credits} credits\n"
    if len(users) > 20:
        text += f"\n... and {len(users)-20} more"
    await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_inactiveusers")
async def admin_inactiveusers_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("⏰ <b>Inactive Users</b>\n\nEnter number of days (default 30):", parse_mode="HTML")
    await state.set_state(Form.waiting_for_inactive_days)
    await callback.answer()

@dp.message(Form.waiting_for_inactive_days)
async def inactive_users_days_handler(message: types.Message, state: FSMContext):
    try:
        days = int(message.text.strip()) if message.text.strip().isdigit() else 30
        users = await get_inactive_users(days)
        if not users:
            await message.answer(f"✅ No inactive users found (last {days} days).")
            return
        text = f"⏰ <b>Inactive Users (Last {days} days)</b>\n\n"
        for uid, username, last_active in users[:15]:
            last_active_dt = datetime.fromisoformat(last_active)
            days_ago = (datetime.now() - last_active_dt).days
            text += f"• <code>{uid}</code> - @{username or 'N/A'} - {days_ago} days ago\n"
        if len(users) > 15:
            text += f"\n... and {len(users)-15} more inactive users"
        await message.answer(text, parse_mode="HTML")
    except:
        await message.answer("❌ Invalid input.")
    await state.clear()

@dp.callback_query(F.data == "add_premium")
async def add_premium_callback(callback: types.CallbackQuery, state: FSMContext):
    if not (callback.from_user.id == config.OWNER_ID or callback.from_user.id in config.ADMIN_IDS or await is_admin(callback.from_user.id)):
        await callback.answer("Admin only!", show_alert=True)
        return
    await callback.message.answer("➕ Enter user ID and optional days (e.g., 123456 30):")
    await state.set_state(Form.waiting_for_add_premium)
    await callback.answer()

@dp.message(Form.waiting_for_add_premium)
async def add_premium_handler(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        uid = int(parts[0])
        days = int(parts[1]) if len(parts) > 1 else None
        await set_user_premium(uid, days)
        await message.reply(f"✅ Premium added for {uid}" + (f" for {days} days." if days else " permanently."))
        try:
            await bot.send_message(uid, "🎉 You are now a premium user!", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "remove_premium")
async def remove_premium_callback(callback: types.CallbackQuery, state: FSMContext):
    if not (callback.from_user.id == config.OWNER_ID or callback.from_user.id in config.ADMIN_IDS or await is_admin(callback.from_user.id)):
        await callback.answer("Admin only!", show_alert=True)
        return
    await callback.message.answer("➖ Enter user ID:")
    await state.set_state(Form.waiting_for_remove_premium)
    await callback.answer()

@dp.message(Form.waiting_for_remove_premium)
async def remove_premium_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await remove_user_premium(uid)
        await message.reply(f"✅ Premium removed from {uid}.")
        try:
            await bot.send_message(uid, "⚠️ Your premium status has been removed.", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    await state.clear()

# ---------- Code Management ----------
@dp.callback_query(F.data == "set_plan_price")
async def set_plan_price_callback(callback: types.CallbackQuery, state: FSMContext):
    if not (callback.from_user.id == config.OWNER_ID or await is_admin(callback.from_user.id)):
        await callback.answer("Admin only!", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Weekly", callback_data="set_price_weekly")],
        [InlineKeyboardButton(text="📆 Monthly", callback_data="set_price_monthly")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]
    ])
    await callback.message.edit_text("💰 Select plan to modify:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("set_price_"))
async def set_price_input(callback: types.CallbackQuery, state: FSMContext):
    plan = callback.data.split("_")[2]
    await state.update_data(plan_type=plan)
    await callback.message.answer(f"Enter new price for {plan.capitalize()} plan (₹):")
    await state.set_state(Form.waiting_for_plan_price)
    await callback.answer()

@dp.message(Form.waiting_for_plan_price)
async def set_price_handler(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        data = await state.get_data()
        plan = data.get('plan_type')
        await update_plan_price(plan, price)
        await message.reply(f"✅ {plan.capitalize()} plan price set to ₹{price}.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "create_offer")
async def create_offer_callback(callback: types.CallbackQuery, state: FSMContext):
    if not (callback.from_user.id == config.OWNER_ID or await is_admin(callback.from_user.id)):
        await callback.answer("Admin only!", show_alert=True)
        return
    await callback.message.answer("🎟️ Enter offer details in format: CODE PLAN DISCOUNT% MAX_USES [EXPIRY]\nExample: OFFER10 weekly 10 5 7d")
    await state.set_state(Form.waiting_for_offer_details)
    await callback.answer()

@dp.message(Form.waiting_for_offer_details)
async def create_offer_handler(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        code = parts[0].upper()
        plan = parts[1].lower()
        discount = int(parts[2])
        if discount < 0 or discount > 100:
            await message.reply("❌ Discount must be between 0 and 100.")
            return
        max_uses = int(parts[3])
        expiry = parse_time_string(parts[4]) if len(parts) > 4 else None
        await create_discount_code(code, plan, discount, max_uses, expiry)
        await message.reply(f"✅ Offer code {code} created for {plan} plan with {discount}% off.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "admin_gencode")
async def admin_gencode_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🎲 <b>Generate Random Code</b>\n\nEnter amount of credits:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_gencode_amount)
    await callback.answer()

@dp.message(Form.waiting_for_gencode_amount)
async def gencode_amount_handler(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        await state.update_data(gencode_amount=amount)
        await message.answer("Enter max number of uses:")
        await state.set_state(Form.waiting_for_gencode_uses)
    except:
        await message.answer("❌ Invalid amount.")

@dp.message(Form.waiting_for_gencode_uses)
async def gencode_uses_handler(message: types.Message, state: FSMContext):
    try:
        uses = int(message.text)
        await state.update_data(gencode_uses=uses)
        await message.answer("Enter expiry time (e.g., 30m, 2h, 1h30m) or send 'none' for no expiry:")
        await state.set_state(Form.waiting_for_gencode_expiry)
    except:
        await message.answer("❌ Invalid number of uses.")

@dp.message(Form.waiting_for_gencode_expiry)
async def gencode_expiry_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data['gencode_amount']
    uses = data['gencode_uses']
    expiry_input = message.text.strip().lower()
    if expiry_input == 'none':
        expiry_minutes = None
    else:
        expiry_minutes = parse_time_string(expiry_input)
        if expiry_minutes is None:
            await message.answer("❌ Invalid time format. Use like 30m, 2h, or send 'none'.")
            return
    code = f"PRO-{secrets.token_hex(3).upper()}"
    await create_redeem_code(code, amount, uses, expiry_minutes)
    expiry_text = ""
    if expiry_minutes:
        if expiry_minutes < 60:
            expiry_text = f"⏰ Expires in: {expiry_minutes} minutes"
        else:
            hours = expiry_minutes // 60
            mins = expiry_minutes % 60
            expiry_text = f"⏰ Expires in: {hours}h {mins}m"
    else:
        expiry_text = "⏰ No expiry"
    await message.answer(
        f"✅ <b>Random Code Created!</b>\n\n"
        f"🎫 <b>Code:</b> <code>{code}</code>\n"
        f"💰 <b>Amount:</b> {amount} credits\n"
        f"👥 <b>Max Uses:</b> {uses}\n"
        f"{expiry_text}",
        parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data == "admin_customcode")
async def admin_customcode_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🎫 <b>Custom Code</b>\n\n"
        "Enter details in format: <code>CODE AMOUNT USES [TIME]</code>\n"
        "Examples:\n"
        "• <code>WELCOME50 50 10</code>\n"
        "• <code>FLASH100 100 5 15m</code>",
        parse_mode="HTML"
    )
    await state.set_state(Form.waiting_for_custom_code)
    await callback.answer()

@dp.message(Form.waiting_for_custom_code)
async def custom_code_handler(message: types.Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        code = parts[0].upper()
        amt = int(parts[1])
        uses = int(parts[2])
        expiry_minutes = parse_time_string(parts[3]) if len(parts) >= 4 else None
        await create_redeem_code(code, amt, uses, expiry_minutes)
        expiry_text = ""
        if expiry_minutes:
            if expiry_minutes < 60:
                expiry_text = f"⏰ Expires in: {expiry_minutes} minutes"
            else:
                hours = expiry_minutes // 60
                mins = expiry_minutes % 60
                expiry_text = f"⏰ Expires in: {hours}h {mins}m"
        else:
            expiry_text = "⏰ No expiry"
        await message.answer(
            f"✅ <b>Custom Code Created!</b>\n\n"
            f"🎫 <b>Code:</b> <code>{code}</code>\n"
            f"💰 <b>Amount:</b> {amt} credits\n"
            f"👥 <b>Max Uses:</b> {uses}\n"
            f"{expiry_text}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "admin_listcodes")
async def admin_listcodes(callback: types.CallbackQuery):
    codes = await get_all_codes()
    if not codes:
        await callback.message.answer("❌ No redeem codes found.")
        return
    text = "🎫 <b>All Redeem Codes</b>\n\n"
    for code_data in codes:
        code, amount, max_uses, current_uses, expiry_minutes, created_date, is_active = code_data
        status = "✅ Active" if is_active else "❌ Inactive"
        expiry_text = ""
        if expiry_minutes:
            created_dt = datetime.fromisoformat(created_date)
            expiry_dt = created_dt + timedelta(minutes=expiry_minutes)
            if expiry_dt > datetime.now():
                time_left = expiry_dt - datetime.now()
                hours = time_left.seconds // 3600
                minutes = (time_left.seconds % 3600) // 60
                expiry_text = f"⏳ {hours}h {minutes}m left"
            else:
                expiry_text = "⌛️ Expired"
        else:
            expiry_text = "♾️ No expiry"
        text += (
            f"🎟 <b>{code}</b> ({status})\n"
            f"💰 Amount: {amount} | 👥 Uses: {current_uses}/{max_uses}\n"
            f"{expiry_text}\n"
            f"📅 Created: {datetime.fromisoformat(created_date).strftime('%d/%m/%y %H:%M')}\n"
            f"{'-'*30}\n"
        )
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await callback.message.answer(part, parse_mode="HTML")
    else:
        await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_activecodes")
async def admin_activecodes(callback: types.CallbackQuery):
    codes = await get_active_codes()
    if not codes:
        await callback.message.answer("✅ No active codes found.")
        return
    text = "✅ <b>Active Codes</b>\n\n"
    for code, amount, max_uses, current_uses in codes[:10]:
        text += f"🎟 <code>{code}</code> - {amount} credits ({current_uses}/{max_uses})\n"
    if len(codes) > 10:
        text += f"\n... and {len(codes)-10} more active codes"
    await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_inactivecodes")
async def admin_inactivecodes(callback: types.CallbackQuery):
    codes = await get_inactive_codes()
    if not codes:
        await callback.message.answer("❌ No inactive codes found.")
        return
    text = "❌ <b>Inactive Codes</b>\n\n"
    for code, amount, max_uses, current_uses in codes[:10]:
        text += f"🎟 <code>{code}</code> - {amount} credits ({current_uses}/{max_uses})\n"
    if len(codes) > 10:
        text += f"\n... and {len(codes)-10} more inactive codes"
    await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_deactivatecode")
async def admin_deactivatecode_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🚫 <b>Deactivate Code</b>\n\nEnter code to deactivate:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_code_deactivate)
    await callback.answer()

@dp.message(Form.waiting_for_code_deactivate)
async def deactivate_code_handler(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    await deactivate_code(code)
    await message.answer(f"✅ Code <code>{code}</code> has been deactivated.", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "admin_codestats")
async def admin_codestats_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📊 <b>Code Statistics</b>\n\nEnter code:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_code_stats)
    await callback.answer()

@dp.message(Form.waiting_for_code_stats)
async def code_stats_handler(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    stats = await get_code_usage_stats(code)
    if stats:
        amount, max_uses, current_uses, unique_users, user_ids = stats
        msg = (
            f"📊 <b>Code Statistics: {code}</b>\n\n"
            f"💰 <b>Amount:</b> {amount} credits\n"
            f"🎯 <b>Uses:</b> {current_uses}/{max_uses}\n"
            f"👥 <b>Unique Users:</b> {unique_users}\n"
            f"🆔 <b>Users:</b> {user_ids or 'None'}"
        )
        await message.answer(msg, parse_mode="HTML")
    else:
        await message.answer(f"❌ Code {code} not found.")
    await state.clear()

@dp.callback_query(F.data == "admin_checkexpired")
async def admin_checkexpired(callback: types.CallbackQuery):
    expired = await get_expired_codes()
    if not expired:
        await callback.message.answer("✅ No expired codes found.")
        return
    text = "⌛️ <b>Expired Codes</b>\n\n"
    for code_data in expired:
        code, amount, current_uses, max_uses, expiry_minutes, created_date = code_data
        created_dt = datetime.fromisoformat(created_date)
        expiry_dt = created_dt + timedelta(minutes=expiry_minutes)
        text += (
            f"🎟 <code>{code}</code>\n"
            f"💰 Amount: {amount} | 👥 Used: {current_uses}/{max_uses}\n"
            f"⏰ Expired on: {expiry_dt.strftime('%d/%m/%y %H:%M')}\n"
            f"{'-'*20}\n"
        )
    text += f"\nTotal: {len(expired)} expired codes"
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await callback.message.answer(part, parse_mode="HTML")
    else:
        await callback.message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_cleanexpired")
async def admin_cleanexpired(callback: types.CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    expired = await get_expired_codes()
    if not expired:
        await callback.message.answer("✅ No expired codes found.")
        return
    deleted = 0
    for code_data in expired:
        await delete_redeem_code(code_data[0])
        deleted += 1
    await callback.message.answer(f"🧹 Cleaned {deleted} expired codes.")

# ---------- Statistics ----------
@dp.callback_query(F.data == "admin_stats_general")
async def admin_stats_general(callback: types.CallbackQuery):
    stats = await get_bot_stats()
    top_ref = await get_top_referrers(5)
    total_lookups = await get_total_lookups()
    text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> {stats['total_users']}\n"
        f"📈 <b>Active Users:</b> {stats['active_users']}\n"
        f"💰 <b>Total Credits in System:</b> {stats['total_credits']}\n"
        f"🎁 <b>Credits Distributed:</b> {stats['credits_distributed']}\n"
        f"🔍 <b>Total Lookups:</b> {total_lookups}\n\n"
    )
    if top_ref:
        text += "🏆 <b>Top 5 Referrers:</b>\n"
        for i, (ref_id, count) in enumerate(top_ref, 1):
            text += f"{i}. User <code>{ref_id}</code>: {count} referrals\n"
    await callback.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_dailystats")
async def admin_dailystats_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📅 <b>Daily Statistics</b>\n\nEnter number of days (default 7):", parse_mode="HTML")
    await state.set_state(Form.waiting_for_dailystats_days)
    await callback.answer()

@dp.message(Form.waiting_for_dailystats_days)
async def dailystats_handler(message: types.Message, state: FSMContext):
    try:
        days = int(message.text.strip()) if message.text.strip().isdigit() else 7
        stats = await get_daily_stats(days)
        text = f"📈 <b>Daily Statistics (Last {days} days)</b>\n\n"
        if not stats:
            text += "No statistics available."
        else:
            for date, new_users, lookups in stats:
                text += f"📅 {date}: +{new_users} users, {lookups} lookups\n"
        await message.answer(text, parse_mode="HTML")
    except:
        await message.answer("❌ Invalid input.")
    await state.clear()

@dp.callback_query(F.data == "admin_lookupstats")
async def admin_lookupstats(callback: types.CallbackQuery):
    total_lookups = await get_total_lookups()
    api_stats = await get_lookup_stats()
    text = f"🔍 <b>Lookup Statistics</b>\n\n📊 <b>Total Lookups:</b> {total_lookups}\n\n"
    if api_stats:
        text += "<b>By API Type:</b>\n"
        for api_type, count in api_stats:
            text += f"• {api_type.upper()}: {count} lookups\n"
    await callback.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_backup")
async def admin_backup_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("💾 <b>Backup User Data</b>\n\nEnter number of days (0 for all data):", parse_mode="HTML")
    await state.set_state(Form.waiting_for_stats_range)
    await callback.answer()

@dp.message(Form.waiting_for_stats_range)
async def backup_handler(message: types.Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days) if days > 0 else datetime.fromtimestamp(0)
        users = await get_users_in_range(start_date.timestamp(), end_date.timestamp())
        if not users:
            await message.answer(f"❌ No users found for given range.")
            return
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['User ID', 'Username', 'Credits', 'Join Date'])
            for user in users:
                join_date = datetime.fromtimestamp(float(user['joined_date'])).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([user['user_id'], user['username'] or 'N/A', user['credits'], join_date])
            temp_file = f.name
        await message.reply_document(FSInputFile(temp_file), caption=f"📊 Users data for last {days} days\nTotal users: {len(users)}")
        os.unlink(temp_file)
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "admin_topref")
async def admin_topref_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🏆 <b>Top Referrers</b>\n\nEnter limit (default 10):", parse_mode="HTML")
    await state.set_state(Form.waiting_for_topref_limit)
    await callback.answer()

@dp.message(Form.waiting_for_topref_limit)
async def topref_handler(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text.strip()) if message.text.strip().isdigit() else 10
        top_ref = await get_top_referrers(limit)
        if not top_ref:
            await message.answer("❌ No referrals yet.")
            return
        text = f"🏆 <b>Top {limit} Referrers</b>\n\n"
        for i, (ref_id, count) in enumerate(top_ref, 1):
            text += f"{i}. User <code>{ref_id}</code>: {count} referrals\n"
        await message.answer(text, parse_mode="HTML")
    except:
        await message.answer("❌ Invalid input.")
    await state.clear()

# ---------- Owner Admin Management ----------
@dp.callback_query(F.data == "admin_addadmin")
async def admin_addadmin_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    await callback.message.answer("➕ <b>Add Admin</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_addadmin_id)
    await callback.answer()

@dp.message(Form.waiting_for_addadmin_id)
async def addadmin_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        await add_admin(uid)
        await message.answer(f"✅ User {uid} added as admin.")
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_removeadmin")
async def admin_removeadmin_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    await callback.message.answer("➖ <b>Remove Admin</b>\n\nEnter user ID:", parse_mode="HTML")
    await state.set_state(Form.waiting_for_removeadmin_id)
    await callback.answer()

@dp.message(Form.waiting_for_removeadmin_id)
async def removeadmin_handler(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        if uid == config.OWNER_ID:
            await message.answer("❌ Cannot remove owner!")
            return
        await remove_admin(uid)
        await message.answer(f"✅ Admin {uid} removed.")
    except:
        await message.answer("❌ Invalid user ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_listadmins")
async def admin_listadmins(callback: types.CallbackQuery):
    admins = await get_all_admins()
    text = "👥 <b>Admin List</b>\n\n"
    text += f"👑 <b>Owner:</b> <code>{config.OWNER_ID}</code>\n\n"
    text += "⚙️ <b>Static Admins:</b>\n"
    for admin_id in config.ADMIN_IDS:
        if admin_id != config.OWNER_ID:
            text += f"• <code>{admin_id}</code>\n"
    if admins:
        text += "\n🗃️ <b>Database Admins:</b>\n"
        for user_id, level in admins:
            text += f"• <code>{user_id}</code> - {level}\n"
    await callback.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data == "admin_settings")
async def admin_settings_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    await callback.message.answer(
        "⚙️ <b>Bot Settings</b>\n\n"
        "1. Change bot name\n"
        "2. Update API endpoints\n"
        "3. Modify channel settings\n"
        "4. Adjust credit settings\n\n"
        "Enter setting number to modify:",
        parse_mode="HTML"
    )
    await state.set_state(Form.waiting_for_settings)
    await callback.answer()

@dp.message(Form.waiting_for_settings)
async def settings_handler(message: types.Message, state: FSMContext):
    await message.answer("⚙️ <b>Settings updated!</b> (placeholder)", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "admin_fulldbbackup")
async def admin_fulldbbackup(callback: types.CallbackQuery):
    if callback.from_user.id != config.OWNER_ID:
        await callback.answer("Owner only!", show_alert=True)
        return
    try:
        pool = await get_pool()
        backup_csv = f"full_backup_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
            if rows:
                col_names = list(rows[0].keys())
                with open(backup_csv, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(col_names)
                    for row in rows:
                        writer.writerow([row[col] for col in col_names])
        await callback.message.answer_document(FSInputFile(backup_csv), caption="💾 Full Users Table Backup (CSV)")
        os.remove(backup_csv)
    except Exception as e:
        await callback.message.answer(f"❌ Backup failed: {e}")

# ---------- Cancel Command ----------
@dp.message(Command("cancel"))
async def cancel_command(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ No active operation to cancel.")
        return
    await state.clear()
    await message.answer("✅ Operation cancelled.", reply_markup=get_main_menu(message.from_user.id))

# ---------- Daily Backup (scheduled) ----------
async def daily_backup():
    try:
        pool = await get_pool()
        csv_backup = f"backup_users_{datetime.now().strftime('%Y%m%d')}.csv"
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users")
            if rows:
                col_names = list(rows[0].keys())
                with open(csv_backup, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(col_names)
                    for row in rows:
                        writer.writerow([row[col] for col in col_names])
        txt_backup = f"backup_stats_{datetime.now().strftime('%Y%m%d')}.txt"
        stats = await get_bot_stats()
        total_lookups = await get_total_lookups()
        with open(txt_backup, 'w', encoding='utf-8') as f:
            f.write(f"Backup Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Users: {stats['total_users']}\n")
            f.write(f"Active Users: {stats['active_users']}\n")
            f.write(f"Total Credits: {stats['total_credits']}\n")
            f.write(f"Credits Distributed: {stats['credits_distributed']}\n")
            f.write(f"Total Lookups: {total_lookups}\n")
        if os.path.exists(csv_backup):
            await bot.send_document(config.BACKUP_CHANNEL, FSInputFile(csv_backup))
            os.remove(csv_backup)
        if os.path.exists(txt_backup):
            await bot.send_document(config.BACKUP_CHANNEL, FSInputFile(txt_backup))
            os.remove(txt_backup)
        logging.info("✅ Daily backup successful.")
    except Exception as e:
        logging.error(f"❌ Backup failed: {e}")

# ---------- Self-Ping ----------
async def self_ping():
    url = config.WEBHOOK_URL
    if not url:
        return
    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10)
                logging.info(f"Self-ping → {resp.status_code}")
        except Exception as e:
            logging.error(f"Self-ping error: {e}")

# ---------- Error Handler ----------
async def error_handler(update: types.Update, exception: Exception):
    logging.error(f"Update {update} caused error {exception}")
    try:
        if update.message:
            await update.message.reply_text("⚠️ An internal error occurred. Please try again later.")
    except:
        pass

dp.error(error_handler)

# ---------- Webhook Setup & Main ----------
async def on_startup():
    await init_db()
    for aid in config.ADMIN_IDS:
        if aid != config.OWNER_ID:
            await add_admin(aid)
    webhook_url = f"{config.WEBHOOK_URL}/{TOKEN}"
    await bot.set_webhook(url=webhook_url)
    logging.info(f"Webhook set to {webhook_url}")
    asyncio.create_task(self_ping())
    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_backup, CronTrigger(hour=0, minute=0))
    scheduler.start()

async def main():
    dp.startup.register(on_startup)
    app_web = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app_web, path=f"/{TOKEN}")
    setup_application(app_web, dp, bot=bot)
    async def health(request):
        return web.Response(text="Number Info Bot is running (webhook mode)!")
    app_web.router.add_get('/', health)
    port = int(os.environ.get("PORT", 8000))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logging.info(f"Bot started on port {port}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
