import telebot
from telebot import apihelper
from telebot.types import JsonSerializable, BotCommand
import json
import os
import random
import string
import time
import threading
import html
import re
from datetime import datetime

# ==========================================
# 1. BOT & OWNER CONFIGURATION (@IQ_Qr_Work_Bot)
# ==========================================
BOT_TOKEN = "8626499617:AAFwcn3dfKp7fF9Gmh2WZMjmekCKi4e6KFI"
BOT_USERNAME = "IQ_Qr_Work_Bot"
OWNER_ID = 8208439680
OWNER_USERNAME = "Deadly_IQ"
EMOJI_PACK_NAME = "TGOTPNews_by_TGOTPNews1Bot"
DATA_FILE = "iq_qr_2_bot_db.json"
EMOJI_CACHE_FILE = "emoji_pack_cache.json"
EMOJI_REFRESH_MINUTES = 30

DEFAULT_WELCOME_TEMPLATE = (
    "{e1} Welcome To IQ Qr Bot {e2}\n"
    "{name} {e3}\n"
    "This Bot Is Best Bot {e4}"
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

ACTIVE_QR_ORDERS = {}
QR_LOCK = threading.RLock()
QR_BROADCAST_MSGS = {}

# ==========================================
# 2. SET TELEGRAM MENU BUTTON (/start & /admin)
# ==========================================
def setup_bot_menu_commands():
    try:
        commands = [
            BotCommand("start", "Start bot and open main menu"),
            BotCommand("admin", "Open Owner Admin Portal")
        ]
        bot.set_my_commands(commands)
        print("✅ Menu commands (/start and /admin) registered!")
    except Exception as e:
        print(f"⚠️ Could not set menu commands: {e}")

setup_bot_menu_commands()

# ==========================================
# 3. LOAD PREMIUM EMOJIS FROM TGOTPNews_by_TGOTPNews1Bot
# ==========================================
PACK_EMOJIS = []
PACK_INFO = {"updated": None, "source": None}
PACK_LOCK = threading.Lock()

FALLBACK_EMOJI_IDS = [
    {"id": "5312536423581202898", "char": "❤️"},
    {"id": "5373141891321699086", "char": "📊"},
    {"id": "5370574634750056701", "char": "🐱"},
    {"id": "5309958691852759293", "char": "💎"},
    {"id": "5312322066326862146", "char": "🏆"},
    {"id": "5312016608252770056", "char": "👑"},
    {"id": "5312241539985029622", "char": "🔥"},
    {"id": "5312138559554171506", "char": "✅"},
    {"id": "5312383351282316458", "char": "❌"},
    {"id": "5312315739840034655", "char": "📘"},
    {"id": "5312486108299375838", "char": "🚀"}
]

def _save_emoji_cache(items):
    try:
        with open(EMOJI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "pack": EMOJI_PACK_NAME,
                "updated": datetime.now().strftime("%d %b %Y, %I:%M %p"),
                "count": len(items),
                "emojis": items
            }, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Could not save emoji cache: {e}")

def _load_emoji_cache():
    try:
        with open(EMOJI_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        emojis = data.get("emojis", [])
        if len(emojis) <= 11 and data.get("pack") != EMOJI_PACK_NAME:
            return [], None
        return emojis, data.get("updated")
    except Exception:
        return [], None

def _fetch_pack_from_telegram():
    items = []
    try:
        raw_set = apihelper._make_request(BOT_TOKEN, "getStickerSet", params={"name": EMOJI_PACK_NAME})
        for st in raw_set.get("stickers", []):
            ce_id = st.get("custom_emoji_id")
            if ce_id:
                ch = st.get("emoji") or "⚡"
                items.append({"id": str(ce_id), "char": ch})
        if items:
            return items
    except Exception:
        pass

    sticker_set = bot.get_sticker_set(EMOJI_PACK_NAME)
    for st in (sticker_set.stickers if sticker_set else []):
        ce_id = getattr(st, "custom_emoji_id", None)
        if ce_id:
            items.append({"id": str(ce_id), "char": getattr(st, "emoji", None) or "⚡"})
    return items

def refresh_emoji_pack():
    global PACK_EMOJIS
    old_ids = {e["id"] for e in PACK_EMOJIS}
    items, source = [], "telegram"
    try:
        items = _fetch_pack_from_telegram()
    except Exception as e:
        print(f"⚠️ Could not load pack {EMOJI_PACK_NAME}: {e}")

    if items:
        _save_emoji_cache(items)
        updated = datetime.now().strftime("%d %b %Y, %I:%M %p")
    else:
        items, updated = _load_emoji_cache()
        source = "saved cache"
        if not items:
            items = list(FALLBACK_EMOJI_IDS)
            source, updated = "fallback", None

    new_ids = {e["id"] for e in items}
    with PACK_LOCK:
        PACK_EMOJIS = items
        PACK_INFO["updated"] = updated
        PACK_INFO["source"] = source

    added = len(new_ids - old_ids) if old_ids else 0
    removed = len(old_ids - new_ids)
    print(f"✅ Emoji pack loaded: {len(items)} premium emojis ({source})")
    return len(items), added, removed, source

def auto_refresh_emoji_pack_loop():
    while True:
        time.sleep(EMOJI_REFRESH_MINUTES * 60)
        try:
            refresh_emoji_pack()
        except Exception as e:
            print(f"⚠️ Auto emoji refresh failed: {e}")

refresh_emoji_pack()

# ==========================================
# 3B. TELEGRAM MESSAGE -> HTML
# ==========================================
def _entity_tags(e):
    t = getattr(e, "type", None) or (e.get("type") if isinstance(e, dict) else None)
    if t == "bold":
        return "<b>", "</b>"
    if t == "italic":
        return "<i>", "</i>"
    if t == "underline":
        return "<u>", "</u>"
    if t == "strikethrough":
        return "<s>", "</s>"
    if t == "spoiler":
        return "<tg-spoiler>", "</tg-spoiler>"
    if t == "code":
        return "<code>", "</code>"
    if t == "pre":
        lang = getattr(e, "language", None) or (e.get("language") if isinstance(e, dict) else None)
        if lang:
            return f'<pre><code class="language-{html.escape(lang)}">', "</code></pre>"
        return "<pre>", "</pre>"
    if t == "text_link":
        url = getattr(e, "url", None) or (e.get("url") if isinstance(e, dict) else None)
        if url:
            return f'<a href="{html.escape(url)}">', "</a>"
    if t == "text_mention":
        user = getattr(e, "user", None) or (e.get("user") if isinstance(e, dict) else None)
        uid = getattr(user, "id", None) if user else None
        if uid:
            return f'<a href="tg://user?id={uid}">', "</a>"
    if t == "custom_emoji":
        ce_id = getattr(e, "custom_emoji_id", None) or (e.get("custom_emoji_id") if isinstance(e, dict) else None)
        if ce_id:
            return f'<tg-emoji emoji-id="{ce_id}">', "</tg-emoji>"
    if t == "blockquote":
        return "<blockquote>", "</blockquote>"
    if t == "expandable_blockquote":
        return "<blockquote expandable>", "</blockquote>"
    return None, None

def message_to_html(text, entities):
    if not text:
        return ""
    if not entities:
        return html.escape(text, quote=False)

    data = text.encode("utf-16-le")
    total = len(data) // 2
    opens, closes, points = {}, {}, {0, total}

    for e in sorted(entities, key=lambda x: (getattr(x, "offset", 0), -getattr(x, "length", 0))):
        o_tag, c_tag = _entity_tags(e)
        if not o_tag:
            continue
        start = getattr(e, "offset", 0)
        end = start + getattr(e, "length", 0)
        opens.setdefault(start, []).append(o_tag)
        closes.setdefault(end, []).insert(0, c_tag)
        points.update([start, end])

    out = []
    ordered = sorted(points)
    for i, pos in enumerate(ordered):
        out.extend(closes.get(pos, []))
        out.extend(opens.get(pos, []))
        if i + 1 < len(ordered):
            seg = data[pos * 2:ordered[i + 1] * 2].decode("utf-16-le")
            out.append(html.escape(seg, quote=False))
    return "".join(out)

def strip_custom_emoji(html_text):
    return re.sub(r'<tg-emoji emoji-id="[^"]+">(.*?)</tg-emoji>', r"\1", html_text, flags=re.S)

def get_pack_emoji_id(index):
    with PACK_LOCK:
        item = PACK_EMOJIS[index % len(PACK_EMOJIS)]
        return str(item["id"])

def get_pack_emoji_char(index):
    with PACK_LOCK:
        item = PACK_EMOJIS[index % len(PACK_EMOJIS)]
        return item.get("char") or "⚡"

def pe(index):
    with PACK_LOCK:
        item = PACK_EMOJIS[index % len(PACK_EMOJIS)]
        ch = item.get("char") or "⚡"
        return f'<tg-emoji emoji-id="{item["id"]}">{ch}</tg-emoji>'

EMOJI_SLOT = {
    "task": 0, "profile": 1, "balance": 2, "edit": 3,
    "withdraw": 4, "leaderboard": 5, "how_to_work": 6, "owner": 7,
    "check": 8, "cross": 9, "timer": 10, "link": 11,
    "user": 12, "price": 13, "alert": 14, "image": 15
}

def slot_id(name):
    return get_pack_emoji_id(EMOJI_SLOT.get(name, 0))

def slot_char(name):
    return get_pack_emoji_char(EMOJI_SLOT.get(name, 0))

def slot_tag(name):
    return pe(EMOJI_SLOT.get(name, 0))

# ==========================================
# 4. GLOWING KEYBOARD ENGINE
# ==========================================
class GlowReplyKeyboard(JsonSerializable):
    def __init__(self, resize_keyboard=True, is_persistent=True, use_custom_emoji=True):
        self.keyboard = []
        self.resize_keyboard = resize_keyboard
        self.is_persistent = is_persistent
        self.use_custom_emoji = use_custom_emoji

    def add_row(self, *buttons):
        row = []
        for b in buttons:
            btn_dict = {"text": b["text"]}
            if b.get("style"):
                btn_dict["style"] = b["style"]
            if self.use_custom_emoji and b.get("emoji_id"):
                btn_dict["icon_custom_emoji_id"] = str(b["emoji_id"])
            row.append(btn_dict)
        self.keyboard.append(row)

    def to_json(self):
        return json.dumps({
            "keyboard": self.keyboard,
            "resize_keyboard": self.resize_keyboard,
            "is_persistent": self.is_persistent
        })


class GlowInlineKeyboard(JsonSerializable):
    def __init__(self, use_custom_emoji=True):
        self.inline_keyboard = []
        self.use_custom_emoji = use_custom_emoji

    def add_row(self, *buttons):
        row = []
        for b in buttons:
            btn_dict = {"text": b["text"]}
            if b.get("url"):
                btn_dict["url"] = b["url"]
            elif b.get("callback_data"):
                btn_dict["callback_data"] = b["callback_data"]
            if b.get("style"):
                btn_dict["style"] = b["style"]
            if self.use_custom_emoji and b.get("emoji_id"):
                btn_dict["icon_custom_emoji_id"] = str(b["emoji_id"])
            row.append(btn_dict)
        self.inline_keyboard.append(row)

    def to_json(self):
        return json.dumps({"inline_keyboard": self.inline_keyboard})


def safe_send(chat_id, text, markup_builder=None):
    if markup_builder is None:
        try:
            return bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception:
            return bot.send_message(chat_id, strip_custom_emoji(text), parse_mode="HTML")

    try:
        return bot.send_message(chat_id, text, reply_markup=markup_builder(True), parse_mode="HTML")
    except Exception as e:
        err_str = str(e).upper()
        if "BUTTON_CUSTOM_EMOJI" in err_str:
            try:
                return bot.send_message(chat_id, text, reply_markup=markup_builder(False), parse_mode="HTML")
            except Exception:
                return bot.send_message(chat_id, strip_custom_emoji(text), reply_markup=markup_builder(False), parse_mode="HTML")
        if "CUSTOM_EMOJI" in err_str or "ENTITIES" in err_str:
            return bot.send_message(chat_id, strip_custom_emoji(text), reply_markup=markup_builder(False), parse_mode="HTML")
        raise e


def safe_send_photo(chat_id, photo_id, caption, markup_builder=None):
    if markup_builder is None:
        try:
            return bot.send_photo(chat_id, photo_id, caption=caption, parse_mode="HTML")
        except Exception:
            return bot.send_photo(chat_id, photo_id, caption=strip_custom_emoji(caption), parse_mode="HTML")

    try:
        return bot.send_photo(chat_id, photo_id, caption=caption, reply_markup=markup_builder(True), parse_mode="HTML")
    except Exception as e:
        err_str = str(e).upper()
        if "BUTTON_CUSTOM_EMOJI" in err_str:
            return bot.send_photo(chat_id, photo_id, caption=caption, reply_markup=markup_builder(False), parse_mode="HTML")
        raise e

# ==========================================
# 5. DATABASE AUTO-RECOVERY & LOAD/SAVE
# ==========================================
def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")

def load_db():
    today = get_today_str()
    default_db = {
        "owner_id": OWNER_ID,
        "owner_username": OWNER_USERNAME,
        "qr_rate": 50,
        "agent_bonus": 5,
        "agent_target": 25,
        "welcome_image": None,
        "welcome_message": None,
        "leaderboard_date": today,
        "users": {},
        "tasks": {},
        "verifications": [],
        "withdrawals": []
    }

    if not os.path.exists(DATA_FILE):
        save_db(default_db)
        return default_db

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ Database corrupted! Creating fresh backup and resetting DB: {e}")
        try:
            os.rename(DATA_FILE, DATA_FILE + ".bak")
        except Exception:
            pass
        save_db(default_db)
        return default_db

    changed = False
    if data.get("owner_id") != OWNER_ID:
        data["owner_id"] = OWNER_ID
        changed = True
    if data.get("owner_username") != OWNER_USERNAME:
        data["owner_username"] = OWNER_USERNAME
        changed = True
    if "welcome_image" not in data:
        data["welcome_image"] = None
        changed = True
    if "welcome_message" not in data:
        data["welcome_message"] = None
        changed = True
    if "agent_bonus" not in data:
        data["agent_bonus"] = 5
        changed = True
    if "agent_target" not in data:
        data["agent_target"] = 25
        changed = True

    for key in ["verifications", "withdrawals"]:
        if key not in data:
            data[key] = []
            changed = True
    if "leaderboard_date" not in data:
        data["leaderboard_date"] = today
        changed = True

    if data["leaderboard_date"] != today:
        data["leaderboard_date"] = today
        for uid in data.get("users", {}):
            data["users"][uid]["daily_completed"] = 0
            data["users"][uid]["daily_earned"] = 0
        changed = True

    for uid, u in data.get("users", {}).items():
        if "account_status" not in u:
            u["account_status"] = "ACTIVE"
            changed = True
        if "daily_completed" not in u:
            u["daily_completed"] = u.get("completed", 0)
            changed = True
        if "daily_earned" not in u:
            u["daily_earned"] = u.get("total_earned", 0)
            changed = True
        if "upi_id" not in u:
            u["upi_id"] = "Not Set"
            changed = True
        if "agent_status" not in u:
            u["agent_status"] = "LOCKED"
            changed = True
        if "agent_bonus_earned" not in u:
            u["agent_bonus_earned"] = 0
            changed = True

    if "tasks" not in data:
        data["tasks"] = {}
        changed = True
    for t in data["tasks"].values():
        if "status" not in t:
            t["status"] = "LEGACY"
            changed = True

    if changed:
        save_db(data)
    return data

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def ensure_user(user):
    db = load_db()
    uid = str(user.id)
    raw_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Worker"
    full_name = html.escape(raw_name)
    uname = html.escape(user.username or "N/A")
    if uid not in db["users"]:
        db["users"][uid] = {
            "id": uid,
            "name": full_name,
            "username": uname,
            "upi_id": "Not Set",
            "account_status": "ACTIVE",
            "balance": 0,
            "total_earned": 0,
            "total_withdrawn": 0,
            "completed": 0,
            "daily_completed": 0,
            "daily_earned": 0,
            "failed": 0,
            "pending_tasks": 0,
            "agent_status": "LOCKED",
            "agent_bonus_earned": 0,
            "joined": datetime.now().strftime("%d %b %Y"),
            "history": []
        }
        save_db(db)
    else:
        db["users"][uid]["username"] = uname
        save_db(db)
    return db["users"][uid]

def is_owner(user_or_id):
    if hasattr(user_or_id, "id"):
        if int(user_or_id.id) == OWNER_ID:
            return True
        uname = getattr(user_or_id, "username", None)
        if uname and uname.strip().lstrip("@").lower() == OWNER_USERNAME.lower():
            return True
        return False
    try:
        return int(user_or_id) == OWNER_ID
    except Exception:
        return False

def check_user_allowed(user_obj, chat_id):
    if is_owner(user_obj):
        return True
    u = ensure_user(user_obj)
    status = u.get("account_status", "ACTIVE")
    if status == "BANNED":
        safe_send(
            chat_id,
            f"{slot_tag('cross')} Account Banned\n\nAapka account Owner (@{OWNER_USERNAME}) dwara permanent ban kar diya gaya hai."
        )
        return False
    if status == "SUSPENDED":
        safe_send(
            chat_id,
            f"{slot_tag('alert')} Account Suspended\n\nAapka account abhi Owner (@{OWNER_USERNAME}) dwara suspend kiya gaya hai."
        )
        return False
    return True

# ==========================================
# 6. GLOWING BOTTOM MENUS
# ==========================================
def build_worker_glow_keyboard(user_or_id=None):
    def _builder(use_ce=True):
        kb = GlowReplyKeyboard(resize_keyboard=True, is_persistent=True, use_custom_emoji=use_ce)
        kb.add_row(
            {"text": "Task", "style": "success", "emoji_id": slot_id("task")},
            {"text": "Profile", "style": "primary", "emoji_id": slot_id("profile")}
        )
        kb.add_row(
            {"text": "Balance", "style": "success", "emoji_id": slot_id("balance")},
            {"text": "Withdraw", "style": "primary", "emoji_id": slot_id("withdraw")}
        )
        kb.add_row(
            {"text": "Leaderboard", "style": "primary", "emoji_id": slot_id("leaderboard")},
            {"text": "How to Work", "style": "primary", "emoji_id": slot_id("how_to_work")}
        )
        kb.add_row(
            {"text": "Agent", "style": "danger", "emoji_id": slot_id("owner")}
        )
        return kb
    return _builder


# ==========================================
# 6B. AGENT SYSTEM
# ==========================================
def agent_is_active(u):
    return u.get("agent_status") == "ACTIVE"

def agent_bonus_for(u, db):
    return int(db.get("agent_bonus", 5)) if agent_is_active(u) else 0

def try_unlock_agent(u, db):
    if u.get("agent_status", "LOCKED") == "LOCKED" and u.get("completed", 0) >= int(db.get("agent_target", 25)):
        u["agent_status"] = "ACTIVE"
        u["agent_since"] = datetime.now().strftime("%d %b %Y")
        u["history"].append("Agent Unlocked")
        return True
    return False

def build_agent_card(u, db):
    target = int(db.get("agent_target", 25))
    bonus = int(db.get("agent_bonus", 5))
    done = u.get("completed", 0)
    status = u.get("agent_status", "LOCKED")

    if status == "ACTIVE":
        return (
            f"{slot_tag('owner')} Agent Panel {slot_tag('check')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('owner')} Verified Agent\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{slot_tag('check')} Status ➜ Active\n"
            f"{slot_tag('timer')} Agent Since ➜ {u.get('agent_since', 'N/A')}\n"
            f"{slot_tag('price')} Base Price ➜ ₹{db['qr_rate']} / Qr\n"
            f"{slot_tag('balance')} Agent Bonus ➜ +₹{bonus} / Qr\n"
            f"{slot_tag('leaderboard')} You Earn ➜ ₹{db['qr_rate'] + bonus} / Qr\n\n"
            f"{slot_tag('task')} Completed ➜ {done} Qr\n"
            f"{slot_tag('price')} Bonus Earned ➜ ₹{u.get('agent_bonus_earned', 0)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('check')} Every Qr pays extra — keep leading"
        )

    if status == "REVOKED":
        return (
            f"{slot_tag('owner')} Agent Panel {slot_tag('cross')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('alert')} Aapka Agent access Owner (@{OWNER_USERNAME}) ne band kar diya hai.\n"
            f"{slot_tag('price')} Abhi aapko normal ₹{db['qr_rate']} / Qr milega.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Agent wapas paane ke liye Owner se contact karein."
        )

    remaining = max(0, target - done)
    filled = min(10, int((done / target) * 10)) if target > 0 else 10
    bar = "▰" * filled + "▱" * (10 - filled)
    return (
        f"{slot_tag('owner')} Agent Panel (Locked — Unlock at {target} Qr)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Completed ➜ {done} / {target} Qr\n"
        f"      {bar}\n"
        f"{slot_tag('timer')} Remaining ➜ {remaining} Qr\n\n"
        f"{slot_tag('price')} Extra Reward ➜ +₹{bonus} on every approved Qr\n"
        f"{slot_tag('leaderboard')} You Earn ➜ ₹{db['qr_rate'] + bonus} / Qr\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('task')} {remaining} Qr aur — Agent unlock"
    )


def build_owner_glow_keyboard():
    def _builder(use_ce=True):
        kb = GlowReplyKeyboard(resize_keyboard=True, is_persistent=True, use_custom_emoji=use_ce)
        kb.add_row(
            {"text": "Upload Qr Link", "style": "success", "emoji_id": slot_id("link")},
            {"text": "Broadcast", "style": "primary", "emoji_id": slot_id("alert")}
        )
        kb.add_row(
            {"text": "Qr Verified", "style": "success", "emoji_id": slot_id("check")},
            {"text": "Withdraw Pending", "style": "primary", "emoji_id": slot_id("withdraw")}
        )
        kb.add_row(
            {"text": "Price Set", "style": "primary", "emoji_id": slot_id("price")},
            {"text": "User Manage", "style": "danger", "emoji_id": slot_id("user")}
        )
        kb.add_row(
            {"text": "Agent Manage", "style": "danger", "emoji_id": slot_id("owner")},
            {"text": "Emoji Pack", "style": "primary", "emoji_id": slot_id("image")}
        )
        kb.add_row(
            {"text": "Set Welcome Image", "style": "success", "emoji_id": slot_id("image")},
            {"text": "Edit Welcome Message", "style": "primary", "emoji_id": slot_id("edit")}
        )
        kb.add_row(
            {"text": "Leaderboard Reset", "style": "danger", "emoji_id": slot_id("leaderboard")},
            {"text": "Back to Main Menu", "style": "primary", "emoji_id": slot_id("task")}
        )
        return kb
    return _builder

# ==========================================
# 7. MESSAGE CARDS
# ==========================================
def render_welcome_text(template, u, db):
    values = {
        "name": u["name"],
        "username": u.get("username", "N/A"),
        "id": str(u["id"]),
        "rate": str(db["qr_rate"]),
        "balance": str(u["balance"]),
        "date": datetime.now().strftime("%d %b %Y"),
        "owner": OWNER_USERNAME,
    }

    def _replace(match):
        key = match.group(1).lower()
        if key in values:
            return values[key]
        if key.startswith("e") and key[1:].isdigit():
            idx = int(key[1:])
            if 1 <= idx <= len(PACK_EMOJIS):
                return pe(idx - 1)
        return match.group(0)

    return re.sub(r"\{([A-Za-z]+\d*)\}", _replace, template)

def build_home_card(u, db):
    template = db.get("welcome_message") or DEFAULT_WELCOME_TEMPLATE
    return render_welcome_text(template, u, db)

def build_profile_card(u, db):
    total_attempts = u["completed"] + u["failed"]
    success_rate = round((u["completed"] / total_attempts) * 100) if total_attempts > 0 else 100
    completed = u["completed"]
    if completed >= 500:
        tier = f"{slot_tag('balance')} Diamond Elite"
    elif completed >= 200:
        tier = f"{slot_tag('owner')} Platinum Pro"
    elif completed >= 50:
        tier = f"{slot_tag('leaderboard')} Gold Worker"
    elif completed >= 10:
        tier = f"{slot_tag('check')} Silver Worker"
    else:
        tier = f"{slot_tag('task')} Rising Star"

    filled = min(10, round(success_rate / 10))
    rate_bar = "▰" * filled + "▱" * (10 - filled)
    upi = u.get("upi_id") or "Not Linked"
    status = u.get("account_status", "Active")

    return (
        f"{slot_tag('profile')} Worker Profile ({tier})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('profile')} Name ➜ {u['name']}\n"
        f"{slot_tag('link')} Username ➜ @{u['username']}\n"
        f"{slot_tag('user')} User ID ➜ {u['id']}\n"
        f"{slot_tag('withdraw')} UPI ➜ {upi}\n"
        f"{slot_tag('check')} Status ➜ {status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('task')} Today ➜ {u.get('daily_completed', 0)} Qr\n"
        f"{slot_tag('check')} Completed ➜ {completed} Qr\n"
        f"{slot_tag('cross')} Failed ➜ {u['failed']} Qr\n"
        f"{slot_tag('leaderboard')} Success ➜ {success_rate}%\n"
        f"      {rate_bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('price')} Qr Price ➜ ₹{db['qr_rate']} / Qr\n"
        f"{slot_tag('owner')} Agent ➜ "
        + (f"Active (+₹{db.get('agent_bonus', 5)} / Qr)\n" if agent_is_active(u)
           else ("Revoked\n" if u.get("agent_status") == "REVOKED"
                 else f"Locked ({completed}/{db.get('agent_target', 25)} Qr)\n"))
        + f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Keep grinding, keep earning"
    )

def build_balance_card(u):
    return (
        f"{slot_tag('balance')} My Wallet Balance\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('price')} Available Balance: ₹{u['balance']}\n"
        f"{slot_tag('task')} Today's Earnings: ₹{u.get('daily_earned', 0)}\n"
        f"{slot_tag('leaderboard')} Total Lifetime Earned: ₹{u['total_earned']}\n"
        f"{slot_tag('withdraw')} Total Withdrawn: ₹{u['total_withdrawn']}\n"
        f"{slot_tag('timer')} Pending Qr Checks: {u['pending_tasks']} Qr\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Instant UPI & Bank Payout — No Minimum Limit!"
    )

def build_leaderboard_text(db):
    users_list = [u for u in db["users"].values() if u.get("account_status", "ACTIVE") == "ACTIVE"]
    users_list.sort(key=lambda x: (x.get("daily_completed", 0), x.get("daily_earned", 0)), reverse=True)

    lb_txt = (
        f"{slot_tag('leaderboard')} Daily Leaderboard ({db.get('leaderboard_date')})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not users_list:
        lb_txt += "Aaj abhi tak koi worker rank nahi hua hai.\n"
    else:
        for idx, usr in enumerate(users_list[:10]):
            rank_emoji = pe(idx)
            d_done = usr.get("daily_completed", 0)
            d_earn = usr.get("daily_earned", 0)
            lb_txt += f"{rank_emoji} #{idx + 1} {usr['name']} — {slot_tag('check')} {d_done} Qr (₹{d_earn})\n"
    lb_txt += f"━━━━━━━━━━━━━━━━━━━━━━\n{slot_tag('timer')} Leaderboard roz daily restart hota hai!"
    return lb_txt

def build_how_to_work_and_rules_card(db):
    return (
        f"{slot_tag('how_to_work')} How to Work & Earn\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('task')} Step 1: Owner jab bhi naya Qr upload karega, sabhi users ko message aayega. 'Claim This Qr' dabayein — jo pehle claim karega sirf usi ko wo Qr milega.\n\n"
        f"{slot_tag('timer')} Step 2: Qr chahiye to 'Task' kholkar uske niche 'Order Qr' dabayein. Owner (@{OWNER_USERNAME}) ko message jayega aur 3 Minute ka timer start hoga.\n\n"
        f"{slot_tag('link')} Step 3: Qr Link open karke payment karein:\n"
        f"• Payment success hone par Complete Qr dabayein.\n"
        f"• Qr fail hone par Qr Failed dabayein.\n\n"
        f"{slot_tag('price')} Step 4: Owner check karke approve karega aur ₹{db['qr_rate']} aapke Balance me add ho jayega.\n\n"
        f"{slot_tag('withdraw')} Step 5: Withdraw button daba kar bina kisi limit ke apna paisa UPI me le lein!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('alert')} Official Work Rules\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} 1. Jab aap turant payment karne ke liye ready hon tabhi 'Task' > 'Order Qr' click karein.\n"
        f"{slot_tag('check')} 2. Qr Link milne ke baad turant scan karke payment complete karein.\n"
        f"{slot_tag('cross')} 3. Agar Qr Link fail ho jaye to galat verify na karein, seedha Qr Failed dabayein.\n"
        f"{slot_tag('alert')} 4. Fake verification click karne par Owner (@{OWNER_USERNAME}) aapka account Suspend ya Ban kar dega."
    )

def build_owner_dashboard_card(db):
    active_orders = sum(1 for v in ACTIVE_QR_ORDERS.values() if v.get("active"))
    pending_qr = sum(1 for v in db["verifications"] if v["status"] == "PENDING")
    pending_wd = sum(1 for w in db["withdrawals"] if w["status"] == "PENDING")
    total_users = len(db["users"])
    has_img = "Set" if db.get("welcome_image") else "Not Set"
    has_msg = "Custom" if db.get("welcome_message") else "Default"

    return (
        f"{slot_tag('owner')} Owner Admin Portal (@{OWNER_USERNAME})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('user')} Owner ID: {OWNER_ID}\n"
        f"{slot_tag('price')} Active Qr Price: ₹{db['qr_rate']} / Qr\n"
        f"{slot_tag('task')} Total Workers: {total_users} ({active_orders} Waiting for Qr)\n"
        f"{slot_tag('link')} Qr Stock: {qr_stock_counts(db)['AVAILABLE']} Available | {qr_stock_counts(db)['CLAIMED']} Claimed\n"
        f"{slot_tag('check')} Qr Verified Queue: {pending_qr} Pending\n"
        f"{slot_tag('withdraw')} Withdraw Queue: {pending_wd} Pending\n"
        f"{slot_tag('image')} Welcome Image: {has_img} | Welcome Text: {has_msg}\n"
        f"{slot_tag('task')} Premium Emojis: {len(PACK_EMOJIS)} ({PACK_INFO.get('source')})"
    )

# ==========================================
# 8. /START & /ADMIN COMMAND HANDLERS
# ==========================================
def deliver_welcome(chat_id, caption, kb_builder, welcome_img=None):
    if welcome_img and len(caption) <= 1024:
        try:
            return safe_send_photo(chat_id, welcome_img, caption, kb_builder)
        except Exception as e:
            err_str = str(e).upper()
            if "WRONG FILE IDENTIFIER" in err_str or "FILE_REFERENCE" in err_str:
                db = load_db()
                db["welcome_image"] = None
                save_db(db)
                print("⚠️ Cleared invalid welcome_image file_id from old bot token.")

    try:
        return safe_send(chat_id, caption, kb_builder)
    except Exception as e:
        print(f"⚠️ Welcome send fallback: {e}")
        plain = strip_custom_emoji(caption)
        return safe_send(chat_id, plain, kb_builder)

def send_welcome_screen(chat_id, user_obj):
    u = ensure_user(user_obj)
    db = load_db()
    deliver_welcome(
        chat_id,
        build_home_card(u, db),
        build_worker_glow_keyboard(user_obj),
        db.get("welcome_image")
    )

@bot.message_handler(commands=['start'])
def start_command(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    send_welcome_screen(message.chat.id, message.from_user)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    ensure_user(message.from_user)
    if not is_owner(message.from_user):
        safe_send(
            message.chat.id,
            f"{slot_tag('cross')} Access Denied!\nSirf Bot Owner @{OWNER_USERNAME} (ID: {OWNER_ID}) hi /admin portal open kar sakta hai."
        )
        return

    db = load_db()
    safe_send(
        message.chat.id,
        build_owner_dashboard_card(db),
        build_owner_glow_keyboard()
    )

# ==========================================
# 9. QR STOCK -> CLAIM / ORDER QR & 3-MINUTE TIMER SYSTEM
# ==========================================
def qr_raw_link(task):
    return task.get("raw_link") or html.unescape(task.get("link", ""))

def qr_stock_counts(db):
    counts = {"AVAILABLE": 0, "CLAIMED": 0, "SUBMITTED": 0}
    for t in db["tasks"].values():
        st = t.get("status")
        if st in counts:
            counts[st] += 1
    return counts

def get_user_open_task(db, uid):
    for t in db["tasks"].values():
        if t.get("status") == "CLAIMED" and t.get("claimed_by") == uid:
            return t
    return None

def build_order_claim_inline(use_ce=True):
    ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
    ikb.add_row(
        {"text": "Order Qr", "callback_data": "order_qr_now", "style": "success", "emoji_id": slot_id("task")}
    )
    return ikb

def build_claim_link_inline(task_id):
    def _builder(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        ikb.add_row({"text": "Claim This Qr", "callback_data": f"claim_link|{task_id}", "style": "success", "emoji_id": slot_id("link")})
        return ikb
    return _builder

def claim_specific_qr(uid, task_id):
    with QR_LOCK:
        db = load_db()
        open_task = get_user_open_task(db, uid)
        if open_task:
            return "OPEN", open_task
        t = db["tasks"].get(task_id)
        if not t:
            return "NOT_FOUND", None
        if t.get("status") != "AVAILABLE":
            return "TAKEN", t
        t["status"] = "CLAIMED"
        t["claimed_by"] = uid
        t["claimed_at"] = datetime.now().strftime("%d %b, %I:%M %p")
        if uid in db["users"]:
            db["users"][uid]["history"].append(f"{t['id']} - Claimed Qr")
        save_db(db)
        return "CLAIMED", t

def close_qr_broadcast(task_id, winner_uid=None):
    with QR_LOCK:
        targets = QR_BROADCAST_MSGS.pop(task_id, [])
    closed_txt = (
        f"{slot_tag('cross')} Qr {task_id} Already Claimed\n"
        f"Ye Qr kisi aur user ne pehle claim kar liya hai.\n"
        f"Naya Qr aate hi aapko message milega."
    )
    for chat_id, message_id in targets:
        if winner_uid is not None and str(chat_id) == str(winner_uid):
            continue
        safe_edit(chat_id, message_id, closed_txt)

def add_open_link_row(ikb, raw_link):
    if raw_link.startswith("http://") or raw_link.startswith("https://"):
        ikb.add_row({"text": "Open Qr Link", "url": raw_link, "style": "primary", "emoji_id": slot_id("link")})

def build_claimed_qr_card(task):
    return (
        f"{slot_tag('task')} Qr Claimed — Aapka Task\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('edit')} Task ID: {task['id']}\n"
        f"{slot_tag('link')} Qr Link:\n{html.escape(qr_raw_link(task))}\n\n"
        f"{slot_tag('price')} Your Reward: ₹{task['reward']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Payment complete hone ke baad 'Complete Qr' dabayein.\n"
        f"{slot_tag('cross')} Qr kaam na kare to 'Qr Failed' dabayein."
    )

def build_claimed_qr_inline(task):
    raw_link = qr_raw_link(task)
    task_id = task["id"]

    def _builder(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        add_open_link_row(ikb, raw_link)
        ikb.add_row(
            {"text": "Complete Qr", "callback_data": f"qr_ok|{task_id}", "style": "success", "emoji_id": slot_id("check")},
            {"text": "Qr Failed", "callback_data": f"qr_fail|{task_id}", "style": "danger", "emoji_id": slot_id("cross")}
        )
        return ikb
    return _builder

def send_claimed_qr(chat_id, task):
    return safe_send(chat_id, build_claimed_qr_card(task), build_claimed_qr_inline(task))

def safe_edit(chat_id, message_id, text, markup_builder=None):
    attempts = [True, False] if markup_builder else [False]
    for use_ce in attempts:
        try:
            markup = markup_builder(use_ce) if markup_builder else None
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="HTML")
            return True
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
    return False

def stop_user_waiting(uid):
    state = ACTIVE_QR_ORDERS.get(uid)
    if state and state.get("active"):
        state["active"] = False
        return state
    return None

def try_claim_qr(uid):
    with QR_LOCK:
        db = load_db()
        open_task = get_user_open_task(db, uid)
        if open_task:
            return "OPEN", open_task
        for t in db["tasks"].values():
            if t.get("status") == "AVAILABLE":
                t["status"] = "CLAIMED"
                t["claimed_by"] = uid
                t["claimed_at"] = datetime.now().strftime("%d %b, %I:%M %p")
                if uid in db["users"]:
                    db["users"][uid]["history"].append(f"{t['id']} - Claimed Qr")
                save_db(db)
                return "CLAIMED", t
    return "EMPTY", None

def notify_owner_qr_claimed(task, u, uid):
    left = qr_stock_counts(load_db())["AVAILABLE"]
    try:
        safe_send(
            OWNER_ID,
            f"{slot_tag('link')} Qr Claimed ({task['id']})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('user')} Worker: {u['name']} ({uid})\n"
            f"{slot_tag('link')} Qr Link:\n{html.escape(qr_raw_link(task))}\n"
            f"{slot_tag('task')} Stock Left: {left} Qr"
        )
    except Exception:
        pass

def handle_qr_request(user_obj, chat_id, mode="order", source_message_id=None):
    u = ensure_user(user_obj)
    uid = str(user_obj.id)
    status, task = try_claim_qr(uid)

    if status == "OPEN":
        safe_send(chat_id, f"{slot_tag('alert')} Aapke paas pehle se ek Qr claimed hai.\nPehle use Complete ya Qr Failed karein:")
        send_claimed_qr(chat_id, task)
        return "Pehle current Qr complete karein!"

    if status == "CLAIMED":
        stop_user_waiting(uid)
        if source_message_id:
            safe_edit(chat_id, source_message_id, f"{slot_tag('check')} Qr Claimed! ({task['id']})\nNiche aapka Qr Link hai.")
        send_claimed_qr(chat_id, task)
        notify_owner_qr_claimed(task, u, uid)
        close_qr_broadcast(task["id"], uid)
        return "Qr Claimed!"

    if mode == "claim":
        safe_send(
            chat_id,
            f"{slot_tag('alert')} Abhi koi Qr Link available nahi hai.\n"
            f"'Order Qr' dabayein — Owner ko request jayegi aur Qr aate hi aapko message milega.",
            build_order_claim_inline
        )
        return "No Qr available right now"

    state = ACTIVE_QR_ORDERS.get(uid)
    if state and state.get("active"):
        safe_send(chat_id, f"{slot_tag('timer')} Aapka Order ({state['order_id']}) pehle se waiting me hai. Kripya wait karein...")
        return "Already waiting for Qr"

    start_waiting_order(user_obj, chat_id, source_message_id)
    return "Order Qr Sent! 3 Minute Timer Started."

def build_waiting_text(order_id, worker_name, qr_rate, time_str):
    return (
        f"{slot_tag('timer')} Order Qr Request Sent ({order_id})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('user')} Worker: {worker_name}\n"
        f"{slot_tag('price')} Per Qr Reward: ₹{qr_rate}\n"
        f"{slot_tag('timer')} Time Remaining: {time_str} (3 Min Timer)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Owner (@{OWNER_USERNAME}) ko message bhej diya gaya hai: User need Qr.\n"
        f"Qr upload hote hi waiting band ho jayegi aur aapko Claim option milega..."
    )

def start_waiting_order(user_obj, chat_id, source_message_id=None):
    uid = str(user_obj.id)
    db = load_db()
    u = db["users"][uid]
    order_id = "ORD-" + ''.join(random.choices(string.digits, k=5))
    u["history"].append(f"{order_id} - Ordered Qr (3m Timer)")
    save_db(db)

    txt = build_waiting_text(order_id, u["name"], db["qr_rate"], "03:00")
    if source_message_id and safe_edit(chat_id, source_message_id, txt):
        message_id = source_message_id
    else:
        message_id = safe_send(chat_id, txt).message_id

    ACTIVE_QR_ORDERS[uid] = {"active": True, "order_id": order_id, "chat_id": chat_id, "message_id": message_id}

    def _owner_send_qr_btn(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        ikb.add_row({"text": "Send Qr Link to User", "callback_data": f"send_qr_usr|{uid}|{order_id}", "style": "success", "emoji_id": slot_id("link")})
        return ikb

    try:
        safe_send(
            OWNER_ID,
            f"{slot_tag('alert')} User need Qr ({order_id})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('user')} Worker: {u['name']} (@{u['username']})\n"
            f"{slot_tag('edit')} User ID: {uid}\n"
            f"{slot_tag('timer')} User Timer: 03:00 Running...\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"'Upload Qr Link' se stock me Qr daalein (sab waiting users ko Claim option mil jayega),\n"
            f"ya niche button se sirf is user ko Qr bhejein:",
            _owner_send_qr_btn
        )
    except Exception:
        pass

    threading.Thread(
        target=run_3min_order_timer,
        args=(chat_id, message_id, uid, order_id, u["name"], db["qr_rate"]),
        daemon=True
    ).start()

def notify_waiting_users_qr_ready(stock_count):
    released = set()
    for uid, state in list(ACTIVE_QR_ORDERS.items()):
        if not state.get("active"):
            continue
        state["active"] = False
        released.add(uid)
        txt = (
            f"{slot_tag('check')} Waiting Off — Qr Link Aa Gaya! ({state['order_id']})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('task')} Available Qr: {stock_count}\n"
            f"{slot_tag('link')} Pehle aao pehle pao! Agle message me 'Claim This Qr' dabakar apna Qr le lein."
        )
        safe_edit(state["chat_id"], state["message_id"], txt)
    return released

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "task")
def msg_task_option(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    u = ensure_user(message.from_user)
    db = load_db()
    stock = qr_stock_counts(db)["AVAILABLE"]

    task_card = (
        f"{slot_tag('task')} Qr Task Center\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('user')} Worker: {u['name']}\n"
        f"{slot_tag('price')} Per Qr Earning: ₹{db['qr_rate']} / Qr\n"
        f"{slot_tag('link')} Available Qr: {stock}\n"
        f"{slot_tag('timer')} Order Timer: 3 Minutes\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('check')} Naya Qr upload hote hi sabko message aayega — pehle claim karne wale ko hi milega.\n"
        f"{slot_tag('check')} Qr chahiye? Niche 'Order Qr' button dabayein."
    )
    safe_send(message.chat.id, task_card, build_order_claim_inline)

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "order qr")
def msg_order_qr(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    handle_qr_request(message.from_user, message.chat.id, mode="order")


def run_3min_order_timer(chat_id, message_id, uid, order_id, worker_name, qr_rate):
    total_seconds = 180
    step = 15

    for remaining in range(total_seconds - step, -1, -step):
        time.sleep(step)
        order_state = ACTIVE_QR_ORDERS.get(uid)
        if not order_state or not order_state.get("active") or order_state.get("order_id") != order_id:
            return

        if remaining > 0:
            time_str = f"{remaining // 60:02d}:{remaining % 60:02d}"
            safe_edit(chat_id, message_id, build_waiting_text(order_id, worker_name, qr_rate, time_str))
        else:
            ACTIVE_QR_ORDERS[uid]["active"] = False
            expired_txt = (
                f"{slot_tag('alert')} 3 Minute Timer Completed ({order_id})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{slot_tag('timer')} Time Remaining: 00:00\n"
                f"Agar aapko abhi bhi Qr chahiye, to niche 'Order Qr' dabayein:"
            )
            safe_edit(chat_id, message_id, expired_txt, build_order_claim_inline)

# ==========================================
# 10. WORKER MENU HANDLERS
# ==========================================
@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "profile")
def msg_profile(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    u = ensure_user(message.from_user)
    db = load_db()

    def _prof_edit_inline(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        ikb.add_row(
            {"text": "Change Name", "callback_data": "self_edit|name", "style": "primary", "emoji_id": slot_id("edit")},
            {"text": "Link UPI", "callback_data": "self_edit|upi", "style": "success", "emoji_id": slot_id("withdraw")}
        )
        return ikb

    safe_send(message.chat.id, build_profile_card(u, db), _prof_edit_inline)

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "balance")
def msg_balance(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    u = ensure_user(message.from_user)
    safe_send(message.chat.id, build_balance_card(u), build_worker_glow_keyboard(message.from_user))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "leaderboard")
def msg_leaderboard(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    db = load_db()
    safe_send(message.chat.id, build_leaderboard_text(db), build_worker_glow_keyboard(message.from_user))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "how to work")
def msg_how_to_work(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    db = load_db()
    safe_send(message.chat.id, build_how_to_work_and_rules_card(db), build_worker_glow_keyboard(message.from_user))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "agent")
def msg_agent(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    ensure_user(message.from_user)
    db = load_db()
    u = db["users"][str(message.from_user.id)]
    if try_unlock_agent(u, db):
        save_db(db)
    safe_send(message.chat.id, build_agent_card(u, db), build_worker_glow_keyboard(message.from_user))

@bot.message_handler(func=lambda m: m.text and m.text.strip().lower() == "withdraw")
def msg_withdraw(message):
    if not check_user_allowed(message.from_user, message.chat.id):
        return
    u = ensure_user(message.from_user)
    if u["balance"] <= 0:
        safe_send(
            message.chat.id,
            f"{slot_tag('alert')} Zero Balance!\n\nYour Balance: ₹{u['balance']}\nPehle Qr task complete karke earning karein!",
            build_worker_glow_keyboard(message.from_user)
        )
        return

    saved_upi = u.get("upi_id", "Not Set")
    msg = safe_send(
        message.chat.id,
        f"{slot_tag('withdraw')} Instant Withdrawal\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('balance')} Available Balance: ₹{u['balance']}\n"
        f"{slot_tag('withdraw')} Saved UPI: {saved_upi}\n"
        f"{slot_tag('check')} Minimum Limit: No Limit (₹1+)\n\n"
        f"Apna Amount aur UPI ID / Bank Details ek line me bhejein:\n"
        f"Example: {u['balance']} rahul@ybl\n\n"
        f"Cancel karne ke liye cancel likhein."
    )
    bot.register_next_step_handler(msg, withdraw_step2)

def withdraw_step2(message):
    if not message.text or message.text.lower().strip() == "cancel":
        safe_send(message.chat.id, f"{slot_tag('cross')} Withdrawal Cancelled.", build_worker_glow_keyboard(message.from_user))
        return

    db = load_db()
    uid = str(message.from_user.id)
    u = db["users"][uid]

    parts = message.text.strip().split(" ", 1)
    if len(parts) < 2:
        safe_send(message.chat.id, f"{slot_tag('cross')} Format galat hai! Example: 50 rahul@ybl")
        return

    try:
        amt = int(parts[0])
        upi = html.escape(parts[1].strip())
        if amt <= 0 or amt > u["balance"]:
            safe_send(message.chat.id, f"{slot_tag('cross')} Amount ₹1 se ₹{u['balance']} ke beech hona chahiye!")
            return

        u["balance"] -= amt
        u["upi_id"] = upi
        wd_id = "WD-" + ''.join(random.choices(string.digits, k=5))
        u["history"].append(f"Withdraw ₹{amt} ({wd_id}) - Pending")

        db["withdrawals"].append({
            "id": wd_id, "uid": uid, "name": u["name"], "amount": amt,
            "upi": upi, "time": datetime.now().strftime("%d %b, %I:%M %p"), "status": "PENDING"
        })
        save_db(db)

        safe_send(
            message.chat.id,
            f"{slot_tag('check')} Withdrawal Submitted\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('task')} Request ID: {wd_id}\n"
            f"{slot_tag('price')} Amount: ₹{amt}\n"
            f"{slot_tag('withdraw')} UPI/Bank: {upi}\n\n"
            f"Owner (@{OWNER_USERNAME}) ke Withdraw Pending panel me aapki request chali gayi hai.",
            build_worker_glow_keyboard(message.from_user)
        )

        def _wd_inline(use_ce=True):
            ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
            ikb.add_row(
                {"text": "Approve & Paid", "callback_data": f"wd_pay|{wd_id}", "style": "success", "emoji_id": slot_id("check")},
                {"text": "Reject & Refund", "callback_data": f"wd_rej|{wd_id}", "style": "danger", "emoji_id": slot_id("cross")}
            )
            return ikb

        try:
            safe_send(
                OWNER_ID,
                f"{slot_tag('withdraw')} New Withdraw Request\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{slot_tag('task')} ID: {wd_id}\n"
                f"{slot_tag('user')} Worker: {u['name']} ({uid})\n"
                f"{slot_tag('price')} Amount: ₹{amt}\n"
                f"{slot_tag('withdraw')} UPI / Bank: {upi}",
                _wd_inline
            )
        except Exception:
            pass
    except ValueError:
        safe_send(message.chat.id, f"{slot_tag('cross')} Amount sirf number me likhein!")

# ==========================================
# 11. OWNER ADMIN PORTAL HANDLERS
# ==========================================
@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "back to main menu")
def msg_back_main(message):
    send_welcome_screen(message.chat.id, message.from_user)

# BROADCAST OPTION (CLEAN OUTPUT - NO OWNER HEADER)
@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "broadcast")
def msg_owner_broadcast(message):
    db = load_db()
    total_users = len(db["users"])
    msg = safe_send(
        message.chat.id,
        f"{slot_tag('alert')} Broadcast Message to All Workers\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('user')} Total Registered Workers: {total_users}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Apna Broadcast Message (Text ya Photo + Caption) abhi bhejein.\n"
        f"• Aap message me Premium Emojis ya <code>{{e1}}</code>, <code>{{name}}</code>, <code>{{balance}}</code>, <code>{{rate}}</code> codes bhi use kar sakte hain.\n\n"
        f"Cancel karne ke liye <code>cancel</code> likhein."
    )
    bot.register_next_step_handler(msg, owner_process_broadcast)

def owner_process_broadcast(message):
    raw_text = message.text if message.text else message.caption
    entities = message.entities if message.text else message.caption_entities

    if raw_text and raw_text.strip().lower() == "cancel":
        safe_send(message.chat.id, f"{slot_tag('cross')} Broadcast Cancelled.", build_owner_glow_keyboard())
        return

    photo_id = message.photo[-1].file_id if message.content_type == "photo" else None
    if not raw_text and not photo_id:
        safe_send(
            message.chat.id,
            f"{slot_tag('cross')} Kripya Text message ya Photo bhejein!",
            build_owner_glow_keyboard()
        )
        return

    template_html = message_to_html(raw_text, entities).strip() if raw_text else ""
    db = load_db()
    users_dict = db.get("users", {})

    if not users_dict:
        safe_send(
            message.chat.id,
            f"{slot_tag('alert')} Abhi tak koi worker registered nahi hai.",
            build_owner_glow_keyboard()
        )
        return

    safe_send(
        message.chat.id,
        f"{slot_tag('timer')} Broadcasting to {len(users_dict)} workers... Kripya wait karein."
    )

    sent_count = 0
    failed_count = 0

    for uid, usr in list(users_dict.items()):
        # Renders directly without prepending "Announcement from Owner"
        final_text = render_welcome_text(template_html, usr, db) if template_html else ""

        try:
            if photo_id:
                if final_text:
                    safe_send_photo(int(uid), photo_id, final_text[:1024])
                else:
                    safe_send_photo(int(uid), photo_id, "")
            else:
                if final_text:
                    safe_send(int(uid), final_text)
            sent_count += 1
        except Exception:
            failed_count += 1
        time.sleep(0.04)

    safe_send(
        message.chat.id,
        f"{slot_tag('check')} Broadcast Completed!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('user')} Total Workers: {len(users_dict)}\n"
        f"{slot_tag('check')} Successfully Sent: {sent_count}\n"
        f"{slot_tag('cross')} Failed / Blocked: {failed_count}",
        build_owner_glow_keyboard()
    )

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "price set")
def msg_owner_price_set(message):
    db = load_db()
    msg = safe_send(
        message.chat.id,
        f"{slot_tag('price')} Price Set\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Current Per Qr Price: ₹{db['qr_rate']}\n"
        f"• Withdraw Limit: No Limit\n\n"
        f"Naya Per Qr Price enter karein (Example: 50):"
    )
    bot.register_next_step_handler(msg, owner_price_set_step2)

def owner_price_set_step2(message):
    if not message.text:
        return
    try:
        new_qr_price = int(message.text.strip().split()[0])
        db = load_db()
        db["qr_rate"] = new_qr_price
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} Price Updated to ₹{db['qr_rate']} / Qr!", build_owner_glow_keyboard())
    except ValueError:
        safe_send(message.chat.id, f"{slot_tag('cross')} Sirf number enter karein (Example: 50)!")

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "upload qr link")
def msg_owner_upload_qr(message):
    db = load_db()
    counts = qr_stock_counts(db)
    waiting = sum(1 for v in ACTIVE_QR_ORDERS.values() if v.get("active"))
    msg = safe_send(
        message.chat.id,
        f"{slot_tag('link')} Upload Qr Link\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('task')} Current Stock: {counts['AVAILABLE']} Qr\n"
        f"{slot_tag('timer')} Waiting Users: {waiting}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Qr Link paste karke bhejein.\n"
        f"Ek saath kai links bhej sakte hain — har line me ek link.\n\n"
        f"• Har Qr ka alag message sabhi Active users ko jayega.\n"
        f"• 1 Qr sirf 1 user claim kar payega — jo pehle claim karega.\n\n"
        f"Cancel karne ke liye cancel likhein."
    )
    bot.register_next_step_handler(msg, owner_save_uploaded_qr)

def owner_save_uploaded_qr(message):
    if not message.text:
        safe_send(message.chat.id, f"{slot_tag('cross')} Sirf Qr Link (text link) paste karein!")
        return
    if message.text.strip().lower() == "cancel":
        safe_send(message.chat.id, f"{slot_tag('cross')} Upload Cancelled.", build_owner_glow_keyboard())
        return

    links = [line.strip() for line in message.text.splitlines() if line.strip()]
    with QR_LOCK:
        db = load_db()
        new_ids = []
        for raw_link in links:
            task_id = "QR-" + ''.join(random.choices(string.digits, k=5))
            while task_id in db["tasks"]:
                task_id = "QR-" + ''.join(random.choices(string.digits, k=5))
            db["tasks"][task_id] = {
                "id": task_id,
                "link": html.escape(raw_link),
                "raw_link": raw_link,
                "reward": db["qr_rate"],
                "time": datetime.now().strftime("%d %b, %I:%M %p"),
                "status": "AVAILABLE",
                "claimed_by": None
            }
            new_ids.append(task_id)
        save_db(db)
        stock = qr_stock_counts(db)["AVAILABLE"]

    released = notify_waiting_users_qr_ready(stock)

    recipients = [
        uid for uid, usr in db["users"].items()
        if not is_owner(uid) and usr.get("account_status", "ACTIVE") == "ACTIVE"
    ]

    sent = 0
    for task_id in new_ids:
        broadcast_txt = (
            f"{slot_tag('task')} New Qr Available! ({task_id})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('price')} Reward: ₹{db['qr_rate']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('alert')} Ye Qr sirf 1 user ko milega.\n"
            f"{slot_tag('check')} Pehle aao pehle pao! Niche 'Claim This Qr' dabayein:"
        )
        QR_BROADCAST_MSGS[task_id] = []
        for uid in recipients:
            try:
                m = safe_send(int(uid), broadcast_txt, build_claim_link_inline(task_id))
                with QR_LOCK:
                    if task_id in QR_BROADCAST_MSGS:
                        QR_BROADCAST_MSGS[task_id].append((int(uid), m.message_id))
                sent += 1
            except Exception:
                pass
            time.sleep(0.04)

    safe_send(
        message.chat.id,
        f"{slot_tag('check')} Qr Uploaded\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('link')} Added: {len(new_ids)} Qr\n"
        f"{slot_tag('task')} Unclaimed Qr Now: {stock}\n"
        f"{slot_tag('timer')} Waiting Off For: {len(released)} User(s)\n"
        f"{slot_tag('user')} Users Notified: {len(recipients)} (Total Messages: {sent})\n"
        f"{slot_tag('alert')} Har Qr sirf pehle claim karne wale 1 user ko milega.",
        build_owner_glow_keyboard()
    )

def dispatch_direct_qr(message, target_uid):
    if not message.text:
        safe_send(message.chat.id, f"{slot_tag('cross')} Sirf Qr Link (text link) paste karein!")
        return
    raw_link = message.text.strip().splitlines()[0].strip()
    target_uid = str(target_uid)

    with QR_LOCK:
        db = load_db()
        task_id = "QR-" + ''.join(random.choices(string.digits, k=5))
        task = {
            "id": task_id,
            "link": html.escape(raw_link),
            "raw_link": raw_link,
            "reward": db["qr_rate"],
            "time": datetime.now().strftime("%d %b, %I:%M %p"),
            "status": "CLAIMED",
            "claimed_by": target_uid,
            "claimed_at": datetime.now().strftime("%d %b, %I:%M %p")
        }
        db["tasks"][task_id] = task
        if target_uid in db["users"]:
            db["users"][target_uid]["history"].append(f"{task_id} - Qr Received from Owner")
        save_db(db)

    state = stop_user_waiting(target_uid)
    if state:
        safe_edit(state["chat_id"], state["message_id"], f"{slot_tag('check')} Waiting Off — Owner ne aapko Qr bhej diya! ({task_id})")

    try:
        send_claimed_qr(int(target_uid), task)
        result = f"{slot_tag('check')} Qr Sent to User {target_uid} (Task {task_id})"
    except Exception:
        result = f"{slot_tag('cross')} User {target_uid} ko Qr nahi bheja ja saka."
    safe_send(message.chat.id, result, build_owner_glow_keyboard())

def build_owner_verify_inline(ver_id, raw_link):
    def _builder(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        add_open_link_row(ikb, raw_link)
        ikb.add_row(
            {"text": "Approve & Pay", "callback_data": f"own_pay|{ver_id}", "style": "success", "emoji_id": slot_id("check")},
            {"text": "Reject (Fail)", "callback_data": f"own_rej|{ver_id}", "style": "danger", "emoji_id": slot_id("cross")}
        )
        return ikb
    return _builder

def build_owner_verify_card(v, title="Qr Complete — Check & Approve"):
    return (
        f"{slot_tag('check')} {title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('edit')} Verify ID: {v['ver_id']}\n"
        f"{slot_tag('task')} Task ID: {v['task_id']}\n"
        f"{slot_tag('user')} Worker: {v['name']} ({v['uid']})\n"
        f"{slot_tag('link')} Qr Link:\n{html.escape(v.get('link') or 'N/A')}\n\n"
        f"{slot_tag('price')} Reward: ₹{v['reward']}\n"
        f"{slot_tag('timer')} Time: {v['time']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Link check karke Approve ya Reject karein:"
    )

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "qr verified")
def msg_owner_qr_verified(message):
    db = load_db()
    pending_list = [v for v in db["verifications"] if v["status"] == "PENDING"]

    if not pending_list:
        safe_send(message.chat.id, f"{slot_tag('check')} Qr Verified Queue Empty!", build_owner_glow_keyboard())
        return

    safe_send(message.chat.id, f"{slot_tag('check')} Pending Qr Verifications ({len(pending_list)}):")
    for v in pending_list:
        safe_send(
            message.chat.id,
            build_owner_verify_card(v, "Qr Verified Check"),
            build_owner_verify_inline(v["ver_id"], v.get("link") or "")
        )

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "withdraw pending")
def msg_owner_withdraw_pending(message):
    db = load_db()
    pending = [w for w in db["withdrawals"] if w["status"] == "PENDING"]

    if not pending:
        safe_send(message.chat.id, f"{slot_tag('withdraw')} Withdraw Pending Queue Empty!", build_owner_glow_keyboard())
        return

    safe_send(message.chat.id, f"{slot_tag('withdraw')} Pending Withdrawals ({len(pending)}):")
    for w in pending:
        wid = w["id"]
        def _wd_inline(use_ce=True, w_id=wid):
            ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
            ikb.add_row(
                {"text": "Approve & Paid", "callback_data": f"wd_pay|{w_id}", "style": "success", "emoji_id": slot_id("check")},
                {"text": "Reject & Refund", "callback_data": f"wd_rej|{w_id}", "style": "danger", "emoji_id": slot_id("cross")}
            )
            return ikb
        safe_send(
            message.chat.id,
            f"{slot_tag('withdraw')} Withdraw Pending\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('task')} ID: {w['id']}\n"
            f"{slot_tag('user')} Worker: {w['name']} ({w['uid']})\n"
            f"{slot_tag('price')} Amount: ₹{w['amount']}\n"
            f"{slot_tag('withdraw')} UPI / Bank: {w['upi']}\n"
            f"{slot_tag('timer')} Time: {w.get('time', 'N/A')}",
            _wd_inline
        )

def build_user_manage_inline(uid, current_status):
    def _builder(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        row = []
        if current_status != "ACTIVE":
            row.append({"text": "Activate", "callback_data": f"usr_st|{uid}|ACTIVE", "style": "success", "emoji_id": slot_id("check")})
        if current_status != "SUSPENDED":
            row.append({"text": "Suspend", "callback_data": f"usr_st|{uid}|SUSPENDED", "style": "primary", "emoji_id": slot_id("alert")})
        if current_status != "BANNED":
            row.append({"text": "Ban User", "callback_data": f"usr_st|{uid}|BANNED", "style": "danger", "emoji_id": slot_id("cross")})
        ikb.add_row(*row)
        return ikb
    return _builder

def format_user_manage_card(u):
    st = u.get("account_status", "ACTIVE")
    return (
        f"{slot_tag('user')} User Control Card\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('edit')} User ID: {u['id']}\n"
        f"{slot_tag('profile')} Name: {u['name']} (@{u.get('username', 'N/A')})\n"
        f"{slot_tag('withdraw')} UPI: {u.get('upi_id', 'Not Set')}\n"
        f"{slot_tag('check')} Status: {st}\n"
        f"{slot_tag('balance')} Balance: ₹{u['balance']} | Done: {u['completed']} | Fail: {u['failed']}"
    )

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "user manage")
def msg_owner_user_manage(message):
    db = load_db()
    if not db["users"]:
        safe_send(message.chat.id, f"{slot_tag('user')} Abhi tak koi user registered nahi hai.")
        return

    safe_send(message.chat.id, f"{slot_tag('user')} User Management ({len(db['users'])} Workers):")
    for uid, u in db["users"].items():
        st = u.get("account_status", "ACTIVE")
        safe_send(message.chat.id, format_user_manage_card(u), build_user_manage_inline(uid, st))

def build_agent_manage_inline(uid, agent_status):
    def _builder(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        if agent_status == "ACTIVE":
            ikb.add_row({"text": "Revoke Agent", "callback_data": f"agt_st|{uid}|REVOKED", "style": "danger", "emoji_id": slot_id("cross")})
        else:
            ikb.add_row({"text": "Make Agent", "callback_data": f"agt_st|{uid}|ACTIVE", "style": "success", "emoji_id": slot_id("check")})
        return ikb
    return _builder

def format_agent_manage_card(u, db):
    st = u.get("agent_status", "LOCKED")
    return (
        f"{slot_tag('owner')} Agent Card — {st}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('profile')} {u['name']} (@{u.get('username', 'N/A')})\n"
        f"{slot_tag('user')} ID: {u['id']}\n"
        f"{slot_tag('check')} Done: {u['completed']} / {db.get('agent_target', 25)} Qr\n"
        f"{slot_tag('price')} Bonus Earned: ₹{u.get('agent_bonus_earned', 0)}"
    )

def _agent_settings_inline(use_ce=True):
    ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
    ikb.add_row(
        {"text": "Set Bonus", "callback_data": "agt_cfg|bonus", "style": "success", "emoji_id": slot_id("price")},
        {"text": "Set Target", "callback_data": "agt_cfg|target", "style": "primary", "emoji_id": slot_id("task")}
    )
    return ikb

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "agent manage")
def msg_owner_agent_manage(message):
    db = load_db()
    users = list(db["users"].values())
    agents = [u for u in users if u.get("agent_status") == "ACTIVE"]
    target = int(db.get("agent_target", 25))
    near = [u for u in users if u.get("agent_status", "LOCKED") != "ACTIVE" and u.get("completed", 0) >= max(0, target - 10)]

    safe_send(
        message.chat.id,
        f"{slot_tag('owner')} Agent Manage\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('price')} Agent Bonus: +₹{db.get('agent_bonus', 5)} / Qr\n"
        f"{slot_tag('task')} Unlock Target: {target} Completed Qr\n"
        f"{slot_tag('check')} Active Agents: {len(agents)}\n"
        f"{slot_tag('timer')} Close to Unlock / Revoked: {len(near)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Worker {target} Qr complete karte hi auto Agent ban jata hai.",
        _agent_settings_inline
    )
    for u in agents + near:
        safe_send(message.chat.id, format_agent_manage_card(u, db), build_agent_manage_inline(u["id"], u.get("agent_status", "LOCKED")))

def owner_save_agent_cfg(message, field):
    if not message.text or message.text.strip().lower() == "cancel":
        safe_send(message.chat.id, f"{slot_tag('cross')} Cancelled.", build_owner_glow_keyboard())
        return
    try:
        value = int(message.text.strip())
        if value < 0 or (field == "target" and value < 1):
            raise ValueError
    except ValueError:
        safe_send(message.chat.id, f"{slot_tag('cross')} Sirf valid number bhejein!", build_owner_glow_keyboard())
        return
    db = load_db()
    if field == "bonus":
        db["agent_bonus"] = value
        txt = f"{slot_tag('check')} Agent Bonus set: +₹{value} / Qr"
    else:
        db["agent_target"] = value
        txt = f"{slot_tag('check')} Agent Unlock Target set: {value} Qr"
    save_db(db)
    safe_send(message.chat.id, txt, build_owner_glow_keyboard())

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "set welcome image")
def msg_owner_set_welcome_image(message):
    msg = safe_send(
        message.chat.id,
        f"{slot_tag('image')} Set Welcome Image\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Nayi Welcome Image lagane ke liye abhi Photo upload karein.\n"
        f"• Welcome Image hatane ke liye remove likh kar bhejein.\n"
        f"• Cancel karne ke liye cancel likhein."
    )
    bot.register_next_step_handler(msg, owner_save_welcome_image)

