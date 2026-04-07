from pydantic import BaseModel


class IndustryOut(BaseModel):
    id: str
    name: str
    slug: str

    model_config = {"from_attributes": True}
