# database.py – Complete SQLite version (all functions from original PostgreSQL version)

import aiosqlite
import os
import re
import time
from datetime import datetime, timedelta

def get_db_path():
    if os.environ.get("RENDER"):
        return "/tmp/bot_data.db"
    return os.getenv("DATABASE_PATH", "bot_data.db")

async def get_db():
    conn = await aiosqlite.connect(get_db_path())
    conn.row_factory = aiosqlite.Row
    return conn

def parse_time_string(time_str):
    if not time_str or str(time_str).lower() == 'none':
        return None
    time_str = str(time_str).lower()
    total = 0
    h = re.search(r'(\d+)h', time_str)
    if h:
        total += int(h.group(1)) * 60
    m = re.search(r'(\d+)m', time_str)
    if m:
        total += int(m.group(1))
    if not h and not m and time_str.isdigit():
        total = int(time_str)
    return total if total > 0 else None

async def init_db():
    async with get_db() as db:
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                credits INTEGER DEFAULT 5,
                joined_date TEXT,
                referrer_id INTEGER,
                is_banned INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                last_active TEXT,
                is_premium INTEGER DEFAULT 0,
                premium_expiry TEXT
            )
        ''')
        # Admins table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                level TEXT DEFAULT 'admin',
                added_by INTEGER,
                added_date TEXT
            )
        ''')
        # Redeem codes table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                max_uses INTEGER,
                current_uses INTEGER DEFAULT 0,
                expiry_minutes INTEGER,
                created_date TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        # Redeem logs
        await db.execute('''
            CREATE TABLE IF NOT EXISTS redeem_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code TEXT,
                claimed_date TEXT,
                UNIQUE(user_id, code)
            )
        ''')
        # Lookup logs
        await db.execute('''
            CREATE TABLE IF NOT EXISTS lookup_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                api_type TEXT,
                input_data TEXT,
                result TEXT,
                lookup_date TEXT
            )
        ''')
        # Premium plans
        await db.execute('''
            CREATE TABLE IF NOT EXISTS premium_plans (
                plan_id TEXT PRIMARY KEY,
                price INTEGER,
                duration_days INTEGER,
                description TEXT
            )
        ''')
        await db.execute("INSERT OR IGNORE INTO premium_plans VALUES ('weekly', 69, 7, 'Weekly Plan')")
        await db.execute("INSERT OR IGNORE INTO premium_plans VALUES ('monthly', 199, 30, 'Monthly Plan')")
        # Discount codes
        await db.execute('''
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
        ''')
        await db.commit()

# ---------- User functions ----------
async def get_user(user_id):
    async with get_db() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id, username, referrer_id=None):
    async with get_db() as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if await cur.fetchone():
                return
        now = str(time.time())
        await db.execute(
            "INSERT INTO users (user_id, username, credits, joined_date, referrer_id, is_banned, total_earned, last_active, is_premium, premium_expiry) VALUES (?, ?, 5, ?, ?, 0, 0, ?, 0, NULL)",
            (user_id, username, now, referrer_id, now)
        )
        await db.commit()

async def update_credits(user_id, amount):
    async with get_db() as db:
        if amount > 0:
            await db.execute("UPDATE users SET credits = credits + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, user_id))
        else:
            await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_ban_status(user_id, status):
    async with get_db() as db:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

async def get_all_users():
    async with get_db() as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row['user_id'] for row in rows]

