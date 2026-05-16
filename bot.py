#!/usr/bin/env python3
"""
Xray Telegram Bot - Full Version with Monitoring & Blocking
===========================================================
Commands:
  /start       - رسالة الترحيب
  /users       - قائمة المستخدمين
  /info <name> - تفاصيل المستخدم
  /active      - المواقع المفتوحة حالياً
  /sites <name>- أكثر المواقع زيارة للمستخدم
  /top         - أكثر المواقع زيارة (عام)
  /block <name> <domain>  - حظر موقع ليوزر
  /unblock <name> <domain>- إلغاء حظر موقع
  /blocks      - قائمة الحظورات
  /add <name>  - إضافة مستخدم
  /del <name>  - حذف مستخدم
  /limit <name> <mb> - تعيين حد البيانات
  /enable <name> - تفعيل مستخدم
  /disable <name>- تعطيل مستخدم
  /reset       - إعادة تعيين الإحصائيات
  /restart     - إعادة تشغيل Xray
"""
import os, json, requests, asyncio, re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ========================== Configuration ==========================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()]
API_URL = os.environ.get("XRAY_API_URL", "").rstrip("/")
API_KEY = os.environ.get("XRAY_API_KEY", "xray123")

# ========================== API Client ==========================
def api_get(path, params=None):
    """Make authenticated GET request to Xray API"""
    try:
        r = requests.get(
            f"{API_URL}{path}",
            headers={"X-API-Key": API_KEY},
            params=params,
            timeout=15
        )
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def api_post(path, data):
    """Make authenticated POST request to Xray API"""
    try:
        r = requests.post(
            f"{API_URL}{path}",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json=data,
            timeout=15
        )
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def api_delete(path, data):
    """Make authenticated DELETE request to Xray API"""
    try:
        r = requests.delete(
            f"{API_URL}{path}",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json=data,
            timeout=15
        )
        return r.json(), r.status_code
    except Exception as e:
        return {"error": str(e)}, 500

# ========================== Helpers ==========================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def fmt_size(mb):
    if mb < 1:
        return f"{mb*1024:.0f} KB"
    elif mb < 1024:
        return f"{mb:.1f} MB"
    else:
        return f"{mb/1024:.2f} GB"

def escape_html(text):
    """Escape HTML special characters for Telegram"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def fmt_duration_bot(minutes):
    """Format minutes into human-readable duration for bot messages"""
    if minutes < 1:
        return f"{int(minutes*60)}ث"
    elif minutes < 60:
        return f"{minutes:.0f}د"
    else:
        h = int(minutes // 60)
        m = int(minutes % 60)
        if m > 0:
            return f"{h}س {m}د"
        return f"{h}س"

# ========================== Command Handlers ==========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    text = """<b>Xray VPN Bot v2.0</b>

مرحباً! البوت يدير سيرفر Xray مع ميزات المراقبة والحظر.

<b>إدارة المستخدمين:</b>
/users - قائمة المستخدمين
/info اسم - تفاصيل المستخدم
/add اسم - إضافة مستخدم
/del اسم - حذف مستخدم
/limit اسم 5000 - تعيين حد البيانات (MB)
/enable اسم - تفعيل المستخدم
/disable اسم - تعطيل المستخدم

<b>المراقبة:</b>
/active - المواقع المفتوحة حالياً
/sites اسم - أكثر مواقع المستخدم
/top - أكثر المواقع زيارة (عام)

<b>الحظر:</b>
/block اسم domain.com - حظر موقع
/unblock اسم domain.com - إلغاء حظر
/blocks - قائمة الحظورات