def owner_save_welcome_image(message):
    db = load_db()
    if message.content_type == "photo":
        file_id = message.photo[-1].file_id
        db["welcome_image"] = file_id
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} Welcome Image successfully set ho gayi hai!", build_owner_glow_keyboard())
    elif message.text and message.text.strip().lower() == "remove":
        db["welcome_image"] = None
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} Welcome Image remove kar di gayi hai!", build_owner_glow_keyboard())
    else:
        safe_send(message.chat.id, f"{slot_tag('cross')} Cancelled.", build_owner_glow_keyboard())

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "edit welcome message")
def msg_owner_edit_welcome_message(message):
    db = load_db()
    current_template = db.get("welcome_message") or DEFAULT_WELCOME_TEMPLATE
    guide = (
        f"{slot_tag('edit')} Edit Welcome Message\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Bas apna naya Welcome Message type karke bhej do. Jaisa likhoge, waisa hi dikhega.\n\n"
        f"{slot_tag('check')} Premium Emoji seedha message me daal do (pack: {EMOJI_PACK_NAME}).\n"
        f"{slot_tag('check')} Ya pack emoji ke code use karo: <code>{{e1}}</code>, <code>{{e2}}</code> ... (list: Emoji Pack button)\n\n"
        f"{slot_tag('task')} Auto Fill Codes:\n"
        f"<code>{{name}}</code> = Worker name\n"
        f"<code>{{username}}</code> = Username\n"
        f"<code>{{id}}</code> = User ID\n"
        f"<code>{{balance}}</code> = Balance\n"
        f"<code>{{rate}}</code> = Qr price\n"
        f"<code>{{date}}</code> = Aaj ki date\n"
        f"<code>{{owner}}</code> = Owner username\n\n"
        f"• <code>default</code> bhejo = default message wapas\n"
        f"• <code>cancel</code> bhejo = cancel"
    )
    safe_send(message.chat.id, guide)
    try:
        safe_send(message.chat.id, f"{slot_tag('image')} Current Message Preview:")
        safe_send(message.chat.id, render_welcome_text(current_template, ensure_user(message.from_user), db))
    except Exception:
        safe_send(message.chat.id, html.escape(strip_custom_emoji(current_template)))
    msg = safe_send(message.chat.id, f"{slot_tag('edit')} Ab apna naya Welcome Message bhejein:")
    bot.register_next_step_handler(msg, owner_save_welcome_message)

