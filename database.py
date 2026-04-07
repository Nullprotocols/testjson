# database.py – PostgreSQL Version (Complete & Ready to Deploy)

import asyncpg
import os
import time
import re
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL environment variable not set!")

_pool = None

async def get_pool():
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
    return _pool

def parse_time_string(time_str):
    """
    Parse time string like '30m', '2h', '1h30m' into minutes.
    Returns None if invalid or 'none'.
    """
    if not time_str or str(time_str).lower() == 'none':
        return None
    time_str = str(time_str).lower()
    total_minutes = 0
    hour_match = re.search(r'(\d+)h', time_str)
    if hour_match:
        total_minutes += int(hour_match.group(1)) * 60
    minute_match = re.search(r'(\d+)m', time_str)
    if minute_match:
        total_minutes += int(minute_match.group(1))
    if not hour_match and not minute_match and time_str.isdigit():
        total_minutes = int(time_str)
    return total_minutes if total_minutes > 0 else None

async def init_db():
    """Initialize all database tables."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 5,
                joined_date TEXT,
                referrer_id BIGINT,
                is_banned INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                last_active TEXT,
                is_premium INTEGER DEFAULT 0,
                premium_expiry TEXT
            )
        """)
        # Admins table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                level TEXT DEFAULT 'admin',
                added_by BIGINT,
                added_date TEXT
            )
        """)
        # Redeem codes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                max_uses INTEGER,
                current_uses INTEGER DEFAULT 0,
                expiry_minutes INTEGER,
                created_date TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        # Redeem logs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS redeem_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                code TEXT,
                claimed_date TEXT,
                UNIQUE(user_id, code)
            )
        """)
        # Lookup logs
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lookup_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                api_type TEXT,
                input_data TEXT,
                result TEXT,
                lookup_date TEXT
            )
        """)
        # Premium plans (for pricing)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS premium_plans (
                plan_id TEXT PRIMARY KEY,
                price INTEGER,
                duration_days INTEGER,
                description TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO premium_plans (plan_id, price, duration_days, description)
            VALUES ('weekly', 69, 7, 'Weekly Plan')
            ON CONFLICT (plan_id) DO NOTHING
        """)
        await conn.execute("""
            INSERT INTO premium_plans (plan_id, price, duration_days, description)
            VALUES ('monthly', 199, 30, 'Monthly Plan')
            ON CONFLICT (plan_id) DO NOTHING
        """)
        # Discount codes for plans
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS discount_codes (
                code TEXT PRIMARY KEY,
                plan_id TEXT,
                discount_percent INTEGER,
                max_uses INTEGER,
                current_uses INTEGER DEFAULT 0,
                expiry_minutes INTEGER,
                created_date TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

# ---------- User functions ----------
async def get_user(user_id):
    """Fetch a user by user_id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def add_user(user_id, username, referrer_id=None):
    """Add a new user if not exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", user_id)
        if exists:
            return
        credits = 5
        current_time = str(time.time())
        await conn.execute("""
            INSERT INTO users (user_id, username, credits, joined_date, referrer_id, is_banned, total_earned, last_active, is_premium, premium_expiry)
            VALUES ($1, $2, $3, $4, $5, 0, 0, $4, 0, NULL)
        """, user_id, username, credits, current_time, referrer_id)

async def update_credits(user_id, amount):
    """Add or remove credits. Positive amount adds, negative subtracts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if amount > 0:
            await conn.execute("UPDATE users SET credits = credits + $1, total_earned = total_earned + $1 WHERE user_id = $2", amount, user_id)
        else:
            await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", amount, user_id)

async def set_ban_status(user_id, status):
    """Ban or unban a user (status=1 for banned)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", status, user_id)

async def get_all_users():
    """Return list of all user IDs."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [row['user_id'] for row in rows]

async def get_user_by_username(username):
    """Find user ID by username (without @)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM users WHERE username = $1", username)
        return row['user_id'] if row else None

async def update_last_active(user_id):
    """Update user's last active timestamp."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_active = $1 WHERE user_id = $2", datetime.now().isoformat(), user_id)

# ---------- Premium functions ----------
async def set_user_premium(user_id, days=None):
    """Grant premium status. If days given, set expiry; else permanent."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if days:
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
            await conn.execute("UPDATE users SET is_premium = 1, premium_expiry = $1 WHERE user_id = $2", expiry, user_id)
        else:
            await conn.execute("UPDATE users SET is_premium = 1, premium_expiry = NULL WHERE user_id = $1", user_id)

async def remove_user_premium(user_id):
    """Remove premium status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = $1", user_id)

async def is_user_premium(user_id):
    """Check if user is premium (and not expired). Auto-remove if expired."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_premium, premium_expiry FROM users WHERE user_id = $1", user_id)
        if not row:
            return False
        is_premium, expiry = row['is_premium'], row['premium_expiry']
        if not is_premium:
            return False
        if expiry:
            expiry_dt = datetime.fromisoformat(expiry)
            if expiry_dt < datetime.now():
                await remove_user_premium(user_id)
                return False
        return True