<b>أخرى:</b>
/reset - إعادة تعيين الإحصائيات
/restart - إعادة تشغيل Xray"""

    await update.message.reply_text(text, parse_mode="HTML")


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    data, code = api_get("/api/users")
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'غير مصرح')}")
        return

    users = data if isinstance(data, list) else data.get("users", data.get("result", []))
    if not users:
        await update.message.reply_text("لا يوجد مستخدمين")
        return

    lines = [f"<b>قائمة المستخدمين ({len(users)})</b>\n"]
    for u in users:
        name = u.get("name", "؟")
        active = "✅" if u.get("active", True) else "❌"
        used = u.get("used_mb", 0)
        limit = u.get("data_limit_mb", 0)
        pct = u.get("usage_percent", 0)
        blocks = u.get("blocked_sites", 0)

        used_hr = fmt_size(used)
        limit_hr = fmt_size(limit)

        # Progress bar
        bar_len = 10
        filled = int(pct / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        line = f"{active} <b>{escape_html(name)}</b>\n"
        line += f"   {bar} {pct:.0f}% ({used_hr}/{limit_hr})"
        if blocks > 0:
            line += f" 🚫{blocks}"
        lines.append(line)

    text = "\n".join(lines)
    if len(text) > 4096:
        # Split into multiple messages
        chunks = [lines[0]]
        for line in lines[1:]:
            if len("\n".join(chunks + [line])) > 4000:
                await update.message.reply_text("\n".join(chunks), parse_mode="HTML")
                chunks = [line]
            else:
                chunks.append(line)
        if chunks:
            await update.message.reply_text("\n".join(chunks), parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")


async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User detail"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /info اسم_المستخدم")
        return

    name = " ".join(context.args)
    data, code = api_get(f"/api/user/{name}")
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'المستخدم غير موجود')}")
        return

    active = "✅ مفعل" if data.get("active", True) else "❌ معطل"
    used = data.get("used_mb", 0)
    limit = data.get("data_limit_mb", 0)
    pct = data.get("usage_percent", 0)
    up = data.get("uplink_mb", 0)
    down = data.get("downlink_mb", 0)
    blocks = data.get("blocked_sites", [])

    text = f"""<b>📊 تفاصيل: {escape_html(name)}</b>

