"""
Auto Telegram Channel Poster
- Gemini (free) se English + Hinglish content
- Pollinations (free) se AI image, upar Pillow se stylish text card
- Roz channel ke hisab se 1-2 post, alag-alag topic
Run: python bot.py  (Railway worker)
Telegram commands (sirf ADMIN_IDS ke liye):
  /add Name chat_id [love|motivation|fact] [09:00,21:00]
  /remove Name | /list | /test Name [live] | /times Name 09:00,21:00 | /myid | /help
"""
import os, io, re, json, time, random, sys, html, logging, threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poster")

BOT_TOKEN = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
DATA_DIR = os.getenv("DATA_DIR", ".")
# folder na ho (Volume attach nahi hua) ya likh na sakein to current folder use karo
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    _t = os.path.join(DATA_DIR, ".w")
    open(_t, "w").close()
    os.remove(_t)
except Exception:
    logging.warning("DATA_DIR '%s' use nahi ho sakta, '.' use kar raha hu (Volume attach karo)", DATA_DIR)
    DATA_DIR = "."
ADMIN_IDS = {int(x) for x in re.findall(r"-?\d+", os.getenv("ADMIN_IDS", ""))}
LOCK = threading.RLock()
STATE_FILE = os.path.join(DATA_DIR, "state.json")
FONT_FILE = os.path.join(DATA_DIR, "font.ttf")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"

# ----------------------------------------------------------------------
# KINDS (channel ke type) -- naya type chahiye to yahan ek block jodo
# ----------------------------------------------------------------------
KINDS = {
    "love": {
        "times": ["09:00", "22:30"],
        "accent": (255, 105, 140),
        "about": "Soulful love quotes, pyaar, breakup, yaadein, ehsaas, intezaar, "
                 "self-love, dosti-wali feelings. Emotional but classy.",
        "themes": ["pehla pyaar", "adhoora pyaar", "intezaar", "yaadein", "breakup ke baad healing",
                   "sacha pyaar", "long distance", "self-love", "chup rehkar pyaar", "rishton ki value",
                   "letting go", "raat ki tanhai", "bharosa", "ek tarfa pyaar", "saath ka ehsaas",
                   "dil ki baat", "judaai", "shukriya us insaan ka", "pyaar mein izzat", "sukoon"],
        "image_style": "dreamy romantic cinematic illustration, soft pink and purple glow, "
                       "silhouettes, moon, hearts, bokeh, no text",
    },
    "motivation": {
        "times": ["06:30", "18:00"],
        "accent": (255, 150, 40),
        "about": "Daily motivation: discipline, success mindset, hard work, consistency, "
                 "failure se seekhna, focus, confidence, early morning, never give up.",
        "themes": ["discipline", "consistency", "failure se seekhna", "focus", "confidence",
                   "mehnat", "sabr", "time ki value", "comfort zone", "self belief",
                   "shuruaat karna", "haar na maanna", "habits", "sapne", "negative logon se door",
                   "apne aap se muqabla", "patience", "growth mindset", "action lena", "risk lena"],
        "image_style": "epic cinematic motivational scene, golden sunrise, mountain peak, "
                       "lone figure, dramatic light, no text",
    },
    "fact": {
        "times": ["13:00", "20:00"],
        "accent": (80, 170, 255),
        "about": "Mind-blowing, TRUE, verifiable facts: space, animals, human body, history, "
                 "science, ocean, geography, technology, food, nature.",
        "themes": ["space", "ocean", "animals", "human body", "history", "science", "geography",
                   "insects", "plants", "technology", "food", "weather", "dinosaurs", "brain",
                   "records", "languages", "chemistry", "physics", "birds", "India"],
        "image_style": "vivid high-quality realistic photo or detailed digital art related to the fact, "
                       "dramatic lighting, no text",
    },
}

# pehli baar chalne par ye 3 channel apne aap add ho jaate hain
DEFAULTS = {
    "TheHeartVerse": ("love", "@TheHeartVerse"),
    "RiseFuelQuotes": ("motivation", "@RiseFuelQuotes"),
    "FactForge": ("fact", "@FactForge"),
}


def full_cfg(entry):
    """state wali entry + kind ka template mila ke poora config"""
    return {**KINDS[entry["kind"]], "kind": entry["kind"],
            "chat_id": entry["chat_id"], "times": entry["times"]}


