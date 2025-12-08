import telebot
from telebot.types import ChatPermissions
from functools import wraps
from collections import deque
import re
import time

API_TOKEN = "YOUR_BOT_TOKEN"
bot = telebot.TeleBot(API_TOKEN, parse_mode="Markdown")

# ====================================================
#                   CONFIGURATION
# ====================================================

USE_REAL_ADMINS = True
STATIC_ADMINS = {123456789}

BLOCK_MEDIA = False
BLOCK_LINKS = True
FLOOD_PROTECTION = True
ANTI_BOT = True
CLEAN_JOIN = True
CLEAN_LEAVE = True

WELCOME_MSG = "🎉 Welcome, {name}!"

MAX_MSG = 5
WINDOW = 4
AUTO_MUTE = 30

URL_REGEX = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+)",
    re.IGNORECASE
)

# ====================================================
#                     DATA STORAGE
# ====================================================

WARNINGS = {}
SHADOW_BANNED = set()
ROLES = {}
FLOOD_TRACKER = {}  # uid -> deque

# ====================================================
#                       HELPERS
# ====================================================

def safe_call(func, *args, **kwargs):
    """Run Telegram API calls safely."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return None


def get_real_admins(chat_id):
    try:
        admins = bot.get_chat_administrators(chat_id)
        return {adm.user.id for adm in admins}
    except:
        return STATIC_ADMINS


def is_admin(uid, chat_id):
    admins = get_real_admins(chat_id) if USE_REAL_ADMINS else STATIC_ADMINS
    return uid in admins


def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not is_admin(message.from_user.id, message.chat.id):
            return safe_call(bot.reply_to, message, "❌ You don’t have permission.")
        return func(message, *args, **kwargs)
    return wrapper


def extract_target(message):
    """Extract user target from reply."""
    if not message.reply_to_message:
        return safe_call(bot.reply_to, message, "Reply to a user's message.")

    user = message.reply_to_message.from_user
    chat_id = message.chat.id
    bot_id = bot.get_me().id

    if user.id == message.from_user.id:
        return safe_call(bot.reply_to, message, "You cannot target yourself.")
    if user.id == bot_id:
        return safe_call(bot.reply_to, message, "I refuse to punish myself 😿")
    if is_admin(user.id, chat_id):
        return safe_call(bot.reply_to, message, "Admins cannot be moderated.")

    return user.id


def full_permissions():
    return ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
        can_send_polls=True
    )

# ====================================================
#                START / HELP
# ====================================================

@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.reply_to(message, """
👋 **Admin Bot Control Panel**

**Moderation**
• /kick — Kick  
• /ban — Ban  
• /unban  
• /mute — 10m  
• /unmute  
• /tban <minutes>  
• /purge  
• /warn  
• /clearwarn  
• /shadowban  
• /unshadow  

**Chat Management**
• /lock /unlock  
• /pin /unpin  
• /slowmode <sec>  

**Roles**
• /role <role>  
• /myrole  

**Security**
• /antilink on/off  
• /antimedia on/off  
• /flood on/off  
• /use_real_admins on/off  

