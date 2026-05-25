import sqlite3
import json
from datetime import date, timedelta
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id       INTEGER PRIMARY KEY,
                    username      TEXT,
                    first_name    TEXT,
                    is_premium    INTEGER DEFAULT 0,
                    premium_until TEXT,
                    mode          TEXT DEFAULT 'general',
                    bonus_msgs    INTEGER DEFAULT 0,
                    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS usage (
                    user_id     INTEGER,
                    usage_date  TEXT,
                    msg_count   INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, usage_date)
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    user_id  INTEGER PRIMARY KEY,
                    messages TEXT DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS referrals (
                    referrer_id  INTEGER,
                    referred_id  INTEGER PRIMARY KEY,
                    rewarded     INTEGER DEFAULT 0
                );
            """)
            # Migrate: add bonus_msgs if missing (for existing DBs)
            try:
                conn.execute("ALTER TABLE users ADD COLUMN bonus_msgs INTEGER DEFAULT 0")
            except Exception:
                pass

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, username, first_name, is_premium, premium_until, mode, bonus_msgs "
                "FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if not row:
                conn.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                    (user_id, username, first_name)
                )
                return {"user_id": user_id, "is_premium": 0, "mode": "general", "bonus_msgs": 0}

            return dict(zip(
                ["user_id", "username", "first_name", "is_premium", "premium_until", "mode", "bonus_msgs"], row
            ))

    # ── Premium ───────────────────────────────────────────────────────────────

    def is_premium(self, user_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT is_premium, premium_until FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row or not row[0]:
                return False
            if row[1] and row[1] < date.today().isoformat():
                conn.execute("UPDATE users SET is_premium = 0 WHERE user_id = ?", (user_id,))
                return False
            return True

    def set_premium(self, user_id: int, days: int = 30):
        until = (date.today() + timedelta(days=days)).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
                (until, user_id)
            )

    def get_premium_until(self, user_id: int) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT premium_until FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0] if row else None

    # ── Usage ─────────────────────────────────────────────────────────────────

    def get_daily_usage(self, user_id: int) -> int:
        today = date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT msg_count FROM usage WHERE user_id = ? AND usage_date = ?",
                (user_id, today)
            ).fetchone()
            return row[0] if row else 0

    def increment_usage(self, user_id: int):
        today = date.today().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO usage (user_id, usage_date, msg_count) VALUES (?, ?, 1)
                   ON CONFLICT(user_id, usage_date) DO UPDATE SET msg_count = msg_count + 1""",
                (user_id, today)
            )

    # ── Bonus Messages ────────────────────────────────────────────────────────

    def get_bonus_msgs(self, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT bonus_msgs FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0] if row else 0

    def add_bonus_msgs(self, user_id: int, count: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET bonus_msgs = bonus_msgs + ? WHERE user_id = ?",
                (count, user_id)
            )

    def use_bonus_msg(self, user_id: int) -> bool:
        """Use one bonus message. Returns True if successful."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT bonus_msgs FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row and row[0] > 0:
                conn.execute(
                    "UPDATE users SET bonus_msgs = bonus_msgs - 1 WHERE user_id = ?",
                    (user_id,)
                )
                return True
            return False

    # ── Mode ──────────────────────────────────────────────────────────────────

    def get_mode(self, user_id: int) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mode FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0] if row else "general"

    def set_mode(self, user_id: int, mode: str):
        with self._conn() as conn:
            conn.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))

    # ── Referrals ─────────────────────────────────────────────────────────────

    def create_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Register referral. Returns True if new, False if already exists."""
        if referrer_id == referred_id:
            return False
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,)
            ).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, referred_id)
            )
            return True

    def get_referrer(self, referred_id: int) -> Optional[int]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT referrer_id FROM referrals WHERE referred_id = ? AND rewarded = 0",
                (referred_id,)
            ).fetchone()
            return row[0] if row else None

    def mark_referral_rewarded(self, referred_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE referrals SET rewarded = 1 WHERE referred_id = ?", (referred_id,)
            )

    def get_referral_count(self, referrer_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (referrer_id,)
            ).fetchone()
            return row[0] if row else 0

    # ── Conversation ──────────────────────────────────────────────────────────

    def get_conversation(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT messages FROM conversations WHERE user_id = ?", (user_id,)
            ).fetchone()
            return json.loads(row[0]) if row else []

    def save_conversation(self, user_id: int, messages: List[Dict]):
        messages = messages[-24:]
        data = json.dumps(messages)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO conversations (user_id, messages) VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET messages = ?""",
                (user_id, data, data)
            )

    def clear_conversation(self, user_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
