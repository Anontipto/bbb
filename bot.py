#!/usr/bin/env python3
# ============================================
#   xray Telegram Bot — يشتغل على Render
#   مع أزرار Inline Keyboard متقدمة
# ============================================

import os, json, time, requests
from flask import Flask, request
from threading import Thread

# ─── الإعدادات ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()]
XRAY_API_URL = os.environ.get("XRAY_API_URL", "")  # https://CODESPACE-10086.app.github.dev
XRAY_API_SECRET = os.environ.get("XRAY_API_SECRET", "changeme")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
CODESPACE_NAME = os.environ.get("CODESPACE_NAME", "")
RENDER_PORT = int(os.environ.get("PORT", 10000))

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

# ─── أدوات ───
def fmt(b):
    if b < 1024: return f"{b} B"
    elif b < 1048576: return f"{b/1024:.1f} KB"
    elif b < 1073741824: return f"{b/1048576:.2f} MB"
    else: return f"{b/1073741824:.2f} GB"

def fmt_duration(sec):
    if sec <= 0: return "—"
    elif sec < 60: return f"{sec}ث"
    elif sec < 3600: return f"{sec//60}د"
    elif sec < 86400: return f"{sec//3600}س {(sec%3600)//60}د"
    else: return f"{sec//86400}ي"

def is_admin(chat_id):
    return chat_id in ADMIN_IDS

# ─── التواصل مع كودسبيس ───
def api_get(endpoint):
    if not XRAY_API_URL:
        return None, "XRAY_API_URL غير مضبوط"
    try:
        r = requests.get(
            f"{XRAY_API_URL}{endpoint}",
            headers={"Authorization": f"Bearer {XRAY_API_SECRET}"},
            timeout=15
        )
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "الكودسبيس مطفي"
    except Exception as e:
        return None, str(e)

def api_post(endpoint, data=None):
    if not XRAY_API_URL:
        return None, "XRAY_API_URL غير مضبوط"
    try:
        r = requests.post(
            f"{XRAY_API_URL}{endpoint}",
            json=data or {},
            headers={"Authorization": f"Bearer {XRAY_API_SECRET}"},
            timeout=15
        )
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "الكودسبيس مطفي — جرب زر تشغيل الكودسبيس"
    except Exception as e:
        return None, str(e)

def start_codespace():
    if not GITHUB_TOKEN or not CODESPACE_NAME:
        return False, "GH_TOKEN أو CODESPACE_NAME غير مضبوط"
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        r = requests.post(
            f"https://api.github.com/user/codespaces/{CODESPACE_NAME}/start",
            headers=headers, timeout=30
        )
        if r.status_code in [200, 202]:
            return True, "جاري التشغيل... يأخذ ١-٢ دقيقة"
        return False, f"خطأ: {r.status_code}"
    except Exception as e:
        return False, str(e)

# ─── أزرار Inline Keyboard ───

def kb_main():
    """القائمة الرئيسية"""
    return {
        "inline_keyboard": [
            [
                {"text": "👥 المستخدمين", "callback_data": "list"},
                {"text": "📊 الترافيك", "callback_data": "traffic"},
            ],
            [
                {"text": "🏆 أكتر المواقع", "callback_data": "top"},
                {"text": "🔴 حي الآن", "callback_data": "live"},
            ],
            [
                {"text": "➕ إضافة مستخدم", "callback_data": "add_help"},
                {"text": "⚙️ حالة السيرفر", "callback_data": "status"},
            ],
            [
                {"text": "🔄 تشغيل الكودسبيس", "callback_data": "wake"},
                {"text": "❓ مساعدة", "callback_data": "help"},
            ],
        ]
    }

def kb_back_main():
    """زر الرجوع للقائمة الرئيسية"""
    return {
        "inline_keyboard": [
            [{"text": "🔙 القائمة الرئيسية", "callback_data": "main"}]
        ]
    }

