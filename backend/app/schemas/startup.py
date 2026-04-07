from pydantic import BaseModel

from app.schemas.industry import IndustryOut


class StartupCard(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    website_url: str | None
    logo_url: str | None
    stage: str
    location_city: str | None
    location_state: str | None
    location_country: str
    ai_score: float | None
    expert_score: float | None
    user_score: float | None
    industries: list[IndustryOut]

    model_config = {"from_attributes": True}


class MediaOut(BaseModel):
    id: str
    url: str
    title: str
    source: str
    media_type: str
    published_at: str | None

    model_config = {"from_attributes": True}


class ScoreHistoryOut(BaseModel):
    score_type: str
    score_value: float
    dimensions_json: dict | None
    recorded_at: str

    model_config = {"from_attributes": True}


class StartupDetail(StartupCard):
    founded_date: str | None
    media: list[MediaOut]
    score_history: list[ScoreHistoryOut]
