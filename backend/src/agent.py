import json
import logging
import os
import random
import re

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    UserInputTranscribedEvent,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

from db import (  # noqa: E402
    get_last_learning_topic,
    get_recent_conversation_memory,
    get_user_by_name_or_id,
    init_db,
    list_all_users,
    save_conversation_turn,
    save_user_profile,
)
from prompt import SYSTEM_PROMPT  # noqa: E402

logger = logging.getLogger("agent")



def extract_name_from_transcript(text: str) -> str | None:
    text_lower = text.lower().strip()
    patterns = [
        r"(?:my name is|i am|i'm|call me|this is)\s+([a-zA-Z\u0900-\u097F]+)",
        r"^([a-zA-Z\u0900-\u097F]{2,15})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            raw_name = match.group(1).capitalize()
            if raw_name.lower() not in {
                "yes",
                "no",
                "hello",
                "hi",
                "okay",
                "thanks",
                "sure",
                "hindi",
                "english",
                "space",
                "math",
                "reading",
            }:
                return raw_name
    return None


def extract_topic_from_transcript(text: str) -> str | None:
    text_lower = text.lower().strip()
    patterns = [
        r"(?:learn|study|practice|talk about|discuss|work on|about)\s+([a-zA-Z\u0900-\u097F\s]{3,35})",
        r"(?:phonics|grammar|vocabulary|fractions|algebra|reading|science|math|history|space|english|hindi)",
    ]
    m = re.search(patterns[0], text_lower)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"\s+(?:today|please|now|with you|together)$", "", cand)
        if len(cand) >= 3:
            return cand.title()
    m2 = re.search(patterns[1], text_lower)
    if m2:
        return m2.group(0).title()
    return None


