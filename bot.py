import os
import logging
import asyncio
from groq import Groq
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)
from database import Database

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
FREE_LIMIT     = 20          # free messages per day
PREMIUM_STARS  = 750         # 750 Stars price profile
PREMIUM_DAYS   = 30
GROQ_MODEL     = "llama-3.3-70b-versatile"
MAX_MEMORY     = 10          # Bounded conversation turns for Groq free tier stability

# ── Adaptive & Humane AI Modes ────────────────────────────────────────────────
MODES = {
    "general": {
        "name": "🤖 AskZen Companion",
        "desc": "An authentic, adaptive, and witty helper",
        "prompt": "You are AskZen, an authentic, supportive, and clever AI companion. Match the user's tone, energy, and vibe naturally. Be empathetic but candid. If the user is casual, be casual and use light wit. Avoid standard corporate AI filler phrases like 'As an AI...', 'Sure, I can help with that!', or 'Is there anything else?'. Just converse naturally, like a sharp, grounded peer. Use markdown smoothly for clarity."
    },
    "code": {
        "name": "💻 Code Partner",
        "desc": "A sharp senior dev sitting right next to you",
        "prompt": "You are a brilliant, highly practical senior software engineer. You don't just dump code blocks; you treat the user like a peer. Think through edge cases out loud, suggest clean and modern architecture, and explain your fixes without being patronizing. Format code beautifully and add meaningful comments."
    },
    "writer": {
        "name": "✍️ Creative Producer",
        "desc": "Collaborative editor and script stylist",
        "prompt": "You are an intuitive creative writer and editor with an eye for rhythm, tone, and impact. Whether working on scripts, essays, or casual copy, match the target audience perfectly. Give suggestions to heighten dramatic tension or emotional clarity when editing creative pieces. Keep feedback sharp, encouraging, and collaborative."
    },
    "analyst": {
        "name": "📊 Strategy Lead",
        "desc": "Structured breakdowns and raw insights",
        "prompt": "You are a pragmatic, data-fluent strategist. Don't state the obvious. Break down complex ecosystems, spot trends, and deliver highly structured, scannable breakdowns. Cut straight to the value, using bolding and formatting to make insights instantly digestible."
    },
    "tutor": {
        "name": "🎓 Mind Coach",
        "desc": "Brilliant breakdowns without the textbook boredom",
        "prompt": "You are an exceptionally engaging, patient tutor. Demystify complex concepts using vivid analogies, real-world examples, and foundational breakdowns. Never speak down to the learner. End your explanations with a single, thought-provoking question to check for understanding and keep them hooked."
    }
}

# ── Init ──────────────────────────────────────────────────────────────────────
db          = Database()
groq_client = Groq(api_key=GROQ_API_KEY)


# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎛 Switch Mode",  callback_data="show_modes"),
            InlineKeyboardButton("🔁 Reset Chat",   callback_data="reset_chat"),
        ],
        [
            InlineKeyboardButton("⭐ Get Premium",  callback_data="show_premium"),
            InlineKeyboardButton("📊 My Status",    callback_data="show_status"),
        ],
    ])


def mode_kb() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for key, m in MODES.items():
        row.append(InlineKeyboardButton(m["name"], callback_data=f"mode_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="show_main")])
    return InlineKeyboardMarkup(buttons)

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="show_main")]])


# ── AI Call with Rolling Memory ───────────────────────────────────────────────
async def call_ai(user_id: int, user_message: str) -> str:
    mode_key = db.get_mode(user_id)
    mode     = MODES.get(mode_key, MODES["general"])
    history  = db.get_conversation(user_id)

    # Append user intent
    history.append({"role": "user", "content": user_message})

    # Strict slice to avoid exceeding free-tier token allowances
    if len(history) > MAX_MEMORY:
        history = history[-MAX_MEMORY:]

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": mode["prompt"]}] + history,
            max_tokens=1200,
            temperature=0.75,
        )
        reply = resp.choices[0].message.content
        
        history.append({"role": "assistant", "content": reply})
        db.save_conversation(user_id, history)
        return reply

    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ I ran into a temporary hitch communicating with my brain. Mind giving that message another go?"


