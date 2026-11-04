"""Data models. Pydantic validates everything the LLM returns."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Region = Literal["tamilnadu", "india"]


class Article(BaseModel):
    title: str
    link: str
    source: str = ""
    published: Optional[datetime] = None
    summary: str = ""
    region: Region


class Pick(BaseModel):
    """One LLM selection. `index` points back to the candidate list,
    so the model can never invent a link or source."""

    index: int
    headline: str = Field(description="Rewritten headline, max 8 words")
    summary: str = Field(description="One factual sentence, max 25 words")
    score: int = Field(ge=1, le=10)


class RankingResponse(BaseModel):
    picks: list[Pick]


class Story(BaseModel):
    """Final, validated story used by later stages (script, image, video)."""

    rank: int
    region: Region
    headline: str
    summary: str
    score: int
    source: str
    link: str


# ---- Stage 3: video script ----
class Scene(BaseModel):
    kind: Literal["hook", "story", "outro"]
    story_index: Optional[int] = None  # index into the stories chosen for the video
    narration: str  # what the voice says
    on_screen: str  # short text shown on the video
    estimated_seconds: float = 0.0  # computed in code, never trusted from the LLM


class ScriptDraft(BaseModel):
    """What the LLM returns."""

    scenes: list[Scene]
    caption_intro: str
    hashtags: list[str]


class VideoScript(BaseModel):
    """Final script used by the voice, image and video stages."""

    date: str
    scenes: list[Scene]
    caption: str
    hashtags: list[str]
    total_seconds: float


# ---- V2: visuals ----
class VisualItem(BaseModel):
    index: int
    queries: list[str]


class VisualPlan(BaseModel):
    items: list[VisualItem]
