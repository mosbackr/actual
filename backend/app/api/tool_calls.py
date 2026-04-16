import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.pitch_analysis import PitchAnalysis
from app.models.tool_call import ToolCall
from app.models.user import User

router = APIRouter()


@router.get("/api/analyze/{analysis_id}/tool-calls")
async def get_tool_calls(
    analysis_id: uuid.UUID,
    since: datetime | None = Query(None, description="Only return tool calls after this timestamp"),
    include_output: bool = Query(False, description="Include full output in response"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify user owns this analysis
    result = await db.execute(
        select(PitchAnalysis).where(
            PitchAnalysis.id == analysis_id,
            PitchAnalysis.user_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Analysis not found")

    query = select(ToolCall).where(
        ToolCall.analysis_id == analysis_id
    ).order_by(ToolCall.created_at.asc())

    if since:
        query = query.where(ToolCall.created_at > since)

    result = await db.execute(query)
    tool_calls = result.scalars().all()

    items = []
    for tc in tool_calls:
        item = {
            "id": str(tc.id),
            "agent_type": tc.agent_type,
            "tool_name": tc.tool_name,
            "input": tc.input,
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "duration_ms": tc.duration_ms,
        }
        if include_output:
            item["output"] = tc.output
        items.append(item)

    return {"tool_calls": items}