def owner_save_welcome_message(message):
    text = message.text if message.text else message.caption
    entities = message.entities if message.text else message.caption_entities

    if not text or text.strip().lower() == "cancel":
        safe_send(message.chat.id, f"{slot_tag('cross')} Cancelled.", build_owner_glow_keyboard())
        return

    db = load_db()
    if text.strip().lower() == "default":
        db["welcome_message"] = None
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} Welcome Message wapas Default set ho gaya hai!", build_owner_glow_keyboard())
        return

    template = message_to_html(text, entities).strip()
    db["welcome_message"] = template
    save_db(db)

    emoji_count = sum(1 for e in (entities or []) if getattr(e, "type", None) == "custom_emoji")
    code_count = len(re.findall(r"\{e\d+\}", template, flags=re.I))
    safe_send(
        message.chat.id,
        f"{slot_tag('check')} Welcome Message save ho gaya!\n"
        f"{slot_tag('task')} Premium Emoji saved: {emoji_count + code_count}\n"
        f"Niche preview dekhein:",
        build_owner_glow_keyboard()
    )

    owner_user = ensure_user(message.from_user)
    deliver_welcome(
        message.chat.id,
        build_home_card(owner_user, db),
        build_owner_glow_keyboard(),
        db.get("welcome_image")
    )

