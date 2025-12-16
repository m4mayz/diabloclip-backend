import os
import json
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

# --- UTILS: COOKIES HANDLING ---
def setup_cookies():
    """
    Menyiapkan file cookies.txt untuk yt-dlp.
    Decode dari ENV 'YOUTUBE_COOKIES' (Base64) ke file fisik.
    """
    cookie_filename = "cookies.txt"
    
    # Cek Environment Variable (Prioritas Production)
    env_cookies = os.getenv("YOUTUBE_COOKIES")
    if env_cookies:
        try:
            decoded_cookies = base64.b64decode(env_cookies).decode('utf-8')
            with open(cookie_filename, "w") as f:
                f.write(decoded_cookies)
            return cookie_filename
        except Exception as e:
            print(f"Gagal decode cookies dari Env: {e}")
            return None

    # Fallback: Cek file lokal (Dev Mode)
    if os.path.exists(cookie_filename):
        return cookie_filename
        
    return None

# --- CORE FUNCTIONS ---

async def download_audio(url: str, video_id: str):
    """Download audio saja untuk transkripsi"""
    output_path = os.path.join(TEMP_DIR, video_id)
    cookie_file = setup_cookies()
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': output_path, # yt-dlp akan tambah .mp3 otomatis
        'quiet': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return f"{output_path}.mp3", info.get('title', 'Unknown Video')

async def transcribe_with_chutes(audio_path: str):
    """Transkripsi Audio -> Text menggunakan Whisper V3"""
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
    """Analisis Viralitas menggunakan Llama 3"""
    system_prompt = """
    You are an expert viral video editor. Analyze the transcript and extract 3-5 clips (15s-60s) with high viral potential.
    
    CONSTRAINTS:
    1. Output MUST be RAW JSON Array. No markdown.
    2. Language: Indonesian (Bahasa Indonesia).
    
    REQUIRED JSON FIELDS:
    - "id": integer
    - "title": string (Catchy title)
    - "start": integer (Start seconds)
    - "end": integer (End seconds)
    - "reason": string (Why is it viral?)
    - "highlight_quote": string (Key sentence)
    - "hook_text": string (Text for video overlay)
    - "social_caption": string (Max 5 words for caption)
    """
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:15000]} # Limit karakter
            ],
            temperature=0.7
        )
        content = response.choices[0].message.content
        # Bersihkan format markdown jika ada
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        print(f"AI Error: {e}")
        # Return dummy data agar tidak crash
        return [{
            "id": 0, "title": "Gagal Analisis AI", 
            "start": 0, "end": 10, 
            "reason": str(e), 
            "highlight_quote": "-", 
            "hook_text": "Error", 
            "social_caption": "Error"
        }]

def process_video_cut(video_id: str, url: str, start: int, end: int):
    """Download video full (jika perlu) lalu potong"""
    # Pastikan nama file output full video konsisten (.mp4)
    video_path = os.path.join(TEMP_DIR, f"{video_id}_full.mp4")
    output_path = os.path.join(TEMP_DIR, f"{video_id}_clip_{start}_{end}.mp4")
    cookie_file = setup_cookies()

    # 1. Download Master Video (Jika belum ada)
    if not os.path.exists(video_path):
        print("Downloading source video...")
        ydl_opts = {
            # Mengambil kualitas terbaik apapun formatnya (webm/mkv/mp4)
            'format': 'bestvideo+bestaudio/best', 
            # Paksa konversi ke MP4 agar kompatibel dengan editor
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(TEMP_DIR, f"{video_id}_full.%(ext)s"),
            'quiet': True,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    
    # 2. Potong Video
    if not os.path.exists(output_path):
        ffmpeg_extract_subclip(video_path, start, end, targetname=output_path)
    
    return output_path