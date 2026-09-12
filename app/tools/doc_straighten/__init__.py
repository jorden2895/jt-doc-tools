"""文件拉正 —— 拍歪 / 掃歪的文件拉正、裁邊、去除不勻底色。"""
from pathlib import Path

from ..base import ToolMetadata, ToolModule
from .router import router

metadata = ToolMetadata(
    id="doc-straighten",
    name="文件拉正",
    description="把拍歪、掃歪的文件拉正，裁掉黑邊、去除不勻的底色，"
                "輸出端正的 PDF。收 PDF、手機拍的照片與文書檔。",
    icon="crop",
    category="檔案編輯",
)

tool = ToolModule(
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).resolve().parent / "templates",
)
