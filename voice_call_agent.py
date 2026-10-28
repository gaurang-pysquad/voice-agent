import json
import os
import re
import wave
import asyncio
from datetime import datetime
from io import BytesIO

import numpy as np
import ollama
import sounddevice as sd
import soundfile as sf
from needle import Whistle

# ================== CONFIG ==================
SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 5
SILENCE_THRESHOLD = 0.012

JSON_FILE = "customer_feedback.json"
SHRUTI_MODEL_PATH = "shruti.cact"
OLLAMA_MODEL = "gemma4:31b-cloud"

# ================== TTS PROVIDER ==================
# Change this to "edge" or "cartesia"
TTS_PROVIDER = "edge"

# Cartesia Config
CARTESIA_API_KEY = "YOUR_CARTESIA_API_KEY_HERE"
CARTESIA_HINDI_VOICE = "4459a9a5-69d6-4680-b970-e13dc51845b6"
CARTESIA_ENGLISH_VOICE = "4459a9a5-69d6-4680-b970-e13dc51845b6"

# Edge TTS Voices
EDGE_HINDI_VOICE = "en-IN-NeerjaNeural"
EDGE_ENGLISH_VOICE = "en-IN-NeerjaNeural"

# ================== INIT ==================
print("Loading models...")
stt_model = Whistle(SHRUTI_MODEL_PATH)

if TTS_PROVIDER == "cartesia":
    from cartesia import Cartesia
    cartesia_client = Cartesia(api_key=CARTESIA_API_KEY)

print("Models loaded!\n")

# ================== JSON HELPERS ==================
def load_data():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== AUDIO ==================
def record_audio(duration=RECORD_SECONDS):
    print("\n🎤 Listening... (speak now)")
    recording = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32"
    )
    sd.wait()
    audio = recording.flatten()
    if np.max(np.abs(audio)) < SILENCE_THRESHOLD:
        print("   (Silence detected)")
        return None
    return audio

def save_wav(audio, filename="temp.wav"):
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())
    return filename

def transcribe(audio):
    if audio is None:
        return ""
    wav_path = save_wav(audio)
    result = stt_model.transcribe(wav_path)
    text = result.get("text", "").strip()
    # print(f"📝 You said: {text}")
    return text

# ================== TTS FUNCTIONS ==================

