"""Report generation for the AI analyst.

Generates Word (.docx) and Excel (.xlsx) reports from conversation data.
Charts are rendered as images via matplotlib.
"""

import io
import logging
import uuid
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.analyst import AnalystConversation, AnalystMessage, AnalystReport, ReportGenStatus
from app.services import s3

logger = logging.getLogger(__name__)

CHART_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"]


def _render_chart_image(chart_config: dict) -> bytes | None:
    """Render a chart config dict to a PNG image using matplotlib."""
    try:
        chart_type = chart_config.get("type", "bar")
        data = chart_config.get("data", [])
        title = chart_config.get("title", "")
        x_key = chart_config.get("xKey", chart_config.get("nameKey", "name"))
        y_keys = chart_config.get("yKeys", [chart_config.get("dataKey", "value")])
        colors = chart_config.get("colors", CHART_COLORS)

        if not data:
            return None

        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#a0a0b0")
        ax.xaxis.label.set_color("#a0a0b0")
        ax.yaxis.label.set_color("#a0a0b0")
        ax.title.set_color("#e0e0e8")
        for spine in ax.spines.values():
            spine.set_color("#2a2a3e")

        labels = [str(d.get(x_key, "")) for d in data]

        if chart_type == "pie":
            data_key = y_keys[0] if y_keys else "value"
            values = [d.get(data_key, 0) for d in data]
            ax.pie(values, labels=labels, colors=colors[:len(values)], autopct="%1.1f%%",
                   textprops={"color": "#e0e0e8"})
        elif chart_type == "scatter":
            for i, yk in enumerate(y_keys):
                x_vals = [d.get(x_key, 0) for d in data]
                y_vals = [d.get(yk, 0) for d in data]
                ax.scatter(x_vals, y_vals, color=colors[i % len(colors)], label=yk, alpha=0.7)
            ax.legend(facecolor="#1a1a2e", edgecolor="#2a2a3e", labelcolor="#a0a0b0")
        else:
            x = range(len(labels))
            width = 0.8 / len(y_keys) if chart_type == "bar" else 0

            for i, yk in enumerate(y_keys):
                values = [d.get(yk, 0) for d in data]
                color = colors[i % len(colors)]

                if chart_type == "bar":
                    offset = (i - len(y_keys) / 2 + 0.5) * width
                    ax.bar([xi + offset for xi in x], values, width=width, color=color, label=yk)
                elif chart_type == "line":
                    ax.plot(x, values, color=color, label=yk, marker="o", markersize=4)
                elif chart_type == "area":
                    ax.fill_between(x, values, color=color, alpha=0.3, label=yk)
                    ax.plot(x, values, color=color)

            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
            if len(y_keys) > 1:
                ax.legend(facecolor="#1a1a2e", edgecolor="#2a2a3e", labelcolor="#a0a0b0")

        ax.set_title(title, fontsize=12, pad=10)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.warning("Chart rendering failed: %s", e)
        plt.close("all")
        return None