# ── Continuous Chat Action Loop ───────────────────────────────────────────────
async def keep_typing_loop(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
        except Exception:
            break


# ── Safe send (handles markdown errors + 4096 char limit) ────────────────────
async def safe_send(update: Update, text: str, **kwargs):
    MAX = 4000
    chunks = []

    if len(text) <= MAX:
        chunks = [text]
    else:
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX:
                chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current)

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown", **kwargs)
        except Exception:
            await update.message.reply_text(chunk, **kwargs)


# ── Command Handlers ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)

    await update.message.reply_text(
        f"👋 Hey *{user.first_name}*! Welcome to *AskZen* — your adaptive, conversational AI companion.\n\n"
        f"*What we can tackle together:*\n"
        f"• Break down complex topics or learn new skills\n"
        f"• Brainstorm, write, or refine creative copy & scripts\n"
        f"• Build, review, and debug clean code\n"
        f"• Dive deep into structured research & strategy analysis\n\n"
        f"🆓 *Free:* {FREE_LIMIT} messages/day\n"
        f"⭐ *Premium:* Unlimited interactions for {PREMIUM_STARS} Stars/month\n\n"
        f"Drop a message below and let's get into it! 👇",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 Shortcut Directory*\n\n"
        "/start — Reopen introduction & main features\n"
        "/mode — Adjust my behavioral perspective\n"
        "/status — Look over your active plan details\n"
        "/reset — Wipe active context for a clean slate\n"
        "/premium — Go unlimited with Premium\n"
        "/help — Bring up this list",
        parse_mode="Markdown",
    )


async def cmd_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id      = update.effective_user.id
    current_mode = MODES[db.get_mode(user_id)]["name"]
    await update.message.reply_text(
        f"*🎛 Active Mode*\n\nCurrent alignment: {current_mode}\n\nSelect a new specialization:",
        parse_mode="Markdown",
        reply_markup=mode_kb(),
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    db.get_or_create_user(user_id)
    is_prem  = db.is_premium(user_id)
    usage    = db.get_daily_usage(user_id)
    mode     = MODES[db.get_mode(user_id)]["name"]
    until    = db.get_premium_until(user_id)

    plan       = "⭐ Premium" if is_prem else "🆓 Free Tier"
    limit_text = "Unlimited Access" if is_prem else f"{usage} / {FREE_LIMIT} used today"
    expiry     = f"\nExpires: {until}" if is_prem and until else ""

    await update.message.reply_text(
        f"*📊 Account Insights*\n\n"
        f"Plan Level: {plan}{expiry}\n"
        f"Daily Allowance: {limit_text}\n"
        f"Active Mindset: {mode}\n\n"
        f"{'✅ Enjoy the unrestricted access!' if is_prem else f'👉 Type /premium to unlock unlimited use'}",
        parse_mode="Markdown",
    )


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.clear_conversation(update.effective_user.id)
    await update.message.reply_text("🔁 Context wiped clean. Let's start fresh!", reply_markup=main_kb())


async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_premium(user_id):
        await update.message.reply_text("⭐ You're already rocking AskZen Premium — enjoy the limitless workspace!")
        return

    await update.message.reply_text(
        f"⭐ *AskZen Premium*\n\n"
        f"✅ Completely unlimited messaging\n"
        f"✅ Unlocked high-performance specialized modes\n"
        f"✅ Enhanced processing speeds\n\n"
        f"*Cost:* {PREMIUM_STARS} Telegram Stars / 30 Days\n\n"
        f"Tap below to switch over instantly 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⭐ Claim AskZen Premium", callback_data="buy_premium")
        ]]),
    )


# ── Message Handler ───────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    text    = update.message.text

    db.get_or_create_user(user_id, user.username, user.first_name)

    if not db.is_premium(user_id):
        usage = db.get_daily_usage(user_id)
        if usage >= FREE_LIMIT:
            await update.message.reply_text(
                f"⚠️ You've fully utilized your {FREE_LIMIT} free messages for the day.\n\n"
                f"Let's reconnect tomorrow, or upgrade right now to clear the caps! 👇",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⭐ Unlock Premium", callback_data="buy_premium")
                ]]),
            )
            return

    db.increment_usage(user_id)

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing_loop(ctx, update.effective_chat.id, stop_typing))

    try:
        reply = await call_ai(user_id, text)
    finally:
        stop_typing.set()
        await typing_task

    await safe_send(update, reply)


