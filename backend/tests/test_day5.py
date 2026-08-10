import json
import os
import sys
import pytest

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import Assistant
from db import (
    get_last_learning_topic,
    get_recent_conversation_memory,
    init_db,
    save_conversation_turn,
)


@pytest.fixture(autouse=True)
def setup_database(tmp_path):
    """Ensure database schema is initialized in an isolated temp database for tests."""
    test_db_path = str(tmp_path / "test_day5.db")
    os.environ["DB_PATH"] = test_db_path
    init_db()
    yield
    os.environ.pop("DB_PATH", None)



@pytest.mark.asyncio
async def test_get_exercise_valid_levels():
    """Test get_exercise function tool for supported levels: beginner, intermediate, advanced."""
    assistant = Assistant()

    for level in ["beginner", "intermediate", "advanced"]:
        result = await assistant.get_exercise(context=None, level=level)
        assert result is not None
        assert "RETRIEVED EXERCISE FOR LEVEL" in result or "Question:" in result
        assert level.capitalize() in result or level in result


@pytest.mark.asyncio
async def test_get_exercise_invalid_level():
    """Test get_exercise handling of an unsupported level (e.g. expert)."""
    assistant = Assistant()
    result = await assistant.get_exercise(context=None, level="expert")
    assert result is not None
    assert "not supported" in result or "beginner" in result
    # Must handle gracefully without throwing an exception or crashing
    assert "INSTRUCTION:" in result or "exercise" in result


@pytest.mark.asyncio
async def test_get_exercise_failure_handling(tmp_path, monkeypatch):
    """Test get_exercise fallback when dataset reading fails."""
    assistant = Assistant()

    # Point exercises.json path to a non-existent file location
    fake_path = str(tmp_path / "non_existent_exercises.json")

    def mock_join(*args):
        if args[-1] == "exercises.json":
            return fake_path
        return os.path.join(*args)

    monkeypatch.setattr("os.path.join", mock_join)

    result = await assistant.get_exercise(context=None, level="beginner")
    assert (
        result
        == "Sorry, I'm having trouble getting a learning exercise right now. Please try again in a moment."
    )


def test_save_and_retrieve_conversation_memory():
    """Test saving a conversation turn to SQLite database and retrieving recent memory."""
    session_id = "test_session_day5_001"
    user_id = "test_user_day5"
    user_msg = "Ved, I want to practice English vocabulary."
    agent_resp = "Sure! Let's practice English vocabulary."
    topic = "English Vocabulary"

    # Save turn
    res = save_conversation_turn(
        session_id=session_id,
        user_id=user_id,
        user_message=user_msg,
        agent_response=agent_resp,
        topic=topic,
    )
    assert res["status"] == "success"

    # Retrieve recent memory
    recent = get_recent_conversation_memory(user_id=user_id, limit=5)
    assert len(recent) > 0
    latest = recent[-1]
    assert latest["user_message"] == user_msg
    assert latest["agent_response"] == agent_resp
    assert latest["topic"] == topic

    # Retrieve last learning topic
    last_topic = get_last_learning_topic(user_id=user_id)
    assert last_topic == topic


@pytest.mark.asyncio
async def test_get_previous_learning_context_tool():
    """Test get_previous_learning_context tool for existing user and empty user."""
    assistant = Assistant()

    # Case 1: Existing session with memory saved
    session_id = "test_session_day5_002"
    user_id = "test_user_day5_retrieval"
    save_conversation_turn(
        session_id=session_id,
        user_id=user_id,
        user_message="I want to practice grammar.",
        agent_response="Let's study verb tenses.",
        topic="English Grammar",
    )

    context_str = await assistant.get_previous_learning_context(
        context=None, identifier=user_id
    )
    assert "PREVIOUS SESSION RELEVANT CONTEXT" in context_str
    assert "English Grammar" in context_str

    # Case 2: Non-existent user with no memory
    empty_context = await assistant.get_previous_learning_context(
        context=None, identifier="unknown_non_existent_user_999"
    )
    assert (
        empty_context
        == "I don't have any previous learning session to continue yet. We can start one now."
    )


@pytest.mark.asyncio
async def test_memory_failure_handling(monkeypatch):
    """Test get_previous_learning_context fallback when DB query encounters an exception."""
    assistant = Assistant()

    def mock_db_error(*args, **kwargs):
        raise RuntimeError("Database connection failure simulation")

    monkeypatch.setattr("agent.get_last_learning_topic", mock_db_error)

    result = await assistant.get_previous_learning_context(
        context=None, identifier="any_user"
    )
    assert (
        result
        == "I'm having trouble accessing our previous conversation right now, but we can start a new practice session."
    )


@pytest.mark.asyncio
async def test_function_calling_and_memory_together():
    """Test combined flow: lookup previous memory context and get appropriate exercise."""
    assistant = Assistant()

    user_id = "combined_flow_user"
    save_conversation_turn(
        session_id="session_combined",
        user_id=user_id,
        user_message="Let's practice beginner vocabulary.",
        agent_response="Great! Let's practice beginner vocabulary.",
        topic="Beginner English Vocabulary",
    )

    # 1. Retrieve previous context
    mem_context = await assistant.get_previous_learning_context(
        context=None, identifier=user_id
    )
    assert "Beginner English Vocabulary" in mem_context

    # 2. Get exercise for beginner level
    exercise = await assistant.get_exercise(context=None, level="beginner")
    assert "RETRIEVED EXERCISE FOR LEVEL 'Beginner'" in exercise
    assert "Question:" in exercise
