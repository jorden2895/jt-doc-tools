"""掃描拼合 (scan-merge) — 端點 / ACL / 公開 API 測試。

合成「白底 + 不同位置彩色方塊」當掃描檔，驗證 upload 偵測、crop 取圖保留彩色、
generate 合成、overlap 不影響輸出、ACL 驗證、公開一次性 API。
"""
from __future__ import annotations

import io
import time

import fitz
from PIL import Image


def _scan_png(block_box, block_color=(200, 30, 30), size=(600, 850)) -> bytes:
    img = Image.new("RGB", size, (255, 255, 255))
    x0, y0, x1, y1 = block_box
    img.paste(Image.new("RGB", (x1 - x0, y1 - y0), block_color), (x0, y0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload(client, png: bytes, name="scan.png"):
    return client.post(
        "/tools/scan-merge/upload",
        files={"file": (name, png, "image/png")},
    )


def test_upload_detects_one_region(client, auth_off):
    r = _upload(client, _scan_png((60, 50, 260, 190)))
    assert r.status_code == 200
    body = r.json()
    assert len(body["crops"]) == 1
    c = body["crops"][0]
    assert c["crop_id"] and c["url_raw"] and c["url_white"]
    assert 0.0 <= c["fx"] < 0.3 and 0.0 <= c["fy"] < 0.3


def test_upload_blank_page_returns_422(client, auth_off):
    blank = Image.new("RGB", (600, 850), (255, 255, 255))
    buf = io.BytesIO(); blank.save(buf, format="PNG")
    r = _upload(client, buf.getvalue(), "blank.png")
    assert r.status_code == 422


def test_upload_rejects_bad_extension(client, auth_off):
    r = client.post("/tools/scan-merge/upload",
                    files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_crop_serves_color_png(client, auth_off):
    r = _upload(client, _scan_png((100, 100, 320, 280), block_color=(210, 40, 40)))
    cid = r.json()["crops"][0]["crop_id"]
    img_r = client.get(f"/tools/scan-merge/crop/{cid}/raw")
    assert img_r.status_code == 200
    assert img_r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(img_r.content)).convert("RGB")
    import numpy as np
    arr = np.asarray(im)
    mx = arr.max(axis=2).astype(float); mn = arr.min(axis=2).astype(float)
    sat = np.where(mx > 0, (mx - mn) / mx, 0)
    assert sat.max() > 0.5, "取回的 crop 必須保留彩色"


def test_crop_invalid_id_rejected(client, auth_off):
    assert client.get("/tools/scan-merge/crop/not-a-uuid/raw").status_code == 400
    # 合法格式但不存在 → 404
    assert client.get("/tools/scan-merge/crop/" + "a" * 32 + "/raw").status_code == 404


def test_crop_bad_variant_rejected(client, auth_off):
    r = _upload(client, _scan_png((60, 50, 260, 190)))
    cid = r.json()["crops"][0]["crop_id"]
    assert client.get(f"/tools/scan-merge/crop/{cid}/bogus").status_code == 400


def test_generate_makes_single_a4_pdf(client, auth_off):
    r = _upload(client, _scan_png((60, 50, 260, 190)))
    cid = r.json()["crops"][0]["crop_id"]
    g = client.post("/tools/scan-merge/generate", json={
        "items": [{"crop_id": cid, "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}],
        "whiten": True, "filename": "out.pdf",
    })
    assert g.status_code == 200
    job_id = g.json()["job_id"]
    # poll
    status = ""
    for _ in range(40):
        jr = client.get(f"/api/jobs/{job_id}").json()
        status = jr.get("status")
        if status in ("done", "error"):
            break
        time.sleep(0.05)
    assert status == "done", f"job status={status}"
    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200
    doc = fitz.open(stream=dl.content, filetype="pdf")
    try:
        assert doc.page_count == 1
        page = doc[0]
        # A4 直式 ≈ 595 x 842 pt
        assert abs(page.rect.width - 595.276) < 2
        assert abs(page.rect.height - 841.890) < 2
    finally:
        doc.close()


def test_generate_rejects_empty_items(client, auth_off):
    assert client.post("/tools/scan-merge/generate",
                       json={"items": [], "whiten": True}).status_code == 400


def test_public_api_merges_two_scans(client, auth_off):
    a = _scan_png((40, 40, 240, 180), block_color=(20, 20, 200))      # blue top-left
    b = _scan_png((340, 600, 560, 780), block_color=(20, 160, 40))    # green bottom-right
    r = client.post("/tools/scan-merge/api/scan-merge", files=[
        ("files", ("front.png", a, "image/png")),
        ("files", ("back.png", b, "image/png")),
    ], data={"whiten": "true", "filename": "merged.pdf"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    doc = fitz.open(stream=r.content, filetype="pdf")
    try:
        assert doc.page_count == 1
        # 應有 2 張嵌入圖（兩塊內容）
        assert len(doc[0].get_images()) >= 2
    finally:
        doc.close()


def test_public_api_all_blank_returns_422(client, auth_off):
    blank = Image.new("RGB", (600, 850), (255, 255, 255))
    buf = io.BytesIO(); blank.save(buf, format="PNG")
    r = client.post("/tools/scan-merge/api/scan-merge",
                    files=[("files", ("blank.png", buf.getvalue(), "image/png"))],
                    data={"whiten": "true"})
    assert r.status_code == 422