# ----------------------------------------------------------------------
# State (history + done slots)
# ----------------------------------------------------------------------
def load_state():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("done", [])
    st.setdefault("history", {})
    if "channels" not in st:
        st["channels"] = {n: {"chat_id": c, "kind": k, "times": KINDS[k]["times"]}
                          for n, (k, c) in DEFAULTS.items()}
    return st


def save_state(st):
    with LOCK:
        st["done"] = st["done"][-200:]
        for k in st["history"]:
            st["history"][k] = st["history"][k][-60:]
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE_FILE)


# ----------------------------------------------------------------------
# Content (Gemini)
# ----------------------------------------------------------------------
KIND_RULES = {
    "love": "english = 1-2 emotional lines (max 30 words). hinglish = same meaning in natural Roman-script "
            "Hinglish (Hindi in English letters), max 30 words. closing = 3 short words style like 'Let go. Learn. Grow.'",
    "motivation": "english = ONE powerful quote line (max 22 words). hinglish = natural Roman-script Hinglish "
                  "version (Hindi in English letters). closing = short punchy line like 'Stay focused. Stay unstoppable.'",
    "fact": "english = starts with 'Did you know?' then 2-3 short lines with the fact and a punchline. "
            "hinglish = starts with 'Kya tumhe pata hai?' then same fact in Roman-script Hinglish. "
            "Facts MUST be 100% true and well-established. closing = short line like 'Mind blown!'",
}


def gemini_json(prompt, tries=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.1, "responseMimeType": "application/json"},
    }
    last = None
    for i in range(tries):
        try:
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=body, timeout=90)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            data = json.loads(text)
            if isinstance(data, list):
                data = data[0]
            for k in ("headline", "english", "hinglish", "closing", "image_prompt", "hashtags"):
                if k not in data:
                    raise ValueError(f"missing {k}")
            return data
        except Exception as e:
            last = e
            log.warning("Gemini try %s failed: %s", i + 1, e)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Gemini fail: {last}")


def make_content(name, cfg, history):
    theme = random.choice(cfg["themes"])
    avoid = "\n".join(f"- {h}" for h in history[-40:]) or "(none)"
    prompt = f"""You write daily posts for a Telegram channel.
Channel: {name}
Niche: {cfg['about']}
Today's theme: {theme}
Today's date: {datetime.now(TZ):%A, %d %B %Y}

Rules:
- Content must be ORIGINAL (never copy famous copyrighted quotes word-for-word).
- Must be completely different from these recent posts:
{avoid}
- {KIND_RULES[cfg['kind']]}
- headline = very short English title for image (max 8 words, no emojis).
- hashtags = array of exactly 3 hashtags, first one is #{name}.
- image_prompt = English, one vivid scene matching the post, style: {cfg['image_style']}. Never include any text/letters in the image.
Return ONLY JSON with keys: headline, english, hinglish, closing, image_prompt, hashtags."""
    return gemini_json(prompt)


# ----------------------------------------------------------------------
# Image
# ----------------------------------------------------------------------
def get_font(size):
    if not os.path.exists(FONT_FILE):
        try:
            r = requests.get(FONT_URL, timeout=30)
            r.raise_for_status()
            with open(FONT_FILE, "wb") as f:
                f.write(r.content)
        except Exception as e:
            log.warning("font download fail: %s", e)
    try:
        return ImageFont.truetype(FONT_FILE, size)
    except Exception:
        try:
            return ImageFont.load_default(size)
        except Exception:
            return ImageFont.load_default()


def ai_background(prompt, size=1080):
    for i in range(3):
        try:
            url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            r = requests.get(url, params={"width": size, "height": size, "nologo": "true",
                                          "seed": random.randint(1, 10**6)}, timeout=120)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB").resize((size, size))
        except Exception as e:
            log.warning("image try %s fail: %s", i + 1, e)
            time.sleep(4)
    return None


