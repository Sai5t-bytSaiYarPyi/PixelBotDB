#!/usr/bin/env python3
"""Pixel Verification Bot — Upgraded Edition"""

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
BOT_TOKEN      = os.getenv("BOT_TOKEN")

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
    {"pts": 160, "price": 15000, "discount": 0,    "profit": 7800,  "label": "160 Points — 15,000 ကျပ် (ပုံမှန်ဈေး)"},
    {"pts": 320, "price": 29500, "discount": 500,  "profit": 15100, "label": "320 Points — 29,500 ကျပ် (500 ကျပ် သက်သာ)"},
    {"pts": 480, "price": 44000, "discount": 1000, "profit": 22400, "label": "480 Points — 44,000 ကျပ် (1,000 ကျပ် သက်သာ)"},
]
PACKAGES_NOCARD = [
    {"pts": 190, "price": 17000, "discount": 0,    "profit": 8450,  "label": "190 Points — 17,000 ကျပ် (ပုံမှန်ဈေး)"},
    {"pts": 380, "price": 33500, "discount": 500,  "profit": 16400, "label": "380 Points — 33,500 ကျပ် (500 ကျပ် သက်သာ)"},
    {"pts": 570, "price": 50000, "discount": 1000, "profit": 24350, "label": "570 Points — 50,000 ကျပ် (1,000 ကျပ် သက်သာ)"},
]

PLANS = [
    {"id": "card",   "name": "ကိုယ်ပိုင်ကတ် ရှိသူ", "desc": "Credit Card ဖြင့် Google Billing မှတ်ပုံတင်ထားသောသူများ"},
    {"id": "nocard", "name": "ကိုယ်ပိုင်ကတ် မရှိသူ", "desc": "Credit Card မရှိဘဲ ဝယ်ယူလိုသောသူများ"},
]

# ══════════════════════════════════════════════════════
#  STATES
# ══════════════════════════════════════════════════════
(
    MAIN_MENU,
    ORDER_PLAN, ORDER_GMAIL, ORDER_PASSWORD, ORDER_2FA,
    BUY_PLAN_SELECT, BUY_PKG, BUY_SCREENSHOT,
) = range(8)

DB = "bot.db"
pending_admin_actions: dict = {}