def kb_user_list(users):
    """أزرار لكل مستخدم في القائمة"""
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
    """أزرار تفاصيل المستخدم"""
    buttons = [
        [
            {"text": "🔗 الرابط", "callback_data": f"u:{name}:link"},
            {"text": "🌐 مواقعه", "callback_data": f"u:{name}:sites"},
        ],
        [
            {"text": "💾 تعديل الحد", "callback_data": f"u:{name}:limit"},
            {"text": "📱 تعديل الأجهزة", "callback_data": f"u:{name}:devices"},
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
    """خيارات حدود البيانات"""
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
                {"text": "⌨️ حد مخصص", "callback_data": f"u:{name}:customlimit"},
            ],
            [
                {"text": "🔙 رجوع", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_devices_options(name):
    """خيارات عدد الأجهزة"""
    return {
        "inline_keyboard": [
            [
                {"text": "1 جهاز", "callback_data": f"u:{name}:setdev:1"},
                {"text": "2 جهاز", "callback_data": f"u:{name}:setdev:2"},
                {"text": "3 أجهزة", "callback_data": f"u:{name}:setdev:3"},
            ],
            [
                {"text": "4 أجهزة", "callback_data": f"u:{name}:setdev:4"},
                {"text": "5 أجهزة", "callback_data": f"u:{name}:setdev:5"},
                {"text": "♾️ بلا حد", "callback_data": f"u:{name}:setdev:99"},
            ],
            [
                {"text": "⌨️ عدد مخصص", "callback_data": f"u:{name}:customdev"},
            ],
            [
                {"text": "🔙 رجوع", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_delete(name):
    """تأكيد الحذف"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، احذف", "callback_data": f"u:{name}:del:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_reset(name):
    """تأكيد تصفير العداد"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، صفر", "callback_data": f"u:{name}:reset:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": f"u:{name}"},
            ],
        ]
    }

def kb_confirm_restart():
    """تأكيد إعادة تشغيل xray"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ نعم، أعد التشغيل", "callback_data": "restart:yes"},
                {"text": "❌ لا، ألغِ", "callback_data": "main"},
            ],
        ]
    }

def kb_add_quick():
    """أزرار إضافة سريعة"""
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
    """تعديل رسالة موجودة بدل إرسال جديدة"""
    data = {"chat_id": chat_id, "message_id": message_id, "text": text[:4096], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TG_API}/editMessageText", json=data, timeout=10)
        if r.status_code == 400 and "message is not modified" in r.text:
            pass  # الرسالة نفسها، عادي
    except: pass

def tg_answer_callback(callback_query_id, text=""):
    """الرد على الضغطة (يظهر إشعار صغير)"""
    try:
        requests.post(f"{TG_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
    except: pass

# ─── متغيرات الحالة ───
# لتتبع حالة المستخدمين (مثل انتظار إدخال مخصص)
user_states = {}  # {chat_id: {"action": "customlimit", "name": "ali"}}

# ─── أوامر البوت ───

def cmd_start(chat_id, message_id=None):
    text = (
        "🚀 <b>بوت إدارة xray</b>\n\n"
        "🔌 السيرفر: GitHub Codespaces\n"
        "🤖 البوت: Render (٢٤/٧)\n\n"
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
    data, err = api_get("/api/list")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    users = data.get("users", [])
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
        total = u.get("traffic_total", 0)
        limit = f"{u.get('data_limit_mb',0)/1024:.1f}GB" if u.get("data_limit_mb", 0) > 0 else "∞"
        text += f"\n{status} <b>{u['name']}</b> — {fmt(total)} / {limit}"

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_user_list(users))
    else:
        tg_send(chat_id, text, reply_markup=kb_user_list(users))

def cmd_user_detail(chat_id, name, message_id=None):
    """عرض تفاصيل مستخدم واحد"""
    data, err = api_get("/api/list")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    user = None
    for u in data.get("users", []):
        if u["name"] == name:
            user = u
            break

    if not user:
        text = f"❌ المستخدم '{name}' غير موجود"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    limit = f"{user.get('data_limit_mb',0)/1024:.1f}GB" if user.get("data_limit_mb", 0) > 0 else "♾️ بلا حد"
    total = user.get("traffic_total", 0)
    up = user.get("traffic_up", 0)
    down = user.get("traffic_down", 0)

    # شريط الاستهلاك
    limit_mb = user.get("data_limit_mb", 0)
    if limit_mb > 0:
        pct = min(100, total / (limit_mb * 1024 * 1024) * 100)
        filled = int(15 * pct / 100)
        bar = "▓" * filled + "░" * (15 - filled)
        usage_line = f"\n📊 {bar} {pct:.1f}%"
    else:
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
    """عرض رابط المستخدم"""
    data, err = api_get("/api/list")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    for u in data.get("users", []):
        if u["name"] == name:
            text = (
                f"🔗 <b>رابط {name}</b>\n\n"
                f"<code>{u.get('link','')}</code>\n\n"
                f"📋 انسخ الرابط وألصقه ببرنامج v2rayNG / Nekobox / Streisand"
            )
            kb = [
                [{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
                 {"text": "🔙 الرئيسية", "callback_data": "main"}]
            ]
            if message_id:
                tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
            else:
                tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
            return

    text = f"❌ المستخدم '{name}' غير موجود"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

def cmd_user_sites(chat_id, name, message_id=None):
    """مواقع المستخدم"""
    data, err = api_get(f"/api/sites?name={name}")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    sites = data.get("sites", [])
    if not sites:
        text = f"🌐 لا يوجد بيانات مواقع لـ {name} بعد."
        kb = [[{"text": "🔙 تفاصيل المستخدم", "callback_data": f"u:{name}"}]]
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
        else:
            tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})
        return

    text = f"🌐 <b>مواقع {name}</b>\n\n"
    total = sum(s.get("bytes", 0) for s in sites)

    for i, s in enumerate(sites[:15], 1):
        pct = (s.get("bytes", 0) / total * 100) if total > 0 else 0
        text += (
            f"<b>{i}.</b> {s['domain']}\n"
            f"   💰 {fmt(s.get('bytes',0))} ({pct:.1f}%) | ⏱ {fmt_duration(s.get('duration_sec',0))}\n"
        )

    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_limit(chat_id, name, message_id=None):
    """عرض خيارات تعديل الحد"""
    text = f"💾 <b>تعديل حد البيانات — {name}</b>\n\nاختار الحد الجديد:"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_limit_options(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_limit_options(name))

def cmd_user_devices(chat_id, name, message_id=None):
    """عرض خيارات تعديل الأجهزة"""
    text = f"📱 <b>تعديل عدد الأجهزة — {name}</b>\n\nاختار العدد الجديد:"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_devices_options(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_devices_options(name))

def cmd_user_confirm_delete(chat_id, name, message_id=None):
    """تأكيد حذف المستخدم"""
    text = f"⚠️ <b>تأكيد حذف: {name}</b>\n\nهل أنت متأكد؟ هذا الإجراء لا يمكن التراجع عنه!"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_delete(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_delete(name))

def cmd_user_confirm_reset(chat_id, name, message_id=None):
    """تأكيد تصفير العداد"""
    text = f"🔄 <b>تصفير عداد: {name}</b>\n\nسيتم تصفير جميع بيانات الترافيك. متأكد؟"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_reset(name))
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_reset(name))

def cmd_user_set_limit(chat_id, name, limit_mb, message_id=None):
    """تعيين حد البيانات"""
    data, err = api_post("/api/limit", {"name": name, "data_limit_mb": int(limit_mb)})
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if data.get("error"):
        text = f"❌ {data['error']}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    limit_str = f"{int(limit_mb)/1024:.1f}GB" if int(limit_mb) > 0 else "♾️ بلا حد"
    text = f"✅ <b>تم تعديل حد {name}</b>\n\n💾 الحد الجديد: {limit_str}"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_set_devices(chat_id, name, count, message_id=None):
    """تعيين عدد الأجهزة"""
    data, err = api_post("/api/devices", {"name": name, "max_devices": int(count)})
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if data.get("error"):
        text = f"❌ {data['error']}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    dev_str = f"{count} جهاز" if int(count) < 99 else "♾️ بلا حد"
    text = f"✅ <b>تم تعديل أجهزة {name}</b>\n\n📱 الأجهزة: {dev_str}"
    kb = [[{"text": "👤 تفاصيل المستخدم", "callback_data": f"u:{name}"},
           {"text": "🔙 الرئيسية", "callback_data": "main"}]]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_delete(chat_id, name, message_id=None):
    """حذف المستخدم"""
    data, err = api_post("/api/del", {"name": name})
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if data.get("error"):
        text = f"❌ {data['error']}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = f"🗑️ <b>تم حذف: {name}</b>"
    kb = [
        [{"text": "👥 قائمة المستخدمين", "callback_data": "list"},
         {"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_user_reset(chat_id, name, message_id=None):
    """تصفير العداد"""
    data, err = api_post("/api/reset", {"name": name})
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = f"✅ <b>تم تصفير عداد {name}</b>"
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
            "طريقة ١ — أزرار سريعة:\n"
            "اضغط على أحد الأزرار بالأسفل\n\n"
            "طريقة ٢ — كتابة:\n"
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
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    if data.get("error"):
        text = f"❌ {data['error']}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    limit_str = f"{data_limit_mb/1024:.1f}GB" if data_limit_mb > 0 else "بلا حد"
    text = (
        f"✅ <b>تم إضافة: {name}</b>\n\n"
        f"📱 أجهزة: {max_devices}\n"
        f"💾 حد: {limit_str}\n"
        f"🔘 xray: {'يعمل ✓' if data.get('xray_running') else 'خطأ ✗'}\n\n"
        f"🔗 <code>{data.get('link','')}</code>"
    )
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
    """إضافة سريعة بالأزرار — لازم اسم"""
    # نحتاج اسم، فنطلب من المستخدم يكتب
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

def cmd_del(chat_id, args, message_id=None):
    if len(args) < 1:
        text = "❌ استعمل: <code>/del اسم</code>\n\nأو اضغط على المستخدم من القائمة واختر حذف"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return
    cmd_user_confirm_delete(chat_id, args[0], message_id)

def cmd_link(chat_id, args, message_id=None):
    if len(args) < 1:
        text = "❌ استعمل: <code>/link اسم</code>\n\nأو اضغط على المستخدم من القائمة واختر الرابط"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return
    cmd_user_link(chat_id, args[0], message_id)

def cmd_traffic(chat_id, message_id=None):
    data, err = api_get("/api/traffic")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    traffic = data.get("traffic", [])
    if not traffic:
        text = "📊 لا يوجد مستخدمين."
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = "📊 <b>تقرير الترافيك</b>\n\n"
    for t in traffic:
        status = "✅" if t.get("active") else "❌"
        limit = f"{t.get('limit_mb',0)/1024:.1f}GB" if t.get("limit_mb", 0) > 0 else "∞"
        pct = t.get("percent", -1)
        if pct >= 0:
            filled = int(12 * pct / 100)
            bar = "▓" * filled + "░" * (12 - filled)
            usage = f"{bar} {pct:.1f}%"
        else:
            usage = "∞"

        text += (
            f"{status} <b>{t['name']}</b>\n"
            f"   ⬆️ {fmt(t.get('up',0))} | ⬇️ {fmt(t.get('down',0))} | 💰 {fmt(t.get('total',0))}\n"
            f"   {usage} / {limit}\n\n"
        )

    # أزرار لكل مستخدم
    buttons = []
    for t in traffic:
        buttons.append([{"text": f"📊 {t['name']}", "callback_data": f"u:{t['name']}"}])
    buttons.append([{"text": "🔙 الرئيسية", "callback_data": "main"}])

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": buttons})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": buttons})

def cmd_top(chat_id, message_id=None):
    data, err = api_get("/api/top")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    top = data.get("top", [])
    if not top:
        text = "🏆 لا يوجد بيانات بعد. استخدم الانترنت وجرب مرة ثانية."
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = "🏆 <b>أكتر المواقع استخداماً</b>\n\n"
    for i, s in enumerate(top, 1):
        pct = s.get("percent", 0)
        filled = int(10 * pct / 100)
        bar = "▓" * filled + "░" * (10 - filled)
        users_str = ", ".join(s.get("users", [])[:3])

        text += (
            f"<b>{i}.</b> {s['domain']}\n"
            f"   💰 {fmt(s['bytes'])} {bar} {pct:.1f}%\n"
            f"   🔗 {s['connections']} اتصال | 👥 {users_str} | ⏱ {fmt_duration(s.get('duration_sec',0))}\n\n"
        )

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

def cmd_sites(chat_id, args, message_id=None):
    endpoint = f"/api/sites?name={args[0]}" if args else "/api/sites"
    data, err = api_get(endpoint)
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    sites = data.get("sites", [])
    if not sites:
        text = "🌐 لا يوجد بيانات بعد."
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    name = args[0] if args else "الكل"
    text = f"🌐 <b>مواقع {name}</b>\n\n"
    total = sum(s.get("bytes", 0) for s in sites)

    for i, s in enumerate(sites[:15], 1):
        pct = (s.get("bytes", 0) / total * 100) if total > 0 else 0
        text += (
            f"<b>{i}.</b> {s['domain']}\n"
            f"   💰 {fmt(s.get('bytes',0))} ({pct:.1f}%) | 🔗 {s.get('connections',0)} | ⏱ {fmt_duration(s.get('duration_sec',0))}\n\n"
        )

    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

def cmd_live(chat_id, message_id=None):
    data, err = api_get("/api/live")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    live = data.get("live", [])
    if not live:
        text = "🔴 لا يوجد اتصالات حية الآن."
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

    text = "🔴 <b>اتصالات حية</b> (آخر ٥ دقائق)\n\n"
    for l in live:
        text += f"👤 <b>{l['user']}</b>\n"
        for d in l.get("domains", [])[:8]:
            text += f"   🌐 {d['domain']} — {d['count']} اتصال\n"
        text += "\n"

    kb = [
        [{"text": "🔄 تحديث", "callback_data": "live"}],
        [{"text": "🔙 الرئيسية", "callback_data": "main"}]
    ]
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup={"inline_keyboard": kb})
    else:
        tg_send(chat_id, text, reply_markup={"inline_keyboard": kb})

def cmd_restart(chat_id, message_id=None):
    """طلب تأكيد إعادة التشغيل"""
    text = "⚠️ <b>إعادة تشغيل xray</b>\n\nسيتم قطع الاتصال على جميع المستخدمين مؤقتاً. متأكد؟"
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_confirm_restart())
    else:
        tg_send(chat_id, text, reply_markup=kb_confirm_restart())

def cmd_restart_confirm(chat_id, message_id=None):
    """تنفيذ إعادة التشغيل"""
    data, err = api_post("/api/restart")
    if err:
        text = f"❌ {err}"
        if message_id:
            tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
        else:
            tg_send(chat_id, text, reply_markup=kb_back_main())
        return

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

def cmd_help(chat_id, message_id=None):
    text = (
        "❓ <b>أوامر البوت</b>\n\n"
        "👤 <b>إدارة المستخدمين:</b>\n"
        "/add اسم [أجهزة] [حدMB]\n"
        "/del اسم — حذف\n"
        "/list — عرض الكل\n"
        "/link اسم — عرض الرابط\n"
        "/limit اسم حدMB — تعديل الحد\n"
        "/devices اسم عدد — تعديل الأجهزة\n"
        "/reset اسم — تصفير العداد\n\n"
        "📊 <b>المراقبة:</b>\n"
        "/traffic — تقرير الترافيك\n"
        "/top — أكتر المواقع\n"
        "/sites [اسم] — المواقع المزارة\n"
        "/live — اتصالات حية\n\n"
        "⚙️ <b>السيرفر:</b>\n"
        "/status — حالة السيرفر\n"
        "/restart — إعادة تشغيل xray\n"
        "/wake — تشغيل الكودسبيس\n\n"
        "🏗️ <b>الهيكل:</b>\n"
        "🤖 البوت: Render (٢٤/٧)\n"
        "📡 xray: GitHub Codespaces"
    )
    if message_id:
        tg_edit(chat_id, message_id, text, reply_markup=kb_back_main())
    else:
        tg_send(chat_id, text, reply_markup=kb_back_main())

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

        elif action == "customdev":
            user_states.pop(chat_id, None)
            try:
                count = int(name)
                cmd_user_set_devices(chat_id, state["name"], count)
            except ValueError:
                tg_send(chat_id, "❌ اكتب رقم صحيح\nمثال: 3")
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
        "/del": lambda: cmd_del(chat_id, args),
        "/delete": lambda: cmd_del(chat_id, args),
        "/link": lambda: cmd_link(chat_id, args),
        "/traffic": lambda: cmd_traffic(chat_id),
        "/top": lambda: cmd_top(chat_id),
        "/sites": lambda: cmd_sites(chat_id, args),
        "/live": lambda: cmd_live(chat_id),
        "/limit": lambda: cmd_user_limit(chat_id, args[0]) if args else tg_send(chat_id, "❌ /limit اسم"),
        "/devices": lambda: cmd_user_devices(chat_id, args[0]) if args else tg_send(chat_id, "❌ /devices اسم"),
        "/reset": lambda: cmd_user_confirm_reset(chat_id, args[0]) if args else tg_send(chat_id, "❌ /reset اسم"),
        "/restart": lambda: cmd_restart(chat_id),
        "/wake": lambda: cmd_wake(chat_id),
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
        tg_answer_callback(callback_query_id)
        cmd_start(chat_id, message_id)

    elif data == "list":
        tg_answer_callback(callback_query_id)
        cmd_list(chat_id, message_id)

    elif data == "traffic":
        tg_answer_callback(callback_query_id)
        cmd_traffic(chat_id, message_id)

    elif data == "top":
        tg_answer_callback(callback_query_id)
        cmd_top(chat_id, message_id)

    elif data == "live":
        tg_answer_callback(callback_query_id, "🔄 جاري التحديث...")
        cmd_live(chat_id, message_id)

    elif data == "status":
        tg_answer_callback(callback_query_id)
        cmd_status(chat_id, message_id)

    elif data == "wake":
        tg_answer_callback(callback_query_id, "🔄 جاري التشغيل...")
        cmd_wake(chat_id, message_id)

    elif data == "help":
        tg_answer_callback(callback_query_id)
        cmd_help(chat_id, message_id)

    elif data == "add_help":
        tg_answer_callback(callback_query_id)
        cmd_add(chat_id, [], message_id)

    elif data == "restart":
        tg_answer_callback(callback_query_id)
        cmd_restart(chat_id, message_id)

    elif data == "restart:yes":
        tg_answer_callback(callback_query_id, "🔄 جاري إعادة التشغيل...")
        cmd_restart_confirm(chat_id, message_id)

    # إضافة سريعة
    elif data.startswith("add:"):
        tg_answer_callback(callback_query_id)
        parts = data.split(":")
        if len(parts) == 3:
            cmd_add_quick(chat_id, int(parts[1]), int(parts[2]), message_id)

    # أزرار المستخدم
    elif data.startswith("u:"):
        parts = data[2:].split(":")

        if len(parts) == 1:
            # u:NAME — عرض تفاصيل المستخدم
            tg_answer_callback(callback_query_id)
            cmd_user_detail(chat_id, parts[0], message_id)

        elif len(parts) == 2:
            action = parts[1]

            if action == "link":
                tg_answer_callback(callback_query_id)
                cmd_user_link(chat_id, parts[0], message_id)

            elif action == "sites":
                tg_answer_callback(callback_query_id)
                cmd_user_sites(chat_id, parts[0], message_id)

            elif action == "limit":
                tg_answer_callback(callback_query_id)
                cmd_user_limit(chat_id, parts[0], message_id)

            elif action == "devices":
                tg_answer_callback(callback_query_id)
                cmd_user_devices(chat_id, parts[0], message_id)

            elif action == "del":
                tg_answer_callback(callback_query_id)
                cmd_user_confirm_delete(chat_id, parts[0], message_id)

            elif action == "reset":
                tg_answer_callback(callback_query_id)
                cmd_user_confirm_reset(chat_id, parts[0], message_id)

            elif action == "disable":
                tg_answer_callback(callback_query_id, "جاري التعطيل...")
                api_post("/api/limit", {"name": parts[0], "data_limit_mb": 1})
                cmd_user_detail(chat_id, parts[0], message_id)

            elif action == "enable":
                tg_answer_callback(callback_query_id, "جاري التفعيل...")
                api_post("/api/limit", {"name": parts[0], "data_limit_mb": 0})
                cmd_user_detail(chat_id, parts[0], message_id)

            elif action == "customlimit":
                tg_answer_callback(callback_query_id)
                user_states[chat_id] = {"action": "customlimit", "name": parts[0]}
                tg_edit(chat_id, message_id,
                    f"💾 <b>حد مخصص لـ {parts[0]}</b>\n\nاكتب الحد بالميغابايت:\n"
                    f"مثال: <code>5000</code> = 5GB\n<code>10240</code> = 10GB",
                    reply_markup=kb_back_main())

            elif action == "customdev":
                tg_answer_callback(callback_query_id)
                user_states[chat_id] = {"action": "customdev", "name": parts[0]}
                tg_edit(chat_id, message_id,
                    f"📱 <b>عدد أجهزة مخصص لـ {parts[0]}</b>\n\nاكتب العدد:\nمثال: <code>3</code>",
                    reply_markup=kb_back_main())

        elif len(parts) == 3:
            sub_action = parts[1]

            if sub_action == "del" and parts[2] == "yes":
                tg_answer_callback(callback_query_id, "🗑️ جاري الحذف...")
                cmd_user_delete(chat_id, parts[0], message_id)

            elif sub_action == "reset" and parts[2] == "yes":
                tg_answer_callback(callback_query_id, "🔄 جاري التصفير...")
                cmd_user_reset(chat_id, parts[0], message_id)

            elif sub_action == "setlimit":
                tg_answer_callback(callback_query_id, "💾 جاري التعديل...")
                cmd_user_set_limit(chat_id, parts[0], parts[2], message_id)

            elif sub_action == "setdev":
                tg_answer_callback(callback_query_id, "📱 جاري التعديل...")
                cmd_user_set_devices(chat_id, parts[0], parts[2], message_id)

    else:
        tg_answer_callback(callback_query_id, "❓ خيار غير معروف")

# ─── Webhook handler ───
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.json
    try:
        if "message" in update:
            msg = update["message"]
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")
            if text:
                handle_message(chat_id, text)

        elif "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            message_id = cb.get("message", {}).get("message_id")
            data = cb.get("data", "")
            cb_id = cb.get("id", "")
            if data:
                handle_callback(chat_id, message_id, data, cb_id)
    except Exception as e:
        print(f"Error: {e}")

    return "ok"

@app.route("/")
def index():
    return "xray Bot is running! 🚀"

# ─── تشغيل ───
def setup_webhook():
    if not BOT_TOKEN:
        print("[bot] TELEGRAM_BOT_TOKEN غير مضبوط!")
        return

    requests.post(f"{TG_API}/deleteWebhook", timeout=10)

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if render_url:
        webhook_url = f"{render_url}/{BOT_TOKEN}"
        r = requests.get(f"{TG_API}/setWebhook?url={webhook_url}", timeout=10)
        if r.json().get("ok"):
            print(f"[bot] Webhook set: {webhook_url}")
        else:
            print(f"[bot] Webhook error: {r.json()}")
    else:
        print("[bot] RENDER_EXTERNAL_URL not found, using polling...")
        Thread(target=polling, daemon=True).start()

def polling():
    last_id = 0
    while True:
        try:
            r = requests.get(f"{TG_API}/getUpdates", params={"offset": last_id, "timeout": 30}, timeout=35)
            data = r.json()
            if data.get("ok"):
                updates = data.get("result", [])
                for update in updates:
                    last_id = update["update_id"] + 1
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg.get("chat", {}).get("id")
                        text = msg.get("text", "")
                        if text:
                            handle_message(chat_id, text)
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb.get("message", {}).get("chat", {}).get("id")
                        message_id = cb.get("message", {}).get("message_id")
                        data_cb = cb.get("data", "")
                        cb_id = cb.get("id", "")
                        if data_cb:
                            handle_callback(chat_id, message_id, data_cb, cb_id)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    setup_webhook()
    app.run(host="0.0.0.0", port=RENDER_PORT)
