TELEGRAM AUTO POSTER - SETUP
1. @BotFather se bot banao -> BOT_TOKEN
2. Bot ko har channel mein Admin banao (Post messages ON)
3. aistudio.google.com/apikey se GEMINI_API_KEY lo
4. Files GitHub repo mein daalo -> Railway pe Deploy from GitHub
5. Railway Variables: BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS, TIMEZONE=Asia/Kolkata
   (ADMIN_IDS ke liye pehle bot ko /myid bhejo, id milega, phir variable daalo)
6. DATA SAVE (redeploy par data na ude) - ek chuno:
   A) MongoDB (recommended): Railway variables mein MONGO_URI (aur chaho to MONGO_DB=autoposter) daalo.
      Channels, times, history sab MongoDB mein save hota hai. Pehli baar purani state.json hogi to apne aap import ho jayegi.
      /start ke menu ke neeche "Data: MongoDB ✅" dikhega.
   B) Volume: mount path /data aur DATA_DIR=/data (MONGO_URI na ho tab ye use hota hai).

BOT KAISE CHALAYE (sab BUTTONS se, private chat mein)
/start  -> TheHeartVerse, RiseFuelQuotes, FactForge ... har channel ka button line by line
Channel pe tap karo:
  ➕ Time Add Karo   -> ghanta -> minute -> AM/PM tap (ya seedha type: 6:30 PM)
  ❌ 9:00 AM         -> time pe tap = hat gaya
  👁 Preview         -> post sirf tumhari chat mein
  🚀 Live Post       -> channel pe asli post (confirm puchta hai)
  🎭 Type Badlo      -> love / motivation / fact
  🗑 Channel Hatao   -> confirm ke baad hat jata hai
/start mein ➕ Naya Channel Add Karo -> channel ka post forward karo (ya @username / -100 id) -> type chuno. Bas.
Time sirf 12 ghante (AM/PM) mein dikhta aur liya jata hai.
/myid -> apna user id (ADMIN_IDS ke liye)

CHANNEL TYPES (har ka apna content + caption + image logic)
  love        -> TheHeartVerse     (quotes, English + Hinglish)
  motivation  -> RiseFuelQuotes
  fact        -> FactForge
  startup     -> StartSpark        (roz 1 startup idea, English + Hinglish)
  cook        -> TheCookTable      (recipe ya kitchen hack, English + Hinglish, sirf food photo)
  timeline    -> TimelineToday     (aaj ki date ke 10+ events, Wikipedia se asli data; ek post mein na aayein to 2, phir 3 post)
Teeno naye channel (StartSpark, TheCookTable, TimelineToday) bot ko pehli baar chalane par apne aap list mein aa jate hain.
Bot ko in channels mein Admin banana (Post messages ON) zaroori hai.

NAYA TYPE (alag logic wala channel) jodna ho: bot.py mein KINDS ke andar ek block copy-paste karo
(content rules, Gemini JSON keys, image style). Caption ka naya design chahiye to CAPTIONS mein ek function jodo.
Wo type apne aap button mein aa jayega.