async def get_premium_users():
    """Return list of premium users (user_id, username, expiry)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, premium_expiry FROM users WHERE is_premium = 1")

async def get_all_premium_users():
    """Return list of all premium users (is_premium=1) with their details."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, premium_expiry FROM users WHERE is_premium = 1 ORDER BY user_id DESC")

async def get_users_with_min_credits(min_credits=100):
    """Return users with credits >= min_credits."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, credits FROM users WHERE credits >= $1 ORDER BY credits DESC", min_credits)

# ---------- Premium plans functions ----------
async def get_plan_price(plan_id):
    """Get price for a plan (weekly/monthly)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT price FROM premium_plans WHERE plan_id = $1", plan_id)
        return row['price'] if row else None

async def update_plan_price(plan_id, price):
    """Update price for a plan."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE premium_plans SET price = $1 WHERE plan_id = $2", price, plan_id)

# ---------- Discount codes ----------
async def create_discount_code(code, plan_id, discount_percent, max_uses, expiry_minutes=None):
    """Create a discount code for a specific plan."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO discount_codes (code, plan_id, discount_percent, max_uses, expiry_minutes, created_date, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, 1)
            ON CONFLICT (code) DO UPDATE SET
                plan_id = EXCLUDED.plan_id,
                discount_percent = EXCLUDED.discount_percent,
                max_uses = EXCLUDED.max_uses,
                expiry_minutes = EXCLUDED.expiry_minutes,
                created_date = EXCLUDED.created_date,
                is_active = 1
        """, code, plan_id, discount_percent, max_uses, expiry_minutes, datetime.now().isoformat())

async def get_discount_by_code(code):
    """Get discount code info without incrementing uses."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT discount_percent, plan_id, max_uses, current_uses, expiry_minutes, created_date, is_active FROM discount_codes WHERE code = $1", code)

async def redeem_discount_code(user_id, code, plan_id):
    """Redeem a discount code. Returns discount percent or error string."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            data = await conn.fetchrow("SELECT discount_percent, max_uses, current_uses, expiry_minutes, created_date, is_active FROM discount_codes WHERE code = $1", code)
            if not data:
                return "invalid"
            discount_percent, max_uses, current_uses, expiry_minutes, created_date, is_active = data['discount_percent'], data['max_uses'], data['current_uses'], data['expiry_minutes'], data['created_date'], data['is_active']
            if not is_active:
                return "inactive"
            if current_uses >= max_uses:
                return "limit_reached"
            if expiry_minutes:
                created_dt = datetime.fromisoformat(created_date)
                if datetime.now() > created_dt + timedelta(minutes=expiry_minutes):
                    return "expired"
            await conn.execute("UPDATE discount_codes SET current_uses = current_uses + 1 WHERE code = $1", code)
            return discount_percent

# ---------- Redeem codes (regular) ----------
async def create_redeem_code(code, amount, max_uses, expiry_minutes=None):
    """Create a regular redeem code that adds credits."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO redeem_codes (code, amount, max_uses, expiry_minutes, created_date, is_active)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (code) DO UPDATE SET
                amount = EXCLUDED.amount,
                max_uses = EXCLUDED.max_uses,
                expiry_minutes = EXCLUDED.expiry_minutes,
                created_date = EXCLUDED.created_date,
                is_active = 1
        """, code, amount, max_uses, expiry_minutes, datetime.now().isoformat())

async def redeem_code_db(user_id, code):
    """Redeem a regular code. Returns amount or error string."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Check if already claimed
            already = await conn.fetchval("SELECT 1 FROM redeem_logs WHERE user_id = $1 AND code = $2", user_id, code)
            if already:
                return "already_claimed"

            data = await conn.fetchrow("SELECT amount, max_uses, current_uses, expiry_minutes, created_date, is_active FROM redeem_codes WHERE code = $1", code)
            if not data:
                return "invalid"
            amount, max_uses, current_uses, expiry_minutes, created_date, is_active = data['amount'], data['max_uses'], data['current_uses'], data['expiry_minutes'], data['created_date'], data['is_active']
            if not is_active:
                return "inactive"
            if current_uses >= max_uses:
                return "limit_reached"
            if expiry_minutes:
                created_dt = datetime.fromisoformat(created_date)
                if datetime.now() > created_dt + timedelta(minutes=expiry_minutes):
                    return "expired"

            await conn.execute("UPDATE redeem_codes SET current_uses = current_uses + 1 WHERE code = $1", code)
            await conn.execute("UPDATE users SET credits = credits + $1, total_earned = total_earned + $1 WHERE user_id = $2", amount, user_id)
            await conn.execute("INSERT INTO redeem_logs (user_id, code, claimed_date) VALUES ($1, $2, $3)", user_id, code, datetime.now().isoformat())
            return amount

