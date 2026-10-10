"""
Auto Telegram Channel Poster
- Gemini (free) se English + Hinglish content
- Pollinations (free) se AI image, upar Pillow se stylish text card
- Roz channel ke hisab se 1-2 post, alag-alag topic
Run: python bot.py  (Railway worker)
Control (sirf ADMIN_IDS ke liye): bot ko /start bhejo -> channel ke BUTTONS aate hain.
  Channel pe tap karo -> time add/remove (12 ghante AM/PM), preview, live post, type badlo, channel hatao.
  /myid  -> apna user id (ADMIN_IDS ke liye)
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
# MongoDB (optional par recommended): MONGO_URI set ho to channels/times/history yahin save hote hain, redeploy par nahi udte
MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB = os.getenv("MONGO_DB", "autoposter")
_mongo_col = None
FONT_FILE = os.path.join(DATA_DIR, "font.ttf")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"

# ----------------------------------------------------------------------
# KINDS (channel ke type) -- naya type chahiye to yahan ek block jodo
# ----------------------------------------------------------------------
KINDS = {
    # ------------------------------------------------------------------
    # NAYA TYPE JODNA HO? bas yahan ek aur block copy-paste karo. Baaki code ko haath lagane ki zarurat nahi.
    #   emoji / title    : button mein dikhta hai
    #   times            : default post time (24hr likho, bot khud AM/PM dikhata hai)
    #   img_label/follow : image ke upar-neeche ka text
    #   cap_label        : caption ka heading
    #   font             : (main font, start size, line-height, UPPERCASE?, handle font, handle size)
    #   quote_style      : caption ke quote ka Unicode style (sans / script / italic)
    #   big_headline     : True = image par headline, False = image par english quote + bada quote mark
    #   quote_marks      : caption mein quote “ ” lagao ya nahi
    #   show_weekday     : caption date mein din (Monday) dikhao ya nahi
    #   rules            : Gemini ko content ke rules
    #   schema/required  : (optional) Gemini se kaun-kaun si JSON keys chahiye;  caption : CAPTIONS mein kaun sa design
    #   overlay          : False = image par text nahi, sirf photo;  source : (optional) asli data ka source (SOURCES)
    # ------------------------------------------------------------------
    "love": {
        "emoji": "\u2764\ufe0f", "title": "Love Quotes",
        "img_label": "THOUGHT OF THE DAY", "follow": "FOLLOW FOR DAILY LOVE LINES",
        "cap_label": "THOUGHT OF THE DAY", "quote_style": "italic",
        "font": ("serif_italic", 98, 1.28, False, "script", 76),
        "big_headline": False, "quote_marks": True, "show_weekday": True,
        "rules": "english = 1-2 emotional lines (max 24 words). hinglish = same meaning in natural Roman-script "
                 "Hinglish (Hindi in English letters), max 24 words. closing = 3 short words style like 'Let go. Learn. Grow.'",
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
        "emoji": "\U0001F525", "title": "Motivation",
        "img_label": "MOTIVATION OF THE DAY", "follow": "FOLLOW FOR DAILY MOTIVATION",
        "cap_label": "MOTIVATION OF THE DAY", "quote_style": "sans",
        "font": ("anton", 150, 1.12, True, "bebas", 64),
        "big_headline": False, "quote_marks": True, "show_weekday": True,
        "rules": "english = ONE powerful quote line (max 22 words). hinglish = natural Roman-script Hinglish "
                 "version (Hindi in English letters). closing = short punchy line like 'Stay focused. Stay unstoppable.'",
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
        "emoji": "\U0001F9E0", "title": "Facts",
        "img_label": "DID YOU KNOW?", "follow": "FOLLOW FOR DAILY FACTS",
        "cap_label": "UNBELIEVABLE FACT OF THE DAY", "quote_style": "sans",
        "font": ("archivo", 104, 1.2, True, "bebas", 64),
        "big_headline": True, "quote_marks": False, "show_weekday": False,
        "rules": "english = starts with 'Did you know?' then 2-3 short lines with the fact and a punchline. "
                 "hinglish = starts with 'Kya tumhe pata hai?' then same fact in Roman-script Hinglish. "
                 "Facts MUST be 100% true and well-established. closing = short line like 'Mind blown!'",
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
    "startup": {
        "emoji": "\U0001F4A1", "title": "Startup Ideas",
        "img_label": "STARTUP IDEA OF THE DAY", "follow": "FOLLOW FOR DAILY STARTUP IDEAS",
        "font": ("anton", 150, 1.12, True, "bebas", 64),
        "big_headline": True, "quote_marks": False, "overlay": True, "caption": "startup",
        "rules": "Give ONE practical, original startup/business idea that a normal person in India can start with low "
                 "investment. It must have a clear problem, a clear customer and a clear way to earn. name = catchy brand "
                 "name (1-2 words, e.g. SeniorSathi). No generic ideas, no 'AI app for everything'.",
        "schema": """- Tone: simple, clear, motivating. Hinglish = casual Roman-script Hindi, easy words.