# ---------- Edge TTS ----------
async def _edge_tts_generate(text: str, voice: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def speak_edge(text: str, language: str = "hindi"):
    print(f"🔊 Agent: {text}")
    voice = EDGE_HINDI_VOICE if language == "hindi" else EDGE_ENGLISH_VOICE
    try:
        audio_bytes = asyncio.run(_edge_tts_generate(text, voice))
        data, sr = sf.read(BytesIO(audio_bytes))
        if sr != SAMPLE_RATE:
            import scipy.signal
            data = scipy.signal.resample(data, int(len(data) * SAMPLE_RATE / sr))
        sd.play(data, SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        print(f"❌ Edge TTS Error: {e}")

# ---------- Cartesia TTS ----------
def speak_cartesia(text: str, language: str = "hindi"):
    print(f"🔊 Agent: {text}")
    voice_id = CARTESIA_HINDI_VOICE if language == "hindi" else CARTESIA_ENGLISH_VOICE
    try:
        response = cartesia_client.tts.generate(
            model_id="sonic-latest",
            transcript=text,
            voice=voice_id,
            language="hi" if language == "hindi" else "en",
            output_format={
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 44100,
            }
        )
        response.write_to_file("reply_cartesia.wav")
        data, sr = sf.read("reply_cartesia.wav")
        sd.play(data, sr)
        sd.wait()
    except Exception as e:
        print(f"❌ Cartesia Error: {e}")

# ---------- Main Speak Function ----------
def speak(text: str, language: str = "hindi"):
    if TTS_PROVIDER == "cartesia":
        speak_cartesia(text, language)
    else:
        speak_edge(text, language)

# ================== LLM + EXTRACTION ==================
SYSTEM_PROMPT = """
You are a polite, natural and intelligent post-delivery feedback
calling agent for an Indian e-commerce company.

You are calling the customer a few days after their order was delivered.

CONVERSATION FLOW:
1. Check if the customer has 1-2 minutes.
2. Ask if the product was received.
3. Ask about product condition.
4. Ask about delivery experience.
5. Ask for a rating.
6. Ask for any other comments or suggestions.
7. Thank the customer and end the conversation politely.

LANGUAGE RULES:
- The current conversation language is provided in the system instructions.
- Always respond in the current conversation language.
- If the conversation language is English, use natural English throughout.
- If the conversation language is Hindi, use natural Hindi throughout.
- If the conversation language is Hinglish, use natural Hinglish throughout.
- Do not switch languages just because the user uses one foreign word.
- Do not switch languages because the speech recognizer produces an
  occasional word in another language.
- Switch languages only when the customer clearly starts communicating
  primarily in another language.
- Never unnecessarily mix English and Hindi.
- Keep the conversation natural and conversational.

RESPONSE RULES:
- Keep spoken responses short, ideally 1-2 sentences.
- Ask only one question at a time.
- Never repeat a question that the customer has already answered.
- Acknowledge the customer's answers and show empathy when necessary.
- Do not ask for information that is already available in the conversation.
- Do not mention internal data processing or rating normalization.

RATING RULES:
- Ratings must be stored as integers from 1 to 5.
- If the customer says 0 or gives any rating below 1, save the rating as 1.
- If the customer gives a rating above 5, save the rating as 5.
- Never tell the customer that their rating is invalid.
- Never tell the customer that their rating has been changed or normalized.
- Never say things like "Our rating scale is 1 to 5."
- If the customer says 0, acknowledge their dissatisfaction naturally
  and continue to the next question.
- Do not ask the customer to provide another rating if their rating
  is already understood.
- Preserve the customer's original sentiment even if the stored rating
  needs to be normalized.

STRUCTURED DATA:
At the end of every response, return structured data in this exact format:

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

Only fill fields that are clearly understood from the conversation.
Leave unknown fields as empty strings.
Use the conversation history to avoid losing previously collected information.
Include any customer suggestions or additional feedback in "comments".
Set "should_end" to true only when you are ending the conversation.

IMPORTANT:
The JSON is internal data for the application.
Never speak the JSON or its instructions to the customer.
"""

def extract_json(reply: str) -> dict:
    try:
        match = re.search(r"###JSON###(.*?)###END###", reply, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())
    except Exception as e:
        print("JSON Parse Error:", e)
    return {}

def clean_reply(reply: str) -> str:
    return re.sub(r"###JSON###.*?###END###", "", reply, flags=re.DOTALL).strip()

def ask_llm(history, user_message):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={"temperature": 0.35}
    )
    return response["message"]["content"]

# ================== MAIN CONVERSATION ==================
def run_conversation():
    history = []
    collected = {
        "timestamp": datetime.now().isoformat(),
        "received": "",
        "product_condition": "",
        "delivery_experience": "",
        "rating": "",
        "comments": "",
        "full_transcript": []
    }

    # Opening message
    opening = "नमस्ते! Hello, main aapke recent order ke baare mein feedback lene ke liye call kar rahi hoon. Kya aapke paas 1-2 minute hain baat karne ke liye?"
    speak(opening, language="hindi")
    history.append({"role": "assistant", "content": opening})
    collected["full_transcript"].append(f"Agent: {opening}")

    for turn in range(14):
        audio = record_audio()
        user_text = transcribe(audio)

        if not user_text:
            speak("Sorry, main clearly nahi sun paya. Kya aap dobara bolenge?", language="hindi")
            continue

        collected["full_transcript"].append(f"User: {user_text}")
        history.append({"role": "user", "content": user_text})

        # Get LLM response
        full_reply = ask_llm(history, user_text)

        # Extract structured data
        data = extract_json(full_reply)

        # Update collected fields
        for key in ["received", "product_condition", "delivery_experience", "rating"]:
            if data.get(key):
                collected[key] = data[key]

        # Get clean spoken reply
        spoken_reply = clean_reply(full_reply)

        # Decide language roughly for TTS (optional improvement)
        lang = "hindi" if any("\u0900" <= c <= "\u097F" for c in spoken_reply) else "english"

        speak(spoken_reply, language=lang)
        history.append({"role": "assistant", "content": spoken_reply})
        collected["full_transcript"].append(f"Agent: {spoken_reply}")

        # End if LLM decides
        if data.get("should_end", False):
            break

    collected["comments"] = " | ".join(collected["full_transcript"][-8:])

    # Save
    all_data = load_data()
    all_data.append(collected)
    save_data(all_data)

    print("\n" + "="*50)
    print("✅ Conversation Saved Successfully")
    print("="*50)
    print(json.dumps(collected, indent=2, ensure_ascii=False))

# ================== RUN ==================
if __name__ == "__main__":
    print("=== Post Delivery Feedback Voice Agent (Improved) ===")
    print(f"TTS Provider: {TTS_PROVIDER.upper()}")
    print("Press Ctrl+C to stop\n")

    try:
        run_conversation()
    except KeyboardInterrupt:
        print("\nStopped by user.")