# ══════════════════════════════════════════════════════
#  DATABASE + AUTO-MIGRATION
# ══════════════════════════════════════════════════════
def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                uid INTEGER PRIMARY KEY, username TEXT,
                name TEXT, points INTEGER DEFAULT 0, joined TEXT
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, 
                plan_id TEXT, plan_name TEXT, pts INTEGER, gmail TEXT, 
                password TEXT, twofa TEXT, status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS pt_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, 
                pts INTEGER, price INTEGER, screenshot TEXT, note TEXT DEFAULT '',
                status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS manual_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, 
                note TEXT, status TEXT DEFAULT 'pending', ts TEXT
            );
            CREATE TABLE IF NOT EXISTS waitlist (uid INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, val TEXT);
        """)
        # Initialize away mode if not exists
        c.execute("INSERT OR IGNORE INTO settings (key, val) VALUES ('admin_away', '0')")
    logging.info("✅ DB Initialized")

def _db(): return sqlite3.connect(DB)
def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def ts_fmt(ts): return ts[:16] if ts else "-"

# --- Settings & Waitlist Functions ---
def get_away_mode() -> bool:
    with _db() as c:
        r = c.execute("SELECT val FROM settings WHERE key='admin_away'").fetchone()
        return r[0] == '1' if r else False

def set_away_mode(state: bool):
    with _db() as c:
        c.execute("UPDATE settings SET val=? WHERE key='admin_away'", ('1' if state else '0',))

def add_waitlist(uid):
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO waitlist (uid) VALUES (?)", (uid,))

def get_waitlist():
    with _db() as c:
        return [r[0] for r in c.execute("SELECT uid FROM waitlist").fetchall()]

def clear_waitlist():
    with _db() as c:
        c.execute("DELETE FROM waitlist")

# --- User & Order Functions ---
def ensure_user(uid, username, name):
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,0,?)", (uid, username, name, now()))

def get_pts(uid):
    with _db() as c:
        r = c.execute("SELECT points FROM users WHERE uid=?", (uid,)).fetchone()
    return r[0] if r else 0

def get_user_info(uid):
    with _db() as c:
        return c.execute("SELECT uid,username,name,points FROM users WHERE uid=?", (uid,)).fetchone()

def add_pts(uid, n):
    with _db() as c:
        c.execute("UPDATE users SET points=points+? WHERE uid=?", (n, uid))

def new_order(uid, plan_id, plan_name, pts, gmail, pwd, twofa):
    with _db() as c:
        cur = c.execute(
            "INSERT INTO orders(uid,plan_id,plan_name,pts,gmail,password,twofa,ts) VALUES(?,?,?,?,?,?,?,?)",
            (uid, plan_id, plan_name, pts, gmail, pwd, twofa, now()))
        return cur.lastrowid

def get_order(oid):
    with _db() as c: return c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()

def set_order_status(oid, status):
    with _db() as c: c.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))

def my_orders(uid):
    with _db() as c:
        return c.execute("SELECT id,plan_name,pts,status,ts FROM orders WHERE uid=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()

def new_pt_req(uid, pts, price, fid):
    with _db() as c:
        return c.execute("INSERT INTO pt_requests(uid,pts,price,screenshot,ts) VALUES(?,?,?,?,?)", (uid, pts, price, fid, now())).lastrowid

def set_pt_status(rid, status):
    with _db() as c: c.execute("UPDATE pt_requests SET status=? WHERE id=?", (status, rid))

def pending_orders():
    with _db() as c: return c.execute("SELECT * FROM orders WHERE status='pending' ORDER BY id DESC").fetchall()

def pending_pts():
    with _db() as c: return c.execute("SELECT * FROM pt_requests WHERE status='pending' ORDER BY id DESC").fetchall()

def all_pt_requests(limit=30):
    with _db() as c:
        return c.execute("SELECT r.id,r.uid,u.name,r.pts,r.price,r.status,r.ts FROM pt_requests r LEFT JOIN users u ON r.uid=u.uid ORDER BY r.id DESC LIMIT ?", (limit,)).fetchall()

def pending_manual_reqs():
    with _db() as c:
        return c.execute("SELECT m.id,m.uid,u.name,u.points,m.note,m.ts FROM manual_requests m LEFT JOIN users u ON m.uid=u.uid WHERE m.status='pending' ORDER BY m.id DESC").fetchall()

def set_manual_status(mid, status):
    with _db() as c: c.execute("UPDATE manual_requests SET status=? WHERE id=?", (status, mid))

def all_users():
    with _db() as c: return c.execute("SELECT uid,username,name,points FROM users").fetchall()

# ══════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════
MAIN_KB = ReplyKeyboardMarkup([
    ["💰 Points ကြည့်",  "🛒 Order တင်"],
    ["💎 Points ဝယ်",   "📋 Orders ကြည့်"],
    ["📖 လမ်းညွှန်",    "📞 Support"],
], resize_keyboard=True)

def plan_kb():
    rows = [[InlineKeyboardButton(f"{'💳' if p['id']=='card' else '👤'} {p['name']}", callback_data=f"plan:{p['id']}")] for p in PLANS]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def buy_plan_kb():
    """For selecting card vs nocard when buying points"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ကိုယ်ပိုင်ကတ် ရှိသူ", callback_data="buyplan:card")],
        [InlineKeyboardButton("👤 ကိုယ်ပိုင်ကတ် မရှိသူ", callback_data="buyplan:nocard")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def pkg_kb(plan_type):
    packages = PACKAGES_CARD if plan_type == "card" else PACKAGES_NOCARD
    rows = [[InlineKeyboardButton(p["label"], callback_data=f"pkg:{plan_type}:{p['pts']}:{p['price']}")] for p in packages]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def admin_kb():
    is_away = get_away_mode()
    away_text = "🟢 Away Mode: OFF (လုပ်ငန်းလည်ပတ်နေသည်)" if not is_away else "🛑 Away Mode: ON (ပိတ်ထားသည်)"
    waitlist_count = len(get_waitlist())
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Pending Orders", callback_data="adm:orders")],
        [InlineKeyboardButton("💰 Pending Point Requests", callback_data="adm:pts")],
        [InlineKeyboardButton("🙋 Manual Point Requests", callback_data="adm:manual")],
        [InlineKeyboardButton(f"👥 All Users & 📊 History", callback_data="adm:stats_menu")],
        [InlineKeyboardButton("➕ Points ထည့် / နုတ် (Bot)", callback_data="adm:addpts")],
        [InlineKeyboardButton(away_text, callback_data="adm:toggle_away")],
        [InlineKeyboardButton(f"📢 Notify Waitlist ({waitlist_count} ယောက်)", callback_data="adm:notify_waitlist")],
    ])

def stats_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Point Request History", callback_data="adm:pts_all")],
        [InlineKeyboardButton("👥 All Users Info", callback_data="adm:users")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="adm:back")]
    ])

def order_action_kb(oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Complete", callback_data=f"done:{oid}"),
         InlineKeyboardButton("❌ Reject",   callback_data=f"rj_menu:{oid}")],
    ])

def reject_kb(oid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 2FA မမှန်ကန်", callback_data=f"rj:2fa:{oid}")],
        [InlineKeyboardButton("💳 Payment Profile မပိတ်", callback_data=f"rj:pay:{oid}")],
        [InlineKeyboardButton("👨‍👩‍👧 Family Group မထွက်", callback_data=f"rj:fam:{oid}")],
        [InlineKeyboardButton("📧 Gmail မမှန်ကန်", callback_data=f"rj:mail:{oid}")],
        [InlineKeyboardButton("❓ အခြား", callback_data=f"rj:other:{oid}")],
    ])

def pts_action_kb(rid, uid, pts):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Approve +{pts}pts", callback_data=f"pts:ok:{rid}:{uid}:{pts}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"pts:no:{rid}:{uid}:0")],
    ])

def manual_action_kb(mid, ruid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ကိုင်တွယ်ပြီး", callback_data=f"man:done:{mid}:{ruid}"),
         InlineKeyboardButton("❌ ပယ်ဖျက်", callback_data=f"man:no:{mid}:{ruid}")],
    ])

def is_admin(uid): return uid in ADMIN_IDS