async def get_all_codes():
    """Return all redeem codes with details."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT code, amount, max_uses, current_uses, expiry_minutes, created_date, is_active FROM redeem_codes ORDER BY created_date DESC")

async def deactivate_code(code):
    """Deactivate a redeem code."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE redeem_codes SET is_active = 0 WHERE code = $1", code)

async def get_active_codes():
    """Return list of active codes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT code, amount, max_uses, current_uses FROM redeem_codes WHERE is_active = 1")

async def get_inactive_codes():
    """Return list of inactive codes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT code, amount, max_uses, current_uses FROM redeem_codes WHERE is_active = 0")

async def get_expired_codes():
    """Return codes that have expired."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT code, amount, current_uses, max_uses, expiry_minutes, created_date
            FROM redeem_codes
            WHERE is_active = 1 AND expiry_minutes IS NOT NULL AND expiry_minutes > 0
              AND (created_date::timestamp + (expiry_minutes || ' minutes')::interval) < now()
        """)

async def delete_redeem_code(code):
    """Delete a redeem code."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM redeem_codes WHERE code = $1", code)

async def get_code_usage_stats(code):
    """Get statistics for a specific redeem code."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT 
                rc.amount, rc.max_uses, rc.current_uses,
                COUNT(DISTINCT rl.user_id) as unique_users,
                array_to_string(array_agg(DISTINCT rl.user_id), ',') as user_ids
            FROM redeem_codes rc
            LEFT JOIN redeem_logs rl ON rc.code = rl.code
            WHERE rc.code = $1
            GROUP BY rc.code
        """, code)

# ---------- Lookup logs ----------
async def log_lookup(user_id, api_type, input_data, result):
    """Log a lookup made by a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO lookup_logs (user_id, api_type, input_data, result, lookup_date)
            VALUES ($1, $2, $3, $4, $5)
        """, user_id, api_type, input_data[:500], str(result)[:1000], datetime.now().isoformat())

async def get_user_lookups(user_id, limit=20):
    """Get recent lookups of a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT api_type, input_data, lookup_date
            FROM lookup_logs
            WHERE user_id = $1
            ORDER BY lookup_date DESC
            LIMIT $2
        """, user_id, limit)

async def get_total_lookups():
    """Get total number of lookups across all users."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM lookup_logs")

async def get_lookup_stats(user_id=None):
    """Get lookup counts per API type. If user_id given, filter by user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id:
            return await conn.fetch("SELECT api_type, COUNT(*) FROM lookup_logs WHERE user_id = $1 GROUP BY api_type", user_id)
        else:
            return await conn.fetch("SELECT api_type, COUNT(*) FROM lookup_logs GROUP BY api_type")

# ---------- Statistics ----------
async def get_bot_stats():
    """Return overall bot statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE credits > 0")
        total_credits = await conn.fetchval("SELECT SUM(credits) FROM users") or 0
        credits_distributed = await conn.fetchval("SELECT SUM(total_earned) FROM users") or 0
        return {
            'total_users': total_users,
            'active_users': active_users,
            'total_credits': total_credits,
            'credits_distributed': credits_distributed
        }

