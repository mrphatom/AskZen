# 🤖 Telegram AI Assistant Bot

A monetizable AI assistant bot powered by **Groq (Llama 3.3)** with **Telegram Stars** payments — zero API cost to run.

---

## ✨ Features

| Feature | Free | Premium |
|---|---|---|
| Messages | 20/day | Unlimited |
| AI Modes (5 personalities) | ✅ | ✅ |
| Conversation memory | ✅ | ✅ (longer) |
| Priority responses | ❌ | ✅ |

### AI Modes
- 🤖 **General** — All-around assistant
- 💻 **Code Expert** — Programming & debugging
- ✍️ **Writing Pro** — Writing, editing & content
- 📊 **Analyst** — Research & strategy
- 🎓 **Tutor** — Learn any topic

---

## 🚀 Setup (5 steps)

### Step 1 — Create your Telegram bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Choose a name and username
4. Copy the **bot token** you receive

### Step 2 — Enable Telegram Stars payments

1. In BotFather, send `/mybots`
2. Select your bot → **Payments**
3. Choose **Telegram Stars** as provider
4. Done — no extra configuration needed

### Step 3 — Get your free Groq API key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (free)
3. Create an API key → copy it

### Step 4 — Deploy to Railway (free)

1. Push this project to a GitHub repo
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
3. Select your repo
4. Go to **Variables** and add:
   ```
   BOT_TOKEN=your_token_here
   GROQ_API_KEY=your_groq_key_here
   ```
5. Railway auto-detects the `Procfile` and deploys

> ✅ That's it. Your bot is live.

---

## 💻 Run locally (optional)

```bash
# 1. Clone & enter directory
cd telegram-ai-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
cp .env.example .env
# Edit .env with your tokens

# 4. Run
python bot.py
```

To load `.env` locally, add this to the top of `bot.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 💰 Monetization

- Users pay **250 Telegram Stars (~$3.50)** for 30 days of Premium
- Telegram Stars are purchased inside the Telegram app — no payment processor setup needed
- You receive Stars directly; withdraw via BotFather → `/mybots` → Payments

To adjust pricing, change in `bot.py`:
```python
PREMIUM_STARS = 250   # Price in Stars
PREMIUM_DAYS  = 30    # Duration in days
```

---

## ⚙️ Customization

### Change free daily limit
```python
FREE_LIMIT = 20  # messages per day
```

### Change AI model
```python
GROQ_MODEL = "llama-3.3-70b-versatile"  # or "llama-3.1-8b-instant" for faster/lighter
```

### Add/edit AI modes
Edit the `MODES` dictionary in `bot.py`. Each mode has:
- `name` — Display name with emoji
- `desc` — Short description
- `prompt` — System prompt (personality)

---

## 📁 Project Structure

```
telegram-ai-bot/
├── bot.py          # Main bot — all handlers, AI, payments
├── database.py     # SQLite — users, usage, conversations
├── requirements.txt
├── Procfile        # Railway deployment
├── .env.example    # Environment variable template
└── README.md
```

---

## 🛠 Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/mode` | Switch AI personality |
| `/status` | Plan & usage info |
| `/reset` | Clear conversation history |
| `/premium` | Upgrade page |
| `/help` | Command reference |

---

## ❓ FAQ

**Q: Will I get charged for Groq API?**  
A: No. Groq's free tier is very generous — more than enough for a starting bot.

**Q: What if Groq rate limits hit?**  
A: The bot returns a friendly error. You can upgrade to Groq paid later if you scale.

**Q: Where is user data stored?**  
A: In a local SQLite file (`bot.db`). On Railway, it persists on disk. For production scale, swap for PostgreSQL.

**Q: Can I add more payment options?**  
A: Yes. Telegram also supports Stripe, YooMoney, and others via BotFather → Payments.
