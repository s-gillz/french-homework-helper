import os
import json
import asyncio
import edge_tts
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use Gemini 2.0 Flash (fast, free, multimodal)
gemini_model = genai.GenerativeModel("gemini-3-flash-preview")


def extract_and_analyze_homework(file_bytes: bytes, file_type: str, grade: int) -> dict:
    """
    Send image/PDF directly to Gemini. No OCR needed.
    Gemini reads the file AND generates the lesson plan in one step.
    """
    from prompts import SYSTEM_PROMPT
    
    # Determine MIME type
    if file_type == "application/pdf":
        mime_type = "application/pdf"
    else:
        mime_type = "image/jpeg" if file_type in ["image/jpeg", "image/jpg"] else "image/png"
    
    # Prepare the prompt
    prompt = SYSTEM_PROMPT.format(grade=grade)
    
    # Create the content parts: prompt + file
    content_parts = [
        prompt,
        {
            "mime_type": mime_type,
            "data": file_bytes
        }
    ]
    
    # Call Gemini
    response = gemini_model.generate_content(
        content_parts,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=1500,
        )
    )
    
    # Parse JSON response
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON from markdown code blocks
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text)


async def _generate_audio(text: str, output_path: str, voice: str = "fr-FR-DeniseNeural"):
    """Internal async TTS"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_audio(text: str, output_path: str) -> str:
    """Generate French pronunciation audio using Edge-TTS (unlimited free)"""
    asyncio.run(_generate_audio(text, output_path))
    return output_path


def generate_vocab_audio(vocab_list: list, output_dir: str) -> list:
    """Generate audio for each vocab word"""
    results = []
    for i, item in enumerate(vocab_list):
        french_word = item.get("french", "")
        if not french_word:
            continue
        audio_path = os.path.join(output_dir, f"vocab_{i}.mp3")
        generate_audio(french_word, audio_path)
        results.append({"index": i, "audio_path": audio_path})
    return results