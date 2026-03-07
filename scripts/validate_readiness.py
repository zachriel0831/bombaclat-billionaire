from __future__ import annotations

# 檢查專案治理與技能檔案完整性。
from dataclasses import dataclass
from pathlib import Path
import re
import sys


REQUIRED_FILES = [
    "AGENTS.md",
    "tasks/todo.md",
    "tasks/lessons.md",
    "memory-bank/40-agent-enterprise-readiness.md",
    "memory-bank/41-skills-engineering-standard.md",
    "memory-bank/42-agent-evals-and-release-gates.md",
    "memory-bank/43-agent-security-and-compliance.md",
    "memory-bank/44-mcp-server-governance.md",
    "skills/registry.yaml",
]


@dataclass
class SkillEntry:
    name: str
    path: str
    evals: str
    changelog: str


def parse_registry(text: str) -> list[SkillEntry]:
    skills: list[SkillEntry] = []
    blocks = re.findall(r"-\s+name:\s*(.+?)(?=\n\s*-\s+name:|\Z)", text, flags=re.S)
    for block in blocks:
        name_line = block.splitlines()[0].strip()
        name = name_line
        path = _capture_field(block, "path")
        evals = _capture_field(block, "evals")
        changelog = _capture_field(block, "changelog")
        skills.append(SkillEntry(name=name, path=path, evals=evals, changelog=changelog))
    return skills


def _capture_field(block: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+)\s*$", block, flags=re.M)
    return m.group(1).strip() if m else ""


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")

    registry_path = root / "skills/registry.yaml"
    if registry_path.exists():
        text = registry_path.read_text(encoding="utf-8")
        if "skills:" not in text:
            errors.append("skills/registry.yaml missing 'skills:' section")
        entries = parse_registry(text)
        if not entries:
            warnings.append("skills/registry.yaml has no skill entries")
        for entry in entries:
            for rel in [entry.path, entry.evals, entry.changelog]:
                if not rel:
                    errors.append(f"Skill '{entry.name}' missing one of path/evals/changelog fields")
                    continue
                if not (root / rel).exists():
                    errors.append(f"Skill '{entry.name}' references missing file: {rel}")

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"- {w}")

    if errors:
        print("Readiness validation failed:")
        for e in errors:
            print(f"- {e}")
        return 1

    print("Readiness validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
