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
    "love": "english = 1-2 emotional lines (max 24 words). hinglish = same meaning in natural Roman-script "
            "Hinglish (Hindi in English letters), max 24 words. closing = 3 short words style like 'Let go. Learn. Grow.'",
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
- Tone: modern, relatable, Gen-Z friendly, short punchy lines. Hinglish should sound like casual texting, simple words.
- headline = very short English hook (max 8 words, no emojis). For facts it is the big text on the image, make it a punchy hook.
- highlight = 1-3 consecutive words copied EXACTLY from the image text (the headline for facts, the english field otherwise) that carry the key idea; they will be shown in colour.
- hashtags = array of exactly 3 hashtags, first one is #{name}.
- image_prompt = English, one vivid scene matching the post, style: {cfg['image_style']}. Never include any text/letters in the image.
Return ONLY JSON with keys: headline, english, hinglish, closing, highlight, image_prompt, hashtags."""
    return gemini_json(prompt)


# ----------------------------------------------------------------------
# Image  (square 1080x1080, bade stylish fonts, highlight words)
# ----------------------------------------------------------------------
W = H = 1080
_BASES = ["https://github.com/google/fonts/raw/main/ofl/", "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/"]
FONT_PATHS = {
    "bold": "poppins/Poppins-Bold.ttf",
    "medium": "poppins/Poppins-Medium.ttf",
    "anton": "anton/Anton-Regular.ttf",               # motivation: bold condensed
    "serif_italic": "dmserifdisplay/DMSerifDisplay-Italic.ttf",   # love: elegant
    "archivo": "archivoblack/ArchivoBlack-Regular.ttf",           # facts: heavy modern
    "script": "greatvibes/GreatVibes-Regular.ttf",    # signature handle
    "bebas": "bebasneue/BebasNeue-Regular.ttf",
}
_font_cache = {}
_font_failed = {}
LABELS = {"love": "THOUGHT OF THE DAY", "motivation": "MOTIVATION OF THE DAY", "fact": "DID YOU KNOW?"}
FOLLOW = {"love": "FOLLOW FOR DAILY LOVE LINES", "motivation": "FOLLOW FOR DAILY MOTIVATION",
          "fact": "FOLLOW FOR DAILY FACTS"}
# kind -> (main font, start size, line-height, uppercase, handle font, handle size)
STYLE = {
    "love": ("serif_italic", 98, 1.28, False, "script", 76),
    "motivation": ("anton", 150, 1.12, True, "bebas", 64),
    "fact": ("archivo", 104, 1.2, True, "bebas", 64),
}


def get_font(size, style="bold"):
    key = (size, style)
    if key in _font_cache:
        return _font_cache[key]
    path = os.path.join(DATA_DIR, "font_" + style + ".ttf")
    if not os.path.exists(path) and time.time() - _font_failed.get(style, 0) > 3600:
        for base in _BASES:
            try:
                r = requests.get(base + FONT_PATHS[style], timeout=30)
                r.raise_for_status()
                with open(path, "wb") as f:
                    f.write(r.content)
                break
            except Exception as e:
                log.warning("font download fail (%s): %s", style, e)
        else:
            _font_failed[style] = time.time()
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        if style != "bold":
            return get_font(size, "bold")
        try:
            font = ImageFont.load_default(size)
        except TypeError:
            font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def ai_background(prompt):
    for i in range(3):
        try:
            url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            # thoda lamba mangwate hain taaki neeche ka watermark crop ho jaye
            r = requests.get(url, params={"width": W, "height": 1180, "nologo": "true",
                                          "seed": random.randint(1, 10**6)}, timeout=120)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB").resize((W, 1180))
            return img.crop((0, 0, W, H))
        except Exception as e:
            log.warning("image try %s fail: %s", i + 1, e)
            time.sleep(4)
    return None


def gradient_bg(accent):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top = tuple(int(c * 0.5) for c in accent)
    bottom = (8, 8, 22)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    return img


def _norm(w):
    return re.sub(r"[^\w]", "", w).lower()


def tag_words(text, highlight):
    """text ke words + kaunse highlight honge (accent colour)"""
    words = text.split()
    flags = [False] * len(words)
    hl = [_norm(w) for w in (highlight or "").split() if _norm(w)]
    if hl:
        nw = [_norm(w) for w in words]
        for i in range(len(nw) - len(hl) + 1):
            if nw[i:i + len(hl)] == hl:
                for j in range(i, i + len(hl)):
                    flags[j] = True
                break
    return list(zip(words, flags))


def layout_lines(draw, tagged, font, max_w):
    lines, cur = [], []
    for item in tagged:
        test = " ".join(w for w, _ in cur + [item])
        if not cur or draw.textlength(test, font=font) <= max_w:
            cur.append(item)
        else:
            lines.append(cur)
            cur = [item]
    if cur:
        lines.append(cur)
    return lines


def spaced_width(draw, text, font, spacing):
    return sum(draw.textlength(c, font=font) for c in text) + spacing * (len(text) - 1)


def spaced_text(draw, cx, y, text, font, fill, spacing):
    x = cx - spaced_width(draw, text, font, spacing) / 2
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + spacing


def make_image(cfg, data, name):
    from PIL import ImageFilter
    acc = cfg["accent"]
    kind = cfg["kind"]
    main_style, start_fs, lh_mul, upper, h_style, h_size = STYLE[kind]

    bg = ai_background(data["image_prompt"]) or gradient_bg(acc)
    base = bg.convert("RGBA")
    base = Image.alpha_composite(base, Image.new("RGBA", (W, H), (4, 4, 14, 125)))
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)
    for y in range(H):
        vd.line([(0, y), (W, y)], fill=(0, 0, 0, int(150 * (abs(y - H / 2) / (H / 2)) ** 2.4)))
    base = Image.alpha_composite(base, vig)
    glow = Image.new("RGBA", (W, H), acc + (0,))
    ImageDraw.Draw(glow).ellipse([W / 2 - 360, H / 2 - 360, W / 2 + 360, H / 2 + 360], fill=acc + (60,))
    base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(140)))

    # --- main text fit ---
    text = (data["headline"] if kind == "fact" else data["english"]).strip().strip('"\u201c\u201d')
    if upper:
        text = text.upper()
    tagged = tag_words(text, data.get("highlight", ""))
    probe = ImageDraw.Draw(base)
    max_w = W - 170
    glyph_h = 0 if kind == "fact" else 105
    max_text_h = 560 - glyph_h // 2
    fs = start_fs
    while True:
        f = get_font(fs, main_style)
        lines = layout_lines(probe, tagged, f, max_w)
        lh = int(fs * lh_mul)
        if (len(lines) * lh <= max_text_h and len(lines) <= 9) or fs <= 36:
            break
        fs -= 4
    text_h = len(lines) * lh
    block_h = glyph_h + text_h + 50
    y = 215 + (650 - block_h) // 2

    d = ImageDraw.Draw(base, "RGBA")
    d.rounded_rectangle([26, 26, W - 26, H - 26], radius=26, outline=(255, 255, 255, 55), width=2)

    # label with side lines
    lf = get_font(26, "medium")
    label = LABELS[kind]
    tw = spaced_width(d, label, lf, 6)
    spaced_text(d, W / 2, 62, label, lf, (255, 255, 255, 235), 6)
    d.line([(W / 2 - tw / 2 - 120, 78), (W / 2 - tw / 2 - 28, 78)], fill=acc + (255,), width=3)
    d.line([(W / 2 + tw / 2 + 28, 78), (W / 2 + tw / 2 + 120, 78)], fill=acc + (255,), width=3)

    # big quote mark
    if kind != "fact":
        gf = get_font(210, main_style)
        gw = d.textlength("\u201c", font=gf)
        d.text(((W - gw) / 2, y - 55), "\u201c", font=gf, fill=acc + (255,))
        y += glyph_h

    # text lines (word by word, highlight accent rang mein)
    space = d.textlength(" ", font=f)
    for line in lines:
        widths = [d.textlength(w, font=f) for w, _ in line]
        total = sum(widths) + space * (len(line) - 1)
        x = (W - total) / 2
        for (w, hl), ww in zip(line, widths):
            d.text((x + 3, y + 4), w, font=f, fill=(0, 0, 0, 170))
            d.text((x, y), w, font=f, fill=(acc + (255,)) if hl else (255, 255, 255, 255))
            x += ww + space
        y += lh

    # accent bar
    d.rounded_rectangle([W / 2 - 55, y + 16, W / 2 + 55, y + 22], radius=3, fill=acc + (255,))

    # handle + follow
    hf = get_font(h_size, h_style)
    tag = "@" + name
    if h_style == "bebas":
        spaced_text(d, W / 2 + 2, H - 168 + 3, tag, hf, (0, 0, 0, 170), 5)
        spaced_text(d, W / 2, H - 168, tag, hf, (255, 255, 255, 255), 5)
    else:
        hw = d.textlength(tag, font=hf)
        d.text(((W - hw) / 2 + 2, H - 180 + 3), tag, font=hf, fill=(0, 0, 0, 170))
        d.text(((W - hw) / 2, H - 180), tag, font=hf, fill=(255, 255, 255, 255))
    spaced_text(d, W / 2, H - 78, FOLLOW[kind], get_font(20, "medium"), acc + (255,), 5)

    out = io.BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=93)
    return out.getvalue()


# ----------------------------------------------------------------------
# Caption (chhota aur saaf)
# ----------------------------------------------------------------------
def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


_MAPS = {"sans": (0x1D5D4, 0x1D5EE, 0x1D7EC),      # bold sans  : 𝗕𝗼𝗹𝗱
         "script": (0x1D4D0, 0x1D4EA, None),        # bold script: 𝓑𝓸𝓵𝓭
         "italic": (0x1D468, 0x1D482, None)}        # bold italic serif


def fancy(text, style="sans"):
    """normal text ko stylish Unicode font mein badalta hai (caption mein font nahi hota, isliye)"""
    A, a, D = _MAPS[style]
    out = []
    for ch in str(text):
        if "A" <= ch <= "Z":
            out.append(chr(A + ord(ch) - 65))
        elif "a" <= ch <= "z":
            out.append(chr(a + ord(ch) - 97))
        elif D and "0" <= ch <= "9":
            out.append(chr(D + ord(ch) - 48))
        else:
            out.append(ch)
    return "".join(out)


RULE = "\u2501" * 12
KIND_CAP = {
    # label, quote style, quote icon
    "love": ("THOUGHT OF THE DAY", "italic"),
    "motivation": ("MOTIVATION OF THE DAY", "sans"),
    "fact": ("UNBELIEVABLE FACT OF THE DAY", "sans"),
}


def build_caption(name, cfg, d):
    now = datetime.now(TZ)
    kind = cfg["kind"]
    label, qstyle = KIND_CAP[kind]
    clean = lambda s: str(s).strip().strip('"\u201c\u201d')
    esc = lambda t: html.escape(t, quote=False)   # ' ko &#x27; nahi banana
    B = lambda raw, style="sans": "<b>" + esc(fancy(raw, style)) + "</b>"   # stylish + bold
    tags = " ".join(t if t.startswith("#") else "#" + t for t in d["hashtags"][:3])
    if kind == "fact":
        date = f"{ordinal(now.day)} {now:%B %Y}"
    else:
        date = f"{now:%A}, {ordinal(now.day)} {now:%B %Y}"
    en, hi = clean(d["english"]), clean(d["hinglish"])
    if kind != "fact":
        en, hi = "\u201c" + en + "\u201d", "\u201c" + hi + "\u201d"
    return (
        f"\u25C6 {B(label)} \u25C6\n"
        f"\u25B8 {B(date)}\n"
        f"<blockquote>\u275D {B('ENGLISH')}\n{B(en, qstyle)}</blockquote>\n"
        f"<blockquote>\u275D {B('HINGLISH')}\n{B(hi, qstyle)}</blockquote>\n"
        f"\u27A4 {B(clean(d['closing']), 'script')}\n\n"
        f"<b>{RULE}</b>\n"
        f"\u2726 {B('FOLLOW')} \u279C <b>@{esc(name)}</b>\n"
        f"\u2726 {B('SHARE WITH SOMEONE WHO NEEDS THIS')}\n"
        f"<blockquote><b>{esc(tags)}</b></blockquote>"
    )


# ----------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------
def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=120, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:300]}")
    return r.json()


def visible_len(cap):
    plain = html.unescape(re.sub(r"<[^>]+>", "", cap))
    return len(plain.encode("utf-16-le")) // 2   # Telegram UTF-16 mein ginta hai


def send_post(chat_id, img_bytes, caption):
    if visible_len(caption) <= 1024:
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
