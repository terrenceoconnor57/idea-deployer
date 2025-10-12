#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
import os

PROJECTS_DIR = Path(__file__).parent / "projects"

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
    projects = find_projects()
    if not projects:
        print("No projects found in projects/.")
        return

    today = date.today().isoformat()

    for proj_dir in projects:
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
