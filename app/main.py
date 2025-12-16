from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from .models import VideoRequest, AnalysisResponse
from .services import download_audio, transcribe_with_chutes, analyze_with_llama, process_video_cut
import uuid
import os

app = FastAPI(title="AI Video Clipper API")

# Setup CORS agar bisa diakses Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Ganti dengan domain frontend saat production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simpan mapping URL sementara (sebaiknya gunakan Database Redis/SQL di production)
# Format: {video_id: url_asli}
url_store = {} 

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_endpoint(req: VideoRequest):
    video_id = str(uuid.uuid4())[:8]
    url_store[video_id] = req.url # Simpan URL asli untuk keperluan download nanti
    
    try:
        # 1. Download Audio
        audio_file, title = await download_audio(req.url, video_id)
        
        # 2. Transcribe
        transcript = await transcribe_with_chutes(audio_file)
        
        # 3. AI Analysis
        clips = await analyze_with_llama(transcript)
        
        # Cleanup Audio (Hemat storage)
        if os.path.exists(audio_file):
            os.remove(audio_file)

        return AnalysisResponse(
            video_id=video_id,
            video_title=title,
            full_text_preview=transcript[:200] + "...",
            clips=clips
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{video_id}")
async def download_endpoint(video_id: str, start: int, end: int, background_tasks: BackgroundTasks):
    url = url_store.get(video_id)
    if not url:
        raise HTTPException(status_code=404, detail="Session expired or ID invalid")
        
    try:
        # Logic pemotongan (termasuk download video master jika belum ada)
        clip_path = process_video_cut(video_id, url, start, end)
        
        # Kirim file ke user
        return FileResponse(
            clip_path, 
            media_type="video/mp4", 
            filename=f"clip_{video_id}_{start}_{end}.mp4"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def health_check():
    return {"status": "Server running", "tech": "FastAPI + Chutes.ai"}