def gradient_bg(accent, size=1080):
    img = Image.new("RGB", (size, size))
    px = img.load()
    top = tuple(int(c * 0.35) for c in accent)
    bottom = (10, 10, 25)
    for y in range(size):
        t = y / size
        col = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(size):
            px[x, y] = col
    return img


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for w in text.split():
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_image(cfg, data, name):
    size = 1080
    bg = ai_background(data["image_prompt"], size) or gradient_bg(cfg["accent"], size)
    base = bg.convert("RGBA")
    base = Image.alpha_composite(base, Image.new("RGBA", (size, size), (0, 0, 0, 120)))
    # neeche aur upar gehra shade
    shade = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(size):
        a = int(110 * (abs(y - size / 2) / (size / 2)) ** 2)
        sd.line([(0, y), (size, y)], fill=(0, 0, 0, a))
    base = Image.alpha_composite(base, shade)
    d = ImageDraw.Draw(base)

    headline = data["headline"].strip()
    if cfg["kind"] == "motivation":
        headline = data["english"].strip().strip('"')
    max_w = size - 180
    fs = 96
    while fs > 40:
        f = get_font(fs)
        lines = wrap(d, headline, f, max_w)
        if len(lines) <= 5 and len(lines) * fs * 1.25 < 560:
            break
        fs -= 6
    lh = int(fs * 1.25)
    y = (size - lh * len(lines)) // 2 - 20
    for ln in lines:
        w = d.textlength(ln, font=f)
        x = (size - w) / 2
        d.text((x + 3, y + 3), ln, font=f, fill=(0, 0, 0, 200))
        d.text((x, y), ln, font=f, fill=(255, 255, 255, 255))
        y += lh

    # accent line + brand
    d.rounded_rectangle([(size / 2 - 60, y + 15), (size / 2 + 60, y + 21)], radius=3, fill=cfg["accent"] + (255,))
    bf = get_font(38)
    tag = "@" + name
    w = d.textlength(tag, font=bf)
    d.text(((size - w) / 2, size - 110), tag, font=bf, fill=cfg["accent"] + (255,))

    out = io.BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


# ----------------------------------------------------------------------
# Caption
# ----------------------------------------------------------------------
def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def build_caption(name, cfg, d):
    now = datetime.now(TZ)
    e = lambda s: html.escape(str(s).strip())
    tags = " ".join(t if t.startswith("#") else "#" + t for t in d["hashtags"][:3])
    handle = f"@{name}"
    kind = cfg["kind"]
    if kind == "love":
        cap = (f"💖 <b>THOUGHT OF THE DAY</b>\n{handle} – {now:%A}, {now.day} {now:%B %Y}\n\n"
               f"<blockquote>🌙 <b>English:</b>\n{e(d['english'])}</blockquote>\n\n"
               f"<blockquote>🌸 <b>Hinglish:</b>\n{e(d['hinglish'])}</blockquote>\n\n"
               f"✨ <b>{e(d['closing'])}</b>\n\nFollow 👉 {handle}\n\n"
               f"<blockquote>{e(tags)}</blockquote>")
    elif kind == "motivation":
        cap = (f"🔥 {handle} – {now:%A}, {ordinal(now.day)} {now:%B %Y}\n<b>MOTIVATION OF THE DAY</b>\n\n"
               f"<blockquote>💪 <b>English:</b>\n\"{e(d['english']).strip(chr(34))}\"</blockquote>\n"
               f"<blockquote>🌟 <b>Hinglish:</b>\n\"{e(d['hinglish']).strip(chr(34))}\"</blockquote>\n"
               f"⏳ {e(d['closing'])}\n🚀 Follow 👉 {handle} for daily motivation!\n\n"
               f"<blockquote>{e(tags)}</blockquote>")
    else:
        cap = (f"🔍 <b>Unbelievable Fact of the Day – {ordinal(now.day)} {now:%B}</b>\n"
               f"<blockquote>{e(tags)}</blockquote>\n\n"
               f"🌍 <b>English:</b>\n<blockquote>{e(d['english'])}</blockquote>\n\n"
               f"🇮🇳 <b>Hinglish:</b>\n<blockquote>{e(d['hinglish'])}</blockquote>\n\n"
               f"📌 Follow 👉 {handle} for more unbelievable facts daily!")
    return cap


# ----------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------
def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=120, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:300]}")
    return r.json()


def send_post(chat_id, img_bytes, caption):
    if len(caption) <= 1024:
        tg("sendPhoto", data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
           files={"photo": ("post.jpg", img_bytes)})
    else:  # caption bahut lamba ho to alag bhejo
        tg("sendPhoto", data={"chat_id": chat_id}, files={"photo": ("post.jpg", img_bytes)})
        tg("sendMessage", data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                "disable_web_page_preview": True})


