#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path
from typing import List, Dict, Set, Optional

from dotenv import load_dotenv
from openai import OpenAI
import os
import re

PROJECT_ROOT = Path(__file__).parent
PROJECTS_DIR = PROJECT_ROOT / "projects"
IDEAS_FILE = PROJECT_ROOT / "ideas.json"

SYSTEM_PROMPT = (
    "You are an expert product and engineering advisor. Given a project state JSON, "
    "propose one concrete, high-impact improvement step that can be implemented next. "
    "Keep the proposal between 80-160 words. Include a short rationale and specific tasks."
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


def generate_iteration_content(project_name: str, state_obj) -> str:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing. Set it in .env or environment.")

    client = OpenAI(api_key=api_key)

    user_content = (
        f"Project: {project_name}\n\n"
        f"State (JSON):\n{json.dumps(state_obj, indent=2, ensure_ascii=False)}\n\n"
        f"Please propose the next concrete improvement step."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.8,
        max_tokens=500,
        n=1,
    )

    return completion.choices[0].message.content.strip()


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

    # 2) Run iteration for each project
    for proj_dir in projects_to_iterate:
        state = load_state(proj_dir)
        if state is None:
            print(f"Skipping {proj_dir.name}: missing or invalid state.json")
            continue
        out_dir = proj_dir / f"iteration_{today}"
        out_dir.mkdir(parents=True, exist_ok=True)
        content = generate_iteration_content(proj_dir.name, state)
        output_file = out_dir / "output.md"
        output_file.write_text(content + "\n", encoding="utf-8")
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
