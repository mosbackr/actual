import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.dataroom import DataroomDocument, DataroomRequest, DataroomSectionReview, DataroomStatus
from app.models.notification import Notification, NotificationType
from app.models.pitch_analysis import AnalysisDocument, AnalysisStatus, PitchAnalysis
from app.models.user import User
from app.services import email_service, s3

logger = logging.getLogger(__name__)

SECTION_PROMPTS = {
    "corporate": (
        "You are a VC due diligence analyst reviewing corporate documents. "
        "Evaluate the corporate structure, cap table health, and governance. "
        "Flag any red flags in equity distribution, vesting schedules, or corporate governance gaps. "
        "Assess whether the corporate structure is suitable for venture financing."
    ),
    "financials": (
        "You are a VC due diligence analyst reviewing financial documents. "
        "Analyze the financial statements for revenue consistency, burn rate sustainability, and projection realism. "
        "Identify discrepancies between historical data and projections. "
        "Evaluate unit economics, runway, and financial health."
    ),
    "fundraising": (
        "You are a VC due diligence analyst reviewing fundraising materials. "
        "Assess the pitch and fundraising materials for clarity, compelling narrative, valuation justification, "
        "and use of funds specificity. Evaluate how well the materials tell the company story."
    ),
    "product": (
        "You are a VC due diligence analyst reviewing product and technical documents. "
        "Review technical architecture, product maturity, and roadmap feasibility. "
        "Assess the technology readiness level (TRL 1-9) and identify technical risks. "
        "Evaluate defensibility of the technical approach."
    ),
    "legal": (
        "You are a VC due diligence analyst reviewing legal documents. "
        "Evaluate IP protection strength, identify material contract risks, "
        "check for compliance gaps, and flag any concerning employment agreement terms. "
        "Assess overall legal readiness for investment."
    ),
    "team": (
        "You are a VC due diligence analyst reviewing team documents. "
        "Evaluate founder backgrounds against the company's domain, assess team completeness "
        "for the current stage, and evaluate advisory board relevance. "
        "Identify any key hiring gaps."
    ),
}

CUSTOM_CRITERIA_PROMPT = (
    "You are a VC due diligence analyst. Evaluate the following dataroom documents "
    "against this specific criterion:\n\n{criteria}\n\n"
    "Provide a thorough evaluation focused specifically on this criterion."
)

REVIEW_OUTPUT_FORMAT = """
Return ONLY a JSON object with these fields:
{
  "score": <number 0-100>,
  "summary": "<2-3 sentence summary of findings>",
  "findings": {
    "strengths": ["<strength 1>", "<strength 2>"],
    "concerns": ["<concern 1>", "<concern 2>"],
    "missing": ["<missing item 1>", "<missing item 2>"],
    "recommendation": "<1-2 sentence recommendation>"
  }
}
"""


async def _extract_document_text(doc: DataroomDocument) -> str:
    """Download a document from S3 and extract text content."""
    try:
        data = s3.download_file(doc.s3_key)
        if doc.file_type in ("txt", "md", "csv"):
            return data.decode("utf-8", errors="replace")[:50000]
        return data.decode("utf-8", errors="replace")[:50000]
    except Exception as e:
        logger.warning(f"Failed to extract text from {doc.original_filename}: {e}")
        return f"[Could not extract text from {doc.original_filename}]"


async def _run_section_review(
    dataroom_request_id: uuid.UUID,
    section: str,
    documents: list[DataroomDocument],
    system_prompt: str,
    criteria_description: str | None = None,
) -> None:
    """Run AI review for a single section or custom criterion."""
    async with async_session() as db:
        review = DataroomSectionReview(
            dataroom_request_id=dataroom_request_id,
            section=section,
            criteria_description=criteria_description,
            status="pending",
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)

        try:
            doc_texts = []
            for doc in documents:
                text = await _extract_document_text(doc)
                doc_texts.append(f"--- {doc.original_filename} ({doc.file_type}) ---\n{text}")

            documents_content = "\n\n".join(doc_texts)

            user_msg = f"Review the following documents:\n\n{documents_content}\n\n{REVIEW_OUTPUT_FORMAT}"

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 2000,
                        "temperature": 0.1,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_msg}],
                    },
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]

            parsed = _parse_json_response(content)

            review.score = parsed.get("score")
            review.summary = parsed.get("summary")
            review.findings = parsed.get("findings")
            review.status = "complete"

        except Exception as e:
            logger.error(f"Section review failed for {section}: {e}")
            review.status = "failed"
            review.summary = f"Review failed: {str(e)[:200]}"

        await db.commit()


