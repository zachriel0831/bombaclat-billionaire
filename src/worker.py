"""
Financial Data Worker
從 task_queue/pending/ 認領任務並依 workflow 執行

多工: 開多個終端機，每個都跑 python src/worker.py --watch

執行:
    python src/worker.py              # 處理完 pending 任務後結束
    python src/worker.py --watch      # 持續監聽
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime

BASE_DIR      = os.path.dirname(os.path.dirname(__file__))   # data-collecting/
SRC_DIR       = os.path.dirname(__file__)
QUEUE_DIR     = os.path.join(BASE_DIR, "task_queue")
PENDING       = os.path.join(QUEUE_DIR, "pending")
RUNNING       = os.path.join(QUEUE_DIR, "running")
DONE          = os.path.join(QUEUE_DIR, "done")
FAILED        = os.path.join(QUEUE_DIR, "failed")
WORKFLOWS_DIR = os.path.join(SRC_DIR, "workflows")

WORKER_ID = f"W{os.getpid()}"
POLL_SEC  = 3

WORKFLOW_MAP = {
    "scraper": "scraper_workflow",
    # 未來可加: "alert": "alert_workflow", "report": "report_workflow"
}


def ensure_dirs():
    for d in [PENDING, RUNNING, DONE, FAILED]:
        os.makedirs(d, exist_ok=True)


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}][{WORKER_ID}] {msg}")


def load_workflow(workflow_name: str):
    module_file = WORKFLOW_MAP.get(workflow_name)
    if not module_file:
        raise ValueError(f"Unknown workflow: '{workflow_name}'. Available: {list(WORKFLOW_MAP.keys())}")
    path = os.path.join(WORKFLOWS_DIR, f"{module_file}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Workflow file not found: {path}")
    spec = importlib.util.spec_from_file_location(module_file, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def claim_task():
    try:
        files = sorted(os.listdir(PENDING))
    except FileNotFoundError:
        return None, None
    for filename in files:
        src = os.path.join(PENDING, filename)
        dst = os.path.join(RUNNING, filename)
        try:
            os.rename(src, dst)
            with open(dst, encoding="utf-8") as f:
                task = json.load(f)
            return dst, task
        except (FileNotFoundError, PermissionError):
            continue
    return None, None


def execute_task(task: dict) -> bool:
    name      = task.get("name", task.get("id", "unknown"))
    workflow  = task.get("workflow", "scraper")
    rules     = task.get("rules", {})
    max_retry = rules.get("retry", 0)

    for attempt in range(max_retry + 1):
        try:
            mod = load_workflow(workflow)
            mod.run(task, SRC_DIR)
            return True
        except Exception as e:
            if attempt < max_retry:
                log(f"[RETRY {attempt+1}/{max_retry}] {name}: {e}")
                time.sleep(2 ** attempt)
            else:
                log(f"[ERROR] {name}: {e}")
                return False
    return False


def finish_task(running_path: str, success: bool):
    filename = os.path.basename(running_path)
    dest = os.path.join(DONE if success else FAILED, filename)
    try:
        with open(running_path, encoding="utf-8") as f:
            task = json.load(f)
        task["finished_at"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        task["worker"] = WORKER_ID
        task["status"] = "done" if success else "failed"
        with open(running_path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
        os.rename(running_path, dest)
    except Exception as e:
        log(f"[WARN] Cannot finalize task: {e}")


def run_once() -> int:
    count = 0
    while True:
        running_path, task = claim_task()
        if task is None:
            break
        name     = task.get("name", task.get("id"))
        workflow = task.get("workflow", "scraper")
        log(f"▶ Claimed [{workflow}] {name}")
        success = execute_task(task)
        finish_task(running_path, success)
        log(f"{'✅' if success else '❌'} {name}")
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log(f"Started (PID={os.getpid()}) | Workflows: {list(WORKFLOW_MAP.keys())}")

    if not args.watch:
        n = run_once()
        log(f"Done. Executed {n} tasks.")
        return

    log("Watch mode — waiting for tasks... (Ctrl+C to stop)")
    idle_reported = False
    while True:
        try:
            n = run_once()
            if n > 0:
                idle_reported = False
            else:
                if not idle_reported:
                    log("Idle, polling...")
                    idle_reported = True
                time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            log("Worker stopped.")
            break


if __name__ == "__main__":
    main()
