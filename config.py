# config.py – Number Info Bot (Complete & Ready to Deploy)

import os

# ---------- Owner & Admins ----------
OWNER_ID = 8104850843
ADMIN_IDS = [5987905091]

# ---------- Force Join Channels (Name, Link, ID) ----------
FORCE_JOIN_CHANNELS = [
    {"name": "All Data Here", "link": "https://t.me/all_data_here", "id": -1003090922367},
    {"name": "OSINT Lookup", "link": "https://t.me/osint_lookup", "id": -1003698567122},
    {"name": "LEGEND CHATS", "link": "https://t.me/legend_chats_osint", "id": -1003672015073}
]

# ---------- Log Channel for Number Lookups ----------
LOG_CHANNEL_NUM = -1003482423742

# ---------- Number Info API ----------
NUM_API = {
    'url': 'https://ayaanmods.site/number.php?key=annonymous&number={}',
    'param': 'number',
    'desc': 'Mobile number lookup',
    'extra_blacklist': ['API_Developer', 'channel_name', 'channel_link']
}

# ---------- Branding ----------
DEV_USERNAME = "@Nullprotocol_X"
POWERED_BY = "NULL PROTOCOL"

# ---------- Backup Channel ----------
BACKUP_CHANNEL = -1003740236326

# ---------- Webhook Settings (for Render deployment) ----------
WEBHOOK_URL = "https://testjson-dkk2.onrender.com"
PORT = int(os.environ.get("PORT", 8000))
