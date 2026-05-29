#!/usr/bin/env python3
"""Pixel Verification Bot — Upgraded Edition v2.0"""

import logging, psycopg2, os
from keep_alive import keep_alive
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN")

admin_env = os.getenv("ADMIN_IDS")
ADMIN_IDS = [int(x) for x in admin_env.split(",")] if admin_env else []
ADMIN_USERNAME = "PixelVerification"
SUPPORT_LINK   = "https://t.me/mosono27"
CHANNEL_ID     = -1003947571347
CHANNEL_LINK   = "https://t.me/PixelVerificationService"

LINK_PAYMENT   = "https://t.me/PixelVerificationService/5"
LINK_FAMILY    = "https://t.me/PixelVerificationService/6"
LINK_NEW_MAIL  = "https://t.me/PixelVerificationService/7"
LINK_2FA       = "https://t.me/PixelVerificationService/7"
YOUTUBE_GUIDE  = "https://youtu.be/YOUR_VIDEO_ID"

KPAY_NO   = "09885697152";  KPAY_NAME  = "Su Su Latt"
WAVE_NO   = "09686851676";  WAVE_NAME  = "Aye Min"

PACKAGES_CARD = [
    {"pts": 160, "price": 15000, "discount": 0,    "profit": 7800,  "label": "🔹 160 Points — 15,000 ကျပ် (ပုံမှန်ဈေး)"},
    {"pts": 320, "price": 29500, "discount": 500,  "profit": 15100, "label": "🔸 320 Points — 29,500 ကျပ် (500 ကျပ် သက်သာ)"},
    {"pts": 480, "price": 44000, "discount": 1000, "profit": 22400, "label": "💎 480 Points — 44,000 ကျပ် (1,000 ကျပ် သက်သာ)"},
]
PACKAGES_NOCARD = [
    {"pts": 190, "price": 17000, "discount": 0,    "profit": 8450,  "label": "🔹 190 Points — 17,000 ကျပ် (ပုံမှန်ဈေး)"},
    {"pts": 380, "price": 33500, "discount": 500,  "profit": 16400, "label": "🔸 380 Points — 33,500 ကျပ် (500 ကျပ် သက်သာ)"},
    {"pts": 570, "price": 50000, "discount": 1000, "profit": 24350, "label": "💎 570 Points — 50,000 ကျပ် (1,000 ကျပ် သက်သာ)"},
]

PLANS = [
    {"id": "card",   "name": "ကိုယ်ပိုင်ကတ် ရှိသူ",  "desc": "Credit Card ဖြင့် Google Billing မှတ်ပုံတင်ထားသောသူများ"},
    {"id": "nocard", "name": "ကိုယ်ပိုင်ကတ် မရှိသူ", "desc": "Credit Card မရှိဘဲ ဝယ်ယူလိုသောသူများ"},
]

# ══════════════════════════════════════════════════════
#  STATES
# ══════════════════════════════════════════════════════
(
    MAIN_MENU,
    ORDER_PLAN, ORDER_GMAIL, ORDER_PASSWORD, ORDER_2FA, ORDER_CONFIRM,
    BUY_PLAN_SELECT, BUY_PKG, BUY_SCREENSHOT,
    BROADCAST_MSG,
) = range(10)

DB_URL = os.getenv("DATABASE_URL")
pending_admin_actions: dict = {}

# ══════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════
def _db():
    """Returns a new psycopg2 connection with autocommit."""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    return conn

