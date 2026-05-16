#!/usr/bin/env python3
# ============================================
#   xray Telegram Bot — يشتغل على Render
#   محدث ليتوافق مع API الجديد (http.server)
#   + إشعارات عند وصول المستخدم للحد
# ============================================

import os, json, time, requests, threading
from flask import Flask, request
from datetime import datetime

# ─── الإعدادات ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()]
XRAY_API_URL = os.environ.get("XRAY_API_URL", "")  # https://CODESPACE-10086.app.github.dev
XRAY_API_KEY = os.environ.get("XRAY_API_KEY", "xray123")  # مفتاح API الجديد
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
CODESPACE_NAME = os.environ.get("CODESPACE_NAME", "")
RENDER_PORT = int(os.environ.get("PORT", 10000))

# إعدادات الإشعارات
NOTIFY_CHECK_INTERVAL = int(os.environ.get("NOTIFY_CHECK_INTERVAL", "120"))  # كل كم ثانية يفحص (افتراضي 2 دقيقة)
NOTIFY_THRESHOLD = int(os.environ.get("NOTIFY_THRESHOLD", "80"))  # نسبة التحذير (افتراضي 80%)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# ─── أدوات ───
def fmt(b):
    """تحويل البايتات لحجم مقروء"""
    if b is None: return "0 B"
    b = int(b)
    if b < 1024: return f"{b} B"
    elif b < 1048576: return f"{b/1024:.1f} KB"
    elif b < 1073741824: return f"{b/1048576:.2f} MB"
    else: return f"{b/1073741824:.2f} GB"

def fmt_duration(sec):
    if sec is None or sec <= 0: return "-"
    elif sec < 60: return f"{sec}ث"
    elif sec < 3600: return f"{sec//60}د"
    elif sec < 86400: return f"{sec//3600}س {(sec%3600)//60}د"
    else: return f"{sec//86400}ي"

def is_admin(chat_id):
    return chat_id in ADMIN_IDS

# ─── التواصل مع كودسبيس (API الجديد) ───
def api_get(endpoint):
    """GET request مع X-API-Key header (بدل Bearer القديم)"""
    if not XRAY_API_URL:
        return None, "XRAY_API_URL غير مضبوط"
    try:
        url = f"{XRAY_API_URL}{endpoint}"
        headers = {"X-API-Key": XRAY_API_KEY}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 401:
            return None, "مفتاح API غلط — تأكد من XRAY_API_KEY"
        if r.status_code == 404:
            return None, "هذا الأمر غير متاح حالياً بالـ API"
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "الكودسبيس مطفي"
    except requests.exceptions.Timeout:
        return None, "انتهت المهلة — الكودسبيس بطيء أو مطفي"
    except Exception as e:
        return None, str(e)

def api_post(endpoint, data=None):
    """POST request مع X-API-Key header"""
    if not XRAY_API_URL:
        return None, "XRAY_API_URL غير مضبوط"
    try:
        url = f"{XRAY_API_URL}{endpoint}"
        headers = {"X-API-Key": XRAY_API_KEY, "Content-Type": "application/json"}
        r = requests.post(url, json=data or {}, headers=headers, timeout=15)
        if r.status_code == 401:
            return None, "مفتاح API غلط — تأكد من XRAY_API_KEY"
        if r.status_code == 404:
            return None, "هذا الأمر غير متاح حالياً بالـ API"
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "الكودسبيس مطفي — جرب زر تشغيل الكودسبيس"
    except requests.exceptions.Timeout:
        return None, "انتهت المهلة — الكودسبيس بطيء أو مطفي"
    except Exception as e:
        return None, str(e)

def start_codespace():
    """تشغيل الكودسبيس عن بعد عبر GitHub API"""
    if not GITHUB_TOKEN or not CODESPACE_NAME:
        return False, "GH_TOKEN أو CODESPACE_NAME غير مضبوط"
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.post(
            f"https://api.github.com/user/codespaces/{CODESPACE_NAME}/start",
            headers=headers, timeout=30
        )
        if r.status_code in [200, 202]:
            return True, "جاري التشغيل... يأخذ 1-2 دقيقة"
        return False, f"خطأ: {r.status_code}"
    except Exception as e:
        return False, str(e)

# ─── الحصول على بيانات المستخدمين (مع fallback) ───
def get_users_with_traffic():
    """يجيب بيانات المستخدمين من API — يدعم الصيغ القديمة والجديدة"""
    # محاولة 1: /api/users (الجديد)
    data, err = api_get("/api/users")
    if data and not err:
        users = data.get("users", [])
        if users:
            return normalize_users(users), None

    # محاولة 2: /api/list (القديم)
    data2, err2 = api_get("/api/list")
    if data2 and not err2:
        users = data2.get("users", [])
        if users:
            return normalize_users(users), None

    # رجع الخطأ
    return [], err or err2 or "ماكو بيانات"

