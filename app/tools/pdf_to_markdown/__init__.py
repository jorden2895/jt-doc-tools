"""PDF → Markdown: convert PDF to GitHub-flavored Markdown via pymupdf4llm.

Suited for: technical manuals, reports, government documents, academic papers
            (anything where the layout is mostly flowing text with headings).
Not suited: forms with many small cells, slides/presentations, multi-column
            magazines (use pdf-extract-text / pdf-to-office instead).
"""
from pathlib import Path

from ..base import ToolMetadata, ToolModule
from .router import router

metadata = ToolMetadata(
    id="pdf-to-markdown",
    name="PDF 轉 Markdown",
    description="PDF 轉結構化 Markdown，保留標題 / 表格 / 粗體，適合餵 LLM、RAG 預處理。",
    icon="paragraph",
    category="格式轉換",
)

tool = ToolModule(
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).resolve().parent / "templates",
)
