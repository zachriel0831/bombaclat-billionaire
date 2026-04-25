"""
check_triggers.py — Requirements Orchestration Trigger Checker
==============================================================
讀取 requirements.yml，根據各任務的 trigger 條件判斷是否應該派出，
並更新任務狀態。設計為獨立執行（Windows Task Scheduler 每分鐘跑一次）。

不依賴 Cowork session — 離線也能運行。

執行方式：
    python check_triggers.py
    python check_triggers.py --dry-run       # 只印出結果，不寫回 yml
    python check_triggers.py --task REQ-001  # 只檢查指定任務
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

# ── 可選：mysql.connector（on_data trigger 需要）─────────────
try:
    import mysql.connector
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

BASE_DIR = Path(__file__).parent
REQUIREMENTS_FILE = BASE_DIR / "requirements.yml"
STATE_FILE = BASE_DIR / ".trigger_state.json"   # 記錄上次檢查的 git hash / 資料筆數


# ── 讀取 .env ────────────────────────────────────────────────
def load_env(env_path: Path) -> dict:
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(BASE_DIR / ".env")


# ── 狀態檔讀寫 ────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ── trigger 檢查函數 ──────────────────────────────────────────

def check_on_merge(task: dict, state: dict) -> tuple[bool, str]:
    """比對 git log，是否有新 commit 合入 watch_branch。"""
    cfg = task.get("trigger_config", {})
    branch = cfg.get("watch_branch", "main")
    key = f"git_hash_{task['id']}"

    try:
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "log", f"origin/{branch}", "-1", "--format=%H"],
            capture_output=True, text=True, timeout=10
        )
        latest_hash = result.stdout.strip()
    except Exception as e:
        return False, f"git log 失敗: {e}"

    prev_hash = state.get(key, "")
    if latest_hash and latest_hash != prev_hash:
        state[key] = latest_hash
        return True, f"偵測到新 commit: {latest_hash[:8]} (branch: {branch})"
    return False, f"無新 commit（最新: {latest_hash[:8] if latest_hash else 'unknown'}）"


def check_on_data(task: dict, state: dict) -> tuple[bool, str]:
    """查 MySQL，是否有新資料。"""
    if not HAS_MYSQL:
        return False, "mysql.connector 未安裝，跳過 on_data 檢查"

    cfg = task.get("trigger_config", {})
    table = cfg.get("table", "t_relay_events")
    source_filter = cfg.get("source_like", "")
    key = f"db_count_{task['id']}"

    try:
        conn = mysql.connector.connect(
            host=ENV.get("MYSQL_HOST", "127.0.0.1"),
            port=int(ENV.get("MYSQL_PORT", 3306)),
            user=ENV.get("MYSQL_USER", "root"),
            password=ENV.get("MYSQL_PASSWORD", "root"),
            database=ENV.get("MYSQL_DATABASE", "news_relay"),
            connection_timeout=5,
        )
        cur = conn.cursor()
        if source_filter:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE source LIKE %s", (source_filter,))
        else:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        return False, f"MySQL 查詢失敗: {e}"

    prev_count = state.get(key, 0)
    if count > prev_count:
        state[key] = count
        return True, f"{table} 新增 {count - prev_count} 筆資料（總計 {count}）"
    return False, f"{table} 無新資料（總計 {count}）"


def check_auto(task: dict, tasks_by_id: dict) -> tuple[bool, str]:
    """檢查所有 depends_on 是否都已 done。"""
    deps = task.get("depends_on", [])
    if not deps:
        return True, "無依賴，可立即執行"

    not_done = [d for d in deps if tasks_by_id.get(d, {}).get("status") != "done"]
    if not_done:
        return False, f"等待依賴完成: {', '.join(not_done)}"
    return True, f"所有依賴已完成: {', '.join(deps)}"


# ── 主邏輯 ────────────────────────────────────────────────────

def run(dry_run: bool = False, target_id: str = None):
    if not REQUIREMENTS_FILE.exists():
        print(f"[ERROR] 找不到 {REQUIREMENTS_FILE}")
        sys.exit(1)

    doc = yaml.safe_load(REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    tasks = doc.get("tasks", [])
    tasks_by_id = {t["id"]: t for t in tasks}
    state = load_state()

    now = datetime.now(timezone.utc).isoformat()
    triggered = []
    summary_lines = [f"\n{'='*60}", f"  check_triggers  {now}", f"{'='*60}"]

    for task in tasks:
        tid = task["id"]
        if target_id and tid != target_id:
            continue

        status = task.get("status", "pending")
        trigger = task.get("trigger", "manual")

        # blocked / done / running → 不動
        if status in ("blocked", "done", "running", "review"):
            summary_lines.append(f"  [{tid}] {status.upper():8s} — 跳過 ({status})")
            continue

        # 判斷是否觸發
        should_run, reason = False, "未觸發"

        if trigger == "manual":
            should_run, reason = False, "manual — 等待人工指令"

        elif trigger == "auto":
            should_run, reason = check_auto(task, tasks_by_id)

        elif trigger == "on_merge":
            should_run, reason = check_on_merge(task, state)

        elif trigger == "on_data":
            should_run, reason = check_on_data(task, state)

        elif trigger == "schedule":
            # schedule 由 Task Scheduler 直接控制執行時機，這裡標記 ready 即可
            should_run, reason = True, "schedule trigger — 由 Task Scheduler 控制"

        marker = "✅ READY" if should_run else "⏸  WAIT "
        summary_lines.append(f"  [{tid}] {marker} | {trigger:10s} | {reason}")

        if should_run and status == "pending":
            task["status"] = "ready"
            triggered.append(task)

    summary_lines.append(f"{'='*60}")
    summary_lines.append(f"  觸發數量: {len(triggered)}")
    summary_lines.append(f"{'='*60}\n")
    print("\n".join(summary_lines))

    if triggered:
        print("── 狀態更新為 ready 的任務 ──")
        for t in triggered:
            print(f"  {t['id']}: {t['title']}")

    if not dry_run:
        REQUIREMENTS_FILE.write_text(
            yaml.dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8"
        )
        save_state(state)
        print("\n[OK] requirements.yml 與 .trigger_state.json 已更新")
    else:
        print("\n[DRY-RUN] 未寫入任何檔案")

    return triggered


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Requirements trigger checker")
    parser.add_argument("--dry-run", action="store_true", help="只印出結果，不寫回 yml")
    parser.add_argument("--task", help="只檢查指定任務 ID（如 REQ-001）")
    args = parser.parse_args()

    triggered = run(dry_run=args.dry_run, target_id=args.task)
    sys.exit(0 if not triggered or args.dry_run else 0)
