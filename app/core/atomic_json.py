"""設定檔的原子寫入 —— 全站一份。

## 為什麼要有這一支

設定檔直接覆寫時，**寫到一半斷電 / 行程被殺就留下一個截斷的檔案**，而每一支
`load()` 都是「剖析失敗就回預設值」—— 於是管理員一條一條建起來的資料安靜地
變成空的，畫面上看不出任何異常，也沒有錯誤訊息。翻譯對照字典（v1.15.20）就是
為這件事先補的，當時記下「全站還有六支不是原子寫入」—— v1.15.34 用 AST 實算
之後是 **18 支**，那份手記漏了 12 支（其中 `api_tokens` 截斷之後 `enforce`
會退回 false，**對外 API 的強制驗證無聲關掉**）。

這裡把那個寫法收成**一支**，而不是抄 18 份：`os.replace` 的前置條件（同一個
檔案系統、先 `fsync` 才有意義、Windows 上目標存在也照樣成功）每抄一次就多一次
抄錯的機會 —— 而且實際就抄錯過：兩支把權限設在**換檔之後**（含 token 的檔案
有一瞬間是 0644），一支拿唯讀的描述子去 fsync。

## 判準

1. 暫存檔要**跟目標同一個目錄**（跨檔案系統 `os.replace` 會丟 `OSError`，
   而資料目錄常是獨立掛載點），而且**檔名要獨一無二**（同時寫的兩個人不可以
   共用同一個暫存檔）。
2. `flush` + `fsync` 之後才 `replace`。少了這一步，中繼資料換過去了但內容
   還在頁快取裡 —— 斷電之後檔案存在、內容是空的，比截斷更難察覺。
3. 失敗要把暫存檔清掉，不要在資料目錄裡養一堆 `*.tmp`。
4. `mode` 要設在**暫存檔**上（不是換過去之後）—— `os.replace` 會沿用暫存檔的
   權限，反過來做的話含密鑰的檔案會有一瞬間是 0644。不支援 `chmod` 的檔案
   系統（Windows）安靜跳過。
5. **換過去之後還要 fsync 目錄**，否則當機之後那個 rename 可能整個不見（檔案
   回到舊內容，或根本不存在）。

## 以 root 執行時

這支會**建出新檔案**，而 `sudo jtdt …` 是 root —— 新檔案就會是 `root:root`，
服務帳號從此寫不進去（v1.15.16 的「救援做完反而登不進去」）。

收尾的 `_chown_data_files_back()` **不是全域掛在派送層的**：只有 `ocr-lang`
那一組（好幾個 return 點）用 `finally` 統一收，其餘是**逐支呼叫**，由
`tests/test_cli_data_dir_ownership.py` 的 `MUST_CHOWN` 手寫清單守著
（會不會寫到資料目錄沒辦法只靠靜態掃描判斷 —— 寫入常常藏在被呼叫的模組裡）。
**新增會以 root 寫設定的 CLI 指令時，要一起加進那份清單。**
"""
from __future__ import annotations

import json
import os
import pathlib
import secrets
from typing import Any


def write_json(path: str | os.PathLike[str], obj: Any, *,
               mode: int | None = None, indent: int = 2) -> None:
    """把 `obj` 以 JSON 原子寫入 `path`（先寫同目錄暫存檔再 `os.replace`）。"""
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent),
               mode=mode)


def write_text(path: str | os.PathLike[str], text: str, *,
               mode: int | None = None) -> None:
    """同 `write_json`，但內容由呼叫端自己序列化（例如已加密的字串）。"""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 暫存檔名要**獨一無二**。固定叫 `<name>.tmp` 的話，兩個同時在寫同一份
    # 設定的寫入者會互相踩：A 寫好一半、B 把同一個暫存檔截斷、A 接著 rename
    # → 換過去的是半份內容，**而那正是原子寫入要防的事**。這不是理論問題：
    # `jtdt` CLI（救援指令）會在服務跑著的時候寫同一份 auth_settings.json。
    tmp = p.with_name(f"{p.name}.tmp-{os.getpid():x}-{secrets.token_hex(4)}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            try:
                os.chmod(tmp, mode)
            except OSError:      # Windows / 不支援 chmod 的檔案系統
                pass
        os.replace(tmp, p)
        _fsync_dir(p.parent)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _fsync_dir(d: pathlib.Path) -> None:
    """把目錄項本身也落地 —— 少了這一步，當機後 rename 可能整個消失。

    這條是從 `auth_settings.save()` 學來的（v1.14.31 對抗式驗證抓到「0 bytes
    的認證設定等於認證關閉」之後補的）。Windows 打不開目錄的檔案描述子，
    `os.open` 直接丟 `OSError` —— 那不是錯誤，是平台差異。
    """
    try:
        fd = os.open(str(d), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
