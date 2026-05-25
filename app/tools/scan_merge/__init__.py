"""掃描拼合：拉入多張掃描（PDF / PNG / JPG），自動抓出有內容的區塊，
依原位置保留原彩色合成到同一張 A4 白底 PDF。主打證件正反面。"""
from pathlib import Path

from ..base import ToolMetadata, ToolModule
from .router import router

metadata = ToolMetadata(
    id="scan-merge",
    name="掃描拼合",
    description="把證件正反面等多張掃描，依原位置、原彩色合成到同一張 A4 白底。",
    icon="credit-card",
    category="檔案編輯",
)

tool = ToolModule(
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).resolve().parent / "templates",
)