async def get_user_by_username(username):
    async with get_db() as db:
        async with db.execute("SELECT user_id FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
            return row['user_id'] if row else None

async def update_last_active(user_id):
    async with get_db() as db:
        await db.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
        await db.commit()

async def is_user_banned(user_id):
    u = await get_user(user_id)
    return u and u['is_banned'] == 1

# ---------- Premium functions ----------
async def set_user_premium(user_id, days=None):
    async with get_db() as db:
        if days:
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
            await db.execute("UPDATE users SET is_premium = 1, premium_expiry = ? WHERE user_id = ?", (expiry, user_id))
        else:
            await db.execute("UPDATE users SET is_premium = 1, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        await db.commit()

async def remove_user_premium(user_id):
    async with get_db() as db:
        await db.execute("UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?", (user_id,))
        await db.commit()

async def is_user_premium(user_id):
    u = await get_user(user_id)
    if not u or not u['is_premium']:
        return False
    expiry = u['premium_expiry']
    if expiry:
        if datetime.fromisoformat(expiry) < datetime.now():
            await remove_user_premium(user_id)
            return False
    return True

async def get_premium_users():
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, premium_expiry FROM users WHERE is_premium = 1") as cursor:
            return await cursor.fetchall()

async def get_all_premium_users():
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, premium_expiry FROM users WHERE is_premium = 1 ORDER BY user_id DESC") as cursor:
            return await cursor.fetchall()

async def get_users_with_min_credits(min_credits=100):
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, credits FROM users WHERE credits >= ? ORDER BY credits DESC", (min_credits,)) as cursor:
            return await cursor.fetchall()

# ---------- Premium plans functions ----------
async def get_plan_price(plan_id):
    async with get_db() as db:
        async with db.execute("SELECT price FROM premium_plans WHERE plan_id = ?", (plan_id,)) as cursor:
            row = await cursor.fetchone()
            return row['price'] if row else None

async def update_plan_price(plan_id, price):
    async with get_db() as db:
        await db.execute("UPDATE premium_plans SET price = ? WHERE plan_id = ?", (price, plan_id))
        await db.commit()

# ---------- Discount codes ----------
async def create_discount_code(code, plan_id, discount_percent, max_uses, expiry_minutes=None):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO discount_codes (code, plan_id, discount_percent, max_uses, expiry_minutes, created_date, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (code, plan_id, discount_percent, max_uses, expiry_minutes, datetime.now().isoformat())
        )
        await db.commit()

async def get_discount_by_code(code):
    async with get_db() as db:
        async with db.execute("SELECT discount_percent, plan_id, max_uses, current_uses, expiry_minutes, created_date, is_active FROM discount_codes WHERE code = ?", (code,)) as cursor:
            return await cursor.fetchone()

async def redeem_discount_code(user_id, code, plan_id):
    async with get_db() as db:
        async with db.execute("BEGIN"):
            data = await get_discount_by_code(code)
            if not data:
                return "invalid"
            if not data['is_active']:
                return "inactive"
            if data['current_uses'] >= data['max_uses']:
                return "limit_reached"
            if data['expiry_minutes']:
                created = datetime.fromisoformat(data['created_date'])
                if datetime.now() > created + timedelta(minutes=data['expiry_minutes']):
                    return "expired"
            await db.execute("UPDATE discount_codes SET current_uses = current_uses + 1 WHERE code = ?", (code,))
            await db.commit()
            return data['discount_percent']

# ---------- Redeem codes (regular) ----------
async def create_redeem_code(code, amount, max_uses, expiry_minutes=None):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO redeem_codes (code, amount, max_uses, expiry_minutes, created_date, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (code, amount, max_uses, expiry_minutes, datetime.now().isoformat())
        )
        await db.commit()

async def redeem_code_db(user_id, code):
    async with get_db() as db:
        async with db.execute("BEGIN"):
            # Check if already claimed
            async with db.execute("SELECT 1 FROM redeem_logs WHERE user_id = ? AND code = ?", (user_id, code)) as cur:
                if await cur.fetchone():
                    return "already_claimed"
            # Get code data
            async with db.execute("SELECT amount, max_uses, current_uses, expiry_minutes, created_date, is_active FROM redeem_codes WHERE code = ?", (code,)) as cur:
                data = await cur.fetchone()
            if not data:
                return "invalid"
            if not data['is_active']:
                return "inactive"
            if data['current_uses'] >= data['max_uses']:
                return "limit_reached"
            if data['expiry_minutes']:
                created = datetime.fromisoformat(data['created_date'])
                if datetime.now() > created + timedelta(minutes=data['expiry_minutes']):
                    return "expired"
            # Update
            await db.execute("UPDATE redeem_codes SET current_uses = current_uses + 1 WHERE code = ?", (code,))
            await db.execute("UPDATE users SET credits = credits + ?, total_earned = total_earned + ? WHERE user_id = ?", (data['amount'], data['amount'], user_id))
            await db.execute("INSERT INTO redeem_logs (user_id, code, claimed_date) VALUES (?, ?, ?)", (user_id, code, datetime.now().isoformat()))
            await db.commit()
            return data['amount']

async def get_all_codes():
    async with get_db() as db:
        async with db.execute("SELECT code, amount, max_uses, current_uses, expiry_minutes, created_date, is_active FROM redeem_codes ORDER BY created_date DESC") as cursor:
            return await cursor.fetchall()

async def deactivate_code(code):
    async with get_db() as db:
        await db.execute("UPDATE redeem_codes SET is_active = 0 WHERE code = ?", (code,))
        await db.commit()

async def get_active_codes():
    async with get_db() as db:
        async with db.execute("SELECT code, amount, max_uses, current_uses FROM redeem_codes WHERE is_active = 1") as cursor:
            return await cursor.fetchall()

async def get_inactive_codes():
    async with get_db() as db:
        async with db.execute("SELECT code, amount, max_uses, current_uses FROM redeem_codes WHERE is_active = 0") as cursor:
            return await cursor.fetchall()

async def get_expired_codes():
    expired = []
    async with get_db() as db:
        async with db.execute("SELECT code, amount, current_uses, max_uses, expiry_minutes, created_date FROM redeem_codes WHERE is_active = 1 AND expiry_minutes IS NOT NULL AND expiry_minutes > 0") as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            created = datetime.fromisoformat(row['created_date'])
            if datetime.now() > created + timedelta(minutes=row['expiry_minutes']):
                expired.append(row)
        return expired

async def delete_redeem_code(code):
    async with get_db() as db:
        await db.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
        await db.commit()

async def get_code_usage_stats(code):
    async with get_db() as db:
        async with db.execute("""
            SELECT 
                rc.amount, rc.max_uses, rc.current_uses,
                COUNT(DISTINCT rl.user_id) as unique_users,
                GROUP_CONCAT(DISTINCT rl.user_id) as user_ids
            FROM redeem_codes rc
            LEFT JOIN redeem_logs rl ON rc.code = rl.code
            WHERE rc.code = ?
            GROUP BY rc.code
        """, (code,)) as cursor:
            return await cursor.fetchone()

# ---------- Lookup logs ----------
async def log_lookup(user_id, api_type, input_data, result):
    async with get_db() as db:
        await db.execute(
            "INSERT INTO lookup_logs (user_id, api_type, input_data, result, lookup_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, api_type, input_data[:500], str(result)[:1000], datetime.now().isoformat())
        )
        await db.commit()

async def get_user_lookups(user_id, limit=20):
    async with get_db() as db:
        async with db.execute("SELECT api_type, input_data, lookup_date FROM lookup_logs WHERE user_id = ? ORDER BY lookup_date DESC LIMIT ?", (user_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_total_lookups():
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM lookup_logs") as cursor:
            row = await cursor.fetchone()
            return row['cnt'] if row else 0

async def get_lookup_stats(user_id=None):
    async with get_db() as db:
        if user_id:
            async with db.execute("SELECT api_type, COUNT(*) as cnt FROM lookup_logs WHERE user_id = ? GROUP BY api_type", (user_id,)) as cursor:
                return await cursor.fetchall()
        else:
            async with db.execute("SELECT api_type, COUNT(*) as cnt FROM lookup_logs GROUP BY api_type") as cursor:
                return await cursor.fetchall()

# ---------- Statistics ----------
async def get_bot_stats():
    async with get_db() as db:
        total = await (await db.execute("SELECT COUNT(*) as c FROM users")).fetchone()
        active = await (await db.execute("SELECT COUNT(*) as c FROM users WHERE credits > 0")).fetchone()
        total_cred = await (await db.execute("SELECT SUM(credits) as s FROM users")).fetchone()
        dist = await (await db.execute("SELECT SUM(total_earned) as s FROM users")).fetchone()
        return {
            'total_users': total['c'] if total else 0,
            'active_users': active['c'] if active else 0,
            'total_credits': total_cred['s'] if total_cred and total_cred['s'] else 0,
            'credits_distributed': dist['s'] if dist and dist['s'] else 0
        }

async def get_user_stats(user_id):
    async with get_db() as db:
        refs = await (await db.execute("SELECT COUNT(*) as refs FROM users WHERE referrer_id = ?", (user_id,))).fetchone()
        codes = await (await db.execute("SELECT COUNT(*) as codes FROM redeem_logs WHERE user_id = ?", (user_id,))).fetchone()
        tot = await (await db.execute("SELECT SUM(amount) as total FROM redeem_logs rl JOIN redeem_codes rc ON rl.code = rc.code WHERE rl.user_id = ?", (user_id,))).fetchone()
        return {
            'referrals': refs['refs'] if refs else 0,
            'codes_claimed': codes['codes'] if codes else 0,
            'total_from_codes': tot['total'] if tot and tot['total'] else 0
        }

async def get_recent_users(limit=20):
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, joined_date FROM users ORDER BY joined_date DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def get_top_referrers(limit=10):
    async with get_db() as db:
        async with db.execute("SELECT referrer_id, COUNT(*) as referrals FROM users WHERE referrer_id IS NOT NULL GROUP BY referrer_id ORDER BY referrals DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def get_users_in_range(start_date, end_date):
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, credits, joined_date FROM users WHERE CAST(joined_date AS FLOAT) BETWEEN ? AND ?", (start_date, end_date)) as cursor:
            return await cursor.fetchall()

async def get_leaderboard(limit=10):
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, credits FROM users WHERE is_banned = 0 ORDER BY credits DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def get_low_credit_users():
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, credits FROM users WHERE credits <= 5 ORDER BY credits ASC") as cursor:
            return await cursor.fetchall()

async def get_inactive_users(days=30):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with get_db() as db:
        async with db.execute("SELECT user_id, username, last_active FROM users WHERE last_active < ? AND is_banned = 0 ORDER BY last_active ASC", (cutoff,)) as cursor:
            return await cursor.fetchall()

async def get_daily_stats(days=7):
    async with get_db() as db:
        # SQLite equivalent: group by date from joined_date (Unix timestamp)
        # We convert joined_date (string of Unix timestamp) to date
        async with db.execute("""
            SELECT 
                date(joined_date, 'unixepoch') as join_date,
                COUNT(*) as new_users
            FROM users
            WHERE datetime(joined_date, 'unixepoch') >= datetime('now', ?)
            GROUP BY join_date
            ORDER BY join_date DESC
        """, (f'-{days} days',)) as cursor:
            rows = await cursor.fetchall()
        # Also need to add lookups per day? Original had lookups subquery. We'll add similar.
        result = []
        for row in rows:
            join_date = row['join_date']
            async with db.execute("SELECT COUNT(*) as lookups FROM lookup_logs WHERE date(lookup_date) = ?", (join_date,)) as cur:
                lookups_row = await cur.fetchone()
            result.append({
                'join_date': join_date,
                'new_users': row['new_users'],
                'lookups': lookups_row['lookups'] if lookups_row else 0
            })
        return result

# ---------- Admin management ----------
async def add_admin(user_id, level='admin'):
    async with get_db() as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)", (user_id, level))
        await db.commit()

async def remove_admin(user_id):
    async with get_db() as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_all_admins():
    async with get_db() as db:
        async with db.execute("SELECT user_id, level FROM admins") as cursor:
            return await cursor.fetchall()

async def is_admin(user_id):
    async with get_db() as db:
        async with db.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row['level'] if row else None

# ---------- Utility ----------
async def search_users(query):
    try:
        q_int = int(query)
    except:
        q_int = 0
    async with get_db() as db:
        # SQLite uses LIKE (case-insensitive by default? Actually only if compiled with unicode, but we use lower())
        async with db.execute("SELECT user_id, username, credits FROM users WHERE LOWER(username) LIKE ? OR user_id = ? LIMIT 20", (f'%{query.lower()}%', q_int)) as cursor:
            return await cursor.fetchall()

async def delete_user(user_id):
    async with get_db() as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM redeem_logs WHERE user_id = ?", (user_id,))
        await db.execute("UPDATE users SET referrer_id = NULL WHERE referrer_id = ?", (user_id,))
        await db.commit()

async def reset_user_credits(user_id):
    async with get_db() as db:
        await db.execute("UPDATE users SET credits = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

async def bulk_update_credits(user_ids, amount):
    async with get_db() as db:
        for uid in user_ids:
            if amount > 0:
                await db.execute("UPDATE users SET credits = credits + ?, total_earned = total_earned + ? WHERE user_id = ?", (amount, amount, uid))
            else:
                await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (amount, uid))
        await db.commit()
