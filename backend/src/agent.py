import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from livekit import api, rtc
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

import database  # noqa: E402
from prompt import OUTBOUND_SYSTEM_PROMPT, SYSTEM_PROMPT  # noqa: E402

logger = logging.getLogger("agent")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self) -> None:
        recent_caller = database.lookup_most_recent_caller()
        if recent_caller and recent_caller.get("name"):
            name = recent_caller.get("name", "")
            facts = recent_caller.get("facts", {})
            topics = (
                facts.get("topics_covered")
                or facts.get("target_goal")
                or "your last lesson"
            )
            greeting = (
                f"Namaste {name}! Welcome back to your AI Learning Assistant. "
                f"Last time we worked on {topics}. Would you like to continue with that "
                f"or explore something new today?"
            )
        else:
            greeting = (
                "Hi! I am your AI Learning Assistant. I can help you learn new concepts, "
                "practice English, improve vocabulary, or study for your next lesson. "
                "What would you like to explore today?"
            )

        activity = getattr(self, "_activity", None)
        if activity is not None and hasattr(activity, "say"):
            activity.say(greeting)

    @function_tool
    async def lookup_caller(self, context: RunContext, user_id_or_name: str) -> str:
        """Look up a caller in the database by their name or user ID to retrieve their stored memory and facts.

        Args:
            user_id_or_name: The name or user ID of the caller to look up.
        """
        logger.info(f"Function tool lookup_caller invoked for: {user_id_or_name}")
        caller = database.lookup_caller(user_id_or_name)
        if not caller:
            caller = database.lookup_caller_by_name(user_id_or_name)
        if not caller:
            return json.dumps(
                {"found": False, "message": f"No memory found for '{user_id_or_name}'."}
            )
        return json.dumps({"found": True, "caller": caller})

    @function_tool
    async def save_caller_memory(
        self,
        context: RunContext,
        user_id: str,
        name: str,
        language_preference: str = "English",
        facts_json: str = "{}",
    ) -> str:
        """Save or update caller information in the memory database. ONLY call this AFTER asking the user for permission and receiving explicit consent.

        Args:
            user_id: Unique identifier for the caller (e.g. name lowercased).
            name: Caller's name.
            language_preference: Caller's preferred language (e.g. 'English', 'Hindi', 'Hinglish').
            facts_json: JSON string containing caller facts such as current_level, topics_covered, mistakes_or_focus_areas, target_goal.
        """
        logger.info(f"Function tool save_caller_memory invoked for {name} ({user_id})")
        database.save_caller(
            user_id=user_id,
            name=name,
            language_preference=language_preference,
            facts=facts_json,
        )
        return json.dumps(
            {
                "success": True,
                "message": f"Successfully saved memory for caller {name}.",
            }
        )

    @function_tool
    async def fetch_concept_knowledge(self, context: RunContext, topic: str) -> str:
        """Fetch live educational topic summary, key facts, and revision timestamp from Wikipedia API.

        Use this tool whenever the user asks for explanations, definitions, or summaries of educational concepts, scientific topics, historical events, or technology terms (e.g. "What is photosynthesis?", "Tell me about Black Holes").

        Args:
            topic: The educational concept or topic name to search (e.g. 'Photosynthesis', 'Quantum Physics', 'Gravity').
        """
        logger.info(f"Function tool fetch_concept_knowledge invoked for topic: {topic}")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}"
        headers = {
            "User-Agent": "VoiceAILearningAssistant/1.0 (contact@example.com; educational livekit agent)"
        }
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

            if response.status_code == 404:
                logger.warning(f"Topic '{topic}' not found on Wikipedia (404).")
                return json.dumps(
                    {
                        "success": False,
                        "topic": topic,
                        "error_type": "NOT_FOUND",
                        "message": f"Educational topic '{topic}' was not found in the live Wikipedia database.",
                        "instruction_for_agent": "Inform the learner out loud that the topic was not found in the live Wikipedia database, then provide a friendly general answer if you know it.",
                        "data_retrieved_at": now_str,
                    }
                )

            response.raise_for_status()
            data = response.json()
            title = data.get("title", topic)
            extract = data.get("extract", "")
            revision_timestamp = data.get("timestamp", now_str)

            return json.dumps(
                {
                    "success": True,
                    "topic": topic,
                    "title": title,
                    "summary": extract,
                    "revision_timestamp": revision_timestamp,
                    "data_retrieved_at": now_str,
                    "source": "Wikipedia REST API (Live Internet)",
                    "instruction_for_agent": "Explain this live information clearly to the learner. State that this data is retrieved live from Wikipedia as of the provided timestamp.",
                }
            )
        except httpx.TimeoutException:
            logger.error(
                f"Timeout while fetching concept knowledge for topic '{topic}'."
            )
            return json.dumps(
                {
                    "success": False,
                    "topic": topic,
                    "error_type": "TIMEOUT",
                    "message": f"The request to fetch live data for '{topic}' timed out.",
                    "instruction_for_agent": "Inform the learner out loud that the live internet service timed out, then offer a clear answer based on your knowledge base.",
                    "data_retrieved_at": now_str,
                }
            )
        except Exception as e:
            logger.error(f"Error fetching concept knowledge for '{topic}': {e}")
            return json.dumps(
                {
                    "success": False,
                    "topic": topic,
                    "error_type": "CONNECTION_ERROR",
                    "message": f"Could not connect to live internet data service for '{topic}': {e!s}",
                    "instruction_for_agent": "Inform the learner out loud that the live network request failed, then provide a helpful explanation directly.",
                    "data_retrieved_at": now_str,
                }
            )

    @function_tool
    async def fetch_word_dictionary(self, context: RunContext, word: str) -> str:
        """Fetch live dictionary definition, phonetic pronunciation, part of speech, and example sentence from Free Dictionary API.

        Use this tool whenever the user asks for the definition, meaning, pronunciation, part of speech, or usage of a specific word (e.g. "What does perseverance mean?", "Define meticulous").

        Args:
            word: The English word to define.
        """
        logger.info(f"Function tool fetch_word_dictionary invoked for word: {word}")
        clean_word = word.strip().lower()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(clean_word)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

            if response.status_code == 404:
                logger.warning(f"Word '{clean_word}' not found in dictionary (404).")
                return json.dumps(
                    {
                        "success": False,
                        "word": clean_word,
                        "error_type": "WORD_NOT_FOUND",
                        "message": f"Word '{clean_word}' was not found in the live English dictionary.",
                        "instruction_for_agent": "Inform the learner out loud that the word was not found in the live dictionary API, then give a helpful definition if you know it.",
                        "data_retrieved_at": now_str,
                    }
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or not data:
                return json.dumps(
                    {
                        "success": False,
                        "word": clean_word,
                        "error_type": "NO_ENTRY",
                        "message": f"No entry returned for '{clean_word}'.",
                        "instruction_for_agent": "Inform the learner out loud that no dictionary entry was returned.",
                        "data_retrieved_at": now_str,
                    }
                )

            first_entry = data[0]
            phonetic = first_entry.get("phonetic", "")
            if not phonetic and first_entry.get("phonetics"):
                for p in first_entry["phonetics"]:
                    if p.get("text"):
                        phonetic = p["text"]
                        break

            meanings = first_entry.get("meanings", [])
            part_of_speech = ""
            definition = ""
            example = ""

            if meanings:
                first_meaning = meanings[0]
                part_of_speech = first_meaning.get("partOfSpeech", "")
                defs = first_meaning.get("definitions", [])
                if defs:
                    definition = defs[0].get("definition", "")
                    example = defs[0].get("example", "")

            return json.dumps(
                {
                    "success": True,
                    "word": clean_word,
                    "phonetic": phonetic,
                    "part_of_speech": part_of_speech,
                    "definition": definition,
                    "example": example,
                    "data_retrieved_at": now_str,
                    "source": "Free Dictionary API (Live Internet)",
                    "instruction_for_agent": "Explain the definition, phonetic pronunciation, part of speech, and example sentence clearly to the learner. State that this definition is retrieved as of live dictionary data.",
                }
            )
        except httpx.TimeoutException:
            logger.error(f"Timeout while fetching dictionary data for '{clean_word}'.")
            return json.dumps(
                {
                    "success": False,
                    "word": clean_word,
                    "error_type": "TIMEOUT",
                    "message": f"Request to live dictionary API for '{clean_word}' timed out.",
                    "instruction_for_agent": "Inform the learner out loud that the live dictionary service timed out, then explain the word definition directly.",
                    "data_retrieved_at": now_str,
                }
            )
        except Exception as e:
            logger.error(f"Error fetching dictionary data for '{clean_word}': {e}")
            return json.dumps(
                {
                    "success": False,
                    "word": clean_word,
                    "error_type": "CONNECTION_ERROR",
                    "message": f"Could not connect to live dictionary service for '{clean_word}': {e!s}",
                    "instruction_for_agent": "Inform the learner out loud that the live network request failed, then define the word based on your knowledge.",
                    "data_retrieved_at": now_str,
                }
            )


server = AgentServer()


# ---------------------------------------------------------------------------
# Day 6 - Outbound English Practice: AssistantOutbound
# ---------------------------------------------------------------------------

OUTBOUND_OPENING_GENERIC = (
    "Hello! This is your AI Learning Assistant calling for your daily "
    "five-minute English practice session. You selected this time for your "
    "practice call. If you'd rather not continue, just say 'stop'. "
    "Is now a good time to practice?"
)


class AssistantOutbound(Agent):
    """Outbound-specific agent for the daily English practice call.

    Differences from the standard Assistant:
    - Opens with the required outbound greeting (who, why, how-to-stop).
    - Personalises the greeting using stored memory (name, level, topics).
    - Exposes a stop_session function tool so the learner can end the call.
    - Uses OUTBOUND_SYSTEM_PROMPT (shorter, practice-focused).
    """

    def __init__(self, ctx: JobContext) -> None:
        self._ctx = ctx
        self._session_ended = False
        learner_name = os.environ.get("LEARNER_NAME", "").strip()

        # Try to load learner memory: first by LEARNER_NAME, then most recent.
        caller: dict | None = None
        if learner_name:
            caller = database.lookup_caller_by_name(learner_name)
        if caller is None:
            caller = database.lookup_most_recent_caller()

        if caller and caller.get("name"):
            name = caller["name"]
            facts = caller.get("facts", {})
            level = facts.get("current_level", "")
            last_topic = facts.get("topics_covered") or facts.get("target_goal") or ""

            greeting = (
                f"Hello {name}! This is your AI Learning Assistant calling "
                "for your daily five-minute English practice session. "
                "You selected this time for your practice call. "
                "If you'd rather not continue, just say 'stop'. "
                "Is now a good time to practice?"
            )

            context_note = "\n\nLEARNER CONTEXT FOR THIS CALL:\n"
            if level:
                context_note += f"  - English level: {level}\n"
            if last_topic:
                context_note += f"  - Last topic: {last_topic}\n"
            context_note += "Use this only to personalise the practice questions."
            logger.info(
                "Outbound call to returning learner '%s' (level=%s, topic=%s)",
                name,
                level or "unknown",
                last_topic or "none",
            )
        else:
            greeting = OUTBOUND_OPENING_GENERIC
            context_note = ""
            logger.info(
                "Outbound call - no stored memory found; using generic opening."
            )

        self._greeting = greeting
        super().__init__(instructions=OUTBOUND_SYSTEM_PROMPT + context_note)

    async def on_enter(self) -> None:
        """Deliver the opening after the answered SIP participant has joined."""
        self.session.say(self._greeting, allow_interruptions=True)

    @function_tool
    async def stop_session(
        self,
        context: RunContext,
    ) -> str:
        """End the English practice session when the learner asks to stop.

        Call this tool whenever the learner says 'stop', 'end the call',
        'I don't want to continue', 'not now', 'bye', or similar.
        Always say a polite goodbye BEFORE calling this tool.
        """
        if self._session_ended:
            return '{"status": "already_ended"}'

        self._session_ended = True
        logger.info("stop_session tool invoked - deleting outbound call room.")

        try:
            await self._ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=self._ctx.room.name)
            )
        except Exception as e:
            logger.warning("Error ending outbound room: %s", e)
        finally:
            self._ctx.shutdown("learner requested end of practice session")

        return (
            '{"status": "session_ended", "message": "Practice session ended. Goodbye!"}'
        )