# ==========================================
# 11B. EMOJI PACK MANAGER
# ==========================================
def _emoji_refresh_inline(use_ce=True):
    ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
    ikb.add_row({"text": "Refresh Emoji Pack", "callback_data": "emoji_refresh", "style": "success", "emoji_id": slot_id("check")})
    ikb.add_row({"text": "Open Pack", "url": f"https://t.me/addemoji/{EMOJI_PACK_NAME}", "style": "primary", "emoji_id": slot_id("link")})
    return ikb

def send_emoji_pack_list(chat_id):
    header = (
        f"{slot_tag('image')} Premium Emoji Pack\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{slot_tag('link')} Pack: {EMOJI_PACK_NAME}\n"
        f"{slot_tag('task')} Total Emojis: {len(PACK_EMOJIS)}\n"
        f"{slot_tag('timer')} Last Saved: {PACK_INFO.get('updated') or 'N/A'} ({PACK_INFO.get('source')})\n"
        f"{slot_tag('check')} Har {EMOJI_REFRESH_MINUTES} minute me auto update + {EMOJI_CACHE_FILE} me save.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome Message me code likho, wahi emoji dikhega:"
    )
    safe_send(chat_id, header, _emoji_refresh_inline)

    lines = [f"{pe(i)}  <code>{{e{i + 1}}}</code>" for i in range(len(PACK_EMOJIS))]
    for start in range(0, len(lines), 40):
        chunk = "\n".join(lines[start:start + 40])
        try:
            bot.send_message(chat_id, chunk, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, strip_custom_emoji(chunk), parse_mode="HTML")

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "emoji pack")
def msg_owner_emoji_pack(message):
    send_emoji_pack_list(message.chat.id)

