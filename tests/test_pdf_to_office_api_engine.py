"""對外 API /tools/pdf-to-office/convert 的引擎參數與 meta 測試。

驗端點接受/正規化 engine 參數並把它記進 job.meta（提交當下即可驗）。

為避免污染共用 job_manager 的 thread pool（真實轉換很慢且在無 soffice 的
CI/開發機上會失敗、占用 worker 導致其他 job 測試逾時），這裡 monkeypatch
`convert_pdf_to_office` 與 preview 產圖成即時 stub，讓 job 秒完成。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.job_manager import job_manager
from app.main import app

_MINI_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def _fast_convert(monkeypatch):
    """讓 /convert 的背景 run() 秒完成，不真的跑 pdf2docx / soffice。"""
    import sys
    import app.tools.pdf_to_office.service  # noqa: F401  ensure module loaded
    import app.tools.pdf_to_office.router   # noqa: F401  ensure module loaded
    # 套件 __init__ 把 `router` 名稱重綁到 APIRouter 實例，故須由 sys.modules
    # 取真正的模組物件來 patch 模組層級函式。
    svc = sys.modules["app.tools.pdf_to_office.service"]
    rtr = sys.modules["app.tools.pdf_to_office.router"]

    def fake_convert(src, work_dir, fmt, *, enable_postprocess=False, engine="pdf2docx-refine"):
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        out = work_dir / ("final.odt" if fmt == "odt" else "final.docx")
        out.write_bytes(b"stub")
        return svc.ConvertResult(
            ok=True, output_path=out, output_format=fmt,
            engine_used=engine, postprocess_done=enable_postprocess, report={},
        )

    monkeypatch.setattr(svc, "convert_pdf_to_office", fake_convert)
    monkeypatch.setattr(rtr, "_generate_preview_pngs", lambda *a, **k: {})


def _post(engine: str | None = None, output_format: str = "docx"):
    client = TestClient(app)
    data = {"output_format": output_format}
    if engine is not None:
        data["engine"] = engine
    return client.post(
        "/tools/pdf-to-office/convert",
        files={"file": ("doc.pdf", _MINI_PDF, "application/pdf")},
        data=data,
    )


def test_convert_default_engine_is_pdf2docx_refine():
    r = _post(engine=None)
    assert r.status_code == 200
    jid = r.json()["job_id"]
    job = job_manager.get(jid)
    assert job is not None
    assert job.meta["engine"] == "pdf2docx-refine"


def test_convert_accepts_jtdt_reform():
    r = _post(engine="jtdt-reform")
    assert r.status_code == 200
    job = job_manager.get(r.json()["job_id"])
    assert job.meta["engine"] == "jtdt-reform"


def test_convert_legacy_alias_normalizes_to_jtdt_reform():
    for alias in ("jtdt-native", "jtreform"):
        r = _post(engine=alias)
        assert r.status_code == 200
        job = job_manager.get(r.json()["job_id"])
        assert job.meta["engine"] == "jtdt-reform"


def test_convert_unknown_engine_falls_back_to_default():
    r = _post(engine="bogus-engine")
    assert r.status_code == 200
    job = job_manager.get(r.json()["job_id"])
    assert job.meta["engine"] == "pdf2docx-refine"


def test_convert_rejects_non_pdf_extension():
    client = TestClient(app)
    r = client.post(
        "/tools/pdf-to-office/convert",
        files={"file": ("doc.txt", _MINI_PDF, "text/plain")},
        data={"output_format": "docx"},
    )
    assert r.status_code == 400


def test_convert_rejects_bad_output_format():
    r = _post(engine="jtdt-reform", output_format="xlsx")
    assert r.status_code == 400
