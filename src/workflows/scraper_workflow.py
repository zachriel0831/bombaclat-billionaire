"""
Workflow: scraper
動態載入爬蟲模組的 main()，適用於 BBC、Reuters、Yahoo Finance 等
"""
import importlib.util
import os
import time

def run(task: dict, base_dir: str) -> bool:
    rate_limit = task.get("rules", {}).get("rate_limit_sec", 0)
    if rate_limit > 0:
        time.sleep(rate_limit)

    module_name = task.get("scraper_module", task["id"])
    file_path   = os.path.join(base_dir, task.get("scraper_file", ""))

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Scraper file not found: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
    return True