class Assistant(Agent):
    def __init__(self, dynamic_instructions: str = "") -> None:
        instructions = SYSTEM_PROMPT + dynamic_instructions
        super().__init__(instructions=instructions)

    @function_tool
    async def lookup_user_profile(self, context: RunContext, identifier: str):
        """Look up a caller's saved learning profile from the SQLite database by their name or ID.

        IMMEDIATELY CALL THIS TOOL whenever a caller tells you their name (e.g. 'I am Prabh', 'My name is Sarah', 'Rahul').

        Args:
            identifier: The caller's name or user ID stated by the user.
        """
        logger.info(f"Tool lookup_user_profile called for identifier: '{identifier}'")
        user = get_user_by_name_or_id(identifier)
        if user:
            logger.info(f"Found user profile in database: {user}")
            topics_str = (
                ", ".join(user["facts"]["topics_covered"])
                if user["facts"]["topics_covered"]
                else "Reading & Literacy"
            )
            mistakes_str = (
                ", ".join(user["facts"]["mistakes_repeated"])
                if user["facts"]["mistakes_repeated"]
                else "None"
            )
            return (
                f"FOUND SAVED RECORD FOR '{user['name']}':\n"
                f"- Name: {user['name']}\n"
                f"- Current Level: {user['facts']['current_level']}\n"
                f"- Topics Covered Previously: {topics_str}\n"
                f"- Repeated Mistakes: {mistakes_str}\n"
                f"- Last Interaction: {user['last_interaction']}\n\n"
                f"INSTRUCTION: Greet {user['name']} warmly by name! Mention what you worked on last time ({topics_str}), and ask if they would like to continue or try a new topic."
            )
        logger.info(f"No profile found for '{identifier}'.")
        return (
            f"NO SAVED RECORD FOUND for '{identifier}'. This caller is a NEW learner.\n"
            f"INSTRUCTION: Greet {identifier} warmly! Ask for permission to save their learning progress: 'Nice to meet you {identifier}! May I save your learning progress as we practice today so I can remember you next time?'"
        )

    @function_tool
    async def save_learning_progress(
        self,
        context: RunContext,
        name: str,
        consent_given: bool,
        current_level: str = "Beginner",
        topics_covered: str = "Reading & Literacy",
        mistakes_repeated: str = "None",
        user_id: str = "",
    ):
        """Save or update the caller's learning progress and topics in the SQLite database.

        MANDATORY CONSENT RULE:
        Before calling this function, you MUST ask the caller:
        'May I save your learning progress so we can continue where we left off next time?'
        If the caller agrees ('Yes', 'Sure', 'Haan', 'Okay', 'Fine'), pass consent_given=True.
        If the caller declines ('No', 'Nahi', 'Don't save'), pass consent_given=False.

        Args:
            name: The caller's name (e.g. 'Prabh', 'Sarah', 'Rahul').
            consent_given: True ONLY IF the caller explicitly agreed to save their data; False if denied.
            current_level: Learner level (e.g. 'Grade 3 Reading', 'Beginner Phonics', 'Intermediate Grammar').
            topics_covered: Comma-separated list of topics discussed (e.g. 'Fractions, Vocabulary, Story Reading').
            mistakes_repeated: Comma-separated list of mistakes to watch for (e.g. 'Silent e rules', 'Verb tenses', 'None').
            user_id: Optional unique user ID. If empty, a slug based on name will be auto-generated.
        """
        logger.info(
            f"Tool save_learning_progress called for '{name}', consent_given={consent_given}, topics='{topics_covered}'"
        )
        if not consent_given:
            return f"Consent was NOT granted by {name}. No data was saved to database per privacy rules."

        clean_user_id = user_id if user_id else name.lower().strip().replace(" ", "_")
        topics_list = (
            [t.strip() for t in topics_covered.split(",") if t.strip()]
            if topics_covered
            else ["Reading & Literacy"]
        )
        mistakes_list = (
            [m.strip() for m in mistakes_repeated.split(",") if m.strip()]
            if mistakes_repeated
            else ["None"]
        )

        result = save_user_profile(
            user_id=clean_user_id,
            name=name,
            language_preference="English & Hindi",
            current_level=current_level,
            topics_covered=topics_list,
            mistakes_repeated=mistakes_list,
            consent_given=consent_given,
        )
        return result["message"]

    @function_tool
    async def get_exercise(self, context: RunContext, level: str):
        """Retrieves an English learning exercise appropriate for the user's requested difficulty level. Call this function whenever the user asks for a new English exercise, practice question, quiz question, grammar question, vocabulary question, or speaking practice activity.

        Args:
            level: The learner's requested difficulty level ('beginner', 'intermediate', or 'advanced').
        """
        logger.info(f"Tool get_exercise called for level: '{level}'")
        try:
            clean_level = (level or "").strip().lower()
            dataset_path = os.path.join(os.path.dirname(__file__), "exercises.json")

            if not os.path.exists(dataset_path):
                logger.error("Dataset file exercises.json missing.")
                return "Sorry, I'm having trouble getting a learning exercise right now. Please try again in a moment."

            with open(dataset_path, "r", encoding="utf-8") as f:
                exercises = json.load(f)

            supported_levels = ["beginner", "intermediate", "advanced"]
            if clean_level not in supported_levels:
                logger.warning(
                    f"Unsupported level requested: '{level}'. Level must be beginner, intermediate, or advanced."
                )
                matching = [e for e in exercises if e.get("level") == "beginner"]
                selected = random.choice(matching) if matching else exercises[0]
                return (
                    f"Requested level '{level}' is not supported. Supported levels are beginner, intermediate, and advanced.\n"
                    f"Here is a beginner exercise to start with:\n"
                    f"- ID: {selected['id']}\n"
                    f"- Level: {selected['level'].capitalize()}\n"
                    f"- Topic: {selected['topic']}\n"
                    f"- Question: {selected['question']}\n"
                    f"- Answer: {selected['answer']}\n\n"
                    f"INSTRUCTION: Explain gracefully that '{level}' is not a supported level (supported levels are beginner, intermediate, and advanced), then present this exercise and ask for their answer."
                )

            matching = [e for e in exercises if e.get("level", "").lower() == clean_level]
            if not matching:
                return "Sorry, I'm having trouble getting a learning exercise right now. Please try again in a moment."

            selected = random.choice(matching)
            logger.info(f"Retrieved exercise ID {selected['id']} for level '{clean_level}'")
            return (
                f"RETRIEVED EXERCISE FOR LEVEL '{clean_level.capitalize()}':\n"
                f"- ID: {selected['id']}\n"
                f"- Level: {selected['level'].capitalize()}\n"
                f"- Topic: {selected['topic']}\n"
                f"- Question: {selected['question']}\n"
                f"- Answer: {selected['answer']}\n\n"
                f"INSTRUCTION: Ask the user this question clearly and wait for their answer!"
            )
        except Exception as e:
            logger.error(f"Error executing get_exercise tool: {e}")
            return "Sorry, I'm having trouble getting a learning exercise right now. Please try again in a moment."

    @function_tool
    async def get_previous_learning_context(self, context: RunContext, identifier: str = ""):
        """Retrieve relevant previous learning context or topics from prior conversations in the database. Call this function when the user asks what they were learning last time, asks to continue their previous practice, or asks about past sessions.

        Args:
            identifier: Optional caller name or user ID.
        """
        logger.info(
            f"Tool get_previous_learning_context called for identifier: '{identifier}'"
        )
        try:
            topic = get_last_learning_topic(user_id=identifier)
            turns = get_recent_conversation_memory(user_id=identifier, limit=3)

            if not topic and not turns:
                return "I don't have any previous learning session to continue yet. We can start one now."

            history_lines = []
            if turns:
                for t in turns:
                    history_lines.append(
                        f"- User: {t['user_message']} | Ved: {t['agent_response']}"
                    )
            history_str = (
                "\n".join(history_lines) if history_lines else "No detailed history available."
            )

            return (
                f"PREVIOUS SESSION RELEVANT CONTEXT:\n"
                f"- Topic: {topic or 'English Practice'}\n"
                f"- Recent Turns:\n{history_str}\n\n"
                f"INSTRUCTION: Tell the user that last time you were practicing '{topic or 'English Practice'}', and offer to continue with another exercise or topic."
            )
        except Exception as e:
            logger.error(f"Error executing get_previous_learning_context: {e}")
            return "I'm having trouble accessing our previous conversation right now, but we can start a new practice session."



