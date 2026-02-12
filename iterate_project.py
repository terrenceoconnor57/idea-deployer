#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path, PurePosixPath
from typing import List, Dict, Set, Optional

from dotenv import load_dotenv
from openai import OpenAI
import os
import re

PROJECT_ROOT = Path(__file__).parent
PROJECTS_DIR = PROJECT_ROOT / "projects"
IDEAS_FILE = PROJECT_ROOT / "ideas.json"

ALLOWED_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".html", ".css", ".sql", ".sh", ".txt"
}
ALLOWED_CODE_BASENAMES = {"Dockerfile", "Makefile", ".gitignore", ".dockerignore"}

SYSTEM_PROMPT = (
    "You are a senior software engineer. Given the project state and current file tree, "
    "produce a small, concrete code iteration as a single JSON object. "
    "Only modify or create real code/config files. No markdown, docs, or PM artifacts.\n\n"
    "Output JSON schema:\n"
    "{\n"
    "  \"summary\": \"1-2 sentences on what changed and why.\",\n"
    "  \"changes\": [\n"
    "    {\"path\": \"relative/posix/path.ext\", \"action\": \"create|update|delete\", \"content\": \"<full file content if create/update>\"}\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- path must be inside the project folder (no leading /, no ..).\n"
    "- For create/update, provide the complete file content.\n"
    "- Only code/config files (py, js, ts, tsx, jsx, json, yaml, yml, toml, ini, cfg, html, css, sql, sh, txt, Makefile, Dockerfile, .gitignore, .dockerignore).\n"
    "- Keep it 1-5 files and runnable."
)


def find_projects() -> List[Path]:
    if not PROJECTS_DIR.exists():
        return []
    return [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]


def load_state(project_dir: Path):
    state_file = project_dir / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_ideas() -> List[Dict[str, str]]:
    if not IDEAS_FILE.exists():
        return []
    try:
        data = json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:60] if len(value) > 60 else value


def ensure_project_initialized(project_slug: str, idea_text: str, created_date: Optional[str]) -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    proj_dir = PROJECTS_DIR / project_slug
    proj_dir.mkdir(parents=True, exist_ok=True)

    state_path = proj_dir / "state.json"
    if not state_path.exists():
        state = {
            "slug": project_slug,
            "idea": idea_text,
            "created_date": created_date or date.today().isoformat(),
            "iterations": [],
        }
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return proj_dir


def is_allowed_code_path(rel_path: str) -> bool:
    try:
        p = PurePosixPath(rel_path)
    except Exception:
        return False
    if p.is_absolute() or not p.parts or ".." in p.parts:
        return False
    if p.suffix in ALLOWED_CODE_EXTENSIONS:
        return True
    if p.name in ALLOWED_CODE_BASENAMES:
        return True
    return False


def list_project_tree(project_dir: Path) -> list:
    entries = []
    for path in project_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(project_dir).as_posix()
            if is_allowed_code_path(rel):
                entries.append({"path": rel})
    return entries


def generate_code_changes(project_name: str, state_obj, file_tree: list) -> dict:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing. Set it in .env or environment.")

    client = OpenAI(api_key=api_key)
    user_payload = {
        "project": project_name,
        "state": state_obj,
        "file_tree": file_tree,
    }
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        temperature=0.6,
        max_tokens=1600,
        n=1,
        response_format={"type": "json_object"},
    )
    raw = completion.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError("Model did not return valid JSON changes.")


def apply_changes(project_dir: Path, changes: list) -> list:
    applied = []
    for change in changes:
        path = str(change.get("path", ""))
        action = str(change.get("action", "")).lower()
        if action not in {"create", "update", "delete"} or not is_allowed_code_path(path):
            continue
        target = project_dir / Path(path)
        if action in {"create", "update"}:
            content = change.get("content")
            if not isinstance(content, str):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            applied.append({"path": path, "action": action})
        elif action == "delete":
            try:
                if target.exists() and target.is_file():
                    target.unlink()
                    applied.append({"path": path, "action": action})
            except Exception:
                pass
    return applied


def main() -> None:
    today = date.today().isoformat()

    # 1) Ensure all projects from ideas.json exist and are initialized
    ideas = load_ideas()
    processed_slugs: Set[str] = set()
    projects_to_iterate: List[Path] = []

    for item in ideas:
        idea_text = str(item.get("idea", "")).strip()
        if not idea_text:
            continue
        slug = str(item.get("project_slug") or slugify(idea_text))
        if not slug or slug in processed_slugs:
            continue
        processed_slugs.add(slug)
        created_date = item.get("date") if isinstance(item.get("date"), str) else None
        proj_dir = ensure_project_initialized(slug, idea_text, created_date)
        projects_to_iterate.append(proj_dir)

    # Fallback: if ideas.json absent or empty, iterate any existing projects
    if not projects_to_iterate:
        projects_to_iterate = find_projects()
        if not projects_to_iterate:
            print("No projects found in projects/ and no ideas.json entries.")
            return

    # 2) Apply code iteration for each project
    for proj_dir in projects_to_iterate:
        state = load_state(proj_dir)
        if state is None:
            print(f"Skipping {proj_dir.name}: missing or invalid state.json")
            continue
        file_tree = list_project_tree(proj_dir)
        try:
            result = generate_code_changes(proj_dir.name, state, file_tree)
        except Exception as e:
            print(f"{proj_dir.name}: failed to generate changes: {e}")
            continue
        summary = str(result.get("summary", "")).strip()
        changes = result.get("changes") or []
        applied = apply_changes(proj_dir, changes)
        # record iteration in state.json
        state.setdefault("iterations", [])
        state["iterations"].append({
            "date": today,
            "summary": summary,
            "applied": applied,
        })
        (proj_dir / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{proj_dir.name}: applied {len(applied)} change(s). {summary}")


if __name__ == "__main__":
    main()
