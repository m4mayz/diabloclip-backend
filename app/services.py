import os
import json
import uuid
import base64
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

# --- FUNGSI BARU: MENANGANI COOKIES ---
def setup_cookies():
    """
    Menyiapkan file cookies.txt untuk yt-dlp.
    Prioritas:
    1. Cek apakah ada environment variable YOUTUBE_COOKIES (Base64).
    2. Cek apakah file cookies.txt fisik sudah ada.
    """
    cookie_filename = "cookies.txt"
    
    # Cek Environment Variable (Prioritas untuk Production/Railway)
    env_cookies = os.getenv("YOUTUBE_COOKIES")
    if env_cookies:
        try:
            # Decode Base64 kembali ke format teks Netscape
            decoded_cookies = base64.b64decode(env_cookies).decode('utf-8')
            # Tulis ke file fisik karena yt-dlp butuh path file
            with open(cookie_filename, "w") as f:
                f.write(decoded_cookies)
            return cookie_filename
        except Exception as e:
            print(f"Gagal decode cookies dari Env: {e}")
            return None

    # Fallback: Cek file lokal (Untuk Local Development)
    if os.path.exists(cookie_filename):
        return cookie_filename
        
    return None

async def download_audio(url: str, video_id: str):
    output_path = os.path.join(TEMP_DIR, video_id)
    cookie_file = setup_cookies() # Panggil helper cookies
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
        'outtmpl': output_path,
        'quiet': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    # Hanya tambahkan opsi cookiefile jika file berhasil dibuat/ditemukan
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return f"{output_path}.mp3", info.get('title', 'Unknown Video')

async def transcribe_with_chutes(audio_path: str):
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="openai/whisper-large-v3",
                file=audio_file
            )
        return transcript.text
    except Exception as e:
        print(f"Transkripsi Error: {e}")
        raise e

async def analyze_with_llama(text: str):
    system_prompt = """
    You are an expert viral video editor. Analyze the transcript and extract 3-5 clips (15s-60s) with high viral potential.
    RETURN ONLY RAW JSON ARRAY. No markdown.
    
    REQUIRED JSON FIELDS:
    - "id": integer
    - "title": string (Indonesian)
    - "start": integer
    - "end": integer
    - "reason": string (Indonesian)
    - "highlight_quote": string (Indonesian)
    - "hook_text": string (Indonesian)
    - "social_caption": string (Max 5 words, Indonesian)
    """
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:15000]}
            ],
            temperature=0.7
        )
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        print(f"AI Error: {e}")
        return [{
            "id": 0, "title": "Gagal Analisis AI", 
            "start": 0, "end": 10, 
            "reason": str(e), 
            "highlight_quote": "-", 
            "hook_text": "Error", 
            "social_caption": "Error"
        }]

def process_video_cut(video_id: str, url: str, start: int, end: int):
    video_path = os.path.join(TEMP_DIR, f"{video_id}_full.mp4")
    output_path = os.path.join(TEMP_DIR, f"{video_id}_clip_{start}_{end}.mp4")
    cookie_file = setup_cookies()

    if not os.path.exists(video_path):
        print("Downloading source video...")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(TEMP_DIR, f"{video_id}_full.%(ext)s"),
            'merge_output_format': 'mp4',
            'quiet': True,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    
    if not os.path.exists(output_path):
        ffmpeg_extract_subclip(video_path, start, end, targetname=output_path)
    
    return output_path