def init_db():
    try:
        conn = _db()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid BIGINT PRIMARY KEY, username TEXT,
                name TEXT, points INTEGER DEFAULT 0, joined TEXT
            );
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY, uid BIGINT,
                plan_id TEXT, plan_name TEXT, pts INTEGER, gmail TEXT,
                password TEXT, twofa TEXT, status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS pt_requests (
                id SERIAL PRIMARY KEY, uid BIGINT,
                pts INTEGER, price INTEGER, screenshot TEXT, note TEXT DEFAULT '',
                status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS manual_requests (
                id SERIAL PRIMARY KEY, uid BIGINT,
                note TEXT, status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS waitlist (uid BIGINT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, val TEXT);
        """)
        c.execute("""
            INSERT INTO settings (key, val) VALUES ('admin_away', '0')
            ON CONFLICT (key) DO NOTHING;
        """)
        c.close()
        conn.close()
        logging.info("✅ PostgreSQL DB Initialized")
    except Exception as e:
        logging.error(f"❌ DB Init Error: {e}")

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def ts_fmt(ts): return ts[:16] if ts else "-"

# ── Settings & Waitlist ──────────────────────────────
def get_away_mode() -> bool:
    conn = _db(); c = conn.cursor()
    c.execute("SELECT val FROM settings WHERE key='admin_away'")
    r = c.fetchone(); c.close(); conn.close()
    return r[0] == '1' if r else False

def set_away_mode(state: bool):
    conn = _db(); c = conn.cursor()
    c.execute("UPDATE settings SET val=%s WHERE key='admin_away'", ('1' if state else '0',))
    c.close(); conn.close()

def add_waitlist(uid):
    conn = _db(); c = conn.cursor()
    c.execute("INSERT INTO waitlist (uid) VALUES (%s) ON CONFLICT (uid) DO NOTHING", (uid,))
    c.close(); conn.close()

def get_waitlist():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT uid FROM waitlist"); rows = [r[0] for r in c.fetchall()]
    c.close(); conn.close(); return rows

def clear_waitlist():
    conn = _db(); c = conn.cursor()
    c.execute("DELETE FROM waitlist"); c.close(); conn.close()

# ── User Functions ───────────────────────────────────
def ensure_user(uid, username, name):
    conn = _db(); c = conn.cursor()
    c.execute("""
        INSERT INTO users (uid, username, name, points, joined)
        VALUES (%s, %s, %s, 0, %s)
        ON CONFLICT (uid) DO UPDATE SET username=EXCLUDED.username, name=EXCLUDED.name
    """, (uid, username, name, now()))
    c.close(); conn.close()

def get_pts(uid):
    conn = _db(); c = conn.cursor()
    c.execute("SELECT points FROM users WHERE uid=%s", (uid,))
    r = c.fetchone(); c.close(); conn.close()
    return r[0] if r else 0

def get_user_info(uid):
    conn = _db(); c = conn.cursor()
    c.execute("SELECT uid, username, name, points FROM users WHERE uid=%s", (uid,))
    r = c.fetchone(); c.close(); conn.close(); return r

def add_pts(uid, n):
    conn = _db(); c = conn.cursor()
    c.execute("UPDATE users SET points=points+%s WHERE uid=%s", (n, uid))
    c.close(); conn.close()

def get_all_user_ids():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT uid FROM users"); rows = [r[0] for r in c.fetchall()]
    c.close(); conn.close(); return rows

# ── Order Functions ──────────────────────────────────
def new_order(uid, plan_id, plan_name, pts, gmail, pwd, twofa):
    conn = _db(); c = conn.cursor()
    c.execute("""
        INSERT INTO orders(uid, plan_id, plan_name, pts, gmail, password, twofa, ts)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (uid, plan_id, plan_name, pts, gmail, pwd, twofa, now()))
    oid = c.fetchone()[0]; c.close(); conn.close(); return oid

def get_order(oid):
    conn = _db(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id=%s", (oid,))
    r = c.fetchone(); c.close(); conn.close(); return r

def set_order_status(oid, status):
    conn = _db(); c = conn.cursor()
    c.execute("UPDATE orders SET status=%s WHERE id=%s", (status, oid))
    c.close(); conn.close()

def my_orders(uid):
    conn = _db(); c = conn.cursor()
    c.execute("SELECT id, plan_name, pts, status, ts FROM orders WHERE uid=%s ORDER BY id DESC LIMIT 10", (uid,))
    rows = c.fetchall(); c.close(); conn.close(); return rows

def pending_orders():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status='pending' ORDER BY id DESC")
    rows = c.fetchall(); c.close(); conn.close(); return rows

# ── Point Request Functions ──────────────────────────
def new_pt_req(uid, pts, price, fid):
    conn = _db(); c = conn.cursor()
    c.execute("""
        INSERT INTO pt_requests(uid, pts, price, screenshot, ts)
        VALUES(%s,%s,%s,%s,%s) RETURNING id
    """, (uid, pts, price, fid, now()))
    rid = c.fetchone()[0]; c.close(); conn.close(); return rid

def set_pt_status(rid, status):
    conn = _db(); c = conn.cursor()
    c.execute("UPDATE pt_requests SET status=%s WHERE id=%s", (status, rid))
    c.close(); conn.close()

def pending_pts():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT * FROM pt_requests WHERE status='pending' ORDER BY id DESC")
    rows = c.fetchall(); c.close(); conn.close(); return rows

def all_pt_requests(limit=30):
    conn = _db(); c = conn.cursor()
    c.execute("""
        SELECT r.id, r.uid, u.name, r.pts, r.price, r.status, r.ts
        FROM pt_requests r LEFT JOIN users u ON r.uid=u.uid
        ORDER BY r.id DESC LIMIT %s
    """, (limit,))
    rows = c.fetchall(); c.close(); conn.close(); return rows

# ── Manual Request Functions ─────────────────────────
def pending_manual_reqs():
    conn = _db(); c = conn.cursor()
    c.execute("""
        SELECT m.id, m.uid, u.name, u.points, m.note, m.ts
        FROM manual_requests m LEFT JOIN users u ON m.uid=u.uid
        WHERE m.status='pending' ORDER BY m.id DESC
    """)
    rows = c.fetchall(); c.close(); conn.close(); return rows

def set_manual_status(mid, status):
    conn = _db(); c = conn.cursor()
    c.execute("UPDATE manual_requests SET status=%s WHERE id=%s", (status, mid))
    c.close(); conn.close()

def all_users():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT uid, username, name, points FROM users ORDER BY points DESC")
    rows = c.fetchall(); c.close(); conn.close(); return rows

def get_stats():
    conn = _db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'"); pending_ord = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status='completed'"); done_ord = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM pt_requests WHERE status='pending'"); pending_pt = c.fetchone()[0]
    c.close(); conn.close()
    return total_users, pending_ord, done_ord, pending_pt

# ══════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════
MAIN_KB = ReplyKeyboardMarkup([
    ["💰 Points ကြည့်",  "🛒 Order တင်"],
    ["💎 Points ဝယ်",   "📋 Orders ကြည့်"],
    ["📖 လမ်းညွှန်",    "📞 Support"],
], resize_keyboard=True)

def plan_kb():
    rows = [
        [InlineKeyboardButton(f"💳 {PLANS[0]['name']}", callback_data="plan:card")],
        [InlineKeyboardButton(f"👤 {PLANS[1]['name']}", callback_data="plan:nocard")],
        [InlineKeyboardButton("❌ ဖျက်မည်", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(rows)

def buy_plan_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ကိုယ်ပိုင်ကတ် ရှိသူ", callback_data="buyplan:card")],
        [InlineKeyboardButton("👤 ကိုယ်ပိုင်ကတ် မရှိသူ", callback_data="buyplan:nocard")],
        [InlineKeyboardButton("❌ ဖျက်မည်", callback_data="cancel")],
    ])

def pkg_kb(plan_type):
    packages = PACKAGES_CARD if plan_type == "card" else PACKAGES_NOCARD
    rows = [[InlineKeyboardButton(p["label"], callback_data=f"pkg:{plan_type}:{p['pts']}:{p['price']}")] for p in packages]
    rows.append([InlineKeyboardButton("⬅️ နောက်သို့", callback_data="buyplan_back")])
    rows.append([InlineKeyboardButton("❌ ဖျက်မည်", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def order_confirm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Order တင်မည်", callback_data="order_confirm")],
        [InlineKeyboardButton("❌ ဖျက်မည်",     callback_data="order_cancel")],
    ])

def admin_kb():
    is_away = get_away_mode()
    away_text = "🟢 Away Mode: OFF" if not is_away else "🔴 Away Mode: ON"
    waitlist_count = len(get_waitlist())
    total_users, p_ord, d_ord, p_pt = get_stats()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📊 Stats: {total_users} Users | {d_ord} Done | {p_ord} Pending", callback_data="adm:stats_summary")],
        [InlineKeyboardButton(f"📋 Pending Orders ({p_ord})",        callback_data="adm:orders")],
        [InlineKeyboardButton(f"💰 Pending Points ({p_pt})",          callback_data="adm:pts")],
        [InlineKeyboardButton("🙋 Manual Requests",                   callback_data="adm:manual")],
        [InlineKeyboardButton("👥 Users List",      callback_data="adm:users"),
         InlineKeyboardButton("📊 Pt History",      callback_data="adm:pts_all")],
        [InlineKeyboardButton("➕ Points ထည့်/နုတ်",               callback_data="adm:addpts")],
        [InlineKeyboardButton("📢 Broadcast ပို့",                   callback_data="adm:broadcast")],
        [InlineKeyboardButton(away_text,                              callback_data="adm:toggle_away")],
        [InlineKeyboardButton(f"🔔 Notify Waitlist ({waitlist_count})", callback_data="adm:notify_waitlist")],
    ])

def order_action_kb(oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Complete", callback_data=f"done:{oid}"),
         InlineKeyboardButton("❌ Reject",   callback_data=f"rj_menu:{oid}")],
    ])

def reject_kb(oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 2FA မမှန်",         callback_data=f"rj:2fa:{oid}")],
        [InlineKeyboardButton("💳 Payment မပိတ်",    callback_data=f"rj:pay:{oid}")],
        [InlineKeyboardButton("👨‍👩‍👧 Family မထွက်", callback_data=f"rj:fam:{oid}")],
        [InlineKeyboardButton("📧 Gmail မမှန်",       callback_data=f"rj:mail:{oid}")],
        [InlineKeyboardButton("❓ အခြား",             callback_data=f"rj:other:{oid}")],
        [InlineKeyboardButton("⬅️ နောက်သို့",        callback_data=f"rj_back:{oid}")],
    ])

def pts_action_kb(rid, uid, pts):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Approve +{pts}pts", callback_data=f"pts:ok:{rid}:{uid}:{pts}"),
         InlineKeyboardButton("❌ Reject",             callback_data=f"pts:no:{rid}:{uid}:0")],
    ])

def manual_action_kb(mid, ruid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ကိုင်တွယ်ပြီး", callback_data=f"man:done:{mid}:{ruid}"),
         InlineKeyboardButton("❌ ပယ်ဖျက်",      callback_data=f"man:no:{mid}:{ruid}")],
    ])

def is_admin(uid): return uid in ADMIN_IDS

