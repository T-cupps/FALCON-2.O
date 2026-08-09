import os
import sys

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import get_user_by_name_or_id, init_db, list_all_users, save_user_profile


def test_full_memory_flow():
    print("--- 1. Initializing Database ---")
    init_db()

    print("\n--- 2. Testing Save with Consent (Step 2 & Step 5) ---")
    res1 = save_user_profile(
        user_id="ramesh_101",
        name="Ramesh",
        language_preference="English & Hindi",
        current_level="Grade 3 Reading - Beginner Phonics",
        topics_covered=["Silent e rules", "Vowel sounds", "Basic Story Reading"],
        mistakes_repeated=["Confusing b and d", "Skipping silent e"],
        consent_given=True,
    )
    print("Save with consent result:", res1)
    assert res1["status"] == "success"

    print("\n--- 3. Testing Lookup Returning Caller (Step 3 & Step 4) ---")
    caller = get_user_by_name_or_id("Ramesh")
    print("Looked up caller by name 'Ramesh':", caller)
    assert caller is not None
    assert caller["name"] == "Ramesh"
    assert caller["facts"]["current_level"] == "Grade 3 Reading - Beginner Phonics"
    assert "Silent e rules" in caller["facts"]["topics_covered"]
    assert "Confusing b and d" in caller["facts"]["mistakes_repeated"]

    print("\n--- 4. Testing Refusal To Save Without Consent (Step 5 HARD RULE) ---")
    res2 = save_user_profile(
        user_id="anonymous_caller",
        name="Private Learner",
        language_preference="English",
        current_level="Advanced",
        topics_covered=["Grammar"],
        mistakes_repeated=[],
        consent_given=False,  # User said NO
    )
    print("Save without consent result:", res2)
    assert res2["status"] == "error"
    assert get_user_by_name_or_id("Private Learner") is None

    print("\n--- 5. Listing All Registered Users ---")
    all_users = list_all_users()
    print("All saved users in SQLite DB:", all_users)

    print("\n[SUCCESS] ALL MEMORY & CONSENT TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_full_memory_flow()