def _parse_json_response(content: str) -> dict:
    """Parse JSON from Claude response, handling fenced and bare JSON."""
    try:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if m:
            return json.loads(m.group(1))
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            raw = content[start:end + 1]
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            return json.loads(raw)
    except json.JSONDecodeError:
        pass
    return {"score": None, "summary": content[:500], "findings": {}}


async def run_dataroom_analysis(dataroom_request_id: str) -> None:
    """Main entry point: run pitch analysis + section reviews + custom criteria."""
    async with async_session() as db:
        request = await db.get(DataroomRequest, uuid.UUID(dataroom_request_id))
        if not request:
            logger.error(f"Dataroom request {dataroom_request_id} not found")
            return

        request.status = DataroomStatus.analyzing
        await db.commit()

        # Load all documents
        doc_result = await db.execute(
            select(DataroomDocument)
            .where(DataroomDocument.dataroom_request_id == request.id)
            .order_by(DataroomDocument.section, DataroomDocument.created_at)
        )
        all_docs = doc_result.scalars().all()

        # Group documents by section
        docs_by_section: dict[str, list[DataroomDocument]] = {}
        for doc in all_docs:
            docs_by_section.setdefault(doc.section, []).append(doc)

        # Create PitchAnalysis record
        company_name = request.company_name or "Unknown Company"
        analysis = PitchAnalysis(
            user_id=request.investor_id,
            company_name=company_name,
            status=AnalysisStatus.pending,
        )
        db.add(analysis)
        await db.flush()

        # Copy documents as AnalysisDocuments
        for doc in all_docs:
            analysis_doc = AnalysisDocument(
                analysis_id=analysis.id,
                filename=doc.original_filename,
                file_type=doc.file_type,
                s3_key=doc.s3_key,
                file_size_bytes=doc.file_size_bytes,
            )
            db.add(analysis_doc)

        request.analysis_id = analysis.id
        await db.commit()

    # Run section reviews in parallel
    review_tasks = []
    for section, docs in docs_by_section.items():
        prompt = SECTION_PROMPTS.get(section)
        if prompt:
            review_tasks.append(
                _run_section_review(request.id, section, docs, prompt)
            )

    # Run custom criteria reviews
    if request.custom_criteria:
        for criterion in request.custom_criteria:
            desc = criterion.get("description", "")
            if desc:
                prompt = CUSTOM_CRITERIA_PROMPT.format(criteria=desc)
                review_tasks.append(
                    _run_section_review(
                        request.id, "custom", all_docs, prompt, criteria_description=desc
                    )
                )

    # Run all reviews concurrently
    if review_tasks:
        await asyncio.gather(*review_tasks, return_exceptions=True)

    # Trigger pitch analysis pipeline (worker picks up pending PitchAnalysis records,
    # but we can also run it directly for immediate processing)
    try:
        from app.services.analysis_worker import _process_job
        await _process_job(analysis.id)
    except Exception as e:
        logger.error(f"Pitch analysis failed for dataroom {dataroom_request_id}: {e}")

    # Mark complete and notify
    async with async_session() as db:
        request = await db.get(DataroomRequest, uuid.UUID(dataroom_request_id))
        if request:
            request.status = DataroomStatus.complete
            await db.commit()

        investor = await db.get(User, request.investor_id)

        notification = Notification(
            user_id=request.investor_id,
            type=NotificationType.dataroom_complete,
            title="Dataroom analysis complete",
            message=f"The analysis for {request.company_name or 'the dataroom'} is ready",
            link=f"/datarooms/{request.id}",
        )
        db.add(notification)
        await db.commit()

        if investor:
            email_service.send_dataroom_complete(
                investor_email=investor.email,
                investor_name=investor.name,
                company_name=request.company_name,
                dataroom_id=str(request.id),
            )

    logger.info(f"Dataroom analysis complete for {dataroom_request_id}")