# ══════════════════════════════════════════════════════
#  SETUP BOT COMMANDS
# ══════════════════════════════════════════════════════
async def setup_bot_commands(application: Application):
    await application.bot.set_my_commands(
        [("start", "Bot ကို စတင်ရန်"), ("cancel", "လက်ရှိ လုပ်ဆောင်မှု ဖျက်ရန်")],
        scope=BotCommandScopeDefault()
    )
    for aid in ADMIN_IDS:
        try:
            await application.bot.set_my_commands(
                [
                    ("start",  "Bot ကို စတင်ရန်"),
                    ("cancel", "လုပ်ဆောင်ချက် ဖျက်ရန်"),
                    ("admin",  "🔧 Admin Panel"),
                    ("addpts", "➕ Points ထည့်/နုတ်"),
                    ("stats",  "📊 Bot Stats ကြည့်"),
                ],
                scope=BotCommandScopeChat(aid)
            )
        except Exception as e:
            logging.warning(f"Could not set admin commands for {aid}: {e}")

# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════
async def notify_admins(bot, text, *, markup=None, photo=None):
    for aid in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(aid, photo=photo, caption=text, parse_mode="Markdown", reply_markup=markup)
            else:
                await bot.send_message(aid, text, parse_mode="Markdown", reply_markup=markup)
        except Exception as e:
            logging.warning(f"notify_admin {aid}: {e}")

async def check_member(bot, uid) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status not in ("left", "kicked", "banned")
    except:
        return False