# ══════════════════════════════════════════════════════
#  SETUP BOT COMMANDS (RESTRICTED MENU)
# ══════════════════════════════════════════════════════
async def setup_bot_commands(application: Application):
    # Default Menu for all normal users
    await application.bot.set_my_commands(
        [("start", "Bot ကို စတင်ရန်"), ("cancel", "လက်ရှိ လုပ်ဆောင်နေတာကို ဖျက်ရန်")], 
        scope=BotCommandScopeDefault()
    )
    # Admin Menu exclusively for admins
    for aid in ADMIN_IDS:
        try:
            await application.bot.set_my_commands(
                [("start", "Bot ကို စတင်ရန်"), ("cancel", "လုပ်ဆောင်ချက် ဖျက်ရန်"), ("admin", "🔧 Admin Panel (Admin Only)")], 
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
    except: return False

async def must_join(update: Update, bot) -> bool:
    uid = update.effective_user.id
    if await check_member(bot, uid): return True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Join ဖို့ ဒီမှာ နှိပ်ပါ", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Join ပြီးပြီ", callback_data="check_join")],
    ])
    msg = "⚠️ *Bot သုံးရန် Channel Join လိုအပ်ပါသည်*\n\n📢 Channel သို့ Join ဖြစ်ပြီးမှ Bot ဆက်သုံးနိုင်ပါမည်"
    if update.message: await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    elif update.callback_query: await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    return False