- headline = short English hook about the problem or idea (max 8 words, no emojis), shown big on the image.
- highlight = 1-3 consecutive words copied EXACTLY from the headline that carry the key idea.
- name = the startup's brand name.
- tagline_en = one line on what the startup is (max 14 words). tagline_hi = same in Roman Hinglish.
- problem_en = 2 short lines: the problem and what the startup offers. problem_hi = same in Roman Hinglish.
- why_en = 2 short lines on why it works (demand and how it earns). why_hi = same in Roman Hinglish.
- hashtags = array of exactly 3 hashtags like #StartupIdea #BusinessIdea #EntrepreneurMindset (topic-relevant).
- image_prompt = English, one vivid scene matching the idea, style: {image_style}. Never include any text/letters in the image.
Return ONLY JSON with keys: headline, highlight, name, tagline_en, tagline_hi, problem_en, problem_hi, why_en, why_hi, hashtags, image_prompt.""",
        "required": ("headline", "name", "tagline_en", "tagline_hi", "problem_en", "problem_hi",
                    "why_en", "why_hi", "hashtags", "image_prompt"),
        "times": ["10:00"],
        "accent": (255, 190, 60),
        "about": "One fresh, practical startup idea every day for aspiring Indian entrepreneurs.",
        "themes": ["elderly care", "education", "agri-tech", "food business", "pet services", "local services",
                   "tourism", "fitness", "women entrepreneurs", "sustainability", "gig economy", "kids and parents",
                   "small shop digitisation", "rural India", "tools for small businesses", "home services",
                   "second-hand market", "health and wellness", "content creation", "logistics"],
        "image_style": "modern cinematic startup scene, glowing lightbulb or city skyline at dusk, entrepreneur "
                       "silhouette, deep navy and gold tones, no text",
    },
    "cook": {
        "emoji": "\U0001F373", "title": "Recipes & Hacks",
        "img_label": "RECIPE OF THE DAY", "follow": "FOLLOW FOR DAILY RECIPES",
        "font": ("archivo", 104, 1.2, True, "bebas", 64),
        "big_headline": True, "quote_marks": False, "overlay": False, "caption": "cook",
        "rules": "English + Hinglish. If the theme starts with 'recipe' write a full easy recipe (post_type = recipe), if it starts "
                 "with 'hack' write one genuinely useful kitchen hack (post_type = hack). Indian-home friendly, realistic "
                 "quantities, accurate and SAFE cooking advice only.",
        "schema": """- Tone: friendly, simple, short lines.
