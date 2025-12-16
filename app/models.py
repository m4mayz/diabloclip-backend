from pydantic import BaseModel
from typing import List

class VideoRequest(BaseModel):
    url: str

class Clip(BaseModel):
    id: int
    title: str
    start: int
    end: int
    reason: str             # Kenapa bagus
    highlight_quote: str    # Kalimat penting/moment
    hook_text: str          # Text on screen
    social_caption: str     # Caption pendek (Max 5 kata)

class AnalysisResponse(BaseModel):
    video_id: str
    video_title: str
    full_text_preview: str
    clips: List[Clip]