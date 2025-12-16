import os
import json
import uuid
import yt_dlp
from openai import OpenAI
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from dotenv import load_dotenv

load_dotenv()

# Setup Chutes Client
client = OpenAI(
    api_key=os.getenv("CHUTES_API_KEY"),
    base_url="https://chutes.ai/api/v1"
)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

async def download_audio(url: str, video_id: str):
    """Download audio saja untuk keperluan transkripsi (Cepat)"""
    output_path = os.path.join(TEMP_DIR, video_id)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
        'outtmpl': output_path,
        'quiet': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return f"{output_path}.mp3", info.get('title', 'Unknown Video')

async def transcribe_with_chutes(audio_path: str):
    """Menggunakan Whisper V3 di Chutes"""
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="openai/whisper-large-v3",
            file=audio_file
        )
    return transcript.text

async def analyze_with_llama(text: str):
    """
    Menggunakan Llama 3 di Chutes dengan prompt yang diperkaya
    untuk menghasilkan metadata viral (Hook, Caption, Quote).
    """
    system_prompt = """
    You are an expert viral video editor. Your task is to analyze the transcript and extract 3-5 clips that have high viral potential for TikTok/Shorts.

    CONSTRAINTS:
    1. Clip duration must be between 15 and 60 seconds.
    2. Output MUST be a valid JSON Array. No markdown formatting.
    3. LANGUAGE: Use Indonesian (Bahasa Indonesia) for all text fields.

    REQUIRED JSON FIELDS FOR EACH CLIP:
    - "id": integer (1, 2, 3...)
    - "title": string (Catchy title)
    - "start": integer (Start time in seconds)
    - "end": integer (End time in seconds)
    - "reason": string (Why is this specific part viral/good?)
    - "highlight_quote": string (The most important sentence spoken in this clip)
    - "hook_text": string (Short, punchy text to put ON THE VIDEO screen to stop scrolling)
    - "social_caption": string (Very short caption for Instagram/TikTok description. MAXIMUM 5 WORDS).
    """
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the transcript:\n{text[:15000]}"}
            ],
            temperature=0.7
        )
        content = response.choices[0].message.content
        
        # Cleaning potential markdown syntax
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
        
    except Exception as e:
        print(f"AI Error: {e}")
        # Fallback dummy jika AI gagal parsing
        return [{
            "id": 0, 
            "title": "Error Parsing", 
            "start": 0, "end": 10, 
            "reason": "AI Error",
            "highlight_quote": "-",
            "hook_text": "Check Manual",
            "social_caption": "Check Video"
        }]
        

def process_video_cut(video_id: str, url: str, start: int, end: int):
    """
    Lazy download: Download video HANYA saat user minta cut.
    Menggunakan cache jika video sudah ada.
    """
    video_path = os.path.join(TEMP_DIR, f"{video_id}_full.mp4")
    output_path = os.path.join(TEMP_DIR, f"{video_id}_clip_{start}_{end}.mp4")

    # 1. Cek apakah master video sudah ada? Jika belum, download.
    if not os.path.exists(video_path):
        print("Downloading source video...")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(TEMP_DIR, f"{video_id}_full.%(ext)s"),
            'merge_output_format': 'mp4', # Force MP4 container
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    
    # 2. Potong Video
    if not os.path.exists(output_path):
        ffmpeg_extract_subclip(video_path, start, end, targetname=output_path)
    
    return output_path