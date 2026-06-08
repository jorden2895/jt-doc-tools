"""pdf-watermark 逐檔順序上傳（issue #27）。

大批次（50-80 份）一次塞進單一 multipart 會撞反向代理 / 伺服器 body 上限而
靜默失敗。改成 create → 逐檔 add（每請求一個小 PDF）→ process。
"""
from __future__ import annotations

import io
import json
import time
import zipfile


def _pdf(idx: int) -> bytes:
    import fitz
    d = fitz.open()
    pg = d.new_page(width=595, height=842)
    pg.insert_text((72, 100), f"doc {idx}")
    b = d.tobytes()
    d.close()
    return b


def _wait(client, job_id, timeout=60):
    for _ in range(timeout * 2):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j.get("status") in ("done", "error", "failed"):
            return j
        time.sleep(0.5)
    return {"status": "timeout"}


def test_batch_create_add_process(client):
    # 1) create（文字浮水印，不需 asset）
    r = client.post("/tools/pdf-watermark/batch/create", data={
        "params": json.dumps({"text": "機密", "mode": "tile", "opacity": 30}),
        "page_mode": "all",
    })
    assert r.status_code == 200, r.text
    batch_id = r.json()["batch_id"]
    assert len(batch_id) == 32

    # 2) 逐檔 add
    n = 15
    for i in range(n):
        ar = client.post(
            f"/tools/pdf-watermark/batch/{batch_id}/add",
            files={"file": (f"doc_{i:03d}.pdf", io.BytesIO(_pdf(i)), "application/pdf")},
            data={"index": str(i)},
        )
        assert ar.status_code == 200, (i, ar.text)

    # 3) process → job → ZIP 內應有 n 份
    pr = client.post(f"/tools/pdf-watermark/batch/{batch_id}/process")
    assert pr.status_code == 200, pr.text
    j = _wait(client, pr.json()["job_id"])
    assert j["status"] == "done", j
    dl = client.get(f"/api/jobs/{pr.json()['job_id']}/download")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK", "應為 ZIP"
    with zipfile.ZipFile(io.BytesIO(dl.content)) as z:
        assert len(z.namelist()) == n


def test_batch_invalid_id_rejected(client):
    # 非 32-hex 的 batch_id → 400（防 path traversal / 亂打）
    r = client.post("/tools/pdf-watermark/batch/..%2f..%2fetc/add",
                    files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                    data={"index": "0"})
    assert r.status_code in (400, 404)
    r2 = client.post("/tools/pdf-watermark/batch/zzz/process")
    assert r2.status_code == 400


def test_batch_unknown_id_410(client):
    # 合法格式但不存在的 batch → 410（已過期）
    fake = "a" * 32
    r = client.post(f"/tools/pdf-watermark/batch/{fake}/process")
    assert r.status_code == 410


def test_batch_add_rejects_non_pdf(client):
    r = client.post("/tools/pdf-watermark/batch/create", data={
        "params": json.dumps({"text": "X", "mode": "tile"}), "page_mode": "all"})
    bid = r.json()["batch_id"]
    ar = client.post(f"/tools/pdf-watermark/batch/{bid}/add",
                     files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
                     data={"index": "0"})
    assert ar.status_code == 400
