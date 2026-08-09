db.py  ->   import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger("db")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database.db")


def get_connection():
    """Get a SQLite database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the SQLite database schema if tables do not exist."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language_preference TEXT DEFAULT 'English',
                    current_level TEXT DEFAULT 'Beginner',
                    topics_covered TEXT DEFAULT '[]',
                    mistakes_repeated TEXT DEFAULT '[]',
                    custom_notes TEXT DEFAULT '',
                    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        logger.info(f"Database initialized at {os.path.abspath(DB_PATH)}")
    finally:
        conn.close()


def get_user_by_name_or_id(identifier: str) -> dict | None:
    """Look up a user profile by user_id or name (case-insensitive search).

    Returns a dict matching the schema:
    {
      "user_id": "string",
      "name": "string",
      "language_preference": "string",
      "facts": {
        "current_level": "string",
        "topics_covered": ["string"],
        "mistakes_repeated": ["string"],
        "custom_notes": "string"
      },
      "last_interaction": "timestamp"
    }
    """
    if not identifier:
        return None

    clean_id = identifier.strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM user_profiles
            WHERE LOWER(user_id) = ? OR LOWER(name) = ? OR LOWER(name) LIKE ?
            ORDER BY last_interaction DESC LIMIT 1
            """,
            (clean_id, clean_id, f"%{clean_id}%"),
        )
        row = cursor.fetchone()
        if not row:
            return None

        try:
            topics = json.loads(row["topics_covered"]) if row["topics_covered"] else []
        except Exception:
            topics = [row["topics_covered"]] if row["topics_covered"] else []

        try:
            mistakes = json.loads(row["mistakes_repeated"]) if row["mistakes_repeated"] else []
        except Exception:
            mistakes = [row["mistakes_repeated"]] if row["mistakes_repeated"] else []

        return {
            "user_id": row["user_id"],
            "name": row["name"],
            "language_preference": row["language_preference"],
            "facts": {
                "current_level": row["current_level"],
                "topics_covered": topics,
                "mistakes_repeated": mistakes,
                "custom_notes": row["custom_notes"] or "",
            },
            "last_interaction": row["last_interaction"],
        }
    finally:
        conn.close()


def save_user_profile(
    user_id: str,
    name: str,
    language_preference: str,
    current_level: str,
    topics_covered: list[str],
    mistakes_repeated: list[str],
    consent_given: bool,
    custom_notes: str = "",
) -> dict:
    """Save or update a user profile in the database.

    HARD RULE (Step 5): If consent_given is False, no data will be saved.
    """
    if not consent_given:
        logger.warning(f"Consent NOT granted for user '{name}'. Skipping save operation.")
        return {
            "status": "error",
            "message": "User consent was NOT granted. No data was saved to database per privacy rules.",
        }

    clean_user_id = user_id or name.lower().strip().replace(" ", "_")
    existing_user = get_user_by_name_or_id(clean_user_id)

    # Merge newly discussed topics with existing saved topics
    merged_topics = []
    if existing_user and existing_user["facts"]["topics_covered"]:
        merged_topics.extend(existing_user["facts"]["topics_covered"])
    for topic in topics_covered:
        if topic and topic not in merged_topics:
            merged_topics.append(topic)

    # Merge mistakes
    merged_mistakes = []
    if existing_user and existing_user["facts"]["mistakes_repeated"]:
        merged_mistakes.extend(existing_user["facts"]["mistakes_repeated"])
    for mistake in mistakes_repeated:
        if mistake and mistake not in merged_mistakes:
            merged_mistakes.append(mistake)

    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    topics_json = json.dumps(merged_topics)
    mistakes_json = json.dumps(merged_mistakes)

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_profiles (
                    user_id, name, language_preference, current_level,
                    topics_covered, mistakes_repeated, custom_notes, last_interaction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    language_preference = excluded.language_preference,
                    current_level = excluded.current_level,
                    topics_covered = excluded.topics_covered,
                    mistakes_repeated = excluded.mistakes_repeated,
                    custom_notes = excluded.custom_notes,
                    last_interaction = excluded.last_interaction
                """,
                (
                    clean_user_id,
                    name,
                    language_preference,
                    current_level,
                    topics_json,
                    mistakes_json,
                    custom_notes,
                    now_str,
                ),
            )
        logger.info(
            f"Successfully saved user profile for '{name}' (ID: {clean_user_id}), topics: {merged_topics}."
        )
        return {
            "status": "success",
            "message": f"Successfully saved progress for {name}. Topics recorded: {', '.join(merged_topics)}.",
            "user": {
                "user_id": clean_user_id,
                "name": name,
                "language_preference": language_preference,
                "facts": {
                    "current_level": current_level,
                    "topics_covered": merged_topics,
                    "mistakes_repeated": merged_mistakes,
                    "custom_notes": custom_notes,
                },
                "last_interaction": now_str,
            },
        }
    finally:
        conn.close()


def list_all_users() -> list[dict]:
    """Helper function to list all registered users in the database."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_profiles ORDER BY last_interaction DESC")
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "language_preference": row["language_preference"],
                    "facts": {
                        "current_level": row["current_level"],
                        "topics_covered": json.loads(row["topics_covered"] or "[]"),
                        "mistakes_repeated": json.loads(row["mistakes_repeated"] or "[]"),
                        "custom_notes": row["custom_notes"] or "",
                    },
                    "last_interaction": row["last_interaction"],
                }
            )
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
