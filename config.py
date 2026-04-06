import os
from dotenv import load_dotenv

load_dotenv()  # for local testing; on Render use env vars directly

TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY", "")
API_PARAM_NAME = os.getenv("API_PARAM_NAME", "number")

# Force channels: list of channel IDs (integers) and their usernames (for invite links)
FORCE_CHANNEL_IDS = [int(x.strip()) for x in os.getenv("FORCE_CHANNEL_IDS", "-1003090922367").split(",")]
FORCE_CHANNEL_USERNAMES = [x.strip() for x in os.getenv("FORCE_CHANNEL_USERNAMES", "all_data_here").split(",")]

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003482423742"))

# Webhook settings
PORT = int(os.getenv("PORT", 8443))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com
WEBHOOK_PATH = f"/{TOKEN}" if TOKEN else "/webhook"