async def must_join(update: Update, bot) -> bool:
    uid = update.effective_user.id
    if await check_member(bot, uid):
        return True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Join ဖို့ ဒီမှာ နှိပ်ပါ", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Join ပြီးပြီ — စစ်ဆေးပါ", callback_data="check_join")],
    ])
    msg = (
        "⚠️ *Bot သုံးရန် Channel Join လိုအပ်ပါသည်*\n\n"
        "📢 Channel သို့ Join ဖြစ်ပြီးမှ Bot ဆက်သုံးနိုင်ပါမည်"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    return False

async def away_check(update: Update) -> bool:
    """Returns True if bot is in away mode — shows message and returns True to block."""
    if get_away_mode():
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Admin ပြန်ရောက်ချိန် အသိပေးပါ", callback_data="waitlist_add")]])
        await update.message.reply_text(
            "⚠️ *ယခု Admin မအားသေးပါ*\n\nAdmin ပြန်ရောက်လာချိန် အသိပေးချက်ရလိုပါက အောက်ပါ ခလုတ်နှိပ်ပါ ↓",
            parse_mode="Markdown", reply_markup=kb
        )
        return True
    return False

# ══════════════════════════════════════════════════════
#  ADMIN TEXT HANDLER
# ══════════════════════════════════════════════════════
async def admin_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    action = pending_admin_actions.get(uid)
    if not action:
        return

    text = update.message.text.strip()
    atype = action.get("type")

    # ── Send redemption link to user ──────────────────
    if atype == "link":
        oid, ruid, gmail = action["oid"], action["ruid"], action["gmail"]
        set_order_status(oid, "completed")
        msg = (
            f"✅ *Order #{oid} ပြီးစီးပါပြီ!*\n\n"
            f"🎁 *Google AI Pro ၁၂-လ Trial Link*\n\n"
            f"`{text}`\n\n"
            f"✉️ Gmail: `{gmail}`\n\n"
            f"⚠️ *ဤ Link ကို အထက်ပါ Gmail အတွက်သာ အသုံးပြုနိုင်ပါသည်*\n"
            f"Gmail မမှန်ပါက _'Can't redeem offer'_ ဖြစ်နိုင်သည်\n\n"
            f"📞 အကူအညီ — @{ADMIN_USERNAME}"
        )
        try:
            await ctx.bot.send_message(ruid, msg, parse_mode="Markdown", disable_web_page_preview=True)
            await update.message.reply_text(
                f"✅ *Order #{oid} Complete!*\n👤 User `{ruid}` ထံ Link ပို့ပြီ ✔️",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ User `{ruid}` ထံ ပို့မရပါ\nError: `{e}`\n\n"
                f"Order #{oid} Complete အဖြစ် မှတ်ပြီ",
                parse_mode="Markdown"
            )
        pending_admin_actions.pop(uid, None)

    # ── Add/Deduct points — step 1: get user ID ───────
    elif atype == "addpts_uid":
        try:
            tuid = int(text)
        except ValueError:
            await update.message.reply_text("❌ User ID မှာ number သာ ထည့်ပါ")
            return
        info = get_user_info(tuid)
        if not info:
            await update.message.reply_text(f"❌ User `{tuid}` DB တွင် မတွေ့ပါ", parse_mode="Markdown")
            return
        _, uname, uname_full, bal = info
        pending_admin_actions[uid] = {"type": "addpts_amt", "tuid": tuid, "name": uname_full, "bal": bal}
        await update.message.reply_text(
            f"👤 *{uname_full}* (`{tuid}`)\n💰 လက်ကျန် — *{bal} pts*\n\n"
            f"ထည့်/နုတ်မည့် Amount ထည့်ပါ\n_(ဥပမာ — `160` ထည့်ရန် | `-160` နုတ်ရန်)_",
            parse_mode="Markdown"
        )

    # ── Add/Deduct points — step 2: apply amount ──────
    elif atype == "addpts_amt":
        try:
            amt = int(text)
        except ValueError:
            await update.message.reply_text("❌ Number သာ ထည့်ပါ")
            return
        tuid, tname, old_bal = action["tuid"], action["name"], action["bal"]
        add_pts(tuid, amt)
        new_bal = get_pts(tuid)
        verb = "ထည့်" if amt > 0 else "နုတ်"
        await update.message.reply_text(
            f"✅ *{tname}* (`{tuid}`)\n"
            f"{'➕' if amt > 0 else '➖'} {abs(amt)} pts {verb}ပြီ\n"
            f"💰 {old_bal} → *{new_bal} pts*",
            parse_mode="Markdown"
        )
        note = (
            f"✅ *Admin မှ {abs(amt)} Points ထည့်ပေးပြီ!*\n💰 Balance: *{new_bal} pts*"
            if amt > 0 else
            f"ℹ️ Admin မှ {abs(amt)} pts နုတ်ခဲ့ပါသည်\n💰 Balance: *{new_bal} pts*"
        )
        try:
            await ctx.bot.send_message(tuid, note, parse_mode="Markdown")
        except:
            pass
        pending_admin_actions.pop(uid, None)

    # ── Broadcast message ─────────────────────────────
    elif atype == "broadcast":
        all_ids = get_all_user_ids()
        sent, failed = 0, 0
        await update.message.reply_text(f"📢 *{len(all_ids)} ယောက်ထံ ပို့နေပါသည်...*", parse_mode="Markdown")
        for target_uid in all_ids:
            try:
                await ctx.bot.send_message(
                    target_uid,
                    f"📢 *Pixel Verification မှ သတင်းစကား*\n\n{text}",
                    parse_mode="Markdown"
                )
                sent += 1
            except:
                failed += 1
        await update.message.reply_text(
            f"✅ *Broadcast ပြီးပါပြီ*\n📤 ပို့ပြီး — {sent} ယောက်\n❌ မပို့ရ — {failed} ယောက်",
            parse_mode="Markdown"
        )
        pending_admin_actions.pop(uid, None)

# ══════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure_user(u.id, u.username or "", u.full_name)
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    await update.message.reply_text(
        f"👋 မင်္ဂလာပါ *{u.first_name}*!\n\n"
        f"🤖 *Pixel Verification Bot* မှ ကြိုဆိုပါသည်\n\n"
        f"💎 Google AI Pro Plan ဝယ်ယူနိုင်သည့် Bot ဖြစ်ပါသည်\n\n"
        f"📌 အောက်မှ Menu ကို ရွေးချယ်ပါ ↓",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )
    return MAIN_MENU

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    total_users, p_ord, d_ord, p_pt = get_stats()
    await update.message.reply_text(
        f"🔧 *Admin Panel*\n{'━'*20}\n"
        f"👥 Users: *{total_users}*\n"
        f"📋 Pending Orders: *{p_ord}*\n"
        f"✅ Completed Orders: *{d_ord}*\n"
        f"💰 Pending Pt Requests: *{p_pt}*\n"
        f"{'━'*20}",
        parse_mode="Markdown",
        reply_markup=admin_kb()
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    total_users, p_ord, d_ord, p_pt = get_stats()
    waitlist = len(get_waitlist())
    away = "ON 🔴" if get_away_mode() else "OFF 🟢"
    await update.message.reply_text(
        f"📊 *Bot Statistics*\n{'━'*20}\n"
        f"👥 Total Users: *{total_users}*\n"
        f"📋 Pending Orders: *{p_ord}*\n"
        f"✅ Completed: *{d_ord}*\n"
        f"💰 Pending Pt Req: *{p_pt}*\n"
        f"🔔 Waitlist: *{waitlist}*\n"
        f"😴 Away Mode: *{away}*\n"
        f"{'━'*20}",
        parse_mode="Markdown"
    )

async def cmd_addpts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        pending_admin_actions[update.effective_user.id] = {"type": "addpts_uid"}
        await update.message.reply_text(
            "➕ *Points ထည့်/နုတ်*\n\nUser ID ထည့်ပါ —",
            parse_mode="Markdown"
        )
        return
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/addpts <uid> <amount>`", parse_mode="Markdown")
        return
    try:
        tuid, amt = int(args[0]), int(args[1])
    except ValueError:
        await update.message.reply_text("❌ uid နှင့် amount မှာ number ဖြစ်ရမည်")
        return
    info = get_user_info(tuid)
    if not info:
        await update.message.reply_text(f"❌ User `{tuid}` မတွေ့ပါ", parse_mode="Markdown")
        return
    _, uname, uname_full, old_bal = info
    add_pts(tuid, amt)
    new_bal = get_pts(tuid)
    verb = "ထည့်" if amt > 0 else "နုတ်"
    await update.message.reply_text(
        f"✅ *{uname_full}* (`{tuid}`)\n"
        f"{'➕' if amt > 0 else '➖'} {abs(amt)} pts {verb}ပြီ\n"
        f"💰 {old_bal} → *{new_bal} pts*",
        parse_mode="Markdown"
    )
    note = (
        f"✅ *Admin မှ {abs(amt)} Points ထည့်ပေးပြီ!*\n💰 Balance: *{new_bal} pts*"
        if amt > 0 else
        f"ℹ️ Admin မှ {abs(amt)} pts နုတ်ခဲ့ပါသည်\n💰 Balance: *{new_bal} pts*"
    )
    try:
        await ctx.bot.send_message(tuid, note, parse_mode="Markdown")
    except:
        pass

# ══════════════════════════════════════════════════════
#  MAIN MENU HANDLERS
# ══════════════════════════════════════════════════════
async def h_points(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    uid = update.effective_user.id
    pts = get_pts(uid)
    info = get_user_info(uid)
    name = info[2] if info else "Unknown"

    # Count orders
    rows = my_orders(uid)
    completed = sum(1 for r in rows if r[3] == "completed")
    pending   = sum(1 for r in rows if r[3] == "pending")

    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Points Balance*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {name}\n"
        f"🎯  *{pts} pts*\n\n"
        f"📊 Orders — ✅ {completed} ပြီး | ⏳ {pending} ဆောင်ရွက်နေဆဲ\n\n"
        f"💎 Points ဝယ်ရန် — Menu မှ *'💎 Points ဝယ်'* နှိပ်ပါ",
        parse_mode="Markdown"
    )

async def h_guide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    text = (
        "📖 *Pixel Verification လမ်းညွှန်*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Google Account ပြင်ဆင်ရမည့် အချက်များ* ↓\n\n"
        "① Google အကောင့် ပုံမှန်ဖြစ်ရမည်\n"
        "    _(locked / restricted မဖြစ်ရ)_\n\n"
        "② Google Payments ထဲမှ Payment Profile\n"
        f"    အဟောင်းများ ဖျက်ပစ်ပါ ↳ [Video]({LINK_PAYMENT})\n\n"
        "③ Family Group တွင် မပါဝင်စေရ\n"
        f"    ↳ [ထွက်နည်း Video]({LINK_FAMILY})\n\n"
        "④ Gemini / Google One Subscription မရှိစေရ\n\n"
        "⑤ Two-step Verification ဖွင့်ပြီး\n"
        "    Authenticator 2FA ပြုလုပ်ထားရမည်\n"
        f"    ↳ [2FA ဖွင့်နည်း Video]({LINK_2FA})\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 *အသုံးဝင်သော Links*\n"
        "• https://myaccount.google.com/signinoptions/twosv\n"
        "• https://payments.google.com\n"
        "• https://families.google.com/families"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def h_my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    rows = my_orders(update.effective_user.id)
    if not rows:
        await update.message.reply_text(
            "📋 *Orders မရှိသေးပါ*\n\n'🛒 Order တင်' ကို နှိပ်ပြီး စတင်နိုင်ပါသည်",
            parse_mode="Markdown"
        )
        return
    ST = {"pending": "⏳ ဆောင်ရွက်နေဆဲ", "completed": "✅ ပြီးစီးပြီ", "rejected": "❌ ပယ်ဖျက်ပြီ"}
    lines = [
        f"{'─'*22}\n"
        f"🧾 *Order #{oid}*\n"
        f"📅 {ts_fmt(ts)}\n"
        f"📦 {pname}  |  💰 {pts} pts\n"
        f"🔖 {ST.get(st, st)}"
        for oid, pname, pts, st, ts in rows
    ]
    await update.message.reply_text(
        f"📋 *Your Orders ({len(rows)})*\n{'─'*22}\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def h_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 *Support & Help*\n{'━'*18}\n\n"
        f"👤 Admin — @{ADMIN_USERNAME}\n"
        f"🔗 {SUPPORT_LINK}\n\n"
        f"⏰ ပုံမှန်ဖြေကြားချိန် — ၁ နာရီ အတွင်း\n\n"
        f"📖 အသုံးပြုနည်း မသိပါက 'လမ်းညွှန်' ကို ကြည့်ပါ",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════
#  ORDER FLOW
# ══════════════════════════════════════════════════════
async def h_start_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await away_check(update):
        return MAIN_MENU
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    plan_lines = "\n\n".join(
        f"{'💳' if p['id']=='card' else '👤'} *{p['name']}*\n   _{p['desc']}_"
        for p in PLANS
    )
    await update.message.reply_text(
        f"🛒 *Order တင်ရန် Plan ရွေးချယ်ပါ*\n{'━'*22}\n\n{plan_lines}\n\n{'━'*22}",
        parse_mode="Markdown",
        reply_markup=plan_kb()
    )
    return ORDER_PLAN

async def cb_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        ctx.user_data.clear()
        await q.message.reply_text("❌ Cancel ပြုလုပ်ပြီ", reply_markup=MAIN_KB)
        return MAIN_MENU
    plan_id = q.data.split(":")[1]
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        return MAIN_MENU
    ctx.user_data["selected_plan"] = plan_id
    cost_pts = 160 if plan_id == "card" else 190
    current_bal = get_pts(q.from_user.id)
    await q.message.reply_text(
        f"🛒 *{plan['name']} Plan ရွေးချယ်ပြီ*\n\n"
        f"{'━'*22}\n"
        f"⚠️ *Order မတင်မီ စစ်ဆေးရမည့်အချက်များ*\n\n"
        f"① Payment Profile ပိတ်ပါ ↳ [Video]({LINK_PAYMENT})\n"
        f"② Family Group ထွက်ပါ ↳ [Video]({LINK_FAMILY})\n"
        f"③ 2FA ဖွင့်ထားပါ ↳ [Video]({LINK_2FA})\n"
        f"{'━'*22}\n"
        f"💰 Order Cost: *{cost_pts} pts* | လက်ကျန်: *{current_bal} pts*\n\n"
        f"📧 *Gmail လိပ်စာ ရိုက်ပါ* ↓",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    return ORDER_GMAIL

async def h_gmail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    gmail = update.message.text.strip()
    if "@" not in gmail or "." not in gmail:
        await update.message.reply_text(
            "❌ *Gmail လိပ်စာ မှန်ကန်မှု မရှိပါ*\n\nဥပမာ — `example@gmail.com`",
            parse_mode="Markdown"
        )
        return ORDER_GMAIL
    ctx.user_data["gmail"] = gmail
    await update.message.reply_text(
        f"📧 Gmail — `{gmail}` ✓\n\n🔒 *Password ရိုက်ပါ* ↓\n\n_⚠️ Bot မှ Password ကို Order ပြီးလျှင် Delete ပြုလုပ်မည်_",
        parse_mode="Markdown"
    )
    return ORDER_PASSWORD

async def h_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["password"] = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text(
        f"🔒 Password ✓ _(မှတ်ဉာဏ်ထဲ သိမ်းပြီ — ပြသမည် မဟုတ်ပါ)_\n\n"
        f"{'━'*22}\n"
        f"🔐 *2FA Backup Key ရိုက်ပါ* ↓\n\n"
        f"_ဥပမာ — `zad6 65hd 5fp6 kjzy mrfc cenj`_\n\n"
        f"📹 [2FA ဖွင့်နည်း — မဖြစ်မနေ ကြည့်ပါ!]({LINK_2FA})\n\n"
        f"_2FA မရှိပါက `skip` ရိုက်ပါ (Order reject ဖြစ်နိုင်သည်)_",
        parse_mode="Markdown"
    )
    return ORDER_2FA

async def h_2fa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    twofa = update.message.text.strip()
    if twofa.lower() == "skip":
        twofa = "N/A"
    ctx.user_data["twofa"] = twofa

    selected_plan_type = ctx.user_data.get("selected_plan")
    if not selected_plan_type:
        await update.message.reply_text("❌ Plan information ပျောက်နေသည်။ ထပ်မံ စတင်ပါ", reply_markup=MAIN_KB)
        return MAIN_MENU

    plan_name = next((p["name"] for p in PLANS if p["id"] == selected_plan_type), "Unknown")
    cost_pts  = 160 if selected_plan_type == "card" else 190
    current_bal = get_pts(update.effective_user.id)

    if current_bal < cost_pts:
        await update.message.reply_text(
            f"❌ *Points မလုံလောက်ပါ!*\n\n"
            f"💰 လိုအပ်သော Points — *{cost_pts} pts*\n"
            f"💰 လက်ကျန် Points — *{current_bal} pts*\n"
            f"📉 ကွာဟချက် — *{cost_pts - current_bal} pts*\n\n"
            f"💎 'Points ဝယ်' မှ ဦးစွာ Points ဝယ်ပါ",
            parse_mode="Markdown",
            reply_markup=MAIN_KB
        )
        ctx.user_data.clear()
        return MAIN_MENU

    # Show confirmation screen
    gmail = ctx.user_data.get("gmail", "N/A")
    twofa_display = twofa if twofa != "N/A" else "⚠️ မပါ (reject ဖြစ်နိုင်)"
    await update.message.reply_text(
        f"📋 *Order Confirmation*\n{'━'*22}\n\n"
        f"📦 Plan — *{plan_name}*\n"
        f"📧 Gmail — `{gmail}`\n"
        f"🔐 2FA — `{twofa_display}`\n\n"
        f"{'━'*22}\n"
        f"💰 နုတ်ယူမည် — *{cost_pts} pts*\n"
        f"💰 လက်ကျန် — *{current_bal} pts*\n"
        f"💰 Order ပြီးနောက် — *{current_bal - cost_pts} pts*\n\n"
        f"{'━'*22}\n"
        f"✅ Order တင်မည်ဆိုလျှင် အောက်ပါ ခလုတ်နှိပ်ပါ ↓",
        parse_mode="Markdown",
        reply_markup=order_confirm_kb()
    )
    return ORDER_CONFIRM

async def cb_order_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "order_cancel":
        ctx.user_data.clear()
        await q.message.reply_text("❌ Order ဖျက်ပြီ", reply_markup=MAIN_KB)
        return MAIN_MENU

    if q.data != "order_confirm":
        return ORDER_CONFIRM

    u = q.from_user
    selected_plan_type = ctx.user_data.get("selected_plan")
    gmail    = ctx.user_data.get("gmail", "N/A")
    password = ctx.user_data.get("password", "N/A")
    twofa    = ctx.user_data.get("twofa", "N/A")

    if not selected_plan_type:
        await q.message.reply_text("❌ Session ကုန်သွားပြီ။ ထပ်မံ Order တင်ပါ", reply_markup=MAIN_KB)
        return MAIN_MENU

    plan_name = next((p["name"] for p in PLANS if p["id"] == selected_plan_type), "Unknown")
    cost_pts  = 160 if selected_plan_type == "card" else 190
    current_bal = get_pts(u.id)

    if current_bal < cost_pts:
        await q.message.reply_text(
            f"❌ *Points မလုံလောက်ပါ!*\n\n"
            f"💰 လိုအပ်သော Points — *{cost_pts} pts*\n"
            f"💰 လက်ကျန် — *{current_bal} pts*\n\n"
            f"💎 Points ဝယ်ပါ",
            parse_mode="Markdown",
            reply_markup=MAIN_KB
        )
        ctx.user_data.clear()
        return MAIN_MENU

    add_pts(u.id, -cost_pts)
    oid = new_order(u.id, selected_plan_type, plan_name, cost_pts, gmail, password, twofa)

    await notify_admins(
        ctx.bot,
        f"🆕 *New Order #{oid}*\n{'─'*22}\n"
        f"👤 [{u.full_name}](tg://user?id={u.id})  `{u.id}`\n"
        f"📦 {plan_name}  |  {cost_pts} pts\n"
        f"📧 Gmail: `{gmail}`\n"
        f"🔒 Password: `{password}`\n"
        f"🔐 2FA: `{twofa}`\n"
        f"🕐 {now()}",
        markup=order_action_kb(oid)
    )

    await q.message.reply_text(
        f"✅ *Order #{oid} တင်ပြီ!*\n\n"
        f"📦 {plan_name}\n"
        f"💰 {cost_pts} pts နုတ်ယူပြီ\n"
        f"💰 လက်ကျန် — *{get_pts(u.id)} pts*\n\n"
        f"⏳ Admin စစ်ဆေးနေပါသည်\n"
        f"ပြီးစီးလျှင် Bot မှ အကြောင်းကြားမည် 🔔\n\n"
        f"📞 မေးမြန်းရန် — @{ADMIN_USERNAME}",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )
    ctx.user_data.clear()
    return MAIN_MENU

# ══════════════════════════════════════════════════════
#  BUY POINTS FLOW
# ══════════════════════════════════════════════════════
async def h_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await away_check(update):
        return MAIN_MENU
    if not await must_join(update, ctx.bot):
        return MAIN_MENU
    pts = get_pts(update.effective_user.id)
    await update.message.reply_text(
        f"💎 *Points ဝယ်ယူရန်*\n{'━'*22}\n\n"
        f"💰 လက်ကျန် — *{pts} pts*\n\n"
        f"ဦးစွာ Card ရှိ/မရှိ ရွေးချယ်ပါ ↓",
        parse_mode="Markdown",
        reply_markup=buy_plan_kb()
    )
    return BUY_PLAN_SELECT

async def cb_buy_plan_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        ctx.user_data.clear()
        await q.message.reply_text("❌ Cancelled", reply_markup=MAIN_KB)
        return MAIN_MENU
    plan_type = q.data.split(":")[1]
    ctx.user_data["buy_plan_type"] = plan_type
    plan_label = "ကိုယ်ပိုင်ကတ် ရှိသူ" if plan_type == "card" else "ကိုယ်ပိုင်ကတ် မရှိသူ"
    await q.message.edit_text(
        f"💎 *{plan_label}*\n\nPackage ရွေးပါ ↓",
        parse_mode="Markdown",
        reply_markup=pkg_kb(plan_type)
    )
    return BUY_PKG

async def cb_pkg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        ctx.user_data.clear()
        await q.message.reply_text("❌ Cancel ပြုလုပ်ပြီ", reply_markup=MAIN_KB)
        return MAIN_MENU
    if q.data == "buyplan_back":
        await q.message.edit_text(
            "💎 *Points ဝယ်ယူရန် အမျိုးအစား ရွေးချယ်ပါ*",
            parse_mode="Markdown",
            reply_markup=buy_plan_kb()
        )
        return BUY_PLAN_SELECT

    _, plan_type, pts_str, price_str = q.data.split(":")
    pts, price = int(pts_str), int(price_str)
    ctx.user_data["buy_pts"]   = pts
    ctx.user_data["buy_price"] = price

    await q.message.edit_text(
        f"💎 *{pts} Points = {price:,} ကျပ်*\n\n"
        f"{'━'*22}\n"
        f"📱 *KPay*\n"
        f"   📞 `{KPAY_NO}`\n"
        f"   👤 {KPAY_NAME}\n\n"
        f"📱 *Wave Pay*\n"
        f"   📞 `{WAVE_NO}`\n"
        f"   👤 {WAVE_NAME}\n\n"
        f"{'━'*22}\n"
        f"⚠️ ငွေပြေစာ Screenshot *အပြည့်အစုံ* (ကိုယ်ရေး + ပမာဏ ပြသသည်) ကို ပို့ပါ\n\n"
        f"📸 Screenshot ↓",
        parse_mode="Markdown"
    )
    return BUY_SCREENSHOT

async def h_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text(
            "❌ *ဓာတ်ပုံ (Screenshot) သာ ပို့ပါ!*\n\nText မဟုတ်ဘဲ Screenshot ပုံကိုသာ ပို့ပါ",
            parse_mode="Markdown"
        )
        return BUY_SCREENSHOT
    u   = update.effective_user
    fid = update.message.photo[-1].file_id
    pts   = ctx.user_data.get("buy_pts", 160)
    price = ctx.user_data.get("buy_price", 15000)
    rid = new_pt_req(u.id, pts, price, fid)

    await notify_admins(
        ctx.bot,
        f"💰 *New Point Request #{rid}*\n{'─'*22}\n"
        f"👤 [{u.full_name}](tg://user?id={u.id})  `{u.id}`\n"
        f"💎 {pts} pts  |  💵 {price:,} ကျပ်\n"
        f"🕐 {now()}",
        photo=fid,
        markup=pts_action_kb(rid, u.id, pts)
    )

    await update.message.reply_text(
        f"✅ *Screenshot ပို့ပြီ! (Request #{rid})*\n\n"
        f"💎 {pts} pts  |  💵 {price:,} ကျပ်\n\n"
        f"⏳ Admin စစ်ဆေးပြီး Points ထည့်ပေးမည် (ပုံမှန် ၁ နာရီ အတွင်း)\n\n"
        f"📞 မေးမြန်းရန် — @{ADMIN_USERNAME}",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )
    ctx.user_data.clear()
    return MAIN_MENU

async def h_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    pending_admin_actions.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Cancel ပြုလုပ်ပြီ", reply_markup=MAIN_KB)
    return MAIN_MENU

# ══════════════════════════════════════════════════════
#  GLOBAL CALLBACK
# ══════════════════════════════════════════════════════
async def global_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    data = q.data

    # ── Waitlist ──────────────────────────────────────
    if data == "waitlist_add":
        add_waitlist(uid)
        await q.message.reply_text(
            "✅ Waitlist ထည့်ပြီ!\nAdmin ပြန်ရောက်လျှင် Bot မှ အကြောင်းကြားပေးမည် 🔔"
        )
        return

    # ── Channel join check ────────────────────────────
    if data == "check_join":
        if await check_member(ctx.bot, uid):
            ensure_user(uid, q.from_user.username or "", q.from_user.full_name)
            await q.message.reply_text("✅ Channel Join ပြီးပြီ! ကြိုဆိုပါသည် 🎉", reply_markup=MAIN_KB)
        else:
            await q.message.reply_text("❌ Channel ကို Join မဖြစ်သေးပါ ⚠️\nJoin ပြီးမှ ဒီခလုတ် နှိပ်ပါ")
        return

    # ── Order confirm/cancel callbacks ───────────────
    if data in ("order_confirm", "order_cancel"):
        return await cb_order_confirm(update, ctx)

    # ── Admin panel callbacks ─────────────────────────
    if data.startswith("adm:"):
        if not is_admin(uid):
            await q.message.reply_text("❌ Admin only!")
            return
        act = data[4:]

        if act == "toggle_away":
            new_state = not get_away_mode()
            set_away_mode(new_state)
            state_text = "ON 🔴 — ဝန်ဆောင်မှု ယာယီပိတ်ထားသည်" if new_state else "OFF 🟢 — ဝန်ဆောင်မှု ပြန်ဖွင့်ပြီ"
            await q.message.edit_reply_markup(reply_markup=admin_kb())
            await q.message.reply_text(f"✅ Away Mode: *{state_text}*", parse_mode="Markdown")

        elif act == "notify_waitlist":
            wl = get_waitlist()
            if not wl:
                await q.message.reply_text("🔔 Waitlist တွင် User မရှိပါ")
                return
            sent = 0
            for user_id in wl:
                try:
                    await ctx.bot.send_message(
                        user_id,
                        "📢 *Admin ပြန်ရောက်ပါပြီ!*\n\nဝန်ဆောင်မှုများ ပြန်လည်ရယူနိုင်ပါပြီ 🎉",
                        parse_mode="Markdown"
                    )
                    sent += 1
                except:
                    pass
            clear_waitlist()
            await q.message.edit_reply_markup(reply_markup=admin_kb())
            await q.message.reply_text(f"✅ {sent} ယောက်ကို အကြောင်းကြားပြီ | Waitlist ရှင်းပြီ")

        elif act == "stats_summary":
            total_users, p_ord, d_ord, p_pt = get_stats()
            waitlist = len(get_waitlist())
            away = "ON 🔴" if get_away_mode() else "OFF 🟢"
            await q.message.reply_text(
                f"📊 *Bot Statistics*\n{'━'*20}\n"
                f"👥 Total Users: *{total_users}*\n"
                f"📋 Pending Orders: *{p_ord}*\n"
                f"✅ Completed Orders: *{d_ord}*\n"
                f"💰 Pending Pt Req: *{p_pt}*\n"
                f"🔔 Waitlist: *{waitlist}*\n"
                f"😴 Away Mode: *{away}*",
                parse_mode="Markdown"
            )

        elif act == "orders":
            rows = pending_orders()
            if not rows:
                await q.message.reply_text("✅ Pending Orders မရှိပါ")
                return
            for r in rows:
                oid, ruid, pid, pname, pts, gmail, pwd, twofa, st, ts = r
                await q.message.reply_text(
                    f"📋 *Order #{oid}*\n{'─'*18}\n"
                    f"👤 ID: `{ruid}`\n"
                    f"📦 {pname}  |  {pts} pts\n"
                    f"📧 `{gmail}`\n"
                    f"🔒 `{pwd}`\n"
                    f"🔐 `{twofa}`\n"
                    f"🕐 {ts_fmt(ts)}",
                    parse_mode="Markdown",
                    reply_markup=order_action_kb(oid)
                )

        elif act == "pts":
            rows = pending_pts()
            if not rows:
                await q.message.reply_text("✅ Pending Point Requests မရှိပါ")
                return
            for r in rows:
                rid, ruid, pts, price, fid, note, st, ts = r
                await ctx.bot.send_photo(
                    q.message.chat_id,
                    photo=fid,
                    caption=(
                        f"💰 *Point Request #{rid}*\n"
                        f"👤 ID: `{ruid}`\n"
                        f"💎 {pts} pts  |  {price:,} ကျပ်\n"
                        f"🕐 {ts_fmt(ts)}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=pts_action_kb(rid, ruid, pts)
                )

        elif act == "manual":
            rows = pending_manual_reqs()
            if not rows:
                await q.message.reply_text("✅ Manual Requests မရှိပါ")
                return
            for r in rows:
                mid, ruid, name, bal, note, ts = r
                await q.message.reply_text(
                    f"🙋 *Manual Request #{mid}*\n{'─'*18}\n"
                    f"👤 [{name}](tg://user?id={ruid})  `{ruid}`\n"
                    f"💰 Balance: {bal} pts\n"
                    f"📝 {note}\n"
                    f"🕐 {ts_fmt(ts)}",
                    parse_mode="Markdown",
                    reply_markup=manual_action_kb(mid, ruid)
                )

        elif act == "pts_all":
            rows = all_pt_requests(30)
            if not rows:
                await q.message.reply_text("📊 Point Requests မရှိသေးပါ")
                return
            ST = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
            lines = [
                f"{ST.get(st,'?')} #{rid} | {name or ruid} | {pts}pts | {price:,}ကျပ် | {ts_fmt(ts)}"
                for rid, ruid, name, pts, price, st, ts in rows
            ]
            text = "📊 *Point Request History (30)*\n" + "\n".join(lines)
            if len(text) > 4000:
                text = text[:4000] + "\n..."
            await q.message.reply_text(text, parse_mode="Markdown")

        elif act == "users":
            users = all_users()
            if not users:
                await q.message.reply_text("👥 Users မရှိသေးပါ")
                return
            lines = "\n".join(
                f"{'─'*18}\n👤 [{n}](tg://user?id={i})  `{i}`\n💰 {p} pts"
                for i, u, n, p in users
            )
            text = f"👥 *Users ({len(users)})*\n{lines}"
            if len(text) > 4000:
                text = text[:4000] + "\n..."
            await q.message.reply_text(text, parse_mode="Markdown")

        elif act == "addpts":
            pending_admin_actions[uid] = {"type": "addpts_uid"}
            await q.message.reply_text(
                "➕ *Points ထည့်/နုတ်*\n\n"
                "User ID ထည့်ပါ —\n"
                "_( /addpts uid amount လဲ သုံးနိုင်သည် )_",
                parse_mode="Markdown"
            )

        elif act == "broadcast":
            pending_admin_actions[uid] = {"type": "broadcast"}
            all_ids = get_all_user_ids()
            await q.message.reply_text(
                f"📢 *Broadcast Message*\n\n"
                f"👥 {len(all_ids)} ယောက်ထံ ပို့မည်\n\n"
                f"ပို့မည့် Message ကို ရိုက်ပါ ↓\n\n"
                f"_(Markdown format အသုံးပြုနိုင်သည် — *bold* `code` )_",
                parse_mode="Markdown"
            )
        return

    # ── Order Complete ────────────────────────────────
    if data.startswith("done:"):
        if not is_admin(uid):
            return
        oid = int(data.split(":")[1])
        row = get_order(oid)
        if not row:
            await q.message.reply_text("❌ Order မတွေ့ပါ")
            return
        pending_admin_actions[uid] = {"type": "link", "oid": oid, "ruid": row[1], "gmail": row[5], "pts": row[4]}
        await q.message.reply_text(
            f"✅ *Order #{oid}*\n"
            f"📧 Gmail: `{row[5]}`\n\n"
            f"Google AI Pro Link ကို ဒီမှာ ပို့ပါ ↓\n"
            f"_(Bot မှ User ထံ တိုက်ရိုက် ပို့ပေးမည်)_",
            parse_mode="Markdown"
        )
        return

    # ── Reject menu ───────────────────────────────────
    if data.startswith("rj_menu:"):
        if not is_admin(uid):
            return
        oid = int(data.split(":")[1])
        await q.message.reply_text(
            f"❌ *Order #{oid} — Reject အကြောင်းရင်း ရွေးပါ* ↓",
            parse_mode="Markdown",
            reply_markup=reject_kb(oid)
        )
        return

    if data.startswith("rj_back:"):
        if not is_admin(uid):
            return
        oid = int(data.split(":")[1])
        await q.message.edit_reply_markup(reply_markup=order_action_kb(oid))
        return

    if data.startswith("rj:"):
        if not is_admin(uid):
            return
        parts  = data.split(":")
        reason = parts[1]
        oid    = int(parts[2])
        row    = get_order(oid)
        if not row:
            return
        ruid, pts = row[1], row[4]
        set_order_status(oid, "rejected")
        add_pts(ruid, pts)
        MSGS = {
            "2fa":  (
                f"❌ *Order ဖျက်သိမ်း + Points ပြန်အမ်းပြီ*\n\n"
                f"📌 အကြောင်းရင်း — 2FA Key မမှန်ကန်ပါ\n\n"
                f"[2FA ဖွင့်နည်း Video]({LINK_2FA}) ကို အဆုံးထိ ကြည့်ပြီး ပြန်တင်ပါ\n\n"
                f"💰 {pts} pts ပြန်ထည့်ပြီ"
            ),
            "pay": (
                f"❌ *Order ဖျက်သိမ်း + Points ပြန်အမ်းပြီ*\n\n"
                f"📌 အကြောင်းရင်း — Payment Profile မပိတ်သောကြောင့်\n\n"
                f"[ပိတ်နည်း Video]({LINK_PAYMENT}) ကြည့်ပြီး ပြန်တင်ပါ\n\n"
                f"💰 {pts} pts ပြန်ထည့်ပြီ"
            ),
            "fam": (
                f"❌ *Order ဖျက်သိမ်း + Points ပြန်အမ်းပြီ*\n\n"
                f"📌 အကြောင်းရင်း — Family Group မထွက်သောကြောင့်\n\n"
                f"[ထွက်နည်း Video]({LINK_FAMILY}) ကြည့်ပြီး ပြန်တင်ပါ\n\n"
                f"💰 {pts} pts ပြန်ထည့်ပြီ"
            ),
            "mail": (
                f"❌ *Order ဖျက်သိမ်း + Points ပြန်အမ်းပြီ*\n\n"
                f"📌 အကြောင်းရင်း — Gmail လိပ်စာ မမှန်ကန်ပါ\n\n"
                f"မှန်ကန်သော Gmail ဖြင့် ပြန်တင်ပါ\n\n"
                f"💰 {pts} pts ပြန်ထည့်ပြီ"
            ),
            "other": (
                f"❌ *Order ဖျက်သိမ်း + Points ပြန်အမ်းပြီ*\n\n"
                f"📌 ပြဿနာတစ်ခုခုကြောင့် မဆောင်ရွက်နိုင်ပါ\n\n"
                f"📞 @{ADMIN_USERNAME} ထံ ဆက်သွယ်ပါ\n\n"
                f"💰 {pts} pts ပြန်ထည့်ပြီ"
            ),
        }
        try:
            await ctx.bot.send_message(ruid, MSGS.get(reason, MSGS["other"]), parse_mode="Markdown")
        except:
            pass
        try:
            await q.message.edit_reply_markup()
        except:
            pass
        await q.message.reply_text(f"❌ Order #{oid} Rejected | {pts} pts refund ပြီ")
        return

    # ── Points approve/reject ─────────────────────────
    if data.startswith("pts:"):
        if not is_admin(uid):
            return
        parts = data.split(":")
        act, rid, ruid = parts[1], int(parts[2]), int(parts[3])
        amt = int(parts[4]) if len(parts) > 4 else 0
        if act == "ok":
            add_pts(ruid, amt)
            set_pt_status(rid, "approved")
            new_bal = get_pts(ruid)
            try:
                await ctx.bot.send_message(
                    ruid,
                    f"✅ *{amt} Points ထည့်ပြီ!*\n\n"
                    f"💰 လက်ကျန် Balance: *{new_bal} pts*\n\n"
                    f"'🛒 Order တင်' ကို နှိပ်ပြီး AI Pro ဝယ်နိုင်ပြီ 🎉",
                    parse_mode="Markdown"
                )
            except:
                pass
            try:
                await q.message.edit_reply_markup()
            except:
                pass
            await q.message.reply_text(f"✅ {amt} pts → User {ruid} ထည့်ပြီ | Balance: {new_bal} pts")
        elif act == "no":
            set_pt_status(rid, "rejected")
            try:
                await ctx.bot.send_message(
                    ruid,
                    f"❌ *Point Request ပယ်ဖျက်ခြင်း*\n\n"
                    f"Screenshot မဆီလျော်သောကြောင့် ပယ်ဖျက်ပြီ\n"
                    f"📞 @{ADMIN_USERNAME} ထံ ဆက်သွယ်ပါ",
                    parse_mode="Markdown"
                )
            except:
                pass
            try:
                await q.message.edit_reply_markup()
            except:
                pass
            await q.message.reply_text(f"❌ Point Request #{rid} Rejected")
        return

    # ── Manual request ────────────────────────────────
    if data.startswith("man:"):
        if not is_admin(uid):
            return
        parts = data.split(":")
        act, mid, ruid = parts[1], int(parts[2]), int(parts[3])
        if act == "done":
            set_manual_status(mid, "resolved")
            try:
                await ctx.bot.send_message(ruid, f"✅ *Manual Request ကိုင်တွယ်ပြီ*\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown")
            except:
                pass
            try:
                await q.message.edit_reply_markup()
            except:
                pass
            await q.message.reply_text(f"✅ Manual Request #{mid} Resolved")
        elif act == "no":
            set_manual_status(mid, "rejected")
            try:
                await ctx.bot.send_message(ruid, f"❌ Request ဆောင်ရွက်မပေးနိုင်ပါ\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown")
            except:
                pass
            try:
                await q.message.edit_reply_markup()
            except:
                pass
            await q.message.reply_text(f"❌ Manual Request #{mid} Rejected")
        return

    # ── Buy flow callbacks ────────────────────────────
    if data.startswith("buyplan:"):
        return await cb_buy_plan_select(update, ctx)
    if data.startswith("plan:"):
        return await cb_plan(update, ctx)
    if data.startswith("pkg:") or data == "buyplan_back":
        return await cb_pkg(update, ctx)

    if data == "cancel":
        ctx.user_data.clear()
        pending_admin_actions.pop(uid, None)
        await q.message.reply_text("❌ Cancel ပြုလုပ်ပြီ", reply_markup=MAIN_KB)
        return MAIN_MENU

# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════
def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    init_db()
    keep_alive()

    app = Application.builder().token(BOT_TOKEN).post_init(setup_bot_commands).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^💰 Points ကြည့်$"),  h_points),
                MessageHandler(filters.Regex("^🛒 Order တင်$"),     h_start_order),
                MessageHandler(filters.Regex("^💎 Points ဝယ်$"),    h_buy),
                MessageHandler(filters.Regex("^📋 Orders ကြည့်$"),  h_my_orders),
                MessageHandler(filters.Regex("^📖 လမ်းညွှန်$"),    h_guide),
                MessageHandler(filters.Regex("^📞 Support$"),       h_support),
                CallbackQueryHandler(global_cb),
            ],
            ORDER_PLAN:     [CallbackQueryHandler(global_cb)],
            ORDER_GMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, h_gmail)],
            ORDER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_password)],
            ORDER_2FA:      [MessageHandler(filters.TEXT & ~filters.COMMAND, h_2fa)],
            ORDER_CONFIRM:  [CallbackQueryHandler(global_cb)],
            BUY_PLAN_SELECT:[CallbackQueryHandler(global_cb)],
            BUY_PKG:        [CallbackQueryHandler(global_cb)],
            BUY_SCREENSHOT: [
                MessageHandler(filters.PHOTO, h_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text(
                    "📸 *Screenshot ပုံကိုသာ ပို့ပါ!*\nText မဟုတ်ဘဲ ပုံကို Gallery မှ ရွေးပြီး ပို့ပါ",
                    parse_mode="Markdown"
                )),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", h_cancel),
            CallbackQueryHandler(global_cb, pattern="^cancel$"),
        ],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CommandHandler("addpts", cmd_addpts))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler), group=1)
    app.add_handler(CallbackQueryHandler(global_cb))

    logging.info("✅ Pixel Verification Bot v2.0 started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