@bot.message_handler(func=lambda m: is_owner(m.from_user) and m.text and m.text.strip().lower() == "leaderboard reset")
def msg_owner_lb_reset(message):
    db = load_db()
    def _lb_inline(use_ce=True):
        ikb = GlowInlineKeyboard(use_custom_emoji=use_ce)
        ikb.add_row({"text": "Restart Daily Leaderboard Now", "callback_data": "lb_reset_now", "style": "danger", "emoji_id": slot_id("leaderboard")})
        return ikb
    safe_send(message.chat.id, build_leaderboard_text(db) + "\n\nNiche button daba kar aaj ka Leaderboard 0 se restart karein:", _lb_inline)

# ==========================================
# 12. INLINE CALLBACK HANDLERS
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = str(call.from_user.id)
    db = load_db()
    parts = call.data.split("|")
    action = parts[0]

    if not is_owner(call.from_user):
        u_check = db["users"].get(uid)
        if u_check and u_check.get("account_status", "ACTIVE") != "ACTIVE":
            bot.answer_callback_query(call.id, "Account Suspended or Banned!", show_alert=True)
            return

    if action == "self_edit":
        field = parts[1]
        if field == "name":
            msg = safe_send(call.message.chat.id, f"{slot_tag('edit')} Name Update\n━━━━━━━━━━━━━━━━━━━━━━\nApna naya Profile Name likh kar bhejein:")
            bot.register_next_step_handler(msg, save_worker_self_name)
        elif field == "upi":
            msg = safe_send(call.message.chat.id, f"{slot_tag('withdraw')} Apna Default UPI ID likh kar bhejein:")
            bot.register_next_step_handler(msg, save_worker_self_upi)
        bot.answer_callback_query(call.id)

    elif action == "emoji_refresh" and is_owner(call.from_user):
        total, added, removed, source = refresh_emoji_pack()
        bot.answer_callback_query(call.id, f"Saved {total} emojis (+{added} / -{removed})", show_alert=True)
        send_emoji_pack_list(call.message.chat.id)

    elif action in ["order_qr_now", "claim_qr"]:
        answer = handle_qr_request(call.from_user, call.message.chat.id, mode="order", source_message_id=call.message.message_id)
        bot.answer_callback_query(call.id, answer)

    elif action == "claim_link":
        task_id = parts[1]
        u = ensure_user(call.from_user)
        status, task = claim_specific_qr(uid, task_id)

        if status == "OPEN":
            bot.answer_callback_query(call.id, "Pehle apna current Qr Complete ya Failed karein!", show_alert=True)
            send_claimed_qr(call.message.chat.id, task)
            return

        if status in ("TAKEN", "NOT_FOUND"):
            bot.answer_callback_query(call.id, "Ye Qr kisi aur user ne pehle hi claim kar liya hai!", show_alert=True)
            safe_edit(
                call.message.chat.id, call.message.message_id,
                f"{slot_tag('cross')} Qr {task_id} Already Claimed\n"
                f"Ye Qr kisi aur user ne pehle claim kar liya hai.\n"
                f"Naya Qr aate hi aapko message milega."
            )
            return

        stop_user_waiting(uid)
        safe_edit(call.message.chat.id, call.message.message_id, f"{slot_tag('check')} Qr Claimed! ({task_id})\nNiche aapka Qr Link hai.")
        send_claimed_qr(call.message.chat.id, task)
        notify_owner_qr_claimed(task, u, uid)
        close_qr_broadcast(task_id, uid)
        bot.answer_callback_query(call.id, "Qr Claimed!")

    elif action == "send_qr_usr" and is_owner(call.from_user):
        target_uid = parts[1]
        order_id = parts[2]
        msg = safe_send(call.message.chat.id, f"{slot_tag('link')} Send Qr Link for Order {order_id}\nUser ID: {target_uid}\n\nApna Qr Link paste karke bhejein:")
        bot.register_next_step_handler(msg, lambda m: dispatch_direct_qr(m, target_uid))
        bot.answer_callback_query(call.id)

    elif action == "qr_ok":
        task_id = parts[1]
        if uid not in db["users"]:
            bot.answer_callback_query(call.id)
            return
        with QR_LOCK:
            db = load_db()
            u = db["users"][uid]
            task = db["tasks"].get(task_id)
            if not task:
                bot.answer_callback_query(call.id, "Task not found!", show_alert=True)
                return
            status = task.get("status")
            is_legacy = status == "LEGACY"
            if not is_legacy and (status != "CLAIMED" or task.get("claimed_by") != uid):
                bot.answer_callback_query(call.id, "Ye Qr aapke paas nahi hai ya pehle hi submit ho chuka hai!", show_alert=True)
                return
            if is_legacy and any(v["task_id"] == task_id and v["uid"] == uid for v in db["verifications"]):
                bot.answer_callback_query(call.id, "Already submitted!", show_alert=True)
                return

            raw_link = qr_raw_link(task)
            reward = task.get("reward", db["qr_rate"])
            ver_id = "VER-" + ''.join(random.choices(string.digits, k=5))
            verification = {
                "ver_id": ver_id, "task_id": task_id, "uid": uid, "name": u["name"],
                "link": raw_link, "reward": reward,
                "time": datetime.now().strftime("%d %b, %I:%M %p"), "status": "PENDING"
            }
            db["verifications"].append(verification)
            if not is_legacy:
                task["status"] = "SUBMITTED"
            u["pending_tasks"] += 1
            u["history"].append(f"{task_id} - Completed, Sent for Approval")
            save_db(db)

        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        safe_send(
            call.message.chat.id,
            f"{slot_tag('check')} Qr Complete — Approval ke liye bheja gaya\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{slot_tag('task')} Task ID: {task_id}\n"
            f"{slot_tag('price')} Reward: ₹{reward}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Agla Qr lene ke liye niche button dabayein:",
            build_order_claim_inline
        )
        try:
            safe_send(OWNER_ID, build_owner_verify_card(verification), build_owner_verify_inline(ver_id, raw_link))
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Sent to Owner for approval!")

    elif action == "qr_fail":
        task_id = parts[1]
        if uid not in db["users"]:
            bot.answer_callback_query(call.id)
            return
        with QR_LOCK:
            db = load_db()
            u = db["users"][uid]
            task = db["tasks"].get(task_id, {})
            if task.get("status") == "CLAIMED" and task.get("claimed_by") != uid:
                bot.answer_callback_query(call.id, "Ye Qr aapke paas nahi hai!", show_alert=True)
                return
            if task.get("status") not in ("CLAIMED", "LEGACY"):
                bot.answer_callback_query(call.id, "Already processed!", show_alert=True)
                return
            if task.get("status") == "CLAIMED":
                task["status"] = "FAILED"
            u["failed"] += 1
            u["history"].append(f"{task_id} - Reported Qr Failed")
            save_db(db)

        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        safe_send(
            call.message.chat.id,
            f"{slot_tag('cross')} Task {task_id} ko Qr Failed report kiya gaya.\nAgla Qr lene ke liye niche button dabayein:",
            build_order_claim_inline
        )
        try:
            safe_send(
                OWNER_ID,
                f"{slot_tag('cross')} Qr Failed Report ({task_id})\n"
                f"{slot_tag('user')} Worker: {u['name']} ({uid})\n"
                f"{slot_tag('link')} Qr Link:\n{html.escape(qr_raw_link(task))}"
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Reported Failed")

    elif action in ["own_pay", "own_rej"] and is_owner(call.from_user):
        ver_id = parts[1]
        with QR_LOCK:
            db = load_db()
            v = next((x for x in db["verifications"] if x["ver_id"] == ver_id), None)
            if not v:
                bot.answer_callback_query(call.id, "Not found!")
                return
            if v["status"] != "PENDING":
                bot.answer_callback_query(call.id, "Already processed!")
                return

            w_uid = v["uid"]
            reward = v["reward"]
            task_id = v["task_id"]
            link_line = f"\n{slot_tag('link')} Qr Link: {html.escape(v.get('link') or 'N/A')}"
            task = db["tasks"].get(task_id)

            if action == "own_pay":
                v["status"] = "APPROVED"
                if task and task.get("status") == "SUBMITTED":
                    task["status"] = "APPROVED"
                bonus = 0
                unlocked = False
                if w_uid in db["users"]:
                    w = db["users"][w_uid]
                    bonus = agent_bonus_for(w, db)
                    total = reward + bonus
                    w["balance"] += total
                    w["total_earned"] += total
                    w["daily_earned"] = w.get("daily_earned", 0) + total
                    w["agent_bonus_earned"] = w.get("agent_bonus_earned", 0) + bonus
                    w["completed"] += 1
                    w["daily_completed"] = w.get("daily_completed", 0) + 1
                    w["pending_tasks"] = max(0, w["pending_tasks"] - 1)
                    bonus_note = f" + Agent ₹{bonus}" if bonus else ""
                    w["history"].append(f"{task_id} - Verified & Paid (+₹{reward}{bonus_note})")
                    unlocked = try_unlock_agent(w, db)
                v["agent_bonus"] = bonus
                save_db(db)
                bonus_line = f"\n{slot_tag('owner')} Agent Bonus: +₹{bonus}" if bonus else ""
                safe_edit(call.message.chat.id, call.message.message_id, f"{slot_tag('check')} Approved & Paid ({ver_id})\nWorker: {v['name']} ({w_uid}){bonus_line}{link_line}")
                new_bal = db["users"].get(w_uid, {}).get("balance", 0)
                try:
                    worker_bonus_line = f"{slot_tag('owner')} Agent Bonus: +₹{bonus}\n" if bonus else ""
                    safe_send(
                        int(w_uid),
                        f"{slot_tag('check')} Qr Task Approved! ({task_id})\n"
                        f"{slot_tag('price')} Added: +₹{reward}\n"
                        f"{worker_bonus_line}"
                        f"{slot_tag('balance')} New Balance: ₹{new_bal}\n\n"
                        f"Agla Qr lene ke liye niche button dabayein:",
                        build_order_claim_inline
                    )
                    if unlocked:
                        safe_send(
                            int(w_uid),
                            f"{slot_tag('owner')} Agent Unlocked! {slot_tag('check')}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Congratulations! Aapne {db.get('agent_target', 25)} Qr complete kar liye.\n"
                            f"{slot_tag('price')} Ab har approved Qr par +₹{db.get('agent_bonus', 5)} extra milega!\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Details ke liye Agent button dabayein.",
                            build_worker_glow_keyboard(int(w_uid))
                        )
                        safe_send(OWNER_ID, f"{slot_tag('owner')} New Agent Unlocked: {v['name']} ({w_uid})")
                except Exception:
                    pass
                bot.answer_callback_query(call.id, "Approved & Paid!")
            else:
                v["status"] = "REJECTED"
                if task and task.get("status") == "SUBMITTED":
                    task["status"] = "REJECTED"
                if w_uid in db["users"]:
                    db["users"][w_uid]["failed"] += 1
                    db["users"][w_uid]["pending_tasks"] = max(0, db["users"][w_uid]["pending_tasks"] - 1)
                    db["users"][w_uid]["history"].append(f"{task_id} - Rejected by Owner")
                save_db(db)
                safe_edit(call.message.chat.id, call.message.message_id, f"{slot_tag('cross')} Rejected ({ver_id})\nWorker: {v['name']} ({w_uid}){link_line}")
                try:
                    safe_send(
                        int(w_uid),
                        f"{slot_tag('cross')} Aapka Qr Task {task_id} Owner ne Reject kar diya hai.\n\nAgla Qr lene ke liye niche button dabayein:",
                        build_order_claim_inline
                    )
                except Exception:
                    pass
                bot.answer_callback_query(call.id, "Rejected!")

    elif action in ["wd_pay", "wd_rej"] and is_owner(call.from_user):
        wd_id = parts[1]
        with QR_LOCK:
            db = load_db()
            for wd in db["withdrawals"]:
                if wd["id"] == wd_id:
                    if wd["status"] != "PENDING":
                        bot.answer_callback_query(call.id, "Already processed!")
                        return
                    w_uid = wd["uid"]
                    if action == "wd_pay":
                        wd["status"] = "PAID"
                        if w_uid in db["users"]:
                            db["users"][w_uid]["total_withdrawn"] += wd["amount"]
                        safe_send(int(w_uid), f"{slot_tag('check')} Withdrawal Paid!\nAmount: ₹{wd['amount']}")
                        safe_edit(call.message.chat.id, call.message.message_id, f"{slot_tag('check')} Paid {wd_id}")
                    else:
                        wd["status"] = "REJECTED"
                        if w_uid in db["users"]:
                            db["users"][w_uid]["balance"] += wd["amount"]
                        safe_send(int(w_uid), f"{slot_tag('cross')} Withdrawal Rejected. ₹{wd['amount']} refunded.")
                        safe_edit(call.message.chat.id, call.message.message_id, f"{slot_tag('cross')} Rejected {wd_id}")
                    save_db(db)
                    break

    elif action == "usr_st" and is_owner(call.from_user):
        target_uid = parts[1]
        new_status = parts[2]
        if target_uid in db["users"]:
            u = db["users"][target_uid]
            u["account_status"] = new_status
            save_db(db)
            safe_edit(call.message.chat.id, call.message.message_id, format_user_manage_card(u), build_user_manage_inline(target_uid, new_status))
            bot.answer_callback_query(call.id, f"Status: {new_status}")

    elif action == "agt_st" and is_owner(call.from_user):
        target_uid = parts[1]
        new_status = parts[2]
        if target_uid in db["users"]:
            u = db["users"][target_uid]
            u["agent_status"] = new_status
            if new_status == "ACTIVE" and not u.get("agent_since"):
                u["agent_since"] = datetime.now().strftime("%d %b %Y")
            u["history"].append(f"Agent {new_status} by Owner")
            save_db(db)
            safe_edit(call.message.chat.id, call.message.message_id, format_agent_manage_card(u, db), build_agent_manage_inline(target_uid, new_status))
            try:
                note = (f"{slot_tag('owner')} Aap ab Agent hain! Har approved Qr par +₹{db.get('agent_bonus', 5)} extra milega."
                        if new_status == "ACTIVE" else
                        f"{slot_tag('alert')} Aapka Agent access Owner ne band kar diya hai.")
                safe_send(int(target_uid), note)
            except Exception:
                pass
            bot.answer_callback_query(call.id, f"Agent: {new_status}")

    elif action == "agt_cfg" and is_owner(call.from_user):
        field = parts[1]
        label = "Agent Bonus (₹ per Qr)" if field == "bonus" else "Agent Unlock Target (Qr count)"
        msg = safe_send(call.message.chat.id, f"{slot_tag('edit')} Naya {label} number me bhejein (cancel = cancel):")
        bot.register_next_step_handler(msg, lambda m: owner_save_agent_cfg(m, field))
        bot.answer_callback_query(call.id)

    elif action == "lb_reset_now" and is_owner(call.from_user):
        db["leaderboard_date"] = get_today_str()
        for u_id in db["users"]:
            db["users"][u_id]["daily_completed"] = 0
            db["users"][u_id]["daily_earned"] = 0
        save_db(db)
        safe_edit(call.message.chat.id, call.message.message_id, build_leaderboard_text(db) + f"\n\n{slot_tag('check')} Leaderboard reset to 0!")
        bot.answer_callback_query(call.id, "Reset Done!")

# ==========================================
# 13. PROFILE EDIT HANDLERS
# ==========================================
def save_worker_self_name(message):
    if not message.text:
        return
    db = load_db()
    uid = str(message.from_user.id)
    if uid in db["users"]:
        db["users"][uid]["name"] = html.escape(message.text.strip()[:40])
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} Name updated successfully!", build_worker_glow_keyboard(message.from_user))

def save_worker_self_upi(message):
    if not message.text:
        return
    db = load_db()
    uid = str(message.from_user.id)
    if uid in db["users"]:
        db["users"][uid]["upi_id"] = html.escape(message.text.strip()[:60])
        save_db(db)
        safe_send(message.chat.id, f"{slot_tag('check')} UPI ID updated successfully!", build_worker_glow_keyboard(message.from_user))

threading.Thread(target=auto_refresh_emoji_pack_loop, daemon=True).start()

print(f"🚀 @{BOT_USERNAME} (Clean Broadcast Without Header) is LIVE!")
bot.infinity_polling()
