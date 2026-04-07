from pydantic import BaseModel


class ExpertApplicationIn(BaseModel):
    bio: str
    years_experience: int
    industry_ids: list[str]
    skill_ids: list[str]


class ExpertApplicationOut(BaseModel):
    id: str
    bio: str
    years_experience: int
    application_status: str
    industries: list[str]
    skills: list[str]
    created_at: str