def _generate_docx(conversation: AnalystConversation, messages: list[AnalystMessage], title: str) -> bytes:
    """Generate a Word document from conversation data."""
    doc = Document()

    # Cover page
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Deep Thesis Analyst Report")
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(99, 102, 241)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.font.size = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(datetime.now(timezone.utc).strftime("%B %d, %Y"))
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_page_break()

    # Conversation content
    for msg in messages:
        if msg.role == "user" or (hasattr(msg.role, "value") and msg.role.value == "user"):
            doc.add_heading(msg.content[:100], level=2)
        else:
            # Assistant response as body text
            for paragraph_text in msg.content.split("\n\n"):
                paragraph_text = paragraph_text.strip()
                if not paragraph_text:
                    continue
                if paragraph_text.startswith("# "):
                    doc.add_heading(paragraph_text[2:], level=2)
                elif paragraph_text.startswith("## "):
                    doc.add_heading(paragraph_text[3:], level=3)
                elif paragraph_text.startswith("- "):
                    for line in paragraph_text.split("\n"):
                        if line.strip().startswith("- "):
                            doc.add_paragraph(line.strip()[2:], style="List Bullet")
                else:
                    doc.add_paragraph(paragraph_text)

            # Render charts as images
            if msg.charts:
                for chart_config in msg.charts:
                    img_bytes = _render_chart_image(chart_config)
                    if img_bytes:
                        buf = io.BytesIO(img_bytes)
                        doc.add_picture(buf, width=Inches(6))
                        cap = doc.add_paragraph(chart_config.get("title", ""))
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap.style = doc.styles["Caption"] if "Caption" in [s.name for s in doc.styles] else None

    # Citations
    all_citations = []
    for msg in messages:
        if msg.citations:
            all_citations.extend(msg.citations)

    if all_citations:
        doc.add_page_break()
        doc.add_heading("Sources", level=1)
        for i, cite in enumerate(all_citations, 1):
            url = cite.get("url", "") if isinstance(cite, dict) else str(cite)
            title_text = cite.get("title", url) if isinstance(cite, dict) else str(cite)
            doc.add_paragraph(f"{i}. {title_text}\n   {url}", style="List Number")

    # Footer
    section = doc.sections[0]
    footer = section.footer
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_para.add_run("Generated by Deep Thesis AI Analyst")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(128, 128, 128)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _generate_xlsx(conversation: AnalystConversation, messages: list[AnalystMessage], title: str) -> bytes:
    """Generate an Excel workbook from conversation data."""
    wb = Workbook()

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Deep Thesis Analyst Report"])
    ws.append([title])
    ws.append([datetime.now(timezone.utc).strftime("%B %d, %Y")])
    ws.append([])
    ws.append(["Question", "Response Summary"])

    for msg in messages:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        if role == "user":
            ws.append([msg.content[:200]])
        elif role == "assistant":
            ws.append(["", msg.content[:500]])

    # Data sheets — one per chart
    chart_num = 0
    for msg in messages:
        if not msg.charts:
            continue
        for chart_config in msg.charts:
            chart_num += 1
            chart_title = chart_config.get("title", f"Chart {chart_num}")
            sheet_name = f"Data {chart_num}"[:31]  # Excel 31-char limit
            ws_data = wb.create_sheet(title=sheet_name)

            data = chart_config.get("data", [])
            if not data:
                continue

            # Headers
            headers = list(data[0].keys())
            ws_data.append(headers)

            # Rows
            for row in data:
                ws_data.append([row.get(h) for h in headers])

            # Add chart
            x_key = chart_config.get("xKey", chart_config.get("nameKey", headers[0]))
            y_keys = chart_config.get("yKeys", [chart_config.get("dataKey")])
            chart_type = chart_config.get("type", "bar")

            try:
                x_col = headers.index(x_key) + 1 if x_key in headers else 1
                chart_obj = None

                if chart_type == "pie":
                    chart_obj = PieChart()
                    data_col = headers.index(y_keys[0]) + 1 if y_keys and y_keys[0] in headers else 2
                    chart_obj.add_data(
                        Reference(ws_data, min_col=data_col, min_row=1, max_row=len(data) + 1),
                        titles_from_data=True,
                    )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )
                elif chart_type in ("line", "area"):
                    chart_obj = LineChart()
                    for yk in y_keys:
                        if yk in headers:
                            col = headers.index(yk) + 1
                            chart_obj.add_data(
                                Reference(ws_data, min_col=col, min_row=1, max_row=len(data) + 1),
                                titles_from_data=True,
                            )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )
                else:
                    chart_obj = BarChart()
                    for yk in y_keys:
                        if yk in headers:
                            col = headers.index(yk) + 1
                            chart_obj.add_data(
                                Reference(ws_data, min_col=col, min_row=1, max_row=len(data) + 1),
                                titles_from_data=True,
                            )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )

                if chart_obj:
                    chart_obj.title = chart_title
                    chart_obj.width = 20
                    chart_obj.height = 12
                    ws_data.add_chart(chart_obj, f"A{len(data) + 4}")
            except Exception as e:
                logger.warning("Excel chart creation failed: %s", e)

    # Sources sheet
    all_citations = []
    for msg in messages:
        if msg.citations:
            all_citations.extend(msg.citations)

    if all_citations:
        ws_sources = wb.create_sheet(title="Sources")
        ws_sources.append(["#", "Title", "URL"])
        for i, cite in enumerate(all_citations, 1):
            url = cite.get("url", "") if isinstance(cite, dict) else str(cite)
            cite_title = cite.get("title", url) if isinstance(cite, dict) else str(cite)
            ws_sources.append([i, cite_title, url])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


async def generate_report(report_id: str) -> None:
    """Generate a report (background task). Updates status in DB and uploads to S3."""
    rid = uuid.UUID(report_id)

    async with async_session() as db:
        try:
            # Load report with conversation and messages
            result = await db.execute(
                select(AnalystReport).where(AnalystReport.id == rid)
            )
            report = result.scalar_one_or_none()
            if not report:
                logger.error("Report %s not found", report_id)
                return

            report.status = ReportGenStatus.generating
            await db.commit()

            # Load conversation with messages
            result = await db.execute(
                select(AnalystConversation)
                .where(AnalystConversation.id == report.conversation_id)
                .options(selectinload(AnalystConversation.messages))
            )
            conversation = result.scalar_one()
            messages = list(conversation.messages)

            # Generate document
            fmt = report.format.value if hasattr(report.format, "value") else report.format
            if fmt == "docx":
                file_bytes = _generate_docx(conversation, messages, report.title)
                ext = "docx"
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                file_bytes = _generate_xlsx(conversation, messages, report.title)
                ext = "xlsx"
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            # Upload to S3
            s3_key = f"analyst-reports/{conversation.id}/{report.id}/report.{ext}"
            s3.upload_file(file_bytes, s3_key)

            report.s3_key = s3_key
            report.file_size_bytes = len(file_bytes)
            report.status = ReportGenStatus.complete
            await db.commit()

            logger.info("Report %s generated: %s (%d bytes)", report_id, s3_key, len(file_bytes))

        except Exception as e:
            logger.error("Report generation failed for %s: %s", report_id, e)
            try:
                report.status = ReportGenStatus.failed
                report.error = str(e)[:500]
                await db.commit()
            except Exception:
                logger.error("Failed to update report status for %s", report_id)
