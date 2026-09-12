"""歷史紀錄的 id 直接從網址進來 —— 一律先驗格式再組路徑。

## 由來（v1.15.34）

盤點「唯讀但會吐出檔案」的管理端點時發現：

    GET /admin/history/{kind}/{hid}/file/{which}

`kind` 走 `mgr_map` 白名單、`which` 走 `mapping` 白名單，**只有 `hid` 沒驗**，
而 `_entry_dir()` 是 `self._root / hid`。Starlette 會把路徑參數裡的 `%2F`
解碼，所以 `hid` 拿得到 `../../..` —— 路徑就組到歷史目錄外面去了。

能讀到的檔案受限於白名單檔名（`original.pdf` / `preview.png` / 輸出檔名），
而且這幾支端點都要 admin，**所以沒有權限提升**。但這個專案有
`safe_paths` 就是為了不要每次都重新判斷「這次危不危險」——
id 有固定格式（`uuid4().hex[:12]`）就該照格式驗。

## 判準

不合法的 id 一律**當成找不到**（回 `None` / `False`），端點自然回 404。
**不可以丟例外** —— 那會變成 500，而 500 的意思是「伺服器壞了」，
使用者送錯網址不該看到它（本專案的既有規則）。
"""
from __future__ import annotations

import pytest

_BAD = [
    "../../etc",           # 目錄跳脫
    "..",
    "a/b",                 # 含分隔符
    "%2e%2e",              # 沒解碼成功時的樣子
    "ZZZZZZZZZZZZ",        # 長度對但不是十六進位
    "0a1b2c3d4e5",         # 少一個字
    "0a1b2c3d4e5f6",       # 多一個字
    "",
]


@pytest.fixture
def mgrs():
    from app.core.history_manager import (history_manager, stamp_history,
                                          watermark_history)
    return (history_manager, stamp_history, watermark_history)


@pytest.mark.parametrize("bad", _BAD)
def test_a_bad_id_is_treated_as_not_found(mgrs, bad):
    for mgr in mgrs:
        assert mgr.get(bad) is None, f"{mgr!r}.get({bad!r}) 沒擋住"
        assert mgr.file(bad, "original") is None, f"{mgr!r}.file({bad!r}) 沒擋住"
        assert mgr.delete(bad) is False, f"{mgr!r}.delete({bad!r}) 沒擋住"


def test_a_well_formed_id_still_works(mgrs, tmp_path):
    """**反向對照**：只驗「壞的被擋住」的話，把三支都改成永遠回 None 也會過。"""
    import fitz
    mgr = mgrs[0]
    doc = fitz.open(); doc.new_page(); src = tmp_path / "o.pdf"
    doc.save(src); doc.close()
    out = tmp_path / "f.pdf"
    out.write_bytes(src.read_bytes())
    meta = mgr.save(src, out, None, "測試.pdf")
    hid = meta["id"]
    assert len(hid) == 12, f"id 格式變了（{hid!r}）—— 驗證式子要跟著改"
    assert mgr.get(hid) is not None
    assert mgr.file(hid, "original") is not None
    assert mgr.delete(hid) is True


def test_the_endpoint_returns_404_not_500(admin_session):
    """端點層再確認一次：壞 id 要 404，不可以 5xx。

    **這幾支歷史端點是稽核員專屬的** —— 裡面是使用者的檔案，連 admin 都看不到
    （`deps.py` 的 AUDITOR_EXCLUSIVE；用 admin 的 session 打會拿到 403，
    我第一版就是這樣寫的，那條測試根本沒走到處理函式）。所以這裡要用
    稽核員的身分。
    """
    from app.core import permissions, sessions, user_manager
    from fastapi.testclient import TestClient
    import app.main as app_main

    uid = user_manager.create_local("hid-auditor", "稽核員", "AuditPass1234")
    permissions.set_subject_roles("user", str(uid), ["auditor"])
    tok, _ = sessions.issue(uid, remember=False, ip="127.0.0.1", ua="pytest")
    c = TestClient(app_main.app)
    c.cookies.set(sessions.COOKIE_NAME, tok)

    for bad in ("zz", "0a1b2c3d4e5", "ZZZZZZZZZZZZ"):
        r = c.get(f"/admin/history/fill/{bad}/file/original")
        assert r.status_code == 404, f"{bad!r} → {r.status_code}（不該 5xx）"


def test_history_files_are_auditor_only(admin_session):
    """順手釘住那條隱私規則：admin 看不到歷史檔案（裡面是使用者的文件）。"""
    c, _u, _p = admin_session
    r = c.get("/admin/history/fill/0a1b2c3d4e5f/file/original")
    assert r.status_code == 403, f"admin 竟然讀得到歷史檔案（{r.status_code}）"
