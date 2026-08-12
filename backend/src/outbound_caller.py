"""
outbound_caller.py — Day 6: Daily English Practice Outbound Call

Triggers a proactive SIP call to the learner's Linphone address using
the LiveKit SIP API. The learner's Linphone client rings; on answer,
they are connected to the AI Learning Assistant in an outbound-practice
LiveKit room.

Usage (manual test):
    uv run python src/outbound_caller.py --call-now

Required environment variables (set in .env.local):
    LIVEKIT_URL               — wss://your-project.livekit.cloud
    LIVEKIT_API_KEY           — LiveKit API key
    LIVEKIT_API_SECRET        — LiveKit API secret
    SIP_OUTBOUND_TRUNK_ID     — ST_xxxxxxxxxxxxxxxxx (from LiveKit dashboard)
    LEARNER_SIP_ADDRESS       — sip:username@sip.linphone.org
    LEARNER_NAME              — (optional) stored name for personalisation
    OUTBOUND_ROOM_PREFIX      — (optional, default: practice-call)
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(".env.local")

logger = logging.getLogger("outbound_caller")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"Environment variable '{name}' is not set. "
            f"Add it to backend/.env.local before making outbound calls."
        )
    return val


def _validate_outbound_configuration(trunk_id: str, learner_sip: str) -> None:
    """Reject common local configuration mistakes before creating a call."""
    if not trunk_id.startswith("ST_"):
        raise RuntimeError(
            "SIP_OUTBOUND_TRUNK_ID must be the stored LiveKit outbound trunk ID "
            "(it starts with 'ST_')."
        )
    if not re.fullmatch(r"sips?:[^@\s]+@[^@\s;?]+", learner_sip):
        raise RuntimeError(
            "LEARNER_SIP_ADDRESS must be a SIP URI such as "
            "sip:username@sip.linphone.org."
        )


async def trigger_practice_call() -> str:
    """
    Place an outbound SIP call to the learner's Linphone address.

    Returns the LiveKit room name so the caller knows which room was created.
    Raises RuntimeError if required env vars are missing.
    """
    # --- Validate required env vars ---
    livekit_url = _require_env("LIVEKIT_URL")
    api_key = _require_env("LIVEKIT_API_KEY")
    api_secret = _require_env("LIVEKIT_API_SECRET")
    trunk_id = _require_env("SIP_OUTBOUND_TRUNK_ID")
    learner_sip = _require_env("LEARNER_SIP_ADDRESS")
    _validate_outbound_configuration(trunk_id, learner_sip)

    room_prefix = os.environ.get("OUTBOUND_ROOM_PREFIX", "practice-call").strip()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    room_name = f"{room_prefix}-{timestamp}-{uuid.uuid4().hex[:6]}"

    logger.info(
        "Initiating outbound practice call to %s | room=%s | trunk=%s",
        learner_sip,
        room_name,
        trunk_id,
    )

    # --- Import livekit.api (available via livekit-agents dependency) ---
    try:
        from livekit import api as lk_api_module
    except ImportError as exc:
        raise RuntimeError(
            "Could not import 'livekit.api'. Ensure 'livekit-agents' is installed "
            "via 'uv sync'."
        ) from exc

    lk = lk_api_module.LiveKitAPI(
        url=livekit_url,
        api_key=api_key,
        api_secret=api_secret,
    )

    try:
        # Step 1 — dispatch the outbound-practice agent to the room FIRST
        # so it is ready when the learner picks up.
        logger.info("Dispatching outbound-practice agent to room '%s'...", room_name)
        dispatch_req = lk_api_module.CreateAgentDispatchRequest(
            agent_name="my-agent",
            room=room_name,
            metadata="outbound-practice",
        )
        dispatch = await lk.agent_dispatch.create_dispatch(dispatch_req)
        logger.info("Agent dispatched — dispatch_id=%s", dispatch.id)

        # Step 2 — dial the learner via SIP outbound trunk.
        # LiveKit's SIP infrastructure places the call; Linphone rings.
        #
        # Per LiveKit API docs, sip_call_to is the phone number or SIP username
        # ONLY — no scheme, no domain, no @. The stored outbound trunk
        # (ST_T3s2sHDgTwYN) already has sip.linphone.org as its address;
        # LiveKit constructs the full SIP URI internally.
        # Extract username from "sip:username@domain" → "username".
        sip_user = re.sub(r"^sips?:", "", learner_sip).split("@")[0]
        logger.info("Placing SIP call to username '%s'...", sip_user)
        sip_req = lk_api_module.CreateSIPParticipantRequest(
            sip_trunk_id=trunk_id,
            sip_call_to=sip_user,
            room_name=room_name,
            participant_identity="learner",
            participant_name="Learner",
            # Play a ringtone on the LiveKit side while the SIP leg is ringing
            play_ringtone=True,
        )
        participant = await lk.sip.create_sip_participant(sip_req)
        logger.info(
            "SIP participant created — identity=%s, room=%s",
            participant.participant_identity,
            room_name,
        )

    finally:
        await lk.aclose()

    logger.info(
        "Outbound call initiated successfully. Room: %s | SIP: %s",
        room_name,
        learner_sip,
    )
    return room_name


# ---------------------------------------------------------------------------
# CLI entry-point — for manual testing: uv run python src/outbound_caller.py --call-now
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Day 6: Trigger an outbound English practice call via Linphone."
    )
    parser.add_argument(
        "--call-now",
        action="store_true",
        help="Immediately place one outbound practice call (for testing).",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    if args.call_now:
        print("\n🔔  Placing outbound practice call NOW...\n")
        try:
            room = await trigger_practice_call()
            print(f"\n✅  Call placed successfully! LiveKit room: {room}")
            print(
                "\n📱  Linphone should ring at: "
                + os.environ.get("LEARNER_SIP_ADDRESS", "(not set)")
            )
            print(
                "    Answer the call in Linphone to speak with the AI Learning Assistant.\n"
            )
        except RuntimeError as e:
            print(f"\n❌  Error: {e}\n")
            sys.exit(1)
    else:
        print("No action specified. Use --call-now to place a test call.")
        print("Or run scheduler.py for scheduled daily calls.")


if __name__ == "__main__":
    asyncio.run(_main())