# ── Callback Handler ──────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    data    = query.data
    await query.answer()

    if data.startswith("mode_"):
        key = data.removeprefix("mode_")
        if key in MODES:
            db.set_mode(user_id, key)
            db.clear_conversation(user_id)
            m = MODES[key]
            await query.edit_message_text(
                f"✅ Mindset realigned to *{m['name']}*\n_{m['desc']}_\n\nContext cleared for a focused start. Let's dive in! 💬",
                parse_mode="Markdown",
            )
        return

    if data == "show_modes":
        current = MODES[db.get_mode(user_id)]["name"]
        await query.edit_message_text(
            f"*🎛 AI Mindsets*\n\nCurrent setting: {current}\n\nSelect a focus:",
            parse_mode="Markdown",
            reply_markup=mode_kb(),
        )

    elif data == "reset_chat":
        db.clear_conversation(user_id)
        await query.edit_message_text("🔁 Context wiped clean. Let's start fresh!", reply_markup=main_kb())

    elif data == "show_status":
        is_prem  = db.is_premium(user_id)
        usage    = db.get_daily_usage(user_id)
        mode     = MODES[db.get_mode(user_id)]["name"]
        until    = db.get_premium_until(user_id)
        plan       = "⭐ Premium" if is_prem else "🆓 Free Tier"
        limit_text = "Unlimited" if is_prem else f"{usage} / {FREE_LIMIT} daily chunks used"
        expiry     = f"\nExpires: {until}" if is_prem and until else ""
        await query.edit_message_text(
            f"*📊 Account Insights*\n\nPlan Level: {plan}{expiry}\nUsage: {limit_text}\nActive Focus: {mode}\n\n"
            f"{'✅ Unlimited access is live.' if is_prem else '👉 Upgrade to skip the daily caps.'}",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )

    elif data == "show_premium":
        if db.is_premium(user_id):
            await query.edit_message_text("⭐ Premium access is already active on this profile!")
            return
        await query.edit_message_text(
            f"⭐ *AskZen Premium*\n\n"
            f"✅ Totally unlimited messages\n"
            f"✅ Full access to specialized persona layers\n"
            f"✅ Priority generation queues\n\n"
            f"*Cost:* {PREMIUM_STARS} Telegram Stars / 30 Days",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Claim Premium Pass", callback_data="buy_premium")],
                [InlineKeyboardButton("⬅️ Return",   callback_data="show_main")],
            ]),
        )

    elif data == "show_main":
        await query.edit_message_text("What are we working on next?", reply_markup=main_kb())

    elif data == "buy_premium":
        await ctx.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="⭐ AskZen Premium",
            description=f"Unrestricted AI assistance for {PREMIUM_DAYS} days. All cognitive mindsets active.",
            payload=f"premium_{user_id}_{PREMIUM_DAYS}",
            provider_token="",   
            currency="XTR",
            prices=[LabeledPrice("Premium Access (30 Days)", PREMIUM_STARS)],
        )


# ── Payment Handlers ──────────────────────────────────────────────────────────
async def precheckout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def payment_success(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.set_premium(user_id, PREMIUM_DAYS)
    until = db.get_premium_until(user_id)
    await update.message.reply_text(
        f"🎉 *Welcome to AskZen Premium!*\n\n"
        f"Your unlimited sandbox is fully unlocked until *{until}*.\n"
        f"Let's see what you create next! ⭐\n\n"
        f"Drop your ideas right here 👇",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        raise ValueError("BOT_TOKEN and GROQ_API_KEY must be configured inside environment vars.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("mode",    cmd_mode))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("premium", cmd_premium))

    # Inputs
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Financials
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

    logger.info("🧘 AskZen is actively running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
