# from __future__ import annotations
#
# import dataclasses
# import json
# import os
# import time
# from pathlib import Path
#
# import streamlit as st
#
# # The agent script uses relative paths (shruti.cact, customer_feedback.json,
# # reply_cartesia.wav). Run from its own folder, like the CLI does.
# os.chdir(Path(__file__).resolve().parent)
#
# from voice_agent import (
#     ENDED,
#     ERROR,
#     IDLE,
#     LISTENING,
#     SPEAKING,
#     THINKING,
#     AgentConfig,
#     ConversationAgent,
#     audio_devices,
#     load_demo_core,
#     load_core,
# )
#
# st.set_page_config(page_title="Hinglish Feedback Call", page_icon="📞", layout="wide")
#
# # `use_container_width` is deprecated in Streamlit >= 1.49 and removed after
# # 2025-12-31; support both old and new installs.
# try:
#     _st_major, _st_minor = (int(x) for x in st.__version__.split(".")[:2])
# except Exception:                                   # pragma: no cover
#     _st_major, _st_minor = 1, 40
# WIDE = {"width": "stretch"} if (_st_major, _st_minor) >= (1, 49) else {"use_container_width": True}
#
# STATUS_UI = {
#     IDLE: ("⚪", "Idle", "normal"),
#     "loading": ("⏳", "Loading models", "normal"),
#     SPEAKING: ("🔊", "Agent speaking", "normal"),
#     LISTENING: ("🎤", "Listening", "normal"),
#     THINKING: ("🧠", "Thinking", "normal"),
#     "saving": ("💾", "Saving record", "normal"),
#     ENDED: ("✅", "Call finished", "normal"),
#     ERROR: ("❌", "Error", "inverse"),
# }
#
#
# # =============================================================================
# # Resources
# # =============================================================================
#
#
# @st.cache_resource(show_spinner=False)
# def get_core(demo: bool, script: str):
#     """Load the agent module once per process (it loads the STT model)."""
#     return load_demo_core() if demo else load_core(script)
#
#
# def default_state() -> None:
#     st.session_state.setdefault("agent", None)
#     st.session_state.setdefault("record", None)
#     st.session_state.setdefault("core_ready", False)
#
#
# default_state()
#
# # Deep links, handy for demos and kiosks:
# #   ?demo=1&input=text&autostart=1
# _qp = st.query_params
# if str(_qp.get("demo", "")).lower() in ("1", "true", "yes"):
#     st.session_state["demo_mode"] = True
# st.session_state.setdefault(
#     "input_mode", "text" if str(_qp.get("input", "")).lower() == "text" else "audio"
# )
#
#
# # =============================================================================
# # Sidebar - configuration
# # =============================================================================
#
#
# def sidebar() -> tuple[AgentConfig, bool, bool]:
#     with st.sidebar:
#         st.header("Call settings")
#
#         demo = st.toggle(
#             "Demo mode (no models, no audio)",
#             value=st.session_state.get("demo_mode", False),
#             help="Runs the same dialogue loop with canned replies. Useful to show the UI "
#                  "on a machine without a microphone or without the Shruti model.",
#         )
#         st.session_state["demo_mode"] = demo
#
#         mode = st.radio(
#             "Input",
#             options=["audio", "text"],
#             key="input_mode",
#             horizontal=True,
#             help="audio = record 5-6 s from the microphone. text = type the customer's reply.",
#         )
#
#         provider = st.radio(
#             "TTS provider",
#             options=["edge", "cartesia"],
#             horizontal=True,
#             disabled=demo,
#         )
#
#         record_seconds = st.slider(
#             "Recording window (seconds)", min_value=3.0, max_value=8.0,
#             value=5.5, step=0.5,
#             help="How long the microphone stays open after the agent finishes speaking.",
#         )
#         max_turns = st.slider("Max turns", 4, 20, 14)
#
#         settle = st.slider(
#             "Pause after the agent speaks (seconds)", 0.0, 0.6, 0.15, 0.05,
#             help="Tail silence before the microphone opens, so the speaker is never "
#                  "recorded through the microphone (echo guard).",
#         )
#
#         with st.expander("Models & voices", expanded=False):
#             ollama_model = st.text_input("Ollama model", value="gemma4:31b-cloud")
#             edge_hi = st.text_input("Edge voice · Hindi", value="en-IN-NeerjaNeural")
#             edge_en = st.text_input("Edge voice · English", value="en-IN-NeerjaNeural")
#
#         cartesia_key = ""
#         cart_hi = cart_en = "4459a9a5-69d6-4680-b970-e13dc51845b6"
#         if provider == "cartesia" and not demo:
#             st.divider()
#             cartesia_key = st.text_input(
#                 "Cartesia API key", type="password", value=st.session_state.get("cartesia_key", "")
#             )
#             st.session_state["cartesia_key"] = cartesia_key
#             cart_hi = st.text_input("Cartesia voice · Hindi", value=cart_hi)
#             cart_en = st.text_input("Cartesia voice · English", value=cart_en)
#             if not cartesia_key:
#                 st.warning("Cartesia needs an API key.")
#
#         cfg = AgentConfig(
#             mode=mode,
#             tts_provider=provider,
#             record_seconds=record_seconds,
#             max_turns=max_turns,
#             ollama_model=ollama_model,
#             edge_hindi_voice=edge_hi,
#             edge_english_voice=edge_en,
#             cartesia_api_key=cartesia_key,
#             cartesia_hindi_voice=cart_hi,
#             cartesia_english_voice=cart_en,
#             settle_seconds=settle,
#         )
#
#         st.divider()
#         with st.expander("Audio devices", expanded=False):
#             if demo:
#                 st.caption("Demo mode - no devices are used.")
#                 audio_ok = True
#                 audio_msg = "demo"
#             else:
#                 try:
#                     audio_ok, audio_msg = audio_devices()
#                 except Exception as exc:      # pragma: no cover - defensive
#                     audio_ok, audio_msg = False, str(exc)
#                 st.caption(audio_msg)
#
#         st.divider()
#         if st.button("🔄 Unload models", **WIDE,
#                      help="Frees the STT model; it reloads on the next call."):
#             running = st.session_state.get("agent")
#             if running is not None and running.is_running():
#                 running.stop()
#                 running.wait(timeout=2)
#             get_core.clear()
#             st.session_state["core_ready"] = False
#             st.session_state["agent"] = None
#             st.rerun()
#
#         run_audio = (not demo) and audio_ok and mode == "audio"
#     return cfg, run_audio, demo
#
#
# # =============================================================================
# # Live call panel
# # =============================================================================
#
#
# def _status_block(snap: dict) -> None:
#     icon, label, _ = STATUS_UI.get(snap["status"], ("⚪", snap["status"], "normal"))
#     left, mid, right = st.columns([2, 3, 3])
#     left.markdown(f"### {icon} {label}")
#     right.metric("Turn", f"{snap['turn']}/{snap['max_turns']}")
#     mid.metric("Elapsed", f"{snap['elapsed']:.0f}s")
#
#     if snap["status"] == LISTENING and snap["mode"] == "audio":
#         elapsed = time.time() - snap["status_since"]
#         window = max(0.1, st.session_state.get("record_seconds", 5.5))
#         st.progress(min(elapsed / window, 1.0), text=f"Microphone open · {min(elapsed, window):.1f}s / {window:.1f}s")
#     elif snap["status"] == THINKING:
#         st.progress(min((time.time() - snap["status_since"]) / 6.0, 0.95),
#                     text=f"Waiting for the model · {time.time() - snap['status_since']:.1f}s")
#     elif snap["status"] == SPEAKING:
#         st.caption(f"Speaking: {snap['detail']}")
#
#     if snap["error"]:
#         st.error(snap["error"])
#
#
# def _transcript(snap: dict) -> None:
#     if not snap["lines"]:
#         st.caption("The conversation will appear here.")
#         return
#     for line in snap["lines"]:
#         with st.chat_message("assistant" if line["role"] == "assistant" else "user"):
#             st.write(line["text"])
#
#
# def render_snapshot() -> None:
#     """Everything that changes while the call runs."""
#     agent: ConversationAgent | None = st.session_state.get("agent")
#     if agent is None:
#         st.info("Press **Start call**. The agent greets the customer, then the "
#                 "microphone opens automatically after it finishes speaking.")
#         return
#
#     snap = agent.snapshot()
#     _status_block(snap)
#     st.divider()
#
#     left, right = st.columns([3, 2], gap="large")
#     with left:
#         st.subheader("Transcript")
#         _transcript(snap)
#     with right:
#         st.subheader("Collected data")
#         collected = snap["collected"]
#         st.dataframe(
#             {
#                 "field": ["received", "product_condition", "delivery_experience", "rating"],
#                 "value": [
#                     collected.get("received") or "—",
#                     collected.get("product_condition") or "—",
#                     collected.get("delivery_experience") or "—",
#                     collected.get("rating") or "—",
#                 ],
#             },
#             hide_index=True,
#             **WIDE,
#         )
#         if snap["result"]:
#             st.download_button(
#                 "⬇️ Download this call (JSON)",
#                 data=json.dumps(snap["result"], ensure_ascii=False, indent=2),
#                 file_name=f"call_{snap['result'].get('timestamp', 'record')}.json",
#                 mime="application/json",
#                 **WIDE,
#             )
#         if snap["end_reason"]:
#             st.caption(f"end_reason · {snap['end_reason']}")
#
#
# live = st.fragment(run_every=0.5)(render_snapshot) if hasattr(st, "fragment") else render_snapshot
#
#
# # =============================================================================
# # Page
# # =============================================================================
#
#
# cfg, run_audio, demo = sidebar()
# st.session_state["record_seconds"] = cfg.record_seconds
#
# st.title("📞 Post-delivery feedback call")
# st.caption("Shruti STT · Ollama · Edge/Cartesia TTS — one turn at a time, hands-free.")
#
# agent: ConversationAgent | None = st.session_state.get("agent")
# call_running = agent is not None and agent.is_running()
#
# start_col, stop_col, new_col = st.columns([1, 1, 2])
# with start_col:
#     start = st.button("▶️ Start call", type="primary", **WIDE,
#                       disabled=call_running)
# with stop_col:
#     stop = st.button("⏹ Stop", **WIDE,
#                      disabled=not call_running)
# with new_col:
#     if st.button("🆕 New call (clear screen)", **WIDE):
#         previous = st.session_state.get("agent")
#         if previous is not None and previous.is_running():
#             previous.stop()
#             previous.wait(timeout=2)
#         st.session_state["agent"] = None
#         st.session_state["record"] = None
#         st.rerun()
#
#
# def _start_call() -> bool:
#     current = st.session_state.get("agent")
#     if current is not None and current.is_running():
#         st.warning("A call is already in progress.")
#         return False
#     if cfg.mode == "audio" and not demo and not run_audio:
#         st.error("No audio device is available. Switch **Input** to *text*, or enable *Demo mode*.")
#         return False
#     try:
#         with st.spinner("Loading the agent (STT model + TTS client)…"):
#             core = get_core(demo, "call_voice_cartesia.py")
#         st.session_state["core_ready"] = True
#         call_cfg = dataclasses.replace(cfg, json_file="demo_calls.json") if demo else cfg
#         st.session_state["agent"] = ConversationAgent(core, call_cfg)
#         st.session_state["agent"].start()
#         st.session_state["_final_rerun"] = False
#         return True
#     except Exception as exc:
#         st.session_state["core_ready"] = False
#         st.error(f"Could not start the call: {type(exc).__name__}: {exc}")
#         st.info(
#             "Checklist:\n"
#             "- `pip install streamlit sounddevice soundfile edge-tts ollama`\n"
#             "- `needle` (Cactus) installed and `shruti.cact` present for STT\n"
#             "- microphone + speakers available in **Audio devices** (sidebar)\n"
#             "- or enable **Demo mode** to try the UI without any of the above."
#         )
#         return False
#
#
# if start:
#     if _start_call():
#         st.rerun()
#
# if str(_qp.get("autostart", "")).lower() in ("1", "true") and not st.session_state.get("_autostarted"):
#     st.session_state["_autostarted"] = True
#     if _start_call():
#         st.rerun()
# if stop and agent is not None:
#     agent.stop()
#     agent.wait(timeout=3)
#     st.rerun()
#
# live()
#
# # ------------------------------------------------------------------ text input
# agent = st.session_state.get("agent")
# if agent is not None and agent.is_running():
#     snap = agent.snapshot()
#     if cfg.mode == "text" and snap["status"] == LISTENING:
#         with st.form("reply", clear_on_submit=True):
#             reply = st.text_input("Customer reply", placeholder="Type what the customer says…")
#             sent = st.form_submit_button("Send ➤")
#         if sent and reply.strip():
#             agent.submit_text(reply)
#             st.rerun()
#
# # ------------------------------------------------------------- finished record
# agent = st.session_state.get("agent")
# if agent is not None:
#     snap = agent.snapshot()
#     if snap["status"] in (ENDED, ERROR) and not st.session_state.get("_final_rerun"):
#         # buttons are rendered before the worker ends: refresh once so
#         # Start becomes clickable and Stop disabled.
#         st.session_state["_final_rerun"] = True
#         st.rerun()
#     if snap["status"] == ENDED and snap["result"]:
#         st.success(f"Call finished ({snap['end_reason']}) — saved to `{snap.get('json_file', 'customer_feedback.json')}`.")
#         with st.expander("Full saved record", expanded=True):
#             st.json(snap["result"])
#     elif snap["status"] == ERROR:
#         st.warning("The call stopped because of an error. Details above.")




