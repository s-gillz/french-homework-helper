import os
import json
import asyncio
import re
import google.generativeai as genai
from dotenv import load_dotenv
from gtts import gTTS

load_dotenv()

# Try to get API key from multiple sources
api_key = None

# Method 1: Streamlit secrets (if running on Streamlit Cloud)
try:
    import streamlit as st
    api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
except:
    pass

# Method 2: Environment variables
if not api_key:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Configure Gemini
if api_key:
    genai.configure(api_key=api_key)
else:
    raise ValueError("GEMINI_API_KEY not found. Please add it to Streamlit secrets or environment variables.")
gemini_model = genai.GenerativeModel("gemini-3-flash-preview")

def parse_json(text):
    """Bulletproof JSON parser for LLM outputs"""
    try: return json.loads(text)
    except: pass
    match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(1))
        except: pass
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(1))
        except: pass
    fixed_text = re.sub(r"'([^']+)':", r'"\1":', text)
    try: return json.loads(fixed_text)
    except: pass
    raise ValueError(f"Could not parse JSON. Raw text: {text[:200]}...")

def build_profile_string(user_data):
    return f"""
    - Grade: {user_data.get('grade', 'Unknown')}
    - First Language: {user_data.get('first_language', 'English')}
    - Learning Style: {user_data.get('learning_style', 'Visual')}
    - IEP Accommodations: {user_data.get('iep_needs', 'None')}
    - Parent Goal: {user_data.get('parent_goal', 'General improvement')}
    """

def extract_and_analyze_homework(file_bytes, file_type, user_data) -> dict:
    from prompts import SYSTEM_PROMPT
    profile = build_profile_string(user_data)
    prompt = SYSTEM_PROMPT.format(profile=profile)
    mime_type = "application/pdf" if file_type == "application/pdf" else "image/jpeg"
    content_parts = [prompt, {"mime_type": mime_type, "data": file_bytes}]
    response = gemini_model.generate_content(
        content_parts,
        generation_config=genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.3, max_output_tokens=1500)
    )
    return parse_json(response.text)

def chat_with_tutor(chat_history, user_input, user_data) -> str:
    from prompts import CONVERSATION_PROMPT
    profile = build_profile_string(user_data)
    prompt = CONVERSATION_PROMPT.format(profile=profile)
    messages = [{"role": "user", "parts": [prompt]}]
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        messages.append({"role": role, "parts": [msg["content"]]})
    messages.append({"role": "user", "parts": [user_input]})
    response = gemini_model.generate_content(messages, generation_config=genai.types.GenerationConfig(temperature=0.7, max_output_tokens=300))
    return response.text

def generate_quiz(user_data) -> list:
    from prompts import QUIZ_PROMPT
    profile = build_profile_string(user_data)
    grade = user_data.get('grade', 4)
    prompt = QUIZ_PROMPT.format(profile=profile, grade=grade)
    response = gemini_model.generate_content(
        [prompt],
        generation_config=genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.5, max_output_tokens=3500)
    )
    return parse_json(response.text)

def generate_reading_comprehension(user_data) -> dict:
    from prompts import READING_PROMPT
    profile = build_profile_string(user_data)
    grade = user_data.get('grade', 4)
    prompt = READING_PROMPT.format(profile=profile, grade=grade)
    response = gemini_model.generate_content(
        [prompt],
        generation_config=genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.6, max_output_tokens=3500)
    )
    return parse_json(response.text)

def generate_audio(text, output_path):
    """Generate French audio using gTTS (Google Text-to-Speech)"""
    try:
        tts = gTTS(text=text, lang='fr', slow=False)
        tts.save(output_path)
        return output_path
    except Exception as e:
        raise Exception(f"Audio generation failed: {str(e)}")

def generate_vocab_audio(vocab_list, output_dir):
    results = []
    for i, item in enumerate(vocab_list):
        french_word = item.get("french", "")
        if not french_word: continue
        audio_path = os.path.join(output_dir, f"vocab_{i}.mp3")
        try:
            generate_audio(french_word, audio_path)
            results.append({"index": i, "audio_path": audio_path})
        except Exception as e:
            print(f"Failed to generate audio for {french_word}: {e}")
            continue
    return results
