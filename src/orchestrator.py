"""
Financial Data Orchestrator
自動讀取 tasks_config/*.json，派發任務到 task_queue/pending/

新增任務：在 tasks_config/ 新增 JSON 設定檔即可，無需改程式碼。

執行:
    python src/orchestrator.py              # 派發一輪
    python src/orchestrator.py --watch      # 每 10 分鐘自動派發
    python src/orchestrator.py --list       # 列出所有任務
    python src/orchestrator.py --status     # 佇列狀態
"""
import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime

BASE_DIR         = os.path.dirname(os.path.dirname(__file__))   # data-collecting/
TASKS_CONFIG_DIR = os.path.join(BASE_DIR, "tasks_config")
QUEUE_DIR        = os.path.join(BASE_DIR, "task_queue")
PENDING          = os.path.join(QUEUE_DIR, "pending")
RUNNING          = os.path.join(QUEUE_DIR, "running")
DONE             = os.path.join(QUEUE_DIR, "done")
FAILED           = os.path.join(QUEUE_DIR, "failed")
INTERVAL         = 10 * 60  # 10 分鐘


def ensure_dirs():
    """執行 ensure dirs 的主要流程。"""
    for d in [PENDING, RUNNING, DONE, FAILED]:
        os.makedirs(d, exist_ok=True)


def load_task_configs() -> list[dict]:
    """載入 load task configs 對應的資料或結果。"""
    configs = []
    for path in glob.glob(os.path.join(TASKS_CONFIG_DIR, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
                cfg["_config_file"] = path
                configs.append(cfg)
        except Exception as e:
            print(f"[WARN] Failed to load {path}: {e}")
    configs.sort(key=lambda c: c.get("rules", {}).get("priority", 99))
    return configs


def dispatch_round(configs: list[dict]) -> int:
    """執行 dispatch round 的主要流程。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dispatched = []
    for task in configs:
        filename  = f"{ts}_{task['id']}.json"
        task_file = os.path.join(PENDING, filename)
        payload   = {**task, "created_at": ts}
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        dispatched.append(task["name"])
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Dispatched {len(dispatched)} tasks")
    for name in dispatched:
        print(f"    · {name}")
    return len(dispatched)


def status():
    """執行 status 的主要流程。"""
    ensure_dirs()
    print(f"\n── Queue Status ─────────────────────")
    print(f"  pending : {len(os.listdir(PENDING))}")
    print(f"  running : {len(os.listdir(RUNNING))}")
    print(f"  done    : {len(os.listdir(DONE))}")
    print(f"  failed  : {len(os.listdir(FAILED))}")
    print(f"─────────────────────────────────────\n")


def list_tasks(configs):
    """執行 list tasks 的主要流程。"""
    print(f"\n── Registered Tasks ({len(configs)}) ─────────")
    for c in configs:
        rules = c.get("rules", {})
        print(f"  [{c.get('id')}]  {c.get('name')}  (workflow:{c.get('workflow')}, priority:{rules.get('priority','-')})")
        print(f"    {c.get('description', '')}")
    print()


def main():
    """程式入口，負責執行此模組的主要流程。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch",  action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--list",   action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    configs = load_task_configs()

    if args.status:
        status(); return
    if args.list:
        list_tasks(configs); return
    if not configs:
        print("[ERROR] No task configs found in tasks_config/"); return

    print("=" * 45)
    print("  Financial Data Orchestrator")
    print(f"  Tasks: {len(configs)}, Mode: {'watch' if args.watch else 'single'}")
    print("=" * 45)

    dispatch_round(configs)

    if args.watch:
        while True:
            try:
                time.sleep(INTERVAL)
                dispatch_round(configs)
            except KeyboardInterrupt:
                print("\n[Orchestrator] Stopped.")
                break


if __name__ == "__main__":
    main()