Welcome system, anti-bot, and join/leave cleaner are active.
""")

# ====================================================
#                     MODERATION
# ====================================================

@bot.message_handler(commands=['kick'])
@admin_only
def kick_user(message):
    uid = extract_target(message)
    if uid:
        safe_call(bot.kick_chat_member, message.chat.id, uid)
        bot.send_message(message.chat.id, f"👢 Kicked `{uid}`")

@bot.message_handler(commands=['ban'])
@admin_only
def ban_user(message):
    uid = extract_target(message)
    if uid:
        safe_call(bot.ban_chat_member, message.chat.id, uid)
        bot.send_message(message.chat.id, f"🚫 Banned `{uid}`")

@bot.message_handler(commands=['unban'])
@admin_only
def unban_user(message):
    uid = extract_target(message)
    if uid:
        safe_call(bot.unban_chat_member, message.chat.id, uid)
        bot.send_message(message.chat.id, f"♻️ Unbanned `{uid}`")

# ====================================================
#                     MUTE SYSTEM
# ====================================================

@bot.message_handler(commands=['mute'])
@admin_only
def mute(message):
    uid = extract_target(message)
    if uid:
        safe_call(bot.restrict_chat_member, message.chat.id, uid,
                  permissions=ChatPermissions(can_send_messages=False),
                  until_date=int(time.time() + 600))
        bot.send_message(message.chat.id, f"🔇 Muted `{uid}` for 10m")

@bot.message_handler(commands=['unmute'])
@admin_only
def unmute(message):
    uid = extract_target(message)
    if uid:
        safe_call(bot.restrict_chat_member, message.chat.id, uid,
                  permissions=full_permissions())
        bot.send_message(message.chat.id, f"🔊 Unmuted `{uid}`")

# ====================================================
#                     TEMP BAN
# ====================================================

@bot.message_handler(commands=['tban'])
@admin_only
def tban(message):
    if not message.reply_to_message:
        return bot.reply_to(message, "Usage: reply + /tban <minutes>")

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return bot.reply_to(message, "Usage: /tban <minutes>")

    minutes = int(parts[1])
    uid = message.reply_to_message.from_user.id

    safe_call(bot.ban_chat_member, message.chat.id, uid,
              until_date=int(time.time() + minutes * 60))

    bot.send_message(message.chat.id,
                     f"⛔ Temp-banned `{uid}` for {minutes} minutes")

# ====================================================
#                     WARN SYSTEM
# ====================================================

@bot.message_handler(commands=['warn'])
@admin_only
def warn(message):
    uid = extract_target(message)
    if not uid:
        return

    chat = message.chat.id
    WARNINGS.setdefault(chat, {})
    WARNINGS[chat][uid] = WARNINGS[chat].get(uid, 0) + 1

    count = WARNINGS[chat][uid]
    if count >= 3:
        safe_call(bot.ban_chat_member, chat, uid)
        bot.send_message(chat, f"⛔ `{uid}` auto-banned (3 warnings)")
    else:
        bot.send_message(chat, f"⚠ Warning {count}/3 for `{uid}`")

@bot.message_handler(commands=['clearwarn'])
@admin_only
def clearwarn(message):
    uid = extract_target(message)
    if uid:
        WARNINGS.get(message.chat.id, {}).pop(uid, None)
        bot.send_message(message.chat.id,
                         f"✨ Warnings cleared for `{uid}`")

# ====================================================
#                         PURGE
# ====================================================

@bot.message_handler(commands=['purge'])
@admin_only
def purge(message):
    if not message.reply_to_message:
        return bot.reply_to(message, "Reply to a message to purge from.")

    start = message.reply_to_message.message_id
    end = message.message_id

    for mid in range(start, end + 1):
        safe_call(bot.delete_message, message.chat.id, mid)

    bot.send_message(message.chat.id, "🗑 Purge complete.")

# ====================================================
#                     LOCK / UNLOCK
# ====================================================

@bot.message_handler(commands=['lock'])
@admin_only
def lock(message):
    safe_call(bot.set_chat_permissions, message.chat.id,
              ChatPermissions(can_send_messages=False))
    bot.send_message(message.chat.id, "🔐 Chat locked")

@bot.message_handler(commands=['unlock'])
@admin_only
def unlock(message):
    safe_call(bot.set_chat_permissions, message.chat.id, full_permissions())
    bot.send_message(message.chat.id, "🔓 Chat unlocked")

# ====================================================
#                     PIN / UNPIN
# ====================================================

@bot.message_handler(commands=['pin'])
@admin_only
def pin(message):
    if not message.reply_to_message:
        return bot.reply_to(message, "Reply to a message to pin.")
    safe_call(bot.pin_chat_message,
              message.chat.id,
              message.reply_to_message.message_id)

@bot.message_handler(commands=['unpin'])
@admin_only
def unpin(message):
    safe_call(bot.unpin_chat_message, message.chat.id)

# ====================================================
#                     SLOWMODE
# ====================================================

@bot.message_handler(commands=['slowmode'])
@admin_only
def slowmode(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return bot.reply_to(message, "Usage: /slowmode <seconds>")

    seconds = int(parts[1])
    safe_call(bot.set_chat_slow_mode, message.chat.id, seconds)
    bot.send_message(message.chat.id,
                     f"🐢 Slowmode set to {seconds}s")

# ====================================================
#                       ROLES
# ====================================================

@bot.message_handler(commands=['role'])
@admin_only
def role(message):
    if not message.reply_to_message:
        return bot.reply_to(message, "Reply + /role <name>")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "Usage: /role <text>")

    uid = message.reply_to_message.from_user.id
    ROLES[uid] = parts[1]

    bot.send_message(message.chat.id,
                     f"🎖 Assigned role: `{parts[1]}`")

@bot.message_handler(commands=['myrole'])
def myrole(message):
    role = ROLES.get(message.from_user.id, "No role assigned")
    bot.reply_to(message, f"Your role: **{role}**")

# ====================================================
#                  SHADOWBAN SYSTEM
# ====================================================

@bot.message_handler(commands=['shadowban'])
@admin_only
def shadowban(message):
    uid = extract_target(message)
    if uid:
        SHADOW_BANNED.add(uid)
        bot.send_message(message.chat.id,
                         f"👁 Shadow-banned `{uid}`")

@bot.message_handler(commands=['unshadow'])
@admin_only
def unshadow(message):
    uid = extract_target(message)
    if uid:
        SHADOW_BANNED.discard(uid)
        bot.send_message(message.chat.id,
                         f"👁 Removed shadowban for `{uid}`")

# ====================================================
#                  SETTINGS / TOGGLES
# ====================================================

def toggle(message, var_name, label):
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "Use: on/off")

    value = parts[1].lower()
    if value not in {"on", "off"}:
        return bot.reply_to(message, "Use: on/off")

    globals()[var_name] = (value == "on")
    bot.reply_to(message, f"{label} {'enabled' if value == 'on' else 'disabled'}")

@bot.message_handler(commands=['antilink'])
@admin_only
def antl(message): toggle(message, "BLOCK_LINKS", "🔗 Anti-link")

@bot.message_handler(commands=['antimedia'])
@admin_only
def antm(message): toggle(message, "BLOCK_MEDIA", "📵 Anti-media")

@bot.message_handler(commands=['flood'])
@admin_only
def antf(message): toggle(message, "FLOOD_PROTECTION", "🚨 Anti-flood")

@bot.message_handler(commands=['use_real_admins'])
@admin_only
def usar(message): toggle(message, "USE_REAL_ADMINS", "🛡 Real admin checks")

# ====================================================
#          UNIFIED JOIN / LEAVE HANDLER
# ====================================================

@bot.message_handler(content_types=['new_chat_members'])
def handle_join(message):
    bot_info = bot.get_me()

    # Clean join notification
    if CLEAN_JOIN:
        safe_call(bot.delete_message, message.chat.id, message.message_id)

    for user in message.new_chat_members:

        # Anti-bot protection
        if ANTI_BOT and user.is_bot and not is_admin(user.id, message.chat.id):
            safe_call(bot.kick_chat_member, message.chat.id, user.id)
            continue

        # Bot introduced
        if user.id == bot_info.id:
            safe_call(bot.send_message, message.chat.id,
                      "👋 Thanks for adding me!\n"
                      "Please promote me to admin so I can clean join/leave messages and protect your group.")
            continue

        # Welcome normal users
        safe_call(bot.send_message, message.chat.id,
                  WELCOME_MSG.replace("{name}", user.first_name))

@bot.message_handler(content_types=['left_chat_member'])
def handle_leave(message):
    if CLEAN_LEAVE:
        safe_call(bot.delete_message, message.chat.id, message.message_id)

# ====================================================
#               MESSAGE FILTER PROTECTION
# ====================================================

@bot.message_handler(content_types=['text', 'photo', 'document', 'video', 'sticker'])
def filter_messages(message):
    uid = message.from_user.id
    chat = message.chat.id

    # Shadowban
    if uid in SHADOW_BANNED:
        return safe_call(bot.delete_message, chat, message.message_id)

    # Anti-link
    if BLOCK_LINKS and message.content_type == "text":
        if URL_REGEX.search(message.text):
            return safe_call(bot.delete_message, chat, message.message_id)

    # Anti-media
    if BLOCK_MEDIA and message.content_type in ['photo', 'video', 'document', 'sticker']:
        return safe_call(bot.delete_message, chat, message.message_id)

    # Flood protection
    if FLOOD_PROTECTION:
        now = time.time()
        dq = FLOOD_TRACKER.setdefault(uid, deque())
        dq.append(now)

        while dq and now - dq[0] > WINDOW:
            dq.popleft()

        if len(dq) > MAX_MSG:
            safe_call(bot.delete_message, chat, message.message_id)
            safe_call(bot.restrict_chat_member,
                      chat,
                      uid,
                      permissions=ChatPermissions(can_send_messages=False),
                      until_date=int(now + AUTO_MUTE))

            bot.send_message(chat,
                             f"🚫 Flood detected! Muted for {AUTO_MUTE}s")

# ====================================================
#                      RUN BOT
# ====================================================

print("Bot is running...")
bot.infinity_polling() 