def normalize_users(users):
    """توحيد صيغة بيانات المستخدمين (قديم + جديد)"""
    result = []
    for u in users:
        # استخراج البيانات بأسماء مختلفة
        name = u.get("name", u.get("email", "?"))

        # الترافيك — يدعم صيغ متعددة
        up = u.get("up", u.get("upload", u.get("traffic_up", u.get("upload_bytes", 0))))
        down = u.get("down", u.get("download", u.get("traffic_down", u.get("download_bytes", 0))))

        # إذا كانت البيانات بـ GB، حوّلها لبايت
        if "used_gb" in u:
            total_used_gb = u.get("used_gb", 0)
            total = int(total_used_gb * 1073741824) if total_used_gb else 0
            if not up and not down:
                up = int(u.get("upload_gb", 0) * 1073741824)
                down = int(u.get("download_gb", 0) * 1073741824)
                total = up + down
        elif "traffic_total" in u:
            total = u.get("traffic_total", 0)
        else:
            total = int(up) + int(down)

        # الحد — يدعم صيغ متعددة
        if "limit_gb" in u:
            limit_gb = u.get("limit_gb", 0)
            limit_mb = int(limit_gb * 1024) if limit_gb else 0
        elif "data_limit_mb" in u:
            limit_mb = u.get("data_limit_mb", 0)
        elif "data_limit" in u:
            limit_mb = int(u.get("data_limit", 0) / 1048576)
        else:
            limit_mb = 0

        result.append({
            "name": name,
            "active": u.get("active", u.get("enabled", True)),
            "uuid": u.get("uuid", u.get("id", "?")),
            "link": u.get("link", ""),
            "max_devices": u.get("max_devices", u.get("device_limit", 2)),
            "up": int(up) if up else 0,
            "down": int(down) if down else 0,
            "total": int(total) if total else 0,
            "limit_mb": int(limit_mb) if limit_mb else 0,
        })
    return result

def get_user_detail(name):
    """يجيب تفاصيل مستخدم واحد"""
    # محاولة 1: /api/user/NAME (الجديد)
    data, err = api_get(f"/api/user/{name}")
    if data and not err:
        users = normalize_users([data.get("user", data)])
        if users:
            return users[0], None

    # محاولة 2: من قائمة الكل
    users, err = get_users_with_traffic()
    if err:
        return None, err
    for u in users:
        if u["name"] == name:
            return u, None
    return None, f"المستخدم '{name}' غير موجود"

# ─── أزرار Inline Keyboard ───

def kb_main():
    return {
        "inline_keyboard": [
            [
                {"text": "👥 المستخدمين", "callback_data": "list"},
                {"text": "📊 الترافيك", "callback_data": "traffic"},
            ],
            [
                {"text": "⚙️ حالة السيرفر", "callback_data": "status"},
                {"text": "🔔 الإشعارات", "callback_data": "notify"},
            ],
            [
                {"text": "➕ إضافة مستخدم", "callback_data": "add_help"},
                {"text": "🔄 تشغيل الكودسبيس", "callback_data": "wake"},
            ],
            [
                {"text": "❓ مساعدة", "callback_data": "help"},
            ],
        ]
    }

def kb_back_main():
    return {
        "inline_keyboard": [
            [{"text": "🔙 القائمة الرئيسية", "callback_data": "main"}]
        ]
    }

