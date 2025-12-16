from pydantic import BaseModel
from typing import List, Optional

class VideoRequest(BaseModel):
    url: str

class Clip(BaseModel):
    id: int
    title: str
    start: int
    end: int
    reason: str

class AnalysisResponse(BaseModel):
    video_id: str
    video_title: str
    full_text_preview: str
    clips: List[Clip]