def prewarm(proc: JobProcess):
    database.initialize_db()
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    if getattr(ctx.job, "metadata", "") == "outbound-practice":
        await outbound_practice_agent(ctx)
        return

    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using Murf Falcon, Gemini, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(model="nova-3", language="multi"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=murf.TTS(
            voice="Abhinav",
            locale="en-IN",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent):
        transcript = ev.transcript.strip().lower()
        if not transcript:
            return

        # Check for Devanagari script characters (native Hindi)
        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in transcript)

        # Check for common Hinglish/Hindi romanized keywords
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
        words = set(transcript.split())
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

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
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

    # Join the room and connect to the user
    await ctx.connect()


# ---------------------------------------------------------------------------
# Day 6 - Outbound English Practice: second @server.rtc_session handler
# ---------------------------------------------------------------------------


async def outbound_practice_agent(ctx: JobContext):
    """Handler for the daily outbound English practice call.

    This is dispatched by outbound_caller.py when the SIP call is placed.
    The learner answers their Linphone, joins this room, and the
    AssistantOutbound greets them with the required outbound opening.
    """
    ctx.log_context_fields = {
        "room": ctx.room.name,
        "agent": "outbound-practice",
    }

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
    def on_user_input_transcribed_outbound(ev: UserInputTranscribedEvent):
        """Same Hindi/Hinglish locale-switching logic as the inbound agent."""
        transcript = ev.transcript.strip().lower()
        if not transcript:
            return

        has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in transcript)
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
        words = set(transcript.split())
        has_hindi_words = not words.isdisjoint(hindi_keywords)

        if has_devanagari or has_hindi_words:
            session.tts.update_options(locale="hi-IN")
        else:
            session.tts.update_options(locale="en-IN")

    # Wait for the SIP participant before starting speech. Otherwise the opening
    # can be spoken while Linphone is ringing and never reach the learner.
    await ctx.connect()
    await ctx.wait_for_participant(identity="learner")

    await session.start(
        agent=AssistantOutbound(ctx),
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


if __name__ == "__main__":
    cli.run_app(server)