def kb_user_list(users):
    buttons = []
    row = []
    for u in users:
        status = "✅" if u.get("active") else "❌"
        row.append({"text": f"{status} {u['name']}", "callback_data": f"u:{u['name']}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "🔙 القائمة الرئيسية", "callback_data": "main"}])
    return {"inline_keyboard": buttons}

def kb_user_detail(name, active=True):
    buttons = [
        [
            {"text": "🔗 الرابط", "callback_data": f"u:{name}:link"},
        ],
        [
            {"text": "💾 تعديل الحد", "callback_data": f"u:{name}:limit"},
        ],
        [
            {"text": "🔄 تصفير العداد", "callback_data": f"u:{name}:reset"},
        ],
    ]
    if active:
        buttons.append([{"text": "🚫 تعطيل", "callback_data": f"u:{name}:disable"}])
    else:
        buttons.append([{"text": "✅ تفعيل", "callback_data": f"u:{name}:enable"}])
    buttons.append([{"text": "🗑️ حذف", "callback_data": f"u:{name}:del"}])
    buttons.append([
        {"text": "🔙 قائمة المستخدمين", "callback_data": "list"},
        {"text": "🏠 الرئيسية", "callback_data": "main"},
    ])
    return {"inline_keyboard": buttons}

def kb_limit_options(name):
    return {
        "inline_keyboard": [
            [
                {"text": "1 GB", "callback_data": f"u:{name}:setlimit:1024"},
                {"text": "3 GB", "callback_data": f"u:{name}:setlimit:3072"},
                {"text": "5 GB", "callback_data": f"u:{name}:setlimit:5120"},
            ],
            [
                {"text": "10 GB", "callback_data": f"u:{name}:setlimit:10240"},
                {"text": "20 GB", "callback_data": f"u:{name}:setlimit:20480"},
                {"text": "50 GB", "callback_data": f"u:{name}:setlimit:51200"},
            ],
            [
                {"text": "♾️ بلا حد", "callback_data": f"u:{name}:setlimit:0"},
            ],
            [
                {"text": "🔙 رجوع", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_delete(name):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، احذف", "callback_data": f"u:{name}:del:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_reset(name):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، صفر", "callback_data": f"u:{name}:reset:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_restart():
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، أعد التشغيل", "callback_data": "restart:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": "main"},
            ],
        ]
    }

def kb_add_quick():
    return {
        "inline_keyboard": [
            [
                {"text": "👤 مستخدم عادي", "callback_data": "add:2:0"},
                {"text": "👤👤 2 جهاز 5GB", "callback_data": "add:2:5120"},
            ],
            [
                {"text": "👤👤👤 3 أجهزة 10GB", "callback_data": "add:3:10240"},
                {"text": "♾️ بلا حدود", "callback_data": "add:5:0"},
            ],
            [
                {"text": "🔙 القائمة الرئيسية", "callback_data": "main"},
            ],
        ]
    }

# ─── إرسال وتعديل الرسائل ───

def tg_send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/sendMessage", json=data, timeout=10)
    except: pass

def tg_edit(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text[:4096], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TG_API}/editMessageText", json=data, timeout=10)
        if r.status_code == 400 and "message is not modified" in r.text:
            pass
    except: pass

def tg_answer_callback(callback_query_id, text=""):
    try:
        requests.post(f"{TG_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
    except: pass

# ─── متغيرات الحالة ───
user_states = {}  # {chat_id: {"action": "customlimit", "name": "ali"}}
notified_users = {}  # {name: True} لتجنب تكرار الإشعارات

# ─── أوامر البوت ───

def cmd_start(chat_id, message_id=None):
    text = (
        "🚀 <b>بوت إدارة xray</b>\n\n"
        "🔌 السيرفر: GitHub Codespaces\n"
        "🤖 البوت: Render (24/7)\n\n"
        "اختار من الأزرار أو اكتب الأمر مباشرة"
    )
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_main())

def cmd_status(chat_id, message_id=None):
    data, err = api_get("/api/status")
    if err:
        text = f"⚙️ <b>حالة السيرفر</b>\n\n❌ {err}\n\nجرب تشغيل الكودسبيس من الزر"
        kb = [[{"text": "🔄 تشغيل الكودسبيس", "callback_data": "wake"}],
              [{"text": "🔙 الرئيسية", "callback_data": "main"}]]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    text = (
        "⚙️ <b>حالة السيرفر</b>\n\n"
        f"📡 العنوان: <code>{data.get('host','?')}</code>\n"
        f"🔘 xray: {'✅ يعمل' if data.get('xray_running') else '❌ متوقف'}\n"
        f"👥 مستخدمين: {data.get('users_active',0)} نشط / {data.get('users_total',0)} إجمالي\n"
        f"🕐 الوقت: {data.get('time','?')}\n"
    )
    kb = [
        [{"text": "🔄 إعادة تشغيل xray", "callback_data": "restart"}],
        [{"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_list(chat_id, message_id=None):
    users, err = get_users_with_traffic()
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if not users:
        text = "📋 لا يوجد مستخدمين بعد.\nاضغط زر إضافة مستخدم"
        kb = [
            [{"text": "➕ إضافة مستخدم", "callback_data": "add_help"}],
            [{"text": "🔙 الرئيسية", "callback_data": "main"}]
        ]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    text = "👥 <b>قائمة المستخدمين</b>\n\nاضغط على اسم المستخدم للتفاصيل\n"
    for u in users:
        status = "✅" if u.get("active") else "❌"
        total = u.get("total", 0)
        limit = f"{u.get('limit_mb',0)/1024:.1f}GB" if u.get("limit_mb", 0) > 0 else "∞"
        text += f"\n{status} <b>{u['name']}</b> — {fmt(total)} / {limit}"

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_user_list(users))
    else:
        tg_send(chat_id, text, reply_markup=kb_user_list(users))

def cmd_user_detail(chat_id, name, message_id=None):
    user, err = get_user_detail(name)
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    limit = f"{user.get('limit_mb',0)/1024:.1f}GB" if user.get("limit_mb", 0) > 0 else "♾️ بلا حد"
    total = user.get("total", 0)
    up = user.get("up", 0)
    down = user.get("down", 0)

    # شريط الاستهلاك
    limit_mb = user.get("limit_mb", 0)
    if limit_mb > 0:
        pct = min(100, total / (limit_mb * 1024 * 1024) * 100)
        filled = int(15 * pct / 100)
        bar = "▓" * filled + "░" * (15 - filled)
        usage_line = f"\n📊 {bar} {pct:.1f}%"
    else:
        pct = -1
        usage_line = "\n📊 بلا حد"

    status = "✅ مفعل" if user.get("active") else "❌ معطل"

    text = (
        f"👤 <b>مستخدم: {name}</b>\n\n"
        f"📌 الحالة: {status}\n"
        f"🆔 UUID: <code>{user.get('uuid','?')[:8]}...</code>\n"
        f"📱 أجهزة: {user.get('max_devices', 2)}\n"
        f"💾 حد البيانات: {limit}\n\n"
        f"📈 <b>الترافيك:</b>\n"
        f"   ⬆️ رفع: {fmt(up)}\n"
        f"   ⬇️ تحميل: {fmt(down)}\n"
        f"   💰 إجمالي: {fmt(total)}"
        f"{usage_line}"
    )

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_user_detail(name, user.get("active", True)))
    else:
        tg_send(chat_id, text, reply_markup=kb_user_detail(name, user.get("active", True)))

def cmd_user_link(chat_id, name, message_id=None):
    user, err = get_user_detail(name)
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    link = user.get("link", "")
    if link:
        text = (
            f"🔗 <b>رابط {name}</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"📋 انسخ الرابط وألصقه ببرنامج v2rayNG / Nekobox / Streisand"
        )
    else:
        text = f"🔗 <b>رابط {name}</b>\n\n❌ الرابط غير متوفر من الـ API\n\n💡 استخدم الأمر بالكودسبيس:\n<code>bash /usr/local/bin/user.sh link {name}</code>"

    kb = [
        [{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
         {"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_limit(chat_id, name, message_id=None):
    text = f"💾 <b>تعديل حد البيانات — {name}</b>\n\nاختار الحد الجديد:"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_limit_options(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_limit_options(name))

def cmd_user_confirm_delete(chat_id, name, message_id=None):
    text = f"⚠️ <b>تأكيد حذف: {name}</b>\n\nهل أنت متأكد؟ هذا الإجراء لا يمكن التراجع عنه!"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_delete(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_delete(name))

def cmd_user_confirm_reset(chat_id, name, message_id=None):
    text = f"🔄 <b>تصفير عداد: {name}</b>\n\nسيتم تصفير جميع بيانات الترافيك. متأكد؟"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_reset(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_reset(name))

def cmd_user_set_limit(chat_id, name, limit_mb, message_id=None):
    data, err = api_post("/api/limit", {"name": name, "data_limit_mb": int(limit_mb)})
    if err:
        # إذا الـ API ما يدعم هالأمر، حاول بطرق ثانية
        text = f"⚠️ <b>تعديل حد {name}</b>\n\n❌ الـ API ما يدعم تعديل الحد حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/user.sh limit {name} {limit_mb}</code>"
        kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
               {"text": "🔙 الرئيسية", "callback_data": "main"}]]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    limit_str = f"{int(limit_mb)/1024:.1f}GB" if int(limit_mb) > 0 else "♾️ بلا حد"
    text = f"✅ <b>تم تعديل حد {name}</b>\n\n💾 الحد الجديد: {limit_str}"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_delete(chat_id, name, message_id=None):
    data, err = api_post("/api/del", {"name": name})
    if err:
        text = f"⚠️ <b>حذف {name}</b>\n\n❌ الـ API ما يدعم الحذف حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/user.sh del {name}</code>"
        kb = [[{"text": "🔙 الرئيسية", "callback_data": "main"}]]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    text = f"🗑️ <b>تم حذف: {name}</b>"
    # مسح من قائمة الإشعارات
    notified_users.pop(name, None)
    kb = [
        [{"text": "👥 قائمة المستخدمين", "callback_data": "list"},
         {"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_reset(chat_id, name, message_id=None):
    data, err = api_post("/api/reset", {"name": name})
    if err:
        text = f"⚠️ <b>تصفير عداد {name}</b>\n\n❌ الـ API ما يدعم التصفير حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/user.sh reset {name}</code>"
        kb = [[{"text": "🔙 الرئيسية", "callback_data": "main"}]]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    # مسح من قائمة الإشعارات بعد التصفير
    notified_users.pop(name, None)
    text = f"✅ <b>تم تصفير عداد {name}</b>"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_enable(chat_id, name, message_id=None):
    data, err = api_post("/api/enable", {"name": name})
    if err:
        text = f"⚠️ <b>تفعيل {name}</b>\n\n❌ الـ API ما يدعم التفعيل حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/user.sh enable {name}</code>"
    else:
        notified_users.pop(name, None)
        text = f"✅ <b>تم تفعيل {name}</b>"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_disable(chat_id, name, message_id=None):
    data, err = api_post("/api/disable", {"name": name})
    if err:
        text = f"⚠️ <b>تعطيل {name}</b>\n\n❌ الـ API ما يدعم التعطيل حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/user.sh disable {name}</code>"
    else:
        text = f"🚫 <b>تم تعطيل {name}</b>"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_add(chat_id, args, message_id=None):
    if len(args) < 1:
        text = (
            "➕ <b>إضافة مستخدم</b>\n\n"
            "طريقة 1 — أزرار سريعة:\n"
            "اضغط على أحد الأزرار بالأسفل\n\n"
            "طريقة 2 — كتابة:\n"
            "<code>/add اسم [أجهزة] [حد_MB]</code>\n\n"
            "أمثلة:\n"
            "<code>/add ali</code> — 2 جهاز, بلا حد\n"
            "<code>/add ali 3</code> — 3 أجهزة\n"
            "<code>/add ali 2 5000</code> — 2 جهاز, 5GB"
        )
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_add_quick())
        else:
            tg_send(chat_id, text, reply_markup=kb_add_quick())
        return

    name = args[0]
    max_devices = int(args[1]) if len(args) > 1 else 2
    data_limit_mb = int(args[2]) if len(args) > 2 else 0

    data, err = api_post("/api/add", {
        "name": name, "max_devices": max_devices, "data_limit_mb": data_limit_mb
    })

    if err:
        text = (
            f"⚠️ <b>إضافة {name}</b>\n\n"
            f"❌ الـ API ما يدعم الإضافة حالياً\n\n"
            f"💡 نفذ يدوياً بالكودسبيس:\n"
            f"<code>bash /usr/local/bin/user.sh add {name} {max_devices} {data_limit_mb}</code>"
        )
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    limit_str = f"{data_limit_mb/1024:.1f}GB" if data_limit_mb > 0 else "بلا حد"
    link = data.get("link", "")
    text = (
        f"✅ <b>تم إضافة: {name}</b>\n\n"
        f"📱 أجهزة: {max_devices}\n"
        f"💾 حد: {limit_str}\n"
    )
    if link:
        text += f"\n🔗 <code>{link}</code>"
    kb = [
        [{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
         {"text": "👥 قائمة الكل", "callback_data": "list"}],
        [{"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_add_quick(chat_id, max_devices, data_limit_mb, message_id=None):
    text = (
        "➕ <b>إضافة سريعة</b>\n\n"
        f"📱 أجهزة: {max_devices}\n"
        f"💾 حد: {'بلا حد' if data_limit_mb == 0 else f'{data_limit_mb/1024:.0f}GB'}\n\n"
        f"اكتب الاسم هكذا:\n"
        f"<code>/add اسم</code>\n\n"
        f"أو اكتب الاسم مباشرة وسيتم استخدام الإعدادات أعلاه"
    )
    user_states[chat_id] = {"action": "add_quick", "max_devices": max_devices, "data_limit_mb": data_limit_mb}
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

def cmd_traffic(chat_id, message_id=None):
    users, err = get_users_with_traffic()
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if not users:
        text = "📊 لا يوجد مستخدمين."
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = "📊 <b>تقرير الترافيك</b>\n\n"
    for u in users:
        status = "✅" if u.get("active") else "❌"
        limit_mb = u.get("limit_mb", 0)
        limit = f"{limit_mb/1024:.1f}GB" if limit_mb > 0 else "∞"

        if limit_mb > 0:
            total = u.get("total", 0)
            pct = min(100, total / (limit_mb * 1024 * 1024) * 100)
            filled = int(12 * pct / 100)
            bar = "▓" * filled + "░" * (12 - filled)
            usage = f"{bar} {pct:.1f}%"
        else:
            usage = "∞"

        text += (
            f"{status} <b>{u['name']}</b>\n"
            f"   ⬆️ {fmt(u.get('up',0))} | ⬇️ {fmt(u.get('down',0))} | 💰 {fmt(u.get('total',0))}\n"
            f"   {usage} / {limit}\n\n"
        )

    buttons = []
    for u in users:
        buttons.append([{"text": f"📊 {u['name']}", "callback_data": f"u:{u['name']}"}])
    buttons.append([{"text": "🔙 الرئيسية", "callback_data": "main"}])

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": buttons})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": buttons})

def cmd_restart(chat_id, message_id=None):
    text = "⚠️ <b>إعادة تشغيل xray</b>\n\nسيتم قطع الاتصال على جميع المستخدمين مؤقتاً. متأكد؟"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_restart())
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_restart())

def cmd_restart_confirm(chat_id, message_id=None):
    data, err = api_post("/api/restart")
    if err:
        text = f"⚠️ <b>إعادة تشغيل xray</b>\n\n❌ الـ API ما يدعم إعادة التشغيل حالياً\n\n💡 نفذ يدوياً بالكودسبيس:\n<code>bash /usr/local/bin/start.sh</code>"
    else:
        ok = data.get("xray_running", False)
        text = f"🔄 <b>إعادة تشغيل xray</b>\n\n{'✅ يعمل الآن' if ok else '❌ خطأ في التشغيل'}"
    kb = [[{"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_wake(chat_id, message_id=None):
    ok, msg = start_codespace()
    if ok:
        text = f"🔄 <b>تشغيل الكودسبيس</b>\n\n✅ {msg}\n\n⏳ بعد ما يشتغل، كل الأوامر رح تكتمل."
    else:
        text = f"🔄 <b>تشغيل الكودسبيس</b>\n\n❌ {msg}\n\n📱 أو شغّله يدوياً من تطبيق GitHub"
    kb = [[{"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_notify_settings(chat_id, message_id=None):
    """إعدادات الإشعارات"""
    text = (
        "🔔 <b>إشعارات الترافيك</b>\n\n"
        f"⏱ فحص كل: {NOTIFY_CHECK_INTERVAL // 60} دقيقة\n"
        f"📊 نسبة التحذير: {NOTIFY_THRESHOLD}%\n\n"
        "البوت يفحص الترافيك دورياً ويرسل إشعار لما:\n"
        "• مستخدم يوصل النسبة المحددة\n"
        "• مستخدم يوصل 100% (تم التعطيل)\n"
    )
    kb = [
        [{"text": "📊 فحص فوري", "callback_data": "notify_check"}],
        [{"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_help(chat_id, message_id=None):
    text = (
        "❓ <b>أوامر البوت</b>\n\n"
        "👤 <b>إدارة المستخدمين:</b>\n"
        "/add اسم [أجهزة] [حدMB]\n"
        "/del اسم — حذف\n"
        "/list — عرض الكل\n"
        "/link اسم — عرض الرابط\n"
        "/limit اسم حدMB — تعديل الحد\n"
        "/reset اسم — تصفير العداد\n\n"
        "📊 <b>المراقبة:</b>\n"
        "/traffic — تقرير الترافيك\n"
        "/status — حالة السيرفر\n\n"
        "⚙️ <b>السيرفر:</b>\n"
        "/restart — إعادة تشغيل xray\n"
        "/wake — تشغيل الكودسبيس\n"
        "/notify — إعدادات الإشعارات\n\n"
        "🏗️ <b>الهيكل:</b>\n"
        "🤖 البوت: Render (24/7)\n"
        "📡 xray: GitHub Codespaces\n\n"
        "💡 <b>ملاحظة:</b> بعض الأوامر تحتاج تحديث API بالكودسبيس"
    )
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

# ─── نظام الإشعارات ───

def check_traffic_and_notify():
    """يفحص الترافيك ويرسل إشعارات للأدمين"""
    users, err = get_users_with_traffic()
    if err or not users:
        return

    for u in users:
        name = u["name"]
        limit_mb = u.get("limit_mb", 0)
        total = u.get("total", 0)
        active = u.get("active", True)

        if limit_mb <= 0:
            continue  # بلا حد، تجاهل

        pct = min(100, total / (limit_mb * 1024 * 1024) * 100)

        # إشعار عند الوصول للنسبة المحددة
        if pct >= NOTIFY_THRESHOLD and not notified_users.get(f"{name}:warn"):
            notified_users[f"{name}:warn"] = True
            for admin_id in ADMIN_IDS:
                tg_send(admin_id,
                    f"⚠️ <b>تحذير ترافيك</b>\n\n"
                    f"👤 المستخدم: {name}\n"
                    f"📊 الاستهلاك: {pct:.1f}% ({fmt(total)} / {limit_mb/1024:.1f}GB)\n"
                    f"⬆️ رفع: {fmt(u.get('up',0))}\n"
                    f"⬇️ تحميل: {fmt(u.get('down',0))}"
                )

        # إشعار عند الوصول 100%
        if pct >= 100 and not notified_users.get(f"{name}:full"):
            notified_users[f"{name}:full"] = True
            for admin_id in ADMIN_IDS:
                tg_send(admin_id,
                    f"🚫 <b>تم تجاوز الحد!</b>\n\n"
                    f"👤 المستخدم: {name}\n"
                    f"📊 الاستهلاك: {pct:.1f}% ({fmt(total)} / {limit_mb/1024:.1f}GB)\n"
                    f"{'❌ تم تعطيله تلقائياً' if not active else '⚠️ ما زال مفعل!'}\n\n"
                    f"💡 لتصفير العداد: /reset {name}"
                )

def notify_loop():
    """حلقة الإشعارات الدورية"""
    while True:
        try:
            check_traffic_and_notify()
        except Exception as e:
            print(f"[Notify] Error: {e}")
        time.sleep(NOTIFY_CHECK_INTERVAL)

# بدء الإشعارات بثريد منفصل
notify_thread = threading.Thread(target=notify_loop, daemon=True)
notify_thread.start()

# ─── معالجة الأوامر النصية ───
def handle_message(chat_id, text):
    if not is_admin(chat_id):
        tg_send(chat_id, "❌ غير مصرح لك.")
        return

    # التحقق من حالة المستخدم (إدخال مخصص)
    state = user_states.get(chat_id)
    if state and not text.startswith("/"):
        action = state.get("action")
        name = text.strip()

        if action == "customlimit":
            user_states.pop(chat_id, None)
            try:
                limit_mb = int(name)
                cmd_user_set_limit(chat_id, state["name"], limit_mb)
            except ValueError:
                tg_send(chat_id, "❌ اكتب رقم صحيح (بالميغابايت)\nمثال: 5000 لـ 5GB")
            return

        elif action == "add_quick":
            user_states.pop(chat_id, None)
            max_d = state.get("max_devices", 2)
            limit_mb = state.get("data_limit_mb", 0)
            cmd_add(chat_id, [name, str(max_d), str(limit_mb)])
            return

    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    handlers = {
        "/start": lambda: cmd_start(chat_id),
        "/status": lambda: cmd_status(chat_id),
        "/list": lambda: cmd_list(chat_id),
        "/add": lambda: cmd_add(chat_id, args),
        "/del": lambda: cmd_user_confirm_delete(chat_id, args[0]) if args else tg_send(chat_id, "❌ /del اسم"),
        "/delete": lambda: cmd_user_confirm_delete(chat_id, args[0]) if args else tg_send(chat_id, "❌ /delete اسم"),
        "/link": lambda: cmd_user_link(chat_id, args[0]) if args else tg_send(chat_id, "❌ /link اسم"),
        "/traffic": lambda: cmd_traffic(chat_id),
        "/limit": lambda: cmd_user_limit(chat_id, args[0]) if args else tg_send(chat_id, "❌ /limit اسم"),
        "/reset": lambda: cmd_user_confirm_reset(chat_id, args[0]) if args else tg_send(chat_id, "❌ /reset اسم"),
        "/restart": lambda: cmd_restart(chat_id),
        "/wake": lambda: cmd_wake(chat_id),
        "/notify": lambda: cmd_notify_settings(chat_id),
        "/help": lambda: cmd_help(chat_id),
    }

    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        tg_send(chat_id, "❓ أمر غير معروف. اضغط /help أو استخدم الأزرار.")

# ─── معالجة ضغطات الأزرار ───
def handle_callback(chat_id, message_id, data, callback_query_id):
    if not is_admin(chat_id):
        tg_answer_callback(callback_query_id, "❌ غير مصرح")
        return

    # القائمة الرئيسية
    if data == "main":
        cmd_start(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # قائمة المستخدمين
    elif data == "list":
        cmd_list(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # الترافيك
    elif data == "traffic":
        cmd_traffic(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # حالة السيرفر
    elif data == "status":
        cmd_status(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # إشعارات
    elif data == "notify":
        cmd_notify_settings(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    elif data == "notify_check":
        check_traffic_and_notify()
        tg_edit(chat_id, message_id, "✅ تم الفحص. إذا ما وصل إشعار = ماكو مستخدم وصل للحد.", reply_markup=kb_back_main())
        tg_answer_callback(callback_query_id, "تم الفحص")

    # مساعدة
    elif data == "help":
        cmd_help(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # تشغيل الكودسبيس
    elif data == "wake":
        cmd_wake(chat_id, message_id)
        tg_answer_callback(callback_query_id)

    # إعادة تشغيل
    elif data == "restart":
        cmd_restart(chat_id, message_id)
        tg_answer_callback(callback_query_id)
    elif data == "restart:yes":
        cmd_restart_confirm(chat_id, message_id)
        tg_answer_callback(callback_query_id, "جاري إعادة التشغيل...")

    # إضافة سريعة
    elif data.startswith("add:"):
        parts = data.split(":")
        if len(parts) >= 3:
            max_dev = parts[1]
            limit_mb = parts[2]
            cmd_add_quick(chat_id, int(max_dev), int(limit_mb), message_id)
        tg_answer_callback(callback_query_id)

    elif data == "add_help":
        cmd_add(chat_id, [])
        tg_answer_callback(callback_query_id)

    # تفاصيل مستخدم
    elif data.startswith("u:"):
        parts = data[2:].split(":")

        if len(parts) == 1:
            # u:NAME — عرض التفاصيل
            cmd_user_detail(chat_id, parts[0], message_id)
            tg_answer_callback(callback_query_id)

        elif len(parts) >= 2:
            name = parts[0]
            action = parts[1]

            if action == "link":
                cmd_user_link(chat_id, name, message_id)
                tg_answer_callback(callback_query_id)

            elif action == "limit":
                cmd_user_limit(chat_id, name, message_id)
                tg_answer_callback(callback_query_id)

            elif action == "setlimit":
                limit_mb = parts[2] if len(parts) > 2 else "0"
                cmd_user_set_limit(chat_id, name, int(limit_mb), message_id)
                tg_answer_callback(callback_query_id, f"تم تعيين الحد: {limit_mb}MB")

            elif action == "customlimit":
                user_states[chat_id] = {"action": "customlimit", "name": name}
                tg_edit(chat_id, message_id,
                    f"⌨️ <b>حد مخصص — {name}</b>\n\nاكتب الحد بالميغابايت:\nمثال: 5000 لـ 5GB",
                    reply_markup=kb_back_main())
                tg_answer_callback(callback_query_id)

            elif action == "reset":
                cmd_user_confirm_reset(chat_id, name, message_id)
                tg_answer_callback(callback_query_id)

            elif action == "reset:yes":
                cmd_user_reset(chat_id, name, message_id)
                tg_answer_callback(callback_query_id, "تم التصفير")

            elif action == "del":
                cmd_user_confirm_delete(chat_id, name, message_id)
                tg_answer_callback(callback_query_id)

            elif action == "del:yes":
                cmd_user_delete(chat_id, name, message_id)
                tg_answer_callback(callback_query_id, "تم الحذف")

            elif action == "enable":
                cmd_user_enable(chat_id, name, message_id)
                tg_answer_callback(callback_query_id, "تم التفعيل")

            elif action == "disable":
                cmd_user_disable(chat_id, name, message_id)
                tg_answer_callback(callback_query_id, "تم التعطيل")

    else:
        tg_answer_callback(callback_query_id, "أمر غير معروف")

# ─── Flask Webhook ───

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if not BOT_TOKEN:
        return "no token", 400

    try:
        update = request.get_json(force=True)

        # رسالة نصية
        if "message" in update:
            msg = update["message"]
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")
            if chat_id and text:
                handle_message(chat_id, text)

        # ضغط زر
        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq.get("message", {}).get("chat", {}).get("id")
            message_id = cq.get("message", {}).get("message_id")
            data = cq.get("data", "")
            callback_query_id = cq.get("id", "")
            if chat_id and data:
                handle_callback(chat_id, message_id, data, callback_query_id)

    except Exception as e:
        print(f"Error processing update: {e}")

    return "ok"

@app.route("/")
def index():
    return "xray Bot is running!"

@app.route("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ─── بدء التشغيل ───

def set_webhook():
    """تعيين الـ webhook عند بدء التشغيل"""
    if not BOT_TOKEN:
        print("WARNING: TELEGRAM_BOT_TOKEN not set!")
        return

    # حذف الـ webhook القديم أولاً
    try:
        requests.post(f"{TG_API}/deleteWebhook", json={"drop_pending_updates": True}, timeout=10)
    except: pass

    # الحصول على رابط الـ Render
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        webhook_url = f"{render_url}/{BOT_TOKEN}"
        try:
            r = requests.post(f"{TG_API}/setWebhook",
                json={"url": webhook_url, "drop_pending_updates": True}, timeout=10)
            print(f"Webhook set: {r.json()}")
        except Exception as e:
            print(f"Failed to set webhook: {e}")
    else:
        print("WARNING: RENDER_EXTERNAL_URL not set, webhook not configured")

def polling_fallback():
    """بديل — polling إذا الـ webhook ما اشتغل"""
    if not BOT_TOKEN:
        return

    print("Starting polling fallback...")
    last_offset = 0
    while True:
        try:
            r = requests.post(f"{TG_API}/getUpdates",
                json={"offset": last_offset, "timeout": 30}, timeout=35)
            updates = r.json().get("result", [])
            for update in updates:
                last_offset = update["update_id"] + 1

                if "message" in update:
                    msg = update["message"]
                    chat_id = msg.get("chat", {}).get("id")
                    text = msg.get("text", "")
                    if chat_id and text:
                        handle_message(chat_id, text)

                elif "callback_query" in update:
                    cq = update["callback_query"]
                    chat_id = cq.get("message", {}).get("chat", {}).get("id")
                    message_id = cq.get("message", {}).get("message_id")
                    data = cq.get("data", "")
                    callback_query_id = cq.get("id", "")
                    if chat_id and data:
                        handle_callback(chat_id, message_id, data, callback_query_id)

        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # تعيين الـ webhook
    set_webhook()

    # تشغيل Flask
    port = RENDER_PORT
    print(f"Starting bot on port {port}...")
    print(f"XRAY_API_URL: {XRAY_API_URL or 'NOT SET'}")
    print(f"ADMIN_IDS: {ADMIN_IDS}")
    print(f"NOTIFY: every {NOTIFY_CHECK_INTERVAL}s, threshold {NOTIFY_THRESHOLD}%")

    # تشغيل polling بثريد احتياطي
    poll_thread = threading.Thread(target=polling_fallback, daemon=True)
    poll_thread.start()

    app.run(host="0.0.0.0", port=port)