def publish(name, st, target=None, record=True):
    cfg = full_cfg(st["channels"][name])
    hist = st["history"].setdefault(name, [])
    data = make_content(name, cfg, hist)
    img = make_image(cfg, data, name)
    cap = build_caption(name, cfg, data)
    send_post(target or cfg["chat_id"], img, cap)
    if record:
        with LOCK:
            hist.append(data["headline"])
    log.info("Posted %s -> %s: %s", name, target or cfg["chat_id"], data["headline"])


# ----------------------------------------------------------------------
# Telegram commands (long polling, alag thread)
# ----------------------------------------------------------------------
HELP = (
    "Commands:\n"
    "/add Name chat_id [type] [times]\n"
    "   ex: /add TheHeartVerse -1001234567890\n"
    "   naya channel: /add MyFacts -100123 fact 10:00,19:00\n"
    "   types: love, motivation, fact\n"
    "/remove Name\n"
    "/list\n"
    "/test Name  -> preview yahin chat mein\n"
    "/test Name live  -> channel pe asli post\n"
    "/times Name 09:00,21:00\n"
    "/myid"
)


def say(chat, text):
    try:
        tg("sendMessage", data={"chat_id": chat, "text": text, "disable_web_page_preview": True})
    except Exception as e:
        log.error("reply fail: %s", e)


def find_name(st, raw):
    raw = raw.lstrip("@").lower()
    for n in st["channels"]:
        if n.lower() == raw:
            return n
    return None