الحالة: {active}
الحد: {fmt_size(limit)}
المستخدم: {fmt_size(used)} ({pct:.1f}%)
رفع: {fmt_size(up)} | تحميل: {fmt_size(down)}
UUID: <code>{escape_html(data.get('uuid', '؟'))}</code>"""

    if blocks:
        text += f"\n\n<b>🚫 مواقع محظورة ({len(blocks)}):</b>"
        for b in blocks[:20]:
            text += f"\n  • {escape_html(b.get('domain', '؟'))}"

    await update.message.reply_text(text, parse_mode="HTML")


async def active_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show currently active/open websites with time and data"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    data, code = api_get("/api/monitoring/active")
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل الاتصال')}")
        return

    active = data.get("active_connections", {})
    total = data.get("total_active_users", 0)

    if not active:
        await update.message.reply_text("🌐 لا توجد اتصالات نشطة حالياً")
        return

    lines = [f"<b>🌐 المواقع المفتوحة حالياً ({total} مستخدم نشط)</b>\n"]
    for user, sites in sorted(active.items()):
        lines.append(f"\n<b>👤 {escape_html(user)}</b>")
        for s in sites[:15]:
            if isinstance(s, str):
                # Old format: just domain string
                lines.append(f"  • {escape_html(s)}")
            else:
                # New format: dict with details
                domain = s.get("domain", "؟")
                mins = s.get("minutes", 0)
                data_hr = s.get("estimated_hr", "")
                visits = s.get("visits", 0)
                time_str = fmt_duration_bot(mins)
                detail = f"⏱{time_str}"
                if data_hr and data_hr != "0 KB":
                    detail += f" 📦{data_hr}"
                lines.append(f"  • {escape_html(domain)} {detail}")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4080] + "\n..."

    await update.message.reply_text(text, parse_mode="HTML")


async def sites_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show most visited sites for a user with time and data"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /sites اسم_المستخدم")
        return

    name = " ".join(context.args)
    data, code = api_get(f"/api/monitoring/user/{name}/sites", {"limit": 25})
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل الاتصال')}")
        return

    sites = data.get("sites", [])
    if not sites:
        await update.message.reply_text(f"لا توجد بيانات مواقع لـ {name}")
        return

    lines = [f"<b>📈 أكثر المواقع زيارة: {escape_html(name)}</b>\n"]
    for i, s in enumerate(sites[:25], 1):
        domain = s.get("domain", "؟")
        visits = s.get("visits", 0)
        mins = s.get("minutes", 0)
        data_hr = s.get("estimated_hr", "")
        sessions = s.get("sessions", 0)
        first = s.get("first_seen", "")
        last = s.get("last_seen", "")

        time_str = fmt_duration_bot(mins)
        line = f"  {i}. {escape_html(domain)}\n"
        line += f"     ⏱ {time_str} | 📦 {data_hr} | 🔗 {visits} زيارة"
        if sessions > 1:
            line += f" | 🔄 {sessions} جلسة"
        if first and last:
            line += f"\n     🕐 {first} - {last}"
        lines.append(line)

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4080] + "\n..."

    await update.message.reply_text(text, parse_mode="HTML")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top visited sites globally with time and data"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    limit = 20
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)

    data, code = api_get("/api/monitoring/top-sites", {"limit": limit})
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل الاتصال')}")
        return

    sites = data.get("top_sites", [])
    if not sites:
        await update.message.reply_text("لا توجد بيانات مواقع بعد")
        return

    lines = [f"<b>🔥 أكثر المواقع زيارة (عام)</b>\n"]
    for i, s in enumerate(sites, 1):
        domain = s.get("domain", "؟")
        visits = s.get("visits", 0)
        mins = s.get("minutes", 0)
        mins_hr = s.get("minutes_hr", "")
        data_hr = s.get("estimated_hr", "")
        users_count = s.get("users_count", 0)

        time_str = mins_hr or fmt_duration_bot(mins)
        line = f"  {i}. {escape_html(domain)}\n"
        line += f"     ⏱ {time_str} | 📦 {data_hr} | 🔗 {visits} | 👥 {users_count}"
        lines.append(line)

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4080] + "\n..."

    await update.message.reply_text(text, parse_mode="HTML")


async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block a website for a specific user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "الاستخدام: /block اسم_المستخدم domain.com\n"
            "مثال: /block ali facebook.com"
        )
        return

    username = context.args[0]
    domain = context.args[1].lower()

    # Clean domain
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.rstrip("/")

    data, code = api_post("/api/block", {"user": username, "domain": domain})
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")
        return

    if data.get("ok"):
        await update.message.reply_text(
            f"🚫 تم حظر <b>{escape_html(domain)}</b> للمستخدم <b>{escape_html(username)}</b>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(data.get("message", "فشل الحظر"))


async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock a website for a specific user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "الاستخدام: /unblock اسم_المستخدم domain.com\n"
            "مثال: /unblock ali facebook.com"
        )
        return

    username = context.args[0]
    domain = context.args[1].lower()

    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.rstrip("/")

    data, code = api_delete("/api/block", {"user": username, "domain": domain})
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")
        return

    if data.get("ok"):
        await update.message.reply_text(
            f"✅ تم إلغاء حظر <b>{escape_html(domain)}</b> للمستخدم <b>{escape_html(username)}</b>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(data.get("message", "الحظر غير موجود"))


async def blocks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all blocked sites"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    data, code = api_get("/api/blocks")
    if code != 200:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")
        return

    blocks = data.get("blocks", [])
    if not blocks:
        await update.message.reply_text("لا توجد مواقع محظورة")
        return

    # Group by user
    user_blocks = {}
    for b in blocks:
        user = b.get("user", "؟")
        if user not in user_blocks:
            user_blocks[user] = []
        user_blocks[user].append(b.get("domain", "؟"))

    lines = [f"<b>🚫 قائمة الحظورات ({len(blocks)})</b>\n"]
    for user, domains in sorted(user_blocks.items()):
        lines.append(f"<b>👤 {escape_html(user)}</b> ({len(domains)} موقع)")
        for d in domains:
            lines.append(f"  • {escape_html(d)}")
        lines.append("")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4080] + "\n..."

    await update.message.reply_text(text, parse_mode="HTML")


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /add اسم_المستخدم")
        return

    name = context.args[0]
    import uuid
    new_uuid = str(uuid.uuid4())

    data, code = api_post("/api/add", {
        "name": name,
        "uuid": new_uuid,
        "max_devices": 2,
        "data_limit_mb": 5000
    })

    if code == 200 and data.get("ok"):
        await update.message.reply_text(
            f"✅ تم إضافة <b>{escape_html(name)}</b>\n"
            f"UUID: <code>{new_uuid}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /del اسم_المستخدم")
        return

    name = context.args[0]
    data, code = api_post("/api/del", {"name": name})

    if code == 200 and data.get("ok"):
        await update.message.reply_text(f"🗑️ تم حذف {escape_html(name)}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set data limit for a user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "الاستخدام: /limit اسم_المستخدم الحجم_MB\n"
            "مثال: /limit ali 10000"
        )
        return

    name = context.args[0]
    try:
        limit_mb = int(context.args[1])
    except ValueError:
        await update.message.reply_text("الحد يجب أن يكون رقم")
        return

    data, code = api_post("/api/limit", {"name": name, "data_limit_mb": limit_mb})

    if code == 200 and data.get("ok"):
        await update.message.reply_text(
            f"✅ تم تعيين حد {fmt_size(limit_mb)} لـ {escape_html(name)}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable a user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /enable اسم_المستخدم")
        return

    name = context.args[0]
    data, code = api_post("/api/enable", {"name": name})

    if code == 200 and data.get("ok"):
        await update.message.reply_text(f"✅ تم تفعيل {escape_html(name)}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disable a user"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: /disable اسم_المستخدم")
        return

    name = context.args[0]
    data, code = api_post("/api/disable", {"name": name})

    if code == 200 and data.get("ok"):
        await update.message.reply_text(f"❌ تم تعطيل {escape_html(name)}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset traffic stats"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    data, code = api_post("/api/reset", {})
    if code == 200 and data.get("ok"):
        await update.message.reply_text("🔄 تم إعادة تعيين الإحصائيات")
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart Xray"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("غير مصرح")
        return

    data, code = api_post("/api/restart", {})
    if code == 200 and data.get("ok"):
        await update.message.reply_text("🔄 تم إعادة تشغيل Xray")
    else:
        await update.message.reply_text(f"خطأ: {data.get('error', 'فشل')}")


# ========================== Traffic Notification Monitor ==========================
async def traffic_monitor(context: ContextTypes.DEFAULT_TYPE):
    """Periodic check for traffic limits - sends notifications at 80% and 100%"""
    data, code = api_get("/api/users")
    if code != 200:
        return

    users = data if isinstance(data, list) else data.get("users", data.get("result", []))
    for u in users:
        name = u.get("name", "")
        pct = u.get("usage_percent", 0)
        active = u.get("active", True)

        if not active:
            continue

        # Check notification state file
        notify_file = f"/tmp/xray_notify_{name}"
        notified = ""
        if os.path.exists(notify_file):
            with open(notify_file, "r") as f:
                notified = f.read().strip()

        if pct >= 100 and notified != "100":
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🚨 <b>تنبيه: المستخدم {escape_html(name)} تجاوز الحد!</b>\n"
                             f"الاستخدام: {pct:.0f}%",
                        parse_mode="HTML"
                    )
                except:
                    pass
            with open(notify_file, "w") as f:
                f.write("100")

        elif pct >= 80 and notified not in ("80", "100"):
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ <b>تحذير: المستخدم {escape_html(name)} وصل 80% من الحد</b>\n"
                             f"الاستخدام: {pct:.0f}%",
                        parse_mode="HTML"
                    )
                except:
                    pass
            with open(notify_file, "w") as f:
                f.write("80")

        elif pct < 80 and notified:
            os.remove(notify_file) if os.path.exists(notify_file) else None


# ========================== Main ==========================
def main():
    import sys

    print("=" * 50, flush=True)
    print("Xray Telegram Bot v2.0 starting...", flush=True)
    print(f"BOT_TOKEN: {'SET' if BOT_TOKEN else 'NOT SET !!!'}", flush=True)
    print(f"API_URL: {API_URL or 'NOT SET !!!'}", flush=True)
    print(f"API_KEY: {'SET' if API_KEY else 'NOT SET'}", flush=True)
    print(f"ADMIN_IDS: {ADMIN_IDS or 'NOT SET !!!'}", flush=True)
    print("=" * 50, flush=True)

    if not BOT_TOKEN:
        print("FATAL: TELEGRAM_BOT_TOKEN not set! Add it in Render Environment.", flush=True)
        sys.exit(1)
    if not API_URL:
        print("FATAL: XRAY_API_URL not set! Add it in Render Environment.", flush=True)
        sys.exit(1)
    if not ADMIN_IDS:
        print("WARNING: TELEGRAM_ADMIN_IDS not set! No one can use the bot.", flush=True)

    # Test API connection
    try:
        r = requests.get(f"{API_URL}/", headers={"X-API-Key": API_KEY}, timeout=10)
        print(f"API test: {r.status_code} - {r.text[:100]}", flush=True)
    except Exception as e:
        print(f"WARNING: Cannot reach API: {e}", flush=True)

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # User management commands
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("users", users_cmd))
        app.add_handler(CommandHandler("info", info_cmd))
        app.add_handler(CommandHandler("add", add_cmd))
        app.add_handler(CommandHandler("del", del_cmd))
        app.add_handler(CommandHandler("limit", limit_cmd))
        app.add_handler(CommandHandler("enable", enable_cmd))
        app.add_handler(CommandHandler("disable", disable_cmd))
        app.add_handler(CommandHandler("reset", reset_cmd))
        app.add_handler(CommandHandler("restart", restart_cmd))

        # Monitoring commands
        app.add_handler(CommandHandler("active", active_cmd))
        app.add_handler(CommandHandler("sites", sites_cmd))
        app.add_handler(CommandHandler("top", top_cmd))

        # Blocking commands
        app.add_handler(CommandHandler("block", block_cmd))
        app.add_handler(CommandHandler("unblock", unblock_cmd))
        app.add_handler(CommandHandler("blocks", blocks_cmd))

        # Traffic notification (every 5 minutes)
        app.job_queue.run_repeating(traffic_monitor, interval=300, first=10)

        print("Bot is running! Waiting for messages...", flush=True)
        app.run_polling()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