server = AgentServer()


def prewarm(proc: JobProcess):
    init_db()
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Track active session user & topics dynamically
    active_user_name = None
    last_user_transcript = ""

    last_topic = get_last_learning_topic()

    saved_users = list_all_users()
    if saved_users:
        returning_user = saved_users[0]
        active_user_name = returning_user["name"]
        logger.info(f"Auto-loaded returning caller profile: {returning_user['name']}")
        topics_str = (
            ", ".join(returning_user["facts"]["topics_covered"])
            if returning_user["facts"]["topics_covered"]
            else (last_topic or "reading & phonics")
        )
        dynamic_instructions = (
            f"\n\n[ACTIVE SESSION CALLER DATA]\n"
            f"RETURNING CALLER FOUND IN DATABASE: {returning_user['name']} (User ID: {returning_user['user_id']})\n"
            f"- Current Level: {returning_user['facts']['current_level']}\n"
            f"- Topics Covered Previously: {topics_str}\n"
            f"- Repeated Mistakes to Watch: {', '.join(returning_user['facts']['mistakes_repeated']) or 'None'}\n"
            f"- Preferred Language: {returning_user['language_preference']}\n"
            f"- Last Interaction: {returning_user['last_interaction']}\n\n"
            f"CRITICAL FIRST-TURN MANDATORY BEHAVIOR FOR RETURNING CALLER:\n"
            f"You ALREADY know this caller is {returning_user['name']}! Do NOT ask 'What is your name?'.\n"
            f"Greet {returning_user['name']} warmly BY NAME right on the very first turn! Example: 'Namaste {returning_user['name']}! Welcome back to your AI Learning Companion. Last time we practiced {topics_str}. Would you like to continue from where we left off or try something new today?'\n"
        )
    else:
        logger.info("No saved users found in database. Starting session as NEW caller.")
        dynamic_instructions = (
            "\n\n[ACTIVE SESSION CALLER DATA]\n"
            "No saved user profiles exist in the database. This is a NEW caller.\n"
            "FIRST-TURN MANDATORY BEHAVIOR FOR NEW CALLER:\n"
            "Greet the new learner and ask for their name! Example: 'Hi! Welcome to your AI Learning Companion. What is your name?'\n"
            "As soon as they tell you their name (e.g. 'Prabh' or 'Rahul'), ask for permission: 'Nice to meet you [Name]! May I save your learning progress as we practice today so I remember you next time?'\n"
            "When they agree ('Yes', 'Sure', 'Haan', 'Okay'), IMMEDIATELY call `save_learning_progress(name='[Name]', consent_given=True)`!\n"
        )

    if last_topic:
        dynamic_instructions += (
            f"\n\n[PERSISTENT CONVERSATION MEMORY DATA]\n"
            f"Most recent learning topic found in database: '{last_topic}'.\n"
            f"If the user asks 'What were we learning last time?' or 'Let's continue my practice', remind them you were working on {last_topic} and use `get_exercise` to provide another exercise!"
        )

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Abhinav",
            locale="en-IN",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent):
        nonlocal active_user_name, last_user_transcript
        transcript = ev.transcript.strip()
        if not transcript:
            return

        last_user_transcript = transcript
        transcript_lower = transcript.lower()


        # Dynamic name extraction & immediate SQLite save
        extracted_name = extract_name_from_transcript(transcript)
        if extracted_name:
            active_user_name = extracted_name
            logger.info(
                f"Auto-extracted name '{extracted_name}' from transcript. Saving to SQLite DB."
            )
            save_user_profile(
                user_id=extracted_name.lower(),
                name=extracted_name,
                language_preference="English & Hindi",
                current_level="Beginner",
                topics_covered=["Reading & Literacy"],
                mistakes_repeated=[],
                consent_given=True,
            )

        # Dynamic topic extraction & immediate SQLite update
        extracted_topic = extract_topic_from_transcript(transcript)
        if extracted_topic and active_user_name:
            logger.info(
                f"Auto-extracted topic '{extracted_topic}' for user '{active_user_name}'. Updating SQLite DB."
            )
            save_user_profile(
                user_id=active_user_name.lower(),
                name=active_user_name,
                language_preference="English & Hindi",
                current_level="Interactive Learning",
                topics_covered=[extracted_topic],
                mistakes_repeated=[],
                consent_given=True,
            )

        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in transcript_lower)

        hindi_keywords = {
            "kya",
            "hai",
            "aur",
            "main",
            "haan",
            "nahin",
            "aap",
            "namaste",
            "shukriya",
            "mein",
            "ke",
            "ki",
            "se",
            "ko",
            "ka",
            "jo",
            "toh",
            "bhi",
            "ho",
            "kar",
            "raha",
            "rahi",
            "rha",
            "rhi",
            "mujhe",
            "mera",
            "meri",
            "hum",
            "tum",
            "apna",
            "apni",
            "karke",
            "karo",
            "karna",
            "tha",
            "thi",
            "the",
            "ab",
            "kab",
            "tab",
            "sab",
            "hindi",
        }
        words = set(transcript_lower.split())
        has_hindi_words = not words.isdisjoint(hindi_keywords)

        if has_devanagari or has_hindi_words:
            logger.info(
                f"Detected Hindi/Hinglish speech: '{ev.transcript}'. Switching TTS locale to hi-IN."
            )
            session.tts.update_options(locale="hi-IN")
        else:
            logger.info(
                f"Detected English speech: '{ev.transcript}'. Switching TTS locale to en-IN."
            )
            session.tts.update_options(locale="en-IN")

    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        nonlocal active_user_name, last_user_transcript
        try:
            item = getattr(ev, "item", None)
            if not item:
                return
            role = getattr(item, "role", None)
            content = getattr(item, "text_content", "") or getattr(item, "content", "")
            if isinstance(content, list):
                content = " ".join([str(c) for c in content])
            text = str(content).strip()
            if not text:
                return

            if role == "user":
                last_user_transcript = text
            elif role == "assistant" and last_user_transcript:
                current_topic = (
                    extract_topic_from_transcript(last_user_transcript)
                    or get_last_learning_topic(active_user_name or "")
                    or "General English"
                )
                save_conversation_turn(
                    session_id=ctx.room.name,
                    user_id=active_user_name or "guest",
                    user_message=last_user_transcript,
                    agent_response=text,
                    topic=current_topic,
                )
                last_user_transcript = ""
        except Exception as e:
            logger.error(f"Error saving turn to conversation memory: {e}")

    await session.start(

        agent=Assistant(dynamic_instructions=dynamic_instructions),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
