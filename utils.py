import os
import json
import asyncio
import edge_tts
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-3-flash-preview")

def build_profile_string(user_data):
    """Formats user data into a readable string for the AI"""
    return f"""
    - Grade: {user_data.get('grade', 'Unknown')}
    - First Language: {user_data.get('first_language', 'English')}
    - Learning Style: {user_data.get('learning_style', 'Visual')}
    - IEP Accommodations: {user_data.get('iep_needs', 'None')}
    - Parent Goal: {user_data.get('parent_goal', 'General improvement')}
    """

def extract_and_analyze_homework(file_bytes, file_type, user_data) -> dict:
    """Sends file to Gemini to read and generate lesson plan"""
    from prompts import SYSTEM_PROMPT
    
    profile = build_profile_string(user_data)
    prompt = SYSTEM_PROMPT.format(profile=profile)
    
    mime_type = "application/pdf" if file_type == "application/pdf" else "image/jpeg"
    
    content_parts = [prompt, {"mime_type": mime_type, "data": file_bytes}]
    
    response = gemini_model.generate_content(
        content_parts,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=1500,
        )
    )
    
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        text = response.text
        if "```json" in text: text = text.split("```json")[1].split("```")[0]
        elif "```" in text: text = text.split("```")[1].split("```")[0]
        return json.loads(text)

def chat_with_tutor(chat_history, user_input, user_data) -> str:
    """Handles the conversational practice mode"""
    from prompts import CONVERSATION_PROMPT
    
    profile = build_profile_string(user_data)
    prompt = CONVERSATION_PROMPT.format(profile=profile)
    
    # Build the message history for Gemini
    messages = [{"role": "user", "parts": [prompt]}]
    
    # Add previous chat history
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "model"
        messages.append({"role": role, "parts": [msg["content"]]})
    
    # Add current input
    messages.append({"role": "user", "parts": [user_input]})
    
    response = gemini_model.generate_content(
        messages,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=300,
        )
    )
    
    return response.text

async def _generate_audio(text, output_path, voice="fr-FR-DeniseNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio(text, output_path):
    asyncio.run(_generate_audio(text, output_path))
    return output_path

def generate_vocab_audio(vocab_list, output_dir):
    results = []
    for i, item in enumerate(vocab_list):
        french_word = item.get("french", "")
        if not french_word: continue
        audio_path = os.path.join(output_dir, f"vocab_{i}.mp3")
        generate_audio(french_word, audio_path)
        results.append({"index": i, "audio_path": audio_path})
    return results