def valid_times(s):
    ts = [t.strip() for t in s.split(",") if t.strip()]
    if not ts or not all(re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", t) for t in ts):
        return None
    return [f"{int(t.split(':')[0]):02d}:{t.split(':')[1]}" for t in ts]


def cmd_add(st, chat, args):
    if len(args) < 2:
        return say(chat, "Aise likho: /add TheHeartVerse -100xxxxxxxxxx")
    name, chat_id = args[0].lstrip("@"), args[1]
    if not re.fullmatch(r"\w{3,}", name):
        return say(chat, "Channel ka naam sirf letters/numbers/underscore ho.")
    kind = None
    times = None
    for a in args[2:]:
        if a.lower() in KINDS:
            kind = a.lower()
        elif valid_times(a):
            times = valid_times(a)
    if kind is None:
        known = DEFAULTS.get(next((n for n in DEFAULTS if n.lower() == name.lower()), ""))
        if known:
            name = next(n for n in DEFAULTS if n.lower() == name.lower())
            kind = known[0]
        else:
            return say(chat, f"'{name}' naya channel hai, type bhi likho:\n"
                             f"/add {name} {chat_id} love|motivation|fact")
    try:
        info = tg("getChat", data={"chat_id": chat_id})["result"]
        me = tg("getMe")["result"]["id"]
        member = tg("getChatMember", data={"chat_id": chat_id, "user_id": me})["result"]
    except Exception as e:
        return say(chat, f"Channel access nahi mila. Chat id sahi hai? Bot ko channel mein admin banaya?\n{str(e)[:150]}")
    if member.get("status") != "administrator":
        return say(chat, "Bot us channel mein admin nahi hai. Pehle admin banao (Post messages ON), phir /add karo.")
    with LOCK:
        old = find_name(st, name)
        if old:
            name = old
        st["channels"][name] = {"chat_id": chat_id, "kind": kind, "times": times or KINDS[kind]["times"]}
        save_state(st)
    e = st["channels"][name]
    say(chat, f"✅ Add ho gaya: {name} ({info.get('title', '')})\nType: {e['kind']}\nTime: {', '.join(e['times'])}\n"
              f"Check karne ke liye: /test {name}")


def cmd_remove(st, chat, args):
    if not args:
        return say(chat, "Aise likho: /remove TheHeartVerse")
    with LOCK:
        n = find_name(st, args[0])
        if not n:
            return say(chat, "Ye channel list mein nahi hai. /list dekho.")
        del st["channels"][n]
        save_state(st)
    say(chat, f"🗑 {n} hata diya. Ab isme auto post nahi hogi.")


def cmd_list(st, chat):
    if not st["channels"]:
        return say(chat, "Koi channel nahi hai. /add use karo.")
    lines = [f"{n} | {e['kind']} | {e['chat_id']} | {', '.join(e['times'])}" for n, e in st["channels"].items()]
    say(chat, "📋 Channels:\n" + "\n".join(lines))


def cmd_times(st, chat, args):
    if len(args) < 2 or not valid_times(args[1]):
        return say(chat, "Aise likho: /times TheHeartVerse 09:00,21:30")
    with LOCK:
        n = find_name(st, args[0])
        if not n:
            return say(chat, "Ye channel list mein nahi hai.")
        st["channels"][n]["times"] = valid_times(args[1])
        save_state(st)
    say(chat, f"⏰ {n} ka time: {', '.join(st['channels'][n]['times'])}")


def cmd_test(st, chat, args):
    if not args:
        return say(chat, "Aise likho: /test TheHeartVerse")
    n = find_name(st, args[0])
    if not n:
        return say(chat, "Ye channel list mein nahi hai. /list dekho.")
    live = len(args) > 1 and args[1].lower() == "live"
    say(chat, f"⏳ {n} ki {'LIVE ' if live else 'preview '}post ban rahi hai (30-60 sec)...")
    try:
        publish(n, st, target=None if live else chat, record=live)
        if live:
            with LOCK:
                save_state(st)
            say(chat, f"✅ {n} pe post ho gayi.")
    except Exception as e:
        say(chat, f"❌ Fail: {str(e)[:300]}")


def handle_message(st, msg):
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    chat = msg["chat"]["id"]
    uid = msg.get("from", {}).get("id")
    parts = text.split()
    cmd, args = parts[0].lower().split("@")[0], parts[1:]
    if cmd == "/myid":
        return say(chat, f"Tumhara user id: {uid}\n(isko ADMIN_IDS variable mein daalo)")
    if not ADMIN_IDS:
        return say(chat, "ADMIN_IDS set nahi hai. /myid se apna id lo aur Railway variable ADMIN_IDS mein daalo.")
    if uid not in ADMIN_IDS:
        return say(chat, "Ye bot sirf owner ke liye hai.")
    if cmd in ("/start", "/help"):
        say(chat, HELP)
    elif cmd == "/add":
        cmd_add(st, chat, args)
    elif cmd in ("/remove", "/del"):
        cmd_remove(st, chat, args)
    elif cmd == "/list":
        cmd_list(st, chat)
    elif cmd == "/times":
        cmd_times(st, chat, args)
    elif cmd == "/test":
        cmd_test(st, chat, args)
    else:
        say(chat, "Ye command nahi pata.\n\n" + HELP)


def command_loop(st):
    offset = 0
    try:
        tg("deleteWebhook")
    except Exception:
        pass
    while True:
        try:
            r = tg("getUpdates", data={"offset": offset, "timeout": 50, "allowed_updates": json.dumps(["message"])})
            for u in r["result"]:
                offset = u["update_id"] + 1
                if "message" in u:
                    # har command alag thread mein, taaki /test ke dauran bot atke nahi
                    threading.Thread(target=handle_message, args=(st, u["message"]), daemon=True).start()
        except Exception as e:
            log.error("poll error: %s", e)
            time.sleep(5)


# ----------------------------------------------------------------------
# Scheduler
# ----------------------------------------------------------------------
def run():
    st = load_state()
    save_state(st)
    threading.Thread(target=command_loop, args=(st,), daemon=True).start()
    fails = {}
    log.info("Bot started. Channels: %s | Admins: %s", ", ".join(st["channels"]), ADMIN_IDS or "NOT SET")
    while True:
        now = datetime.now(TZ)
        with LOCK:
            items = [(n, dict(e)) for n, e in st["channels"].items()]
        for name, entry in items:
            for t in entry["times"]:
                h, m = map(int, t.split(":"))
                slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
                key = f"{name}|{slot:%Y-%m-%d}|{t}"
                if key in st["done"] or fails.get(key, 0) >= 4:
                    continue
                if slot <= now < slot + timedelta(minutes=90):
                    try:
                        publish(name, st)
                        with LOCK:
                            st["done"].append(key)
                        save_state(st)
                    except Exception as e:
                        fails[key] = fails.get(key, 0) + 1
                        log.error("Post fail %s (%s): %s", key, fails[key], e)
                        time.sleep(60)
        time.sleep(30)


if __name__ == "__main__":
    run()