# ══════════════════════════════════════════════════════
#  ADMIN TEXT HANDLER
# ══════════════════════════════════════════════════════
async def admin_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return
    action = pending_admin_actions.get(uid)
    if not action: return

    text = update.message.text.strip()
    atype = action.get("type")

    if atype == "link":
        oid, ruid, gmail = action["oid"], action["ruid"], action["gmail"]
        set_order_status(oid, "completed")
        msg = (
            f"✅ *အားလုံးပြီးစီးပါပြီ!*\n\n"
            f"🎁 *Google AI Pro ၁၂-လ Trial Link (အောက်ပါ Link ကို တစ်ချက်နှိပ်ပြီး Copy ကူးပါ)* —\n\n"
            f"`{text}`\n\n"
            f"✉️ Gmail: `{gmail}`\n\n"
            f"⚠️ *ဤ Link ကို အထက်ပါ Gmail အတွက်သာ အသုံးပြုနိုင်ပါသည်*\n"
            f"Gmail မမှန်ပါက _'Can't redeem offer'_ ပြဿနာ ကြုံနိုင်သည်\n\n"
            f"📞 အကူအညီလိုပါက — @{ADMIN_USERNAME}"
        )
        try:
            await ctx.bot.send_message(ruid, msg, parse_mode="Markdown", disable_web_page_preview=True)
            await update.message.reply_text(f"✅ Order #{oid} complete\n👤 User `{ruid}` ထံ Link ပို့ပြီ ✔️", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Link ပို့မရပါ (uid:{ruid})\nError: {e}\n\nOrder #{oid} complete ဆင် မှတ်ပြီ")
        pending_admin_actions.pop(uid, None)

    elif atype == "addpts_uid":
        try: tuid = int(text)
        except ValueError: await update.message.reply_text("❌ User ID မှာ number သာ ထည့်ပါ"); return
        info = get_user_info(tuid)
        if not info:
            await update.message.reply_text(f"❌ User `{tuid}` DB တွင် မတွေ့ပါ", parse_mode="Markdown"); return
        _, uname, uname_full, bal = info
        pending_admin_actions[uid] = {"type": "addpts_amt", "tuid": tuid, "name": uname_full, "bal": bal}
        await update.message.reply_text(
            f"👤 *{uname_full}* (`{tuid}`)\n💰 လက်ကျန် — *{bal} pts*\n\n"
            f"ထည့်/နုတ်မည့် Amount ထည့်ပါ\n_(ဥပမာ — `160` ထည့်ရန် / `-160` နုတ်ရန်)_", parse_mode="Markdown")

    elif atype == "addpts_amt":
        try: amt = int(text)
        except ValueError: await update.message.reply_text("❌ Number သာ ထည့်ပါ"); return
        tuid, tname, old_bal = action["tuid"], action["name"], action["bal"]
        add_pts(tuid, amt)
        new_bal = get_pts(tuid)
        verb = "ထည့်" if amt > 0 else "နုတ်"

        await update.message.reply_text(
            f"✅ *{tname}* (`{tuid}`)\n{'➕' if amt>0 else '➖'} {abs(amt)} pts {verb}ပြီ\n💰 {old_bal} → *{new_bal} pts*", parse_mode="Markdown")
        
        note = f"✅ *Admin မှ {abs(amt)} Points ထည့်ပေးပြီ!*\n💰 Balance: *{new_bal} pts*" if amt > 0 else f"ℹ️ Admin မှ {abs(amt)} pts နုတ်ခဲ့ပါသည်\n💰 Balance: *{new_bal} pts*"
        try: await ctx.bot.send_message(tuid, note, parse_mode="Markdown")
        except: pass
        pending_admin_actions.pop(uid, None)

# ══════════════════════════════════════════════════════
#  MAIN COMMANDS
# ══════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure_user(u.id, u.username or "", u.full_name)
    if not await must_join(update, ctx.bot): return MAIN_MENU
    await update.message.reply_text(
        f"👋 မင်္ဂလာပါ *{u.first_name}*!\n\n🤖 *Pixel Verification Bot* မှ ကြိုဆိုပါသည်\n📌 အောက်မှ Menu ကို ရွေးချယ်ပါ —",
        parse_mode="Markdown", reply_markup=MAIN_KB)
    return MAIN_MENU

async def cmd_addpts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    args = ctx.args
    if not args:
        pending_admin_actions[update.effective_user.id] = {"type": "addpts_uid"}
        await update.message.reply_text("➕ *Points ထည့်/နုတ် (Step-by-step)*\n\nUser ID ထည့်ပါ —", parse_mode="Markdown")
        return
    if len(args) < 2:
        await update.message.reply_text("❌ Format: `/addpts <uid> <amount>`", parse_mode="Markdown"); return
    try: tuid, amt = int(args[0]), int(args[1])
    except ValueError: await update.message.reply_text("❌ uid နှင့် amount မှာ number ဖြစ်ရမည်"); return
    info = get_user_info(tuid)
    if not info: await update.message.reply_text(f"❌ User `{tuid}` မတွေ့ပါ", parse_mode="Markdown"); return
    _, uname, uname_full, old_bal = info
    add_pts(tuid, amt)
    new_bal = get_pts(tuid)
    verb = "ထည့်" if amt > 0 else "နုတ်"
    await update.message.reply_text(f"✅ *{uname_full}* (`{tuid}`)\n{'➕' if amt>0 else '➖'} {abs(amt)} pts {verb}ပြီ\n💰 {old_bal} → *{new_bal} pts*", parse_mode="Markdown")
    note = f"✅ *Admin မှ {abs(amt)} Points ထည့်ပေးပြီ!*\n💰 Balance: *{new_bal} pts*" if amt > 0 else f"ℹ️ Admin မှ {abs(amt)} pts နုတ်ခဲ့ပါသည်\n💰 Balance: *{new_bal} pts*"
    try: await ctx.bot.send_message(tuid, note, parse_mode="Markdown")
    except: pass

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("🔧 *Admin Panel*", parse_mode="Markdown", reply_markup=admin_kb())

# ══════════════════════════════════════════════════════
#  MAIN MENU HANDLERS
# ══════════════════════════════════════════════════════
async def h_points(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot): return MAIN_MENU
    pts = get_pts(update.effective_user.id)
    await update.message.reply_text(f"━━━━━━━━━━━━━━━━━\n💰 *Points Balance*\n━━━━━━━━━━━━━━━━━\n\n🎯  *{pts} pts*\n\n💎 Points ဝယ်ရန် Menu မှ ရွေးပါ", parse_mode="Markdown")

async def h_guide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot): return MAIN_MENU
    text = (
        "📖 *Pixel Verification လမ်းညွှန်* 😇\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎥 YouTube သင်ခန်းစာ — {YOUTUBE_GUIDE}\n\n"
        "①  Google အကောင့် ပုံမှန်ဖြစ်ရမည်၊ locked/restricted မဖြစ်ရ\n"
        "②  Google Payments — payment profile အဟောင်းများ ဖျက်ပစ်ပါ\n"
        "③  Family Group တွင် မပါဝင်စေရ\n"
        "④  Gemini / Google One Subscription မရှိစေရ\n"
        "⑤  Two-step verification + Authenticator 2FA ပြုလုပ်ထားရမည်\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📹 2FA ပြုလုပ်နည်း — {LINK_2FA}\n⚠️ *မဖြစ်မနေ ကြည့်ပါ!* ⚠️\n\n"
        "🔗 *Links*\n• https://myaccount.google.com/signinoptions/twosv\n• https://payments.google.com\n• https://families.google.com/families"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def h_my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await must_join(update, ctx.bot): return MAIN_MENU
    rows = my_orders(update.effective_user.id)
    if not rows: await update.message.reply_text("📋 Orders မရှိသေးပါ"); return
    ST = {"pending": "⏳ ဆောင်ရွက်နေဆဲ", "completed": "✅ ပြီးစီးပြီ", "rejected": "❌ ပယ်ဖျက်ပြီ"}
    lines = [f"{'─'*22}\n🧾 Order #{oid}  |  {ts_fmt(ts)}\n📦 {pname}\n💰 {pts} pts\n🔖 {ST.get(st,st)}" for oid, pname, pts, st, ts in rows]
    await update.message.reply_text(f"📋 *Your Orders*\n{'─'*22}\n" + "\n".join(lines), parse_mode="Markdown")

async def h_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📞 *Support*\n\n👤 @{ADMIN_USERNAME}\n🔗 {SUPPORT_LINK}", parse_mode="Markdown")

# ══════════════════════════════════════════════════════
#  ORDER FLOW
# ══════════════════════════════════════════════════════
async def h_start_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if get_away_mode():
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Admin လာလျှင် အသိပေးပါ", callback_data="waitlist_add")]])
        await update.message.reply_text("⚠️ ယခု Admin မအားသေးပါ။\nAdmin ပြန်ရောက်လာချိန် အသိပေးချက်ရယူရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။", reply_markup=kb)
        return MAIN_MENU
    if not await must_join(update, ctx.bot): return MAIN_MENU
    plan_lines = "\n\n".join(f"{'💳' if p['id']=='card' else '👤'} *{p['name']}*\n   {p['desc']}" for p in PLANS)
    await update.message.reply_text(f"🛒 *Plan ရွေးချယ်ပါ*\n{'━'*22}\n\n{plan_lines}", parse_mode="Markdown", reply_markup=plan_kb())
    return ORDER_PLAN

async def cb_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancel": await q.message.reply_text("❌ Cancel", reply_markup=MAIN_KB); return MAIN_MENU
    plan_id = q.data.split(":")[1]
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan: return MAIN_MENU
    ctx.user_data["selected_plan"] = plan_id
    await q.message.reply_text(
        f"🛒 *Order လက်ခံပြီ* — _{plan['name']} အတွက်_\n\n{'━'*22}\n"
        f"① Payment Profile ပိတ်ပါ ↳ [Video]({LINK_PAYMENT})\n"
        f"② Family Group ထွက်ပါ ↳ [Video]({LINK_FAMILY})\n"
        f"⚠️ New Gmail ရှောင်ပါ ↳ [Video]({LINK_NEW_MAIL})\n\n{'━'*22}\n"
        f"📧 *အဆင့် ၁ — Gmail လိပ်စာ ရိုက်ပါ*", parse_mode="Markdown", disable_web_page_preview=True)
    return ORDER_GMAIL

async def h_gmail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["gmail"] = update.message.text.strip()
    await update.message.reply_text(f"📧 `{ctx.user_data['gmail']}`\n\n🔒 *အဆင့် ၂ — Password ရိုက်ပါ*", parse_mode="Markdown")
    return ORDER_PASSWORD

async def h_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["password"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await update.message.reply_text(
        f"🔒 Password ✓\n\n{'━'*22}\n🔐 *အဆင့် ၃ — 2FA Key ရိုက်ပါ*\n\n_ဥပမာ — zad6 65hd 5fp6 kjzy mrfc cenj_\n\n"
        f"📹 [2FA ဖွင့်နည်း — မဖြစ်မနေ ကြည့်ပါ!]({LINK_2FA})\n\n", parse_mode="Markdown")
    return ORDER_2FA

async def h_2fa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    twofa = update.message.text.strip()
    if twofa.lower() == "skip": twofa = "N/A"
    u = update.effective_user
    
    selected_plan_type = ctx.user_data.get("selected_plan")
    
    # Plan မရွေးထားရင် အစကပြန်စခိုင်းမည်
    if not selected_plan_type:
        await update.message.reply_text("❌ Order information incomplete. Please start again.", reply_markup=MAIN_KB)
        return MAIN_MENU
        
    plan_name = next((p["name"] for p in PLANS if p["id"] == selected_plan_type), "Unknown Plan")
    
    # Plan အမျိုးအစားပေါ်မူတည်၍ ဖြတ်မည့် Points ကို သတ်မှတ်ခြင်း (Card=160, NoCard=190)
    cost_pts = 160 if selected_plan_type == "card" else 190
    
    # User ၏ လက်ရှိ Points Balance ကို စစ်ဆေးခြင်း
    current_bal = get_pts(u.id)
    if current_bal < cost_pts:
        await update.message.reply_text(
            f"❌ *Points မလုံလောက်ပါ!*\n\n"
            f"လိုအပ်သော Points: {cost_pts} pts\n"
            f"လက်ရှိ Balance: {current_bal} pts\n\n"
            f"💎 Menu မှ 'Points ဝယ်' ကိုနှိပ်ပြီး အရင်ဝယ်ယူပေးပါ။", 
            parse_mode="Markdown", reply_markup=MAIN_KB
        )
        ctx.user_data.clear()
        return MAIN_MENU

    # Points နုတ်ယူပြီး Order တင်ခြင်း
    add_pts(u.id, -cost_pts)
    oid = new_order(u.id, selected_plan_type, plan_name, cost_pts, ctx.user_data["gmail"], ctx.user_data["password"], twofa)
    
    await notify_admins(ctx.bot,
        f"🆕 *New Order #{oid}*\n{'─'*22}\n👤 [{u.full_name}](tg://user?id={u.id})  `{u.id}`\n"
        f"📦 {plan_name}  |  {cost_pts} pts\n📧 Gmail: `{ctx.user_data['gmail']}`\n"
        f"🔒 Password: `{ctx.user_data['password']}`\n🔐 2FA: `{twofa}`\n🕐 {now()}", markup=order_action_kb(oid))
    
    await update.message.reply_text(
        f"✅ *Order #{oid} တင်ပြီ!*\n\n📦 {plan_name}\n💰 {cost_pts} pts (နုတ်ယူပြီး)\n\n"
        f"⏳ Admin စစ်ဆေးနေပါသည် — ပြီးစီးလျှင် Bot မှ အကြောင်းကြားမည်\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown", reply_markup=MAIN_KB)
    
    ctx.user_data.clear()
    return MAIN_MENU

# ══════════════════════════════════════════════════════
#  BUY POINTS FLOW (NEW)
# ══════════════════════════════════════════════════════
async def h_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if get_away_mode():
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Admin လာလျှင် အသိပေးပါ", callback_data="waitlist_add")]])
        await update.message.reply_text("⚠️ ယခု Admin မအားသေးပါ။\nAdmin ပြန်ရောက်လာချိန် အသိပေးချက်ရယူရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။", reply_markup=kb)
        return MAIN_MENU
    if not await must_join(update, ctx.bot): return MAIN_MENU
    
    # ဤနေရာတွင် User ကို Card ရှိ/မရှိ အရင်မေးမည်
    await update.message.reply_text("💎 *Points ဝယ်ယူရန် အမျိုးအစား ရွေးချယ်ပါ*", parse_mode="Markdown", reply_markup=buy_plan_kb())
    return BUY_PLAN_SELECT

async def cb_buy_plan_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancel":
        await q.message.reply_text("❌ Cancelled", reply_markup=MAIN_KB); return MAIN_MENU
    
    plan_type = q.data.split(":")[1] # 'card' or 'nocard'
    ctx.user_data["selected_plan"] = plan_type
    
    await q.message.edit_text("💎 *Points Package ရွေးပါ*", parse_mode="Markdown", reply_markup=pkg_kb(plan_type))
    return BUY_PKG

async def cb_pkg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancel": await q.message.reply_text("❌ Cancel", reply_markup=MAIN_KB); return MAIN_MENU
    
    _, plan_type, pts, price = q.data.split(":")
    ctx.user_data["buy_pts"], ctx.user_data["buy_price"] = int(pts), int(price)
    
    await q.message.edit_text(
        f"💎 *{pts} Points = {int(price):,} ကျပ်*\n\n{'━'*22}\n"
        f"📱 *KPay* — `{KPAY_NO}`  👤 {KPAY_NAME}\n\n📱 *Wave Pay* — `{WAVE_NO}`  👤 {WAVE_NAME}\n\n{'━'*22}\n"
        f"⚠️ ငွေလွှဲပြေစာ Screenshot *အပြည့်အစုံ* ပို့ပါ\n\n📸 Screenshot ↓", parse_mode="Markdown")
    return BUY_SCREENSHOT

async def h_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ ဓာတ်ပုံ (Screenshot) သာ ပို့ပါ!")
        return BUY_SCREENSHOT
    u, fid = update.effective_user, update.message.photo[-1].file_id
    pts, price = ctx.user_data.get("buy_pts", 160), ctx.user_data.get("buy_price", 15000)
    rid = new_pt_req(u.id, pts, price, fid)
    
    await notify_admins(ctx.bot,
        f"💰 *New Point Request #{rid}*\n{'─'*22}\n👤 [{u.full_name}](tg://user?id={u.id})  `{u.id}`\n"
        f"💎 {pts} pts  |  💵 {price:,} ကျပ်\n🕐 {now()}", photo=fid, markup=pts_action_kb(rid, u.id, pts))
    
    await update.message.reply_text(
        f"✅ *Screenshot ပို့ပြီ! (Request #{rid})*\n\n💎 {pts} pts  |  💵 {price:,} ကျပ်\n\n"
        f"⏳ Admin စစ်ဆေးပြီး Points ထည့်ပေးမည်\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown", reply_markup=MAIN_KB)
    ctx.user_data.clear()
    return MAIN_MENU

async def h_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    pending_admin_actions.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Cancel", reply_markup=MAIN_KB)
    return MAIN_MENU

# ══════════════════════════════════════════════════════
#  GLOBAL CALLBACK
# ══════════════════════════════════════════════════════
async def global_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid, data = q.from_user.id, q.data

    # ── Waitlist ─────────────────────────────────────
    if data == "waitlist_add":
        add_waitlist(uid)
        await q.message.reply_text("✅ Admin ပြန်ရောက်လျှင် အကြောင်းကြားပေးပါမည်။")
        return

    # ── Channel join ─────────────────────────────────
    if data == "check_join":
        if await check_member(ctx.bot, uid):
            ensure_user(uid, q.from_user.username or "", q.from_user.full_name)
            await q.message.reply_text("✅ Join ပြီးပြီ! 🎉", reply_markup=MAIN_KB)
        else: await q.message.reply_text("❌ Channel ကို Join မဖြစ်သေးပါ ⚠️")
        return

    # ── Admin panel ──────────────────────────────────
    if data.startswith("adm:"):
        if not is_admin(uid): await q.message.reply_text("❌ Admin only!"); return
        act = data[4:]

        if act == "toggle_away":
            new_state = not get_away_mode()
            set_away_mode(new_state)
            await q.message.edit_reply_markup(reply_markup=admin_kb())
            await q.message.reply_text(f"✅ Away Mode သည် ယခုအခါ *{'ON' if new_state else 'OFF'}* ဖြစ်သွားပါပြီ။", parse_mode="Markdown")

        elif act == "notify_waitlist":
            waitlist_users = get_waitlist()
            if not waitlist_users:
                await q.message.reply_text("Waitlist တွင် User မရှိပါ။")
                return
            for user_id in waitlist_users:
                try: await ctx.bot.send_message(user_id, "📢 *Admin ပြန်ရောက်ပါပြီ။* ဝန်ဆောင်မှုများ ပြန်လည်ရယူနိုင်ပါပြီ။", parse_mode="Markdown")
                except: pass
            clear_waitlist()
            await q.message.edit_reply_markup(reply_markup=admin_kb())
            await q.message.reply_text(f"✅ User {len(waitlist_users)} ဦးကို အကြောင်းကြားပြီးပါပြီ။ Waitlist ကို ရှင်းလင်းလိုက်ပါပြီ။")

        elif act == "stats_menu":
            await q.message.edit_reply_markup(reply_markup=stats_menu_kb())

        elif act == "back":
            await q.message.edit_reply_markup(reply_markup=admin_kb())

        elif act == "orders":
            rows = pending_orders()
            if not rows: await q.message.reply_text("✅ Pending Orders မရှိပါ"); return
            for r in rows:
                oid,ruid,pid,pname,pts,gmail,pwd,twofa,st,ts = r
                await q.message.reply_text(
                    f"📋 *Order #{oid}*\n{'─'*18}\n👤 ID: `{ruid}`\n📦 {pname}  |  {pts} pts\n"
                    f"📧 `{gmail}`\n🔒 `{pwd}`\n🔐 `{twofa}`\n🕐 {ts_fmt(ts)}", parse_mode="Markdown", reply_markup=order_action_kb(oid))

        elif act == "pts":
            rows = pending_pts()
            if not rows: await q.message.reply_text("✅ Pending Requests မရှိပါ"); return
            for r in rows:
                rid,ruid,pts,price,fid,note,st,ts = r
                await ctx.bot.send_photo(
                    q.message.chat_id, photo=fid,
                    caption=f"💰 *Point Request #{rid}*\n👤 ID: `{ruid}`\n💎 {pts} pts  |  {price:,} ကျပ်\n🕐 {ts_fmt(ts)}",
                    parse_mode="Markdown", reply_markup=pts_action_kb(rid, ruid, pts))

        elif act == "manual":
            rows = pending_manual_reqs()
            if not rows: await q.message.reply_text("✅ Manual Requests မရှိပါ"); return
            for r in rows:
                mid, ruid, name, bal, note, ts = r
                await q.message.reply_text(
                    f"🙋 *Manual Request #{mid}*\n{'─'*18}\n👤 [{name}](tg://user?id={ruid})  `{ruid}`\n"
                    f"💰 Balance: {bal} pts\n📝 {note}\n🕐 {ts_fmt(ts)}", parse_mode="Markdown", reply_markup=manual_action_kb(mid, ruid))

        elif act == "pts_all":
            rows = all_pt_requests(30)
            if not rows: await q.message.reply_text("📊 Requests မရှိသေးပါ"); return
            ST = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
            lines = [f"{ST.get(st,'?')} #{rid} | {name or ruid} | {pts}pts | {price:,}ကျပ် | {ts_fmt(ts)}" for rid,ruid,name,pts,price,st,ts in rows]
            text = "📊 *Point Request History (30)*\n" + "\n".join(lines)
            if len(text) > 4000: text = text[:4000] + "\n..."
            await q.message.reply_text(text, parse_mode="Markdown")

        elif act == "users":
            users = all_users()
            lines = "\n".join(f"{'─'*18}\n👤 [{n}](tg://user?id={i})  `{i}`\n💰 {p} pts" for i,u,n,p in users)
            await q.message.reply_text(f"👥 *Users ({len(users)})*\n{lines}", parse_mode="Markdown")

        elif act == "addpts":
            pending_admin_actions[uid] = {"type": "addpts_uid"}
            await q.message.reply_text("➕ *Points ထည့်/နုတ်*\n\nUser ID ထည့်ပါ —\n_( /addpts uid amount လဲ သုံးနိုင်သည် )_", parse_mode="Markdown")
        return

    # ── Order Complete ────────────────────────────────
    if data.startswith("done:"):
        if not is_admin(uid): return
        oid = int(data.split(":")[1])
        row = get_order(oid)
        if not row: await q.message.reply_text("Order မတွေ့ပါ"); return
        pending_admin_actions[uid] = {"type": "link", "oid": oid, "ruid": row[1], "gmail": row[5], "pts": row[4]}
        await q.message.reply_text(f"✅ *Order #{oid}*\n📧 Gmail: `{row[5]}`\n\n⬇️ Google AI Pro Link ကို ဒီမှာ ပို့ပါ\n_(Bot မှ User ထံ တိုက်ရိုက် ပို့ပေးမည်)_", parse_mode="Markdown")
        return

    # ── Reject ────────────────────────────────────────
    if data.startswith("rj_menu:"):
        if not is_admin(uid): return
        oid = int(data.split(":")[1])
        await q.message.reply_text(f"❌ Order #{oid} — Reject အကြောင်းရင်း ရွေးပါ:", reply_markup=reject_kb(oid)); return

    if data.startswith("rj:"):
        if not is_admin(uid): return
        parts = data.split(":")
        reason, oid = parts[1], int(parts[2])
        row = get_order(oid)
        if not row: return
        ruid, pts = row[1], row[4]
        set_order_status(oid, "rejected")
        add_pts(ruid, pts)
        MSGS = {
            "2fa":  f"❌ *Order ဖျက်သိမ်း + ငွေပြန်အမ်းပြီ*\n\n2FA မမှန်ကန်သောကြောင့်ပါ\n[2FA ဖွင့်နည်း Video]({LINK_2FA}) ကို အဆုံးထိ ကြည့်ပြီး ပြန်တင်ပါ\n\n💰 {pts} pts ပြန်ထည့်ပြီ",
            "pay":  f"❌ *Order ဖျက်သိမ်း + ငွေပြန်အမ်းပြီ*\n\nPayment Profile မပိတ်သောကြောင့်ပါ\n[ပိတ်နည်း Video]({LINK_PAYMENT})\n\n💰 {pts} pts ပြန်ထည့်ပြီ",
            "fam":  f"❌ *Order ဖျက်သိမ်း + ငွေပြန်အမ်းပြီ*\n\nFamily Group မထွက်သောကြောင့်ပါ\n[ထွက်နည်း Video]({LINK_FAMILY})\n\n💰 {pts} pts ပြန်ထည့်ပြီ",
            "mail": f"❌ *Order ဖျက်သိမ်း + ငွေပြန်အမ်းပြီ*\n\nGmail မမှန်ကန်သောကြောင့်ပါ\nမှန်ကန်သော Gmail နဲ့ ပြန်တင်ပါ\n\n💰 {pts} pts ပြန်ထည့်ပြီ",
            "other":f"❌ *Order ဖျက်သိမ်း + ငွေပြန်အမ်းပြီ*\n\nပြဿနာတစ်ခုခုရှိ၍ မဆောင်ရွက်နိုင်ပါ\n📞 @{ADMIN_USERNAME}\n\n💰 {pts} pts ပြန်ထည့်ပြီ",
        }
        try: await ctx.bot.send_message(ruid, MSGS.get(reason, MSGS["other"]), parse_mode="Markdown")
        except: pass
        try: await q.message.edit_reply_markup()
        except: pass
        await q.message.reply_text(f"❌ Order #{oid} reject + {pts}pts refund ပြီ")
        return

    # ── Points approve/reject ─────────────────────────
    if data.startswith("pts:"):
        if not is_admin(uid): return
        parts = data.split(":")
        act, rid, ruid = parts[1], int(parts[2]), int(parts[3])
        amt = int(parts[4]) if len(parts) > 4 else 0
        if act == "ok":
            add_pts(ruid, amt)
            set_pt_status(rid, "approved")
            try: await ctx.bot.send_message(ruid, f"✅ *{amt} Points ထည့်ပြီ!*\n💰 Balance: *{get_pts(ruid)} pts*\n\nကျေးဇူးတင်ပါသည် 🙏", parse_mode="Markdown")
            except: pass
            try: await q.message.edit_reply_markup()
            except: pass
            await q.message.reply_text(f"✅ {amt} pts → User {ruid} ထည့်ပြီ")
        elif act == "no":
            set_pt_status(rid, "rejected")
            try: await ctx.bot.send_message(ruid, f"❌ *Point Request reject ဖြစ်ပြီ*\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown")
            except: pass
            try: await q.message.edit_reply_markup()
            except: pass
            await q.message.reply_text(f"❌ Point Request #{rid} reject ပြီ")
        return

    # ── Manual request ────────────────────────────────
    if data.startswith("man:"):
        if not is_admin(uid): return
        parts = data.split(":")
        act, mid, ruid = parts[1], int(parts[2]), int(parts[3])
        if act == "done":
            set_manual_status(mid, "resolved")
            try: await ctx.bot.send_message(ruid, f"✅ *Manual Request ကိုင်တွယ်ပြီ*\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown")
            except: pass
            try: await q.message.edit_reply_markup()
            except: pass
            await q.message.reply_text(f"✅ Manual Request #{mid} resolved ပြီ")
        elif act == "no":
            set_manual_status(mid, "rejected")
            try: await ctx.bot.send_message(ruid, f"❌ Request ဆောင်ရွက်မပေးနိုင်ပါ\n📞 @{ADMIN_USERNAME}", parse_mode="Markdown")
            except: pass
            try: await q.message.edit_reply_markup()
            except: pass
            await q.message.reply_text(f"❌ Manual Request #{mid} rejected ပြီ")
        return

    # ── Plan / Package Handlers for Buy Flow ──────────
    if data.startswith("buyplan:"): return await cb_buy_plan_select(update, ctx)
    if data.startswith("plan:"): return await cb_plan(update, ctx)
    if data.startswith("pkg:"): return await cb_pkg(update, ctx)
    
    if data == "cancel":
        ctx.user_data.clear()
        pending_admin_actions.pop(uid, None)
        await q.message.reply_text("❌ Cancel", reply_markup=MAIN_KB)
        return MAIN_MENU

# ══════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════
def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    init_db()

    # Web server ကို စတင် Run ပါမည် (ဒီစာကြောင်းလေး ထပ်ထည့်ပေးပါ)
    keep_alive() 

    app = Application.builder().token(BOT_TOKEN).post_init(setup_bot_commands).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^💰 Points ကြည့်$"), h_points),
                MessageHandler(filters.Regex("^🛒 Order တင်$"),    h_start_order),
                MessageHandler(filters.Regex("^💎 Points ဝယ်$"),   h_buy),
                MessageHandler(filters.Regex("^📋 Orders ကြည့်$"), h_my_orders),
                MessageHandler(filters.Regex("^📖 လမ်းညွှန်$"),   h_guide),
                MessageHandler(filters.Regex("^📞 Support$"),      h_support),
                CallbackQueryHandler(global_cb),
            ],
            ORDER_PLAN:     [CallbackQueryHandler(global_cb)],
            ORDER_GMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, h_gmail)],
            ORDER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, h_password)],
            ORDER_2FA:      [MessageHandler(filters.TEXT & ~filters.COMMAND, h_2fa)],
            BUY_PLAN_SELECT:[CallbackQueryHandler(global_cb)],
            BUY_PKG:        [CallbackQueryHandler(global_cb)],
            BUY_SCREENSHOT: [
                MessageHandler(filters.PHOTO, h_screenshot),
                MessageHandler(filters.TEXT, lambda u,c: u.message.reply_text("📸 Screenshot ပို့ပါ")),
            ],
        },
        fallbacks=[CommandHandler("cancel", h_cancel), CallbackQueryHandler(global_cb, pattern="^cancel$")],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("addpts", cmd_addpts))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler), group=1)
    app.add_handler(CallbackQueryHandler(global_cb))

    logging.info("✅ Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
