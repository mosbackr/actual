from pydantic import BaseModel


class PaginatedParams(BaseModel):
    page: int = 1
    per_page: int = 20


class PaginatedResponse(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int