async def get_user_stats(user_id):
    """Return statistics for a specific user: referrals, codes claimed, total from codes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE referrer_id = $1) as referrals,
                (SELECT COUNT(*) FROM redeem_logs WHERE user_id = $1) as codes_claimed,
                (SELECT SUM(amount) FROM redeem_logs rl JOIN redeem_codes rc ON rl.code = rc.code WHERE rl.user_id = $1) as total_from_codes
        """, user_id)

async def get_recent_users(limit=20):
    """Get most recently joined users."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, joined_date FROM users ORDER BY joined_date DESC LIMIT $1", limit)

async def get_top_referrers(limit=10):
    """Get users with most referrals."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT referrer_id, COUNT(*) as referrals
            FROM users
            WHERE referrer_id IS NOT NULL
            GROUP BY referrer_id
            ORDER BY referrals DESC
            LIMIT $1
        """, limit)

async def get_users_in_range(start_date, end_date):
    """Get users who joined between two timestamps (unix time)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, credits, joined_date FROM users WHERE joined_date::float BETWEEN $1 AND $2", start_date, end_date)

async def get_leaderboard(limit=10):
    """Get top users by credits."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, credits FROM users WHERE is_banned = 0 ORDER BY credits DESC LIMIT $1", limit)

async def get_low_credit_users():
    """Get users with 5 or fewer credits."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, credits FROM users WHERE credits <= 5 ORDER BY credits ASC")

async def get_inactive_users(days=30):
    """Get users inactive for specified days."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return await conn.fetch("SELECT user_id, username, last_active FROM users WHERE last_active < $1 AND is_banned = 0 ORDER BY last_active ASC", cutoff)

async def get_daily_stats(days=7):
    """Get daily stats for the last N days."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT 
                to_char(to_timestamp(joined_date::float), 'YYYY-MM-DD') as join_date,
                COUNT(*) as new_users,
                (SELECT COUNT(*) FROM lookup_logs 
                 WHERE to_char(lookup_date::timestamp, 'YYYY-MM-DD') = to_char(to_timestamp(joined_date::float), 'YYYY-MM-DD')) as lookups
            FROM users 
            WHERE to_timestamp(joined_date::float) >= now() - $1 * interval '1 day'
            GROUP BY join_date
            ORDER BY join_date DESC
        """, days)

# ---------- Admin management ----------
async def add_admin(user_id, level='admin'):
    """Add a user to admin table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO admins (user_id, level) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level", user_id, level)

async def remove_admin(user_id):
    """Remove a user from admin table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = $1", user_id)

async def get_all_admins():
    """Return list of all admins with levels."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, level FROM admins")

async def is_admin(user_id):
    """Check if user is admin (returns level or None)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT level FROM admins WHERE user_id = $1", user_id)
        return row

# ---------- Utility ----------
async def search_users(query):
    """Search users by username or ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            q_int = int(query)
        except:
            q_int = 0
        return await conn.fetch("SELECT user_id, username, credits FROM users WHERE username ILIKE $1 OR user_id = $2 LIMIT 20", f"%{query}%", q_int)

async def delete_user(user_id):
    """Delete a user and related logs."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM redeem_logs WHERE user_id = $1", user_id)
            await conn.execute("UPDATE users SET referrer_id = NULL WHERE referrer_id = $1", user_id)

async def reset_user_credits(user_id):
    """Set user credits to 0."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET credits = 0 WHERE user_id = $1", user_id)

async def bulk_update_credits(user_ids, amount):
    """Add credits to multiple users."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for uid in user_ids:
                if amount > 0:
                    await conn.execute("UPDATE users SET credits = credits + $1, total_earned = total_earned + $1 WHERE user_id = $2", amount, uid)
                else:
                    await conn.execute("UPDATE users SET credits = credits + $1 WHERE user_id = $2", amount, uid)
