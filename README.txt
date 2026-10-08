TELEGRAM AUTO POSTER - SETUP
1. @BotFather se bot banao -> BOT_TOKEN
2. Bot ko har channel mein Admin banao (Post messages ON)
3. aistudio.google.com/apikey se GEMINI_API_KEY lo
4. Files GitHub repo mein daalo -> Railway pe Deploy from GitHub
5. Railway Variables: BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS, TIMEZONE=Asia/Kolkata
   (ADMIN_IDS ke liye pehle bot ko /myid bhejo, id milega, phir variable daalo)
6. Railway mein Volume banao, mount path /data, aur variable DATA_DIR=/data
   (isse /add /remove ki list redeploy ke baad bhi bachi rehti hai)

BOT COMMANDS (bot ko private chat mein bhejo)
/add TheHeartVerse -1001234567890
/add MyFacts -100123 fact 10:00,19:00     (naya channel: type bhi likho)
/remove TheHeartVerse
/list
/test TheHeartVerse          (preview sirf tumhari chat mein)
/test TheHeartVerse live     (channel pe asli post)
/times TheHeartVerse 09:00,21:30
/myid
Types: love, motivation, fact
