"""
Summary Sender
監聽 data/summaries/pending/ 目錄，把 Cowork 生成的摘要發送到 LINE

Cowork 任務生成摘要後存到 data/summaries/pending/{timestamp}.txt
此模組讀取並透過 LINE API 推播，成功後移到 data/summaries/sent/
"""
import json
import os
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent.parent   # data-collecting/
PENDING_DIR = BASE_DIR / "data" / "summaries" / "pending"
SENT_DIR    = BASE_DIR / "data" / "summaries" / "sent"
FAILED_DIR  = BASE_DIR / "data" / "summaries" / "failed"

LINE_API_URL  = "https://api.line.me/v2/bot/message/push"
LINE_TOKEN    = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
TARGET_IDS    = [t.strip() for t in os.environ.get("LINE_DIRECT_TARGET_USER_IDS", "").split(",") if t.strip()]

POLL_SEC = 10


def push_line(target_id: str, text: str) -> bool:
    """直接呼叫 LINE push API"""
    if not LINE_TOKEN:
        print("[WARN] LINE_CHANNEL_ACCESS_TOKEN not set")
        return False

    payload = json.dumps({
        "to": target_id,
        "messages": [{"type": "text", "text": text[:4500]}]
    }).encode("utf-8")

    req = urllib.request.Request(
        LINE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        print(f"[ERROR] LINE push failed {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"[ERROR] LINE push error: {e}")
        return False


def process_pending():
    """處理 pending/ 裡所有摘要檔案"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(PENDING_DIR.glob("*.txt"))
    if not files:
        return 0

    processed = 0
    for path in files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            path.rename(FAILED_DIR / path.name)
            continue

        success_all = True
        for target_id in TARGET_IDS:
            ok = push_line(target_id, text)
            if not ok:
                success_all = False
                print(f"  [FAIL] → {target_id}")
            else:
                print(f"  [OK]   → {target_id}")

        dest = SENT_DIR if success_all else FAILED_DIR
        path.rename(dest / path.name)
        processed += 1
        print(f"[summary_sender] {'sent' if success_all else 'failed'}: {path.name}")

    return processed


def main_watch():
    """持續監聽模式"""
    print(f"[summary_sender] Watching {PENDING_DIR} ...")
    print(f"  Targets: {TARGET_IDS or '(none set)'}")
    idle = False
    while True:
        try:
            n = process_pending()
            if n > 0:
                idle = False
            else:
                if not idle:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Idle, waiting...")
                    idle = True
            time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            print("[summary_sender] Stopped.")
            break


def main_once():
    """執行一次就結束"""
    n = process_pending()
    print(f"[summary_sender] Processed {n} summaries.")


if __name__ == "__main__":
    import sys
    if "--watch" in sys.argv:
        main_watch()
    else:
        main_once()