- post_type = recipe or hack.
- headline = dish or hack title (max 7 words, no emojis).
- emoji = one fitting food/kitchen emoji.
- intro = one tasty line (max 16 words).
- ingredients = array of at most 8 short strings with quantity, e.g. Paneer cubes (200g). For a hack: what you need (may be empty).
- steps = array of 3-6 short steps (each max 16 words, no numbering).
- tip = one short pro tip (max 18 words).
- headline_hi, intro_hi, ingredients_hi, steps_hi, tip_hi = the SAME content in casual Roman-script Hinglish (Hindi in English letters): same number of items, same order, same quantities.
- hashtags = array of exactly 3 food hashtags.
- image_prompt = English, the finished dish (or the hack's main item), style: {image_style}. Never include any text/letters in the image.
Return ONLY JSON with keys: post_type, headline, headline_hi, emoji, intro, intro_hi, ingredients, ingredients_hi, steps, steps_hi, tip, tip_hi, hashtags, image_prompt.""",
        "required": ("post_type", "headline", "intro", "intro_hi", "ingredients", "ingredients_hi", "steps", "steps_hi",
                    "hashtags", "image_prompt"),
        "times": ["12:30", "19:30"],
        "accent": (255, 140, 60),
        "about": "Easy tasty recipes and smart kitchen hacks for home cooks.",
        "themes": ["recipe: quick breakfast", "recipe: paneer", "recipe: street food at home", "recipe: healthy snacks",
                   "recipe: one-pot dinner", "recipe: sweet dessert", "recipe: dal and sabzi", "recipe: rolls and wraps",
                   "recipe: egg dishes", "recipe: rice dishes", "recipe: parathas", "recipe: monsoon snacks",
                   "recipe: kids tiffin", "hack: kitchen time-savers", "hack: storage and freshness",
                   "hack: cleaning the kitchen", "hack: cooking mistakes to avoid", "hack: spice and flavour tricks",
                   "hack: fridge and leftovers", "hack: budget cooking"],
        "image_style": "professional food photography, close-up of the finished dish on a rustic wooden table, warm "
                       "natural light, fresh garnish, shallow depth of field, appetizing, no text",
    },
    "timeline": {
        "emoji": "\U0001F570", "title": "Today In History",
        "img_label": "TODAY IN HISTORY", "follow": "FOLLOW FOR DAILY HISTORY",
        "font": ("archivo", 104, 1.2, True, "bebas", 64),
        "big_headline": True, "quote_marks": False, "overlay": False, "caption": "timeline",
        "source": "onthisday",
        "min_events": 10,
        "rules": "Pick 10 to 12 interesting events that happened on TODAY's date (same day and month, any year). Years must "
                 "be exact and facts 100% true. Mix different fields. Tragic events: one respectful line, no graphic detail. "
                 "The theme is only a soft hint.",
        "schema": """- Tone: clear and engaging. Hinglish = casual Roman-script Hindi, easy words.
- headline = short English hook for the date (max 8 words, no emojis).
- events = array of 10 to 12 objects (NEVER fewer than 10), each with keys year (number), en (ONE short line, max 12 words), hi (same in Roman Hinglish, max 12 words), emoji (one fitting emoji). Oldest year first. Keep every line SHORT.
- hashtags = array of exactly 5 hashtags: #HistoryFacts #TodayInHistory, the date like #25July, plus 2 topic hashtags.
- image_prompt = English, one iconic scene of the most visual event, style: {image_style}. No close-up faces, never include any text/letters in the image.
Return ONLY JSON with keys: headline, events, hashtags, image_prompt.""",
        "required": ("headline", "events", "hashtags", "image_prompt"),
        "times": ["07:00"],
        "accent": (212, 165, 90),
        "about": "What happened on this exact date in history: discoveries, firsts, milestones.",
        "themes": ["science and discovery", "inventions", "sports", "film and music", "India", "space",
                   "leaders and politics", "firsts and records", "nature", "world events"],
        "image_style": "vintage sepia historical illustration, old parchment texture, antique clock, dramatic "
                       "cinematic light, no text",
    },
}

# pehli baar chalne par ye 3 channel apne aap add ho jaate hain
DEFAULTS = {
    "TheHeartVerse": ("love", "@TheHeartVerse"),
    "RiseFuelQuotes": ("motivation", "@RiseFuelQuotes"),
    "FactForge": ("fact", "@FactForge"),
    "StartSpark": ("startup", "@StartSpark"),
    "TheCookTable": ("cook", "@TheCookTable"),
    "TimelineToday": ("timeline", "@TimelineToday"),
}
ORIGINAL_DEFAULTS = {"TheHeartVerse", "RiseFuelQuotes", "FactForge"}


def full_cfg(entry):
    """state wali entry + kind ka template mila ke poora config"""
    return {**KINDS[entry["kind"]], "kind": entry["kind"],
            "chat_id": entry["chat_id"], "times": entry["times"]}


# ----------------------------------------------------------------------
# State (history + done slots)
# ----------------------------------------------------------------------
def mongo_col():
    global _mongo_col
    if _mongo_col is None:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        _mongo_col = client[MONGO_DB]["state"]
    return _mongo_col


def _read_file_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def load_state():
    if MONGO_URI:
        st = None
        for i in range(5):
            try:
                st = mongo_col().find_one({"_id": "main"})
                break
            except Exception as e:
                log.error("MongoDB connect try %s fail: %s", i + 1, e)
                time.sleep(5)
        else:
            # khali state se shuru karte to purana data overwrite ho jata, isliye ruk jao
            raise RuntimeError("MongoDB se connect nahi ho paya. MONGO_URI check karo.")
        if st:
            st.pop("_id", None)
        else:
            st = _read_file_state()      # pehli baar: purani state.json ho to wahi import ho jati hai
            log.info("MongoDB khali hai%s", " - state.json se data import kiya" if st else "")
    else:
        st = _read_file_state()
        log.warning("MONGO_URI set nahi hai: data file mein ja raha hai, redeploy par ud sakta hai!")
    st = st or {}
    st.setdefault("done", [])
    st.setdefault("history", {})
    if "seeded" not in st:   # purani state mein pehle wale 3 pehle hi seed maane jaate hain
        st["seeded"] = sorted(ORIGINAL_DEFAULTS) if "channels" in st else []
    st.setdefault("channels", {})
    for n, (k, c) in DEFAULTS.items():
        if n not in st["seeded"]:
            st["seeded"].append(n)
            st["channels"].setdefault(n, {"chat_id": c, "kind": k, "times": list(KINDS[k]["times"])})
    return st


def save_state(st):
    with LOCK:
        st["done"] = st["done"][-200:]
        for k in st["history"]:
            st["history"][k] = st["history"][k][-60:]
        if MONGO_URI:
            try:
                mongo_col().replace_one({"_id": "main"}, {**st, "_id": "main"}, upsert=True)
                return
            except Exception as e:
                log.error("MongoDB save fail (file mein backup ja raha hai): %s", e)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE_FILE)


# ----------------------------------------------------------------------
# Content (Gemini)
# ----------------------------------------------------------------------
DEFAULT_REQUIRED = ("headline", "english", "hinglish", "closing", "image_prompt", "hashtags")
DEFAULT_SCHEMA = """- Tone: modern, relatable, Gen-Z friendly, short punchy lines. Hinglish should sound like casual texting, simple words.
- headline = very short English hook (max 8 words, no emojis). For facts it is the big text on the image, make it a punchy hook.
- highlight = 1-3 consecutive words copied EXACTLY from the image text (the headline for facts, the english field otherwise) that carry the key idea; they will be shown in colour.
- hashtags = array of exactly 3 hashtags, first one is #{name}.
- image_prompt = English, one vivid scene matching the post, style: {image_style}. Never include any text/letters in the image.
Return ONLY JSON with keys: headline, english, hinglish, closing, highlight, image_prompt, hashtags."""


def onthisday_events(now):
    """Wikipedia 'On this day' se aaj ki date ke asli events (free). Na mile to '' (tab Gemini apni yaad se likhta hai)"""
    try:
        r = requests.get(f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{now.month:02d}/{now.day:02d}",
                         headers={"User-Agent": "TelegramAutoPoster/1.0"}, timeout=30)
        r.raise_for_status()
        ev = [e for e in r.json().get("events", []) if e.get("text") and e.get("year") and len(e["text"]) < 230]
        random.shuffle(ev)
        ev = sorted(ev[:60], key=lambda e: e["year"])
        if not ev:
            return ""
        lines = "\n".join(f"{e['year']}: {e['text']}" for e in ev)
        return "Verified real events that happened on this exact date (Wikipedia). Pick ONLY from these, keep the year exact:\n" + lines + "\n"
    except Exception as e:
        log.warning("onthisday fail: %s", e)
        return ""


SOURCES = {"onthisday": onthisday_events}


def gemini_json(prompt, required=DEFAULT_REQUIRED, min_events=0, tries=3):
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
            for k in required:
                if k not in data:
                    raise ValueError(f"missing {k}")
            for k in ("hashtags", "ingredients", "steps", "ingredients_hi", "steps_hi"):
                if k in data and not isinstance(data[k], list):
                    raise ValueError(f"{k} list nahi hai")
            if "events" in required:
                ev = data["events"]
                if not isinstance(ev, list) or len(ev) < max(1, min_events) or not all(
                        isinstance(e, dict) and all(x in e for x in ("year", "en", "hi")) for e in ev):
                    raise ValueError("events galat format")
            return data
        except Exception as e:
            last = e
            log.warning("Gemini try %s failed: %s", i + 1, e)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Gemini fail: {last}")


def make_content(name, cfg, history):
    theme = random.choice(cfg["themes"])
    avoid = "\n".join(f"- {h}" for h in history[-40:]) or "(none)"
    now = datetime.now(TZ)
    fn = SOURCES.get(cfg.get("source"))
    facts = fn(now) if fn else ""
    schema = cfg.get("schema", DEFAULT_SCHEMA).format(name=name, image_style=cfg["image_style"])
    prompt = f"""You write daily posts for a Telegram channel.
Channel: {name}
Niche: {cfg['about']}
Today's theme: {theme}
Today's date: {now:%A, %d %B %Y}
{facts}
Rules:
- Content must be ORIGINAL (never copy famous copyrighted quotes word-for-word).
- Must be completely different from these recent posts:
{avoid}
- {cfg['rules']}
{schema}"""
    return gemini_json(prompt, cfg.get("required", DEFAULT_REQUIRED), cfg.get("min_events", 0))


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
    main_style, start_fs, lh_mul, upper, h_style, h_size = cfg["font"]

    bg = ai_background(data["image_prompt"])
    if bg is not None and not cfg.get("overlay", True):
        out = io.BytesIO()          # is channel ki image par text nahi, sirf photo
        bg.save(out, "JPEG", quality=93)
        return out.getvalue()
    bg = bg or gradient_bg(acc)
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
    text = (data["headline"] if cfg["big_headline"] else data["english"]).strip().strip('"\u201c\u201d')
    if upper:
        text = text.upper()
    tagged = tag_words(text, data.get("highlight", ""))
    probe = ImageDraw.Draw(base)
    max_w = W - 170
    glyph_h = 0 if cfg["big_headline"] else 105
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
    label = cfg["img_label"]
    tw = spaced_width(d, label, lf, 6)
    spaced_text(d, W / 2, 62, label, lf, (255, 255, 255, 235), 6)
    d.line([(W / 2 - tw / 2 - 120, 78), (W / 2 - tw / 2 - 28, 78)], fill=acc + (255,), width=3)
    d.line([(W / 2 + tw / 2 + 28, 78), (W / 2 + tw / 2 + 120, 78)], fill=acc + (255,), width=3)

    # big quote mark
    if cfg["quote_marks"]:
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
    spaced_text(d, W / 2, H - 78, cfg["follow"], get_font(20, "medium"), acc + (255,), 5)

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


def caption_quote(name, cfg, d):
    now = datetime.now(TZ)
    label, qstyle = cfg["cap_label"], cfg["quote_style"]
    clean = lambda s: str(s).strip().strip('"\u201c\u201d')
    esc = lambda t: html.escape(t, quote=False)   # ' ko &#x27; nahi banana
    B = lambda raw, style="sans": "<b>" + esc(fancy(raw, style)) + "</b>"   # stylish + bold
    tags = " ".join(t if t.startswith("#") else "#" + t for t in d["hashtags"][:3])
    if cfg["show_weekday"]:
        date = f"{now:%A}, {ordinal(now.day)} {now:%B %Y}"
    else:
        date = f"{ordinal(now.day)} {now:%B %Y}"
    en, hi = clean(d["english"]), clean(d["hinglish"])
    if cfg["quote_marks"]:
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


def _esc(t):
    return html.escape(str(t).strip(), quote=False)


def _clean(s):
    return str(s).strip().strip('"\u201c\u201d')


def _tags(d, n):
    return " ".join(t if t.startswith("#") else "#" + t for t in d["hashtags"][:n])


def caption_startup(name, cfg, d):
    now = datetime.now(TZ)
    date = f"{now:%A} \u2022 {ordinal(now.day)} {now:%B}"
    idea = _esc(_clean(d["name"]))

    def block(tagline, problem, why, why_label):
        return (f"Startup Idea:\n\U0001F4F1 \"{idea}\" \u2013 {_esc(_clean(tagline))}\n\n"
                f"\U0001F465 {_esc(problem)}\n\n\U0001F4C8 {why_label}\n{_esc(why)}")
    en = block(d["tagline_en"], d["problem_en"], d["why_en"], "Why it works:")
    hi = block(d["tagline_hi"], d["problem_hi"], d["why_hi"], "Kyu chalega:")
    return (
        f"\U0001F680 <b>#{_esc(name)} \u2013 Startup Idea of the Day</b>\n"
        f"\U0001F4C5 <b>{date}</b>\n{RULE}\n\n"
        f"\U0001F1EC\U0001F1E7 <b>English:</b>\n<blockquote>{en}</blockquote>\n"
        f"---\n\n"
        f"\U0001F1EE\U0001F1F3 <b>Hinglish:</b>\n<blockquote>{hi}</blockquote>\n"
        f"---\n\n"
        f"\U0001F4CC Follow \U0001F449 <b>@{_esc(name)}</b> for a new powerful idea every day!\n"
        f"<blockquote>{_esc(_tags(d, 3))}</blockquote>"
    )


def caption_cook(name, cfg, d, short=False):
    now = datetime.now(TZ)
    date = f"{now:%A} \u2022 {ordinal(now.day)} {now:%B}"
    is_hack = str(d.get("post_type", "")).lower().startswith("h")
    label = "Kitchen Hack of the Day" if is_hack else "Recipe of the Day"
    emoji = d.get("emoji") or ("\U0001F4A1" if is_hack else "\U0001F958")

    def block(hi):
        if hi:
            need, how, tl = ("Zaroorat ka saaman", "Kaise karein", "Khaas Tip") if is_hack else ("Saamagri", "Banane ka tarika", "Khaas Tip")
            title = d.get("headline_hi") or d["headline"]
            intro, tip = d.get("intro_hi") or d.get("intro"), d.get("tip_hi") or d.get("tip")
            ings, steps = d.get("ingredients_hi") or d.get("ingredients"), d.get("steps_hi") or d.get("steps")
        else:
            need, how, tl = ("What you need", "How to do it", "Pro Tip") if is_hack else ("Ingredients", "Quick Recipe", "Pro Tip")
            title, intro, tip = d["headline"], d.get("intro"), d.get("tip")
            ings, steps = d.get("ingredients"), d.get("steps")
        ings = [x for x in (ings or []) if str(x).strip()]
        steps = [x for x in (steps or []) if str(x).strip()]
        parts = [f"{_esc(emoji)} <b>{_esc(_clean(title))}</b>"]
        if intro and not short:
            parts.append(_esc(intro))
        if ings:
            parts += ["", f"\U0001F4DD <b>{need}:</b>"] + [f"\u2022 {_esc(i)}" for i in ings]
        if steps:
            parts += ["", f"\U0001F525 <b>{how}:</b>"] + [f"{k}. {_esc(s)}" for k, s in enumerate(steps, 1)]
        if tip and not short:
            parts += ["", f"\U0001F4A1 <b>{tl}:</b> {_esc(tip)}"]
        return "\n".join(parts)

    cap = (f"\U0001F37D <b>#{_esc(name)} \u2013 {label}</b>\n"
           f"\U0001F4C5 <b>{date}</b>\n{RULE}\n\n"
           f"\U0001F1EC\U0001F1E7 <b>English:</b>\n<blockquote>{block(False)}</blockquote>\n"
           f"\U0001F1EE\U0001F1F3 <b>Hinglish:</b>\n<blockquote>{block(True)}</blockquote>\n\n"
           f"\U0001F4CC Follow \U0001F449 <b>@{_esc(name)}</b> for daily tasty dishes &amp; easy recipes!\n"
           f"<blockquote>{_esc(_tags(d, 3))}</blockquote>")
    if not short and visible_len(cap) > 4000:      # Telegram limit 4096
        return caption_cook(name, cfg, d, short=True)
    return cap


CAPTION_LIMIT = 1024      # Telegram: photo ke saath caption ki limit


def _timeline_parts(name, d, now, p):
    evs = d["events"][:12]
    size = -(-len(evs) // p)                       # ceil
    chunks = [evs[i:i + size] for i in range(0, len(evs), size)]
    n = len(chunks)
    date = f"{now:%A} \u2013 {ordinal(now.day)} {now:%B}"
    line = "\u25C7" + "\u2501" * 14 + "\u25C7"
    caps = []
    for i, ch in enumerate(chunks):
        en = "\n".join(f"\U0001F537 {_esc(e['year'])} \u2013 {_esc(_clean(e['en']))} {_esc(e.get('emoji', ''))}" for e in ch)
        hi = "\n".join(f"\U0001F537 {_esc(e['year'])} \u2013 {_esc(_clean(e['hi']))} {_esc(e.get('emoji', ''))}" for e in ch)
        part = f" \u2022 Part {i + 1}/{n}" if n > 1 else ""
        if i == 0:
            head = (f"{line}\n\U0001F4C5 <b>{date}</b>\n"
                    f"\u3010 <b>Today In History</b> | #{_esc(name)} \u3011{part}\n{line}\n\n")
        else:
            head = f"\U0001F4C5 <b>{date}</b> | #{_esc(name)}{part}\n\n"
        foot = ""
        if i == n - 1:
            foot = (f"\U0001F501 Follow \U0001F449 <b>@{_esc(name)}</b> for daily historical facts &amp; events!\n"
                    f"<blockquote>{_esc(_tags(d, 5))}</blockquote>")
        caps.append(f"{head}\U0001F570 <b>English:</b>\n<blockquote>{en}</blockquote>\n"
                    f"\U0001F5E3 <b>Hinglish:</b>\n<blockquote>{hi}</blockquote>\n{foot}")
    return caps


def caption_timeline(name, cfg, d):
    """Saare events ek post mein na aayein to 2 post, phir bhi na aayein to 3 post (list return hoti hai)"""
    now = datetime.now(TZ)
    caps = []
    for p in (1, 2, 3):
        caps = _timeline_parts(name, d, now, p)
        if all(visible_len(c) <= CAPTION_LIMIT for c in caps):
            break
    return caps


CAPTIONS = {"quote": caption_quote, "startup": caption_startup, "cook": caption_cook, "timeline": caption_timeline}


def build_caption(name, cfg, d):
    """har kind ka apna caption design: KINDS mein 'caption' key se chuna jata hai"""
    return CAPTIONS[cfg.get("caption", "quote")](name, cfg, d)


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
    caps = build_caption(name, cfg, data)
    if isinstance(caps, str):
        caps = [caps]
    dest = target or cfg["chat_id"]
    for i, cap in enumerate(caps):
        if i == 0:
            send_post(dest, img, cap)
            continue
        time.sleep(2)
        for attempt in range(3):   # pehla part ja chuka hai, isliye yahan fail par poori post dobara nahi bhejte
            try:
                send_post(dest, img, cap)
                break
            except Exception as e:
                log.error("part %s send try %s fail: %s", i + 1, attempt + 1, e)
                time.sleep(5)
    if record:
        with LOCK:
            hist.append(data["headline"])
    log.info("Posted %s -> %s: %s", name, target or cfg["chat_id"], data["headline"])


# ----------------------------------------------------------------------
# Telegram control panel (buttons, long polling, alag thread)
# ----------------------------------------------------------------------
PENDING = {}        # user id -> {"step": ...}  (jab bot ko user se text / forward chahiye)
BUSY = set()        # jin channels ki post abhi ban rahi hai
MAX_TIMES = 8


def say(chat, text, markup=None):
    show(chat, None, text, markup)


def show(chat, mid, text, markup=None):
    """mid ho to wahi message edit hota hai (buttons ek hi screen mein badalte hain), warna naya message"""
    data = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
    if markup:
        data["reply_markup"] = markup
    try:
        if mid:
            tg("editMessageText", data={**data, "message_id": mid})
        else:
            tg("sendMessage", data=data)
    except Exception as e:
        if "not modified" in str(e):
            return
        log.error("show fail: %s", e)
        if mid:
            try:
                tg("sendMessage", data=data)
            except Exception as e2:
                log.error("send fail: %s", e2)


def find_name(st, raw):
    raw = raw.lstrip("@").lower()
    for n in st["channels"]:
        if n.lower() == raw:
            return n
    return None


# ---------- 12 ghante ka time (andar 24hr "HH:MM" save hota hai, dikhta hamesha AM/PM) ----------
def fmt12(t24):
    h, m = map(int, t24.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def to24(h, m, ap):
    return f"{h % 12 + (12 if ap == 'PM' else 0):02d}:{m:02d}"


def parse12(s):
    """'6pm' '6:30 PM' '6.30 p.m.' -> '18:30'.  24 ghante wala (18:00) ya AM/PM ke bina -> None"""
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(a|p)\.?\s*m\.?", s.strip().lower())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if not (1 <= h <= 12 and 0 <= mi <= 59):
        return None
    return to24(h, mi, "AM" if m.group(3) == "a" else "PM")


def add_time(st, n, t24):
    """-> (ok, message)"""
    with LOCK:
        e = st["channels"][n]
        if t24 in e["times"]:
            return False, f"{fmt12(t24)} pehle se hai"
        if len(e["times"]) >= MAX_TIMES:
            return False, f"Maximum {MAX_TIMES} time hi rakh sakte ho"
        e["times"] = sorted(e["times"] + [t24])
        now = datetime.now(TZ)
        h, m = map(int, t24.split(":"))
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        note = ""
        if slot <= now < slot + timedelta(minutes=90):
            # abhi-abhi guzra time add kiya to turant post na chali jaye
            st["done"].append(f"{n}|{slot:%Y-%m-%d}|{t24}")
            note = " (aaj ka slot nikal gaya, kal se post hogi)"
        save_state(st)
    return True, f"✅ {fmt12(t24)} add ho gaya{note}"


# ---------- buttons ----------
def kb(rows):
    return json.dumps({"inline_keyboard": rows})


def Btn(text, data):
    return {"text": text, "callback_data": data}


def kind_emoji(kind):
    return KINDS.get(kind, {}).get("emoji", "📢")


def sc_main(st):
    rows = [[Btn(f"{kind_emoji(e['kind'])}  {n}", f"ch:{n}")] for n, e in st["channels"].items()]
    rows.append([Btn("➕ Naya Channel Add Karo", "na")])
    text = ("🎛 Channel Manager\n\nKis channel ko manage karna hai? Neeche se chuno 👇" if st["channels"]
            else "🎛 Channel Manager\n\nAbhi koi channel nahi hai. Neeche se add karo 👇")
    text += "\n\n" + ("\U0001F4BE Data: MongoDB \u2705" if MONGO_URI
                      else "\U0001F4BE Data: file \u26A0\uFE0F (redeploy par ud sakta hai, MONGO_URI daalo)")
    return text, kb(rows)


def sc_channel(st, n):
    e = st["channels"][n]
    lines = [f"{kind_emoji(e['kind'])} {n}", f"Type: {e['kind']}", f"Channel ID: {e['chat_id']}", "",
             "⏰ Post ka time:"]
    lines += [f"   • {fmt12(t)}" for t in e["times"]] or ["   (koi time nahi - ➕ se add karo)"]
    rows = []
    if e["times"]:
        lines += ["", "Time hatana ho to uspe tap karo 👇"]
        btns = [Btn(f"❌ {fmt12(t)}", f"td:{n}:{t.replace(':', '')}") for t in e["times"]]
        rows += [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows += [
        [Btn("➕ Time Add Karo", f"ta:{n}")],
        [Btn("👁 Preview", f"pv:{n}"), Btn("🚀 Live Post", f"lv:{n}")],
        [Btn("🎭 Type Badlo", f"ky:{n}"), Btn("🗑 Channel Hatao", f"rm:{n}")],
        [Btn("⬅ Back", "main")],
    ]
    return "\n".join(lines), kb(rows)


def sc_hour(n):
    rows = [[Btn(str(h), f"th:{n}:{h}") for h in range(r, r + 4)] for r in (1, 5, 9)]
    rows.append([Btn("⬅ Back", f"ch:{n}")])
    return (f"⏰ {n} - naya time\n\nPehle ghanta chuno 👇\n"
            f"(ya seedha type karo, jaise: 6:17 PM)"), kb(rows)


def sc_minute(n, h):
    mins = list(range(0, 60, 5))
    rows = [[Btn(f"{h}:{m:02d}", f"tm:{n}:{h}:{m}") for m in mins[i:i + 4]] for i in range(0, 12, 4)]
    rows.append([Btn("⬅ Back", f"ta:{n}")])
    return f"⏰ {n} - {h} baje, ab minute chuno 👇", kb(rows)


def sc_ampm(n, h, m):
    rows = [[Btn("🌅 AM (subah)", f"tp:{n}:{h}:{m}:AM"), Btn("🌙 PM (dopahar/raat)", f"tp:{n}:{h}:{m}:PM")],
            [Btn("⬅ Back", f"th:{n}:{h}")]]
    return f"⏰ {n} - {h}:{m:02d}  AM ya PM? 👇", kb(rows)


def sc_kinds(text, cb_prefix, current=None, back="main"):
    rows = [[Btn(f"{k['emoji']} {k['title']}" + ("  ✔" if name == current else ""), f"{cb_prefix}:{name}")]
            for name, k in KINDS.items()]
    rows.append([Btn("⬅ Back" if back != "main" else "❌ Cancel", back)])
    return text, kb(rows)


def check_channel(ref):
    info = tg("getChat", data={"chat_id": ref})["result"]
    me = tg("getMe")["result"]["id"]
    member = tg("getChatMember", data={"chat_id": info["id"], "user_id": me})["result"]
    return info, member.get("status") == "administrator"


def extract_chat_ref(msg):
    fo = msg.get("forward_origin") or {}
    if fo.get("type") == "channel":
        return str(fo["chat"]["id"])
    if msg.get("forward_from_chat"):
        return str(msg["forward_from_chat"]["id"])
    t = (msg.get("text") or "").strip()
    if re.fullmatch(r"-?\d{5,}", t):
        return t
    m = re.fullmatch(r"(?:https?://t\.me/|@)?([A-Za-z]\w{3,})", t)
    return "@" + m.group(1) if m else None


def run_job(chat, n, fn):
    """lambi post banane wala kaam; ek channel pe ek baar mein ek hi"""
    with LOCK:
        if n in BUSY:
            return say(chat, f"⏳ {n} ki post pehle se ban rahi hai, thoda ruko.")
        BUSY.add(n)
    try:
        fn()
    finally:
        with LOCK:
            BUSY.discard(n)


# ---------- callbacks (button taps) ----------
def handle_callback(st, cq):
    uid = cq["from"]["id"]
    msg = cq.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    mid = msg.get("message_id")
    answered = []

    def ans(text=None, alert=False):
        if answered:
            return
        answered.append(1)
        d = {"callback_query_id": cq["id"]}
        if text:
            d.update(text=text, show_alert=alert)
        try:
            tg("answerCallbackQuery", data=d)
        except Exception as e:
            log.warning("answerCallback fail: %s", e)

    try:
        if uid not in ADMIN_IDS:
            return ans("Ye bot sirf owner ke liye hai.", True)
        if chat is None:
            return
        parts = (cq.get("data") or "").split(":")
        act = parts[0]
        if act not in ("nk", "th", "tm"):
            PENDING.pop(uid, None)

        n = None
        if act not in ("main", "na", "nk"):
            n = find_name(st, parts[1]) if len(parts) > 1 else None
            if not n:
                ans("Ye channel ab list mein nahi hai.", True)
                return show(chat, mid, *sc_main(st))

        if act == "main":
            show(chat, mid, *sc_main(st))
        elif act == "ch":
            show(chat, mid, *sc_channel(st, n))

        # --- naya channel ---
        elif act == "na":
            PENDING[uid] = {"step": "cid"}
            show(chat, mid,
                 "➕ Naya Channel\n\n1) Bot ko us channel mein Admin banao (Post messages ON)\n"
                 "2) Phir yahan bhejo:\n"
                 "   • channel ka @username ya -100... id\n"
                 "   • ya channel ka koi bhi post yahan FORWARD kar do (sabse aasan)",
                 kb([[Btn("❌ Cancel", "main")]]))
        elif act == "nk":
            p = PENDING.get(uid)
            if not p or p.get("step") != "kind" or parts[1] not in KINDS:
                ans("Session khatam ho gaya, dobara Naya Channel dabao.", True)
                return show(chat, mid, *sc_main(st))
            PENDING.pop(uid, None)
            kind = parts[1]
            with LOCK:
                st["channels"][p["name"]] = {"chat_id": p["chat_id"], "kind": kind, "times": list(KINDS[kind]["times"])}
                save_state(st)
            ans("✅ Channel add ho gaya")
            show(chat, mid, *sc_channel(st, p["name"]))

        # --- time add ---
        elif act == "ta":
            PENDING[uid] = {"step": "time", "name": n}
            show(chat, mid, *sc_hour(n))
        elif act == "th":
            show(chat, mid, *sc_minute(n, int(parts[2])))
        elif act == "tm":
            show(chat, mid, *sc_ampm(n, int(parts[2]), int(parts[3])))
        elif act == "tp":
            ok, text = add_time(st, n, to24(int(parts[2]), int(parts[3]), parts[4]))
            ans(text, not ok)
            show(chat, mid, *sc_channel(st, n))

        # --- time remove ---
        elif act == "td":
            t = f"{parts[2][:2]}:{parts[2][2:]}"
            with LOCK:
                if t in st["channels"][n]["times"]:
                    st["channels"][n]["times"].remove(t)
                    save_state(st)
            ans(f"🗑 {fmt12(t)} hata diya")
            show(chat, mid, *sc_channel(st, n))

        # --- preview / live ---
        elif act == "pv":
            ans("⏳ Preview ban raha hai (30-60 sec)...")

            def job():
                try:
                    publish(n, st, target=chat, record=False)
                except Exception as e:
                    say(chat, f"❌ Fail: {str(e)[:300]}")
                say(chat, *sc_channel(st, n))
            run_job(chat, n, job)
        elif act == "lv":
            show(chat, mid, f"🚀 {n} pe ASLI post jayegi.\n\nPakka?",
                 kb([[Btn("✅ Haan, post karo", f"lg:{n}"), Btn("❌ Cancel", f"ch:{n}")]]))
        elif act == "lg":
            ans("⏳ Post ban rahi hai...")
            show(chat, mid, f"⏳ {n} ki live post ban rahi hai (30-60 sec)...")

            def job():
                try:
                    publish(n, st)
                    with LOCK:
                        save_state(st)
                    say(chat, f"✅ {n} pe post ho gayi.")
                except Exception as e:
                    say(chat, f"❌ Fail: {str(e)[:300]}")
                say(chat, *sc_channel(st, n))
            run_job(chat, n, job)

        # --- type badlo ---
        elif act == "ky":
            show(chat, mid, *sc_kinds(f"🎭 {n} ka type chuno 👇\n(content aur image ka style isse decide hota hai)",
                                      f"ks:{n}", st["channels"][n]["kind"], f"ch:{n}"))
        elif act == "ks":
            kind = parts[2]
            if kind in KINDS:
                with LOCK:
                    st["channels"][n]["kind"] = kind
                    save_state(st)
                ans(f"✅ Type: {KINDS[kind]['title']}")
            show(chat, mid, *sc_channel(st, n))

        # --- channel hatao ---
        elif act == "rm":
            show(chat, mid, f"🗑 {n} ko hata dein?\n\nIsme auto post band ho jayegi.",
                 kb([[Btn("✅ Haan, hatao", f"ry:{n}"), Btn("❌ Cancel", f"ch:{n}")]]))
        elif act == "ry":
            with LOCK:
                st["channels"].pop(n, None)
                save_state(st)
            ans(f"🗑 {n} hata diya")
            show(chat, mid, *sc_main(st))
        else:
            ans()
    except Exception as e:
        log.exception("callback error")
        ans(f"❌ Error: {str(e)[:150]}", True)
    finally:
        ans()


# ---------- messages (/start + jab bot text/forward maang raha ho) ----------
def handle_pending(st, chat, uid, msg):
    p = PENDING[uid]
    step = p["step"]
    text = (msg.get("text") or "").strip()
    cancel = kb([[Btn("❌ Cancel", "main")]])

    if step == "cid":
        ref = extract_chat_ref(msg)
        if not ref:
            return say(chat, "Samajh nahi aaya. @username ya -100... id bhejo, ya channel ka post forward karo.", cancel)
        try:
            info, is_admin = check_channel(ref)
        except Exception as e:
            return say(chat, f"Channel access nahi mila. Id/username sahi hai? Bot channel mein admin hai?\n{str(e)[:150]}", cancel)
        if not is_admin:
            return say(chat, "Bot us channel mein admin nahi hai. Pehle admin banao (Post messages ON), phir dobara bhejo.", cancel)
        p.update(chat_id=str(info["id"]), title=info.get("title", ""))
        if info.get("username"):
            return finish_name(st, chat, uid, p, info["username"])
        p["step"] = "name"
        return say(chat, f"✅ Channel mil gaya: {p['title']}\n\nIs channel ka koi chhota naam likho (letters/numbers/_, jaise MyFacts). "
                         "Yahi image par @naam ki tarah dikhega.", cancel)

    if step == "name":
        name = text.lstrip("@")
        if not re.fullmatch(r"\w{3,32}", name):
            return say(chat, "Naam 3-32 letters/numbers/underscore ka ho (space nahi). Dobara likho.", cancel)
        return finish_name(st, chat, uid, p, name)

    if step == "time":
        t24 = parse12(text)
        n = p["name"]
        back = kb([[Btn("⬅ Back", f"ch:{n}")]])
        if not t24:
            return say(chat, "⚠️ 12 ghante wala time AM/PM ke saath likho, jaise 6:30 PM ya 9 am\n(18:00 jaisa 24 ghante wala nahi chalega)", back)
        PENDING.pop(uid, None)
        ok, res = add_time(st, n, t24)
        say(chat, res)
        return say(chat, *sc_channel(st, n))


def finish_name(st, chat, uid, p, name):
    if not re.fullmatch(r"\w{3,32}", name):
        return say(chat, "Is channel ka username 3-32 letters/numbers/_ ka hona chahiye, dusra naam likho.",
                   kb([[Btn("❌ Cancel", "main")]]))
    old = find_name(st, name)
    if old:
        PENDING.pop(uid, None)
        say(chat, f"{old} pehle se list mein hai.")
        return say(chat, *sc_channel(st, old))
    p.update(step="kind", name=name)
    say(chat, *sc_kinds(f"✅ Channel mil gaya: {p['title'] or name}\nNaam: {name}\n\nAb iska type chuno 👇",
                        "nk"))


def handle_message(st, msg):
    chat = msg["chat"]["id"]
    if msg["chat"].get("type") != "private":
        return
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    if text.startswith("/myid"):
        return say(chat, f"Tumhara user id: {uid}\n(isko ADMIN_IDS variable mein daalo)")
    if not ADMIN_IDS:
        return say(chat, "ADMIN_IDS set nahi hai. /myid se apna id lo aur Railway variable ADMIN_IDS mein daalo.")
    if uid not in ADMIN_IDS:
        return say(chat, "Ye bot sirf owner ke liye hai.")
    if text.startswith("/"):
        PENDING.pop(uid, None)
        cmd = text.split()[0].lower().split("@")[0]
        if cmd in ("/start", "/menu", "/help", "/cancel", "/manage"):
            return say(chat, *sc_main(st))
        return say(chat, "Sab kuch buttons se hota hai 👇  (menu ke liye /start)", None)
    if uid in PENDING:
        handle_pending(st, chat, uid, msg)


def command_loop(st):
    offset = 0
    try:
        tg("deleteWebhook")
    except Exception:
        pass
    while True:
        try:
            r = tg("getUpdates", data={"offset": offset, "timeout": 50,
                                       "allowed_updates": json.dumps(["message", "callback_query"])})
            for u in r["result"]:
                offset = u["update_id"] + 1
                # har kaam alag thread mein, taaki preview/live ke dauran buttons atke nahi
                if "message" in u:
                    threading.Thread(target=handle_message, args=(st, u["message"]), daemon=True).start()
                elif "callback_query" in u:
                    threading.Thread(target=handle_callback, args=(st, u["callback_query"]), daemon=True).start()
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
    log.info("Bot started. Storage: %s | Channels: %s | Admins: %s", "MongoDB" if MONGO_URI else "file",
             ", ".join(st["channels"]), ADMIN_IDS or "NOT SET")
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