import base64
import json
import os
import re
import subprocess
import tempfile
import uuid
import asyncio

from datetime import datetime
from pathlib import Path

import streamlit as st
import ollama
import edge_tts

from streamlit.components.v1 import declare_component
from needle import Whistle


# ============================================================
# CONFIGURATION
# ============================================================

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
SILENCE_THRESHOLD = 0.012

JSON_FILE = Path("customer_feedback.json")

SHRUTI_MODEL_PATH = os.getenv(
    "SHRUTI_MODEL_PATH",
    "shruti.cact",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4:31b-cloud",
)

EDGE_HINDI_VOICE = os.getenv(
    "EDGE_HINDI_VOICE",
    "hi-IN-SwaraNeural",
)

EDGE_ENGLISH_VOICE = os.getenv(
    "EDGE_ENGLISH_VOICE",
    "en-IN-NeerjaNeural",
)


# ============================================================
# STREAMLIT AUDIO COMPONENT
# Requires frontend/index.html
# ============================================================

FRONTEND_DIR = Path(__file__).parent / "frontend"

voice_component = declare_component(
    "voice_feedback_audio",
    path=str(FRONTEND_DIR),
)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a polite, natural post-delivery feedback calling agent
for an Indian e-commerce company.

The conversation is with a customer a few days after their
order was delivered.

