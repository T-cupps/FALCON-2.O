import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger("db")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database.db")


def get_connection():
    """Get a SQLite database connection with row factory."""
    current_db_path = os.environ.get("DB_PATH", DB_PATH)
    conn = sqlite3.connect(current_db_path)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT DEFAULT '',
                    user_message TEXT NOT NULL,
                    agent_response TEXT NOT NULL,
                    topic TEXT DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def save_conversation_turn(
    session_id: str,
    user_id: str,
    user_message: str,
    agent_response: str,
    topic: str = "",
) -> dict:
    """Save a conversation turn (user message & agent response) into SQLite database."""
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_session_id = session_id or "default_session"
    clean_user_id = user_id or "guest"
    clean_user_msg = user_message.strip()
    clean_agent_resp = agent_response.strip()

    if not clean_user_msg or not clean_agent_resp:
        return {"status": "skipped", "message": "Empty message or response, skipping save."}

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO conversation_memory (
                    session_id, user_id, user_message, agent_response, topic, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_session_id,
                    clean_user_id,
                    clean_user_msg,
                    clean_agent_resp,
                    topic,
                    now_str,
                ),
            )
        logger.info(
            f"Saved conversation turn for session '{clean_session_id}', topic '{topic}' into database."
        )
        return {"status": "success", "message": "Saved conversation turn to database."}
    except Exception as e:
        logger.error(f"Error saving conversation turn to database: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def get_recent_conversation_memory(
    user_id: str = "", session_id: str = "", limit: int = 5
) -> list[dict]:
    """Retrieve recent conversation memory turns from SQLite database."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                """
                SELECT * FROM conversation_memory
                WHERE LOWER(user_id) = ? OR LOWER(session_id) = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (user_id.lower().strip(), session_id.lower().strip(), limit),
            )
        elif session_id:
            cursor.execute(
                """
                SELECT * FROM conversation_memory
                WHERE LOWER(session_id) = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (session_id.lower().strip(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM conversation_memory
                ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        turns = []
        for r in reversed(rows):  # return in chronological order
            turns.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "user_id": r["user_id"],
                    "user_message": r["user_message"],
                    "agent_response": r["agent_response"],
                    "topic": r["topic"],
                    "timestamp": r["timestamp"],
                }
            )
        return turns
    except Exception as e:
        logger.error(f"Error retrieving conversation memory from database: {e}")
        return []
    finally:
        conn.close()


def get_last_learning_topic(user_id: str = "", session_id: str = "") -> str | None:
    """Retrieve the most recent learning topic or context from conversation memory or user profile."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # First check conversation memory for recent explicit topic
        if user_id:
            cursor.execute(
                """
                SELECT topic FROM conversation_memory
                WHERE (LOWER(user_id) = ? OR LOWER(session_id) = ?) AND topic != ''
                ORDER BY timestamp DESC LIMIT 1
                """,
                (user_id.lower().strip(), session_id.lower().strip()),
            )
        else:
            cursor.execute(
                """
                SELECT topic FROM conversation_memory
                WHERE topic != ''
                ORDER BY timestamp DESC LIMIT 1
                """
            )
        row = cursor.fetchone()
        if row and row["topic"]:
            return row["topic"]

        # Fallback to user_profiles topics for specified user
        if user_id:
            user = get_user_by_name_or_id(user_id)
            if user and user["facts"]["topics_covered"]:
                return user["facts"]["topics_covered"][-1]
            return None

        all_users = list_all_users()
        if all_users and all_users[0]["facts"]["topics_covered"]:
            return all_users[0]["facts"]["topics_covered"][-1]

        return None
    except Exception as e:
        logger.error(f"Error getting last learning topic: {e}")
        return None
    finally:
        conn.close()



if __name__ == "__main__":
    init_db()
    print("Database initialized.")
