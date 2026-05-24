import os
import logging
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
PREMIUM_STARS  = 250         # Telegram Stars price (~$3.50)
PREMIUM_DAYS   = 30
GROQ_MODEL     = "llama-3.3-70b-versatile"

# ── AI Modes ──────────────────────────────────────────────────────────────────
MODES = {
    "general": {
        "name": "🤖 General Assistant",
        "desc": "Smart all-around helper",
        "prompt": (
            "You are a highly capable, friendly AI assistant. Be direct, concise, and genuinely helpful. "
            "Use markdown formatting (bold, bullet points, code blocks) when it improves clarity. "
            "Avoid filler phrases. Think before answering complex questions."
        ),
    },
    "code": {
        "name": "💻 Code Expert",
        "desc": "Programming & debugging",
        "prompt": (
            "You are a senior software engineer with deep expertise across all languages and frameworks. "
            "Write clean, efficient, well-commented code. Debug systematically. "
            "Always explain your approach. Format code in proper code blocks."
        ),
    },
    "writer": {
        "name": "✍️ Writing Pro",
        "desc": "Writing, editing & content",
        "prompt": (
            "You are a professional writer and editor. Help craft compelling emails, essays, social posts, "
            "scripts, and creative content. Improve clarity, tone, and impact. "
            "Ask about the audience and purpose when it matters."
        ),
    },
    "analyst": {
        "name": "📊 Analyst",
        "desc": "Research, strategy & insights",
        "prompt": (
            "You are a sharp analyst skilled at breaking down complex topics, summarizing research, "
            "building frameworks, and delivering structured insights. Use bullet points and headers. "
            "Be data-driven and concise."
        ),
    },
    "tutor": {
        "name": "🎓 Tutor",
        "desc": "Learn any topic clearly",
        "prompt": (
            "You are a patient, brilliant tutor. Explain concepts at the right level for the learner. "
            "Use examples, analogies, and step-by-step breakdowns. "
            "Check for understanding and encourage curiosity."
        ),
    },
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


# ── AI Call ───────────────────────────────────────────────────────────────────
async def call_ai(user_id: int, user_message: str) -> str:
    mode_key = db.get_mode(user_id)
    mode     = MODES.get(mode_key, MODES["general"])
    history  = db.get_conversation(user_id)

    history.append({"role": "user", "content": user_message})

    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": mode["prompt"]}] + history,
            max_tokens=1500,
            temperature=0.7,
        )
        reply = resp.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        db.save_conversation(user_id, history)
        return reply

    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "⚠️ Something went wrong on my end. Please try again."


# ── Safe send (handles markdown errors + 4096 char limit) ────────────────────
async def safe_send(update: Update, text: str, **kwargs):
    MAX = 4000
    chunks = []

    if len(text) <= MAX:
        chunks = [text]
    else:
        # Split on double newlines, then single newlines
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
        f"👋 Hey *{user.first_name}*! Welcome to *AskZen* — your AI assistant, powered by Llama 3.3.\n\n"
        f"*What I can do:*\n"
        f"• Answer questions on any topic\n"
        f"• Write, edit & improve your text\n"
        f"• Help with code & debugging\n"
        f"• Research, summarize & analyze\n"
        f"• Teach you anything, step by step\n\n"
        f"🆓 *Free:* {FREE_LIMIT} messages/day\n"
        f"⭐ *AskZen Premium:* Unlimited messages for {PREMIUM_STARS} Stars/month\n\n"
        f"Just start chatting! 👇",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*📖 Commands*\n\n"
        "/start — Welcome & overview\n"
        "/mode — Switch AI personality\n"
        "/status — Your plan & usage\n"
        "/reset — Clear conversation\n"
        "/premium — Upgrade to Premium\n"
        "/help — This message\n\n"
        "*Tips:*\n"
        "• I remember context within our chat\n"
        "• Switch /mode to get a specialist AI\n"
        "• Use /reset to start fresh",
        parse_mode="Markdown",
    )