Conversation flow:
1. Ask if the customer has 1-2 minutes.
2. Ask whether the product was received.
3. Ask about product condition.
4. Ask about delivery experience.
5. Ask for a rating from 1 to 5.
6. Ask for comments or suggestions.
7. Thank the customer and end politely.

Language:
- Respond naturally in Hindi, English, or Hinglish.
- Follow the language the customer primarily uses.
- Keep spoken replies short, ideally 1-2 sentences.
- Ask only one question at a time.
- Do not repeat questions already answered.
- Show empathy when appropriate.

Ratings:
- Store ratings as integers from 1 to 5.
- If the customer says below 1, store 1.
- If the customer says above 5, store 5.
- Do not explain normalization to the customer.

At the end of EVERY response, include internal data
in exactly this format:

###JSON###
{
  "received": "",
  "product_condition": "",
  "delivery_experience": "",
  "rating": "",
  "comments": "",
  "should_end": false
}
###END###

Only fill fields clearly understood from the conversation.
Retain previously collected information.
Set should_end=true only when ending the conversation.
Never speak the JSON to the customer.
"""


# ============================================================
# FEEDBACK STORAGE
# ============================================================

def load_feedback():
    try:
        if JSON_FILE.exists():
            return json.loads(
                JSON_FILE.read_text(encoding="utf-8")
            )
    except (json.JSONDecodeError, OSError):
        pass

    return []


def save_feedback(record):
    records = load_feedback()
    records.append(record)

    JSON_FILE.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# LLM RESPONSE PROCESSING
# ============================================================

def extract_json(reply):
    match = re.search(
        r"###JSON###(.*?)###END###",
        reply,
        re.DOTALL,
    )

    if not match:
        return {}

    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}


def clean_reply(reply):
    return re.sub(
        r"###JSON###.*?###END###",
        "",
        reply,
        flags=re.DOTALL,
    ).strip()


def ask_llm(history, user_text):
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={
            "temperature": 0.35,
        },
    )

    return response["message"]["content"]


# ============================================================
# TEXT-TO-SPEECH
# ============================================================

async def generate_speech(text, language="hindi"):
    if language == "hindi":
        voice = EDGE_HINDI_VOICE
    else:
        voice = EDGE_ENGLISH_VOICE

    communicate = edge_tts.Communicate(
        text,
        voice,
    )

    chunks = []

    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            chunks.append(chunk["data"])

    return b"".join(chunks)


def tts_bytes(text, language="hindi"):
    return asyncio.run(
        generate_speech(text, language)
    )


def detect_language(text):
    has_hindi = any(
        "\u0900" <= char <= "\u097F"
        for char in text
    )

    return "hindi" if has_hindi else "english"


# ============================================================
# SPEECH-TO-TEXT
# ============================================================

@st.cache_resource(show_spinner="Loading speech recognition model...")
def load_stt_model():
    return Whistle(SHRUTI_MODEL_PATH)


def transcribe_webm(webm_bytes):
    """
    Convert browser-recorded WebM/Opus audio to
    16 kHz mono WAV and transcribe it.
    """

    if not webm_bytes:
        return ""

    stt_model = load_stt_model()

    with tempfile.TemporaryDirectory() as tmpdir:

        webm_path = Path(tmpdir) / "input.webm"
        wav_path = Path(tmpdir) / "input.wav"

        webm_path.write_bytes(webm_bytes)

        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(webm_path),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-sample_fmt",
            "s16",
            str(wav_path),
        ]

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg is not installed. "
                "Install it using: sudo apt install ffmpeg"
            ) from exc

        except subprocess.CalledProcessError as exc:
            details = exc.stderr.decode(
                "utf-8",
                errors="ignore",
            )[-800:]

            raise RuntimeError(
                f"Could not convert browser audio to WAV: {details}"
            ) from exc

        import soundfile as sf
        import numpy as np

        audio, _sr = sf.read(
            str(wav_path),
            dtype="float32",
        )

        if (
            audio.size == 0
            or float(np.max(np.abs(audio))) < SILENCE_THRESHOLD
        ):
            return ""

        result = stt_model.transcribe(
            str(wav_path)
        )

        return (result.get("text") or "").strip()


# ============================================================
# SESSION STATE
# ============================================================

def initialise_state():

    defaults = {
        "started": False,
        "finished": False,
        "history": [],
        "record": {
            "timestamp": datetime.now().isoformat(),
            "received": "",
            "product_condition": "",
            "delivery_experience": "",
            "rating": "",
            "comments": "",
            "full_transcript": [],
        },
        "agent_text": "",
        "agent_audio": "",
        "response_id": "",
        "last_processed_turn": "",
        "status": "Ready",
        "turn_count": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================
# PREPARE AGENT AUDIO
# ============================================================

def queue_agent_reply(text, language=None):

    language = language or detect_language(text)

    audio = tts_bytes(
        text,
        language,
    )

    st.session_state.agent_text = text

    st.session_state.agent_audio = (
        base64.b64encode(audio).decode("ascii")
    )

    # A new ID tells the frontend that a new response is ready.
    st.session_state.response_id = uuid.uuid4().hex

    st.session_state.status = "Agent is speaking…"


# ============================================================
# PROCESS USER AUDIO
# ============================================================

def process_user_turn(component_value):

    if not isinstance(component_value, dict):
        return

    turn_id = component_value.get("turn_id")
    audio_b64 = component_value.get("audio_b64")

    if (
        not turn_id
        or not audio_b64
        or turn_id == st.session_state.last_processed_turn
    ):
        return

    # Mark the turn before processing to prevent duplicates.
    st.session_state.last_processed_turn = turn_id

    st.session_state.status = "Transcribing your response…"

    try:
        webm_bytes = base64.b64decode(audio_b64)

        user_text = transcribe_webm(webm_bytes)

    except Exception as exc:
        st.session_state.status = (
            f"Audio processing error: {exc}"
        )

        queue_agent_reply(
            "Sorry, mujhe aapki awaaz clearly nahi sunai di. "
            "Kya aap dobara bolenge?",
            "hindi",
        )

        return

    if not user_text:

        st.session_state.status = (
            "No speech detected; asking you to repeat."
        )

        queue_agent_reply(
            "Sorry, main aapki baat clearly nahi sun paya. "
            "Kya aap dobara bolenge?",
            "hindi",
        )

        return

    # Save the customer response in conversation history.
    st.session_state.record["full_transcript"].append(
        f"User: {user_text}"
    )

    st.session_state.history.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    st.session_state.turn_count += 1

    st.session_state.status = "Thinking…"

    try:
        full_reply = ask_llm(
            st.session_state.history[:-1],
            user_text,
        )

    except Exception as exc:
        st.session_state.status = f"Ollama error: {exc}"

        queue_agent_reply(
            "Sorry, abhi thodi technical problem hai. "
            "Kya aap ek pal rukenge?",
            "hindi",
        )

        return

    data = extract_json(full_reply)

    spoken_reply = clean_reply(full_reply)

    if not spoken_reply:
        spoken_reply = (
            "Thank you. Kya aap kuch aur share karna chahenge?"
        )

    # Update collected feedback fields.
    for key in (
        "received",
        "product_condition",
        "delivery_experience",
        "rating",
        "comments",
    ):
        if data.get(key):
            st.session_state.record[key] = data[key]

    st.session_state.history.append(
        {
            "role": "assistant",
            "content": spoken_reply,
        }
    )

    st.session_state.record["full_transcript"].append(
        f"Agent: {spoken_reply}"
    )

    # End the conversation when requested by the model.
    if (
        data.get("should_end")
        or st.session_state.turn_count >= 14
    ):

        st.session_state.finished = True

        if not st.session_state.record.get("comments"):
            st.session_state.record["comments"] = " | ".join(
                st.session_state.record["full_transcript"][-8:]
            )

        save_feedback(
            st.session_state.record
        )

        queue_agent_reply(
            spoken_reply,
            detect_language(spoken_reply),
        )

        st.session_state.status = (
            "Conversation complete. Feedback saved."
        )

    else:

        queue_agent_reply(
            spoken_reply,
            detect_language(spoken_reply),
        )


# ============================================================
# START CONVERSATION
# ============================================================

def start_conversation():

    if st.session_state.started:
        return

    st.session_state.started = True

    opening = (
        "नमस्ते! Hello, main aapke recent order ke baare mein "
        "feedback lene ke liye call kar rahi hoon. "
        "Kya aapke paas 1-2 minute hain baat karne ke liye?"
    )

    st.session_state.history.append(
        {
            "role": "assistant",
            "content": opening,
        }
    )

    st.session_state.record["full_transcript"].append(
        f"Agent: {opening}"
    )

    try:
        queue_agent_reply(
            opening,
            "hindi",
        )

    except Exception as exc:
        st.session_state.status = f"TTS error: {exc}"
        st.error(
            f"Could not generate the opening voice: {exc}"
        )


# ============================================================
# MAIN STREAMLIT APP
# ============================================================

def main():

    st.set_page_config(
        page_title="Voice Feedback Agent",
        page_icon="🎙️",
        layout="centered",
    )

    initialise_state()

    st.title("🎙️ Customer Feedback")

    st.caption(
        "Voice-only feedback conversation. "
        "Keep this tab open and allow microphone access."
    )

    if not st.session_state.started:

        st.info(
            "Press Start once. The agent will speak, "
            "then automatically listen for 5 seconds "
            "after each reply."
        )

        if st.button(
            "Start conversation",
            type="primary",
            use_container_width=True,
        ):

            start_conversation()
            st.rerun()

    if st.session_state.started:

        st.caption(
            f"Status: {st.session_state.status}"
        )

        # Browser component handles playback and recording.
        value = voice_component(
            audio_b64=st.session_state.agent_audio,
            response_id=st.session_state.response_id,
            record_seconds=RECORD_SECONDS,
            finished=st.session_state.finished,
            key="voice_component",
            default=None,
        )

        # Process the returned browser recording once.
        if value and not st.session_state.finished:

            previous_turn = (
                st.session_state.last_processed_turn
            )

            process_user_turn(value)

            if (
                st.session_state.last_processed_turn
                != previous_turn
            ):
                st.rerun()

        if st.session_state.finished:

            st.success(
                "Conversation finished. Feedback has been "
                "saved to customer_feedback.json."
            )

            if st.button(
                "Start a new conversation",
                use_container_width=True,
            ):

                keys_to_reset = [
                    "started",
                    "finished",
                    "history",
                    "record",
                    "agent_text",
                    "agent_audio",
                    "response_id",
                    "last_processed_turn",
                    "status",
                    "turn_count",
                ]

                for key in keys_to_reset:
                    st.session_state.pop(
                        key,
                        None,
                    )

                st.rerun()


if __name__ == "__main__":
    main()