async def cmd_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id      = update.effective_user.id
    current_mode = MODES[db.get_mode(user_id)]["name"]
    await update.message.reply_text(
        f"*🎛 AI Mode*\n\nCurrent: {current_mode}\n\nPick a mode:",
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

    plan       = "⭐ Premium" if is_prem else "🆓 Free"
    limit_text = "Unlimited" if is_prem else f"{usage} / {FREE_LIMIT} today"
    expiry     = f"\nExpires: {until}" if is_prem and until else ""

    await update.message.reply_text(
        f"*📊 Your Status*\n\n"
        f"Plan: {plan}{expiry}\n"
        f"Messages: {limit_text}\n"
        f"Mode: {mode}\n\n"
        f"{'✅ Enjoy unlimited messages!' if is_prem else f'👉 /premium to go unlimited'}",
        parse_mode="Markdown",
    )


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.clear_conversation(update.effective_user.id)
    await update.message.reply_text("🔁 Conversation cleared. Fresh start!", reply_markup=main_kb())


async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_premium(user_id):
        await update.message.reply_text("⭐ You're already on AskZen Premium — enjoy unlimited messages!")
        return

    await update.message.reply_text(
        f"⭐ *AskZen Premium*\n\n"
        f"✅ Unlimited messages\n"
        f"✅ All 5 AI modes\n"
        f"✅ Longer conversation memory\n"
        f"✅ Priority processing\n\n"
        f"*Price:* {PREMIUM_STARS} Telegram Stars / 30 days\n\n"
        f"Tap below to subscribe 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⭐ Buy AskZen Premium", callback_data="buy_premium")
        ]]),
    )


# ── Message Handler ───────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    text    = update.message.text

    db.get_or_create_user(user_id, user.username, user.first_name)

    # Daily limit check
    if not db.is_premium(user_id):
        usage = db.get_daily_usage(user_id)
        if usage >= FREE_LIMIT:
            await update.message.reply_text(
                f"⚠️ You've used your {FREE_LIMIT} free messages for today.\n\n"
                f"Come back tomorrow, or upgrade to keep going now! 👇",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⭐ Get Premium", callback_data="buy_premium")
                ]]),
            )
            return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    db.increment_usage(user_id)

    reply = await call_ai(user_id, text)
    await safe_send(update, reply)


# ── Callback Handler ──────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    data    = query.data
    await query.answer()

    # ── Mode switch
    if data.startswith("mode_"):
        key = data.removeprefix("mode_")
        if key in MODES:
            db.set_mode(user_id, key)
            db.clear_conversation(user_id)
            m = MODES[key]
            await query.edit_message_text(
                f"✅ Switched to *{m['name']}*\n_{m['desc']}_\n\nChat history cleared. Go! 💬",
                parse_mode="Markdown",
            )
        return

    if data == "show_modes":
        current = MODES[db.get_mode(user_id)]["name"]
        await query.edit_message_text(
            f"*🎛 AI Mode*\n\nCurrent: {current}\n\nPick a mode:",
            parse_mode="Markdown",
            reply_markup=mode_kb(),
        )

    elif data == "reset_chat":
        db.clear_conversation(user_id)
        await query.edit_message_text("🔁 Conversation cleared. Fresh start!", reply_markup=main_kb())

    elif data == "show_status":
        is_prem  = db.is_premium(user_id)
        usage    = db.get_daily_usage(user_id)
        mode     = MODES[db.get_mode(user_id)]["name"]
        until    = db.get_premium_until(user_id)
        plan       = "⭐ Premium" if is_prem else "🆓 Free"
        limit_text = "Unlimited" if is_prem else f"{usage} / {FREE_LIMIT} today"
        expiry     = f"\nExpires: {until}" if is_prem and until else ""
        await query.edit_message_text(
            f"*📊 Your Status*\n\nPlan: {plan}{expiry}\nMessages: {limit_text}\nMode: {mode}\n\n"
            f"{'✅ Enjoy unlimited messages!' if is_prem else '👉 Upgrade for unlimited access'}",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )

    elif data == "show_premium":
        if db.is_premium(user_id):
            await query.edit_message_text("⭐ You're already Premium!")
            return
        await query.edit_message_text(
            f"⭐ *AskZen Premium*\n\n"
            f"✅ Unlimited messages\n"
            f"✅ All 5 AI modes\n"
            f"✅ Longer memory\n\n"
            f"*Price:* {PREMIUM_STARS} Telegram Stars / 30 days",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Buy Now", callback_data="buy_premium")],
                [InlineKeyboardButton("⬅️ Back",   callback_data="show_main")],
            ]),
        )

    elif data == "show_main":
        await query.edit_message_text("What would you like to do?", reply_markup=main_kb())

    elif data == "buy_premium":
        await ctx.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="⭐ AskZen Premium",
            description=f"Unlimited AI messages for {PREMIUM_DAYS} days. All 5 modes included.",
            payload=f"premium_{user_id}_{PREMIUM_DAYS}",
            provider_token="",   # Empty for Telegram Stars
            currency="XTR",
            prices=[LabeledPrice("Premium – 30 days", PREMIUM_STARS)],
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
        f"You're now Premium until *{until}*.\n"
        f"Enjoy unlimited messages! ⭐\n\n"
        f"Just keep chatting 👇",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN or not GROQ_API_KEY:
        raise ValueError("BOT_TOKEN and GROQ_API_KEY must be set in environment variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("mode",    cmd_mode))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("premium", cmd_premium))

    # Messages & callbacks
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Payments
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))

    logger.info("🧘 AskZen is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
