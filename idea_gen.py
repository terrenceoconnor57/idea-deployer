#!/usr/bin/env python3
import json
import os
from datetime import date
from pathlib import Path
from typing import List, Dict, Set

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).parent
IDEAS_FILE = PROJECT_ROOT / "ideas.json"

BLACKLIST_KEYWORDS = {
    "fitness",
    "habit tracker",
    "to-do",
    "todo",
    "journal",
    "recipe",
    "quote",
    "chatbot",
    "weather",
    "blog",
    "reminder",
}

SYSTEM_PROMPT = (
    "You are an expert product strategist. Generate strictly 1-2 concise, fresh, non-obvious, and buildable website/SaaS product ideas. "
    "Avoid cliches, clones, and overused tropes. Keep each idea under 60 words. Do not number or bullet them. Separate multiple ideas with a blank line."
)


def load_ideas() -> List[Dict[str, str]]:
    if not IDEAS_FILE.exists():
        return []
    try:
        with IDEAS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except json.JSONDecodeError:
        # If file corrupt, back it up and start fresh
        backup_path = IDEAS_FILE.with_suffix(".bak.json")
        try:
            backup_path.write_text(IDEAS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        return []


def save_ideas(ideas: List[Dict[str, str]]) -> None:
    with IDEAS_FILE.open("w", encoding="utf-8") as f:
        json.dump(ideas, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def contains_blacklisted_keyword(text: str) -> bool:
    lower_text = normalize(text)
    for kw in BLACKLIST_KEYWORDS:
        if kw in lower_text:
            return True
    return False


def is_duplicate(existing_ideas: List[Dict[str, str]], candidate: str) -> bool:
    normalized_candidate = normalize(candidate)
    seen: Set[str] = set()
    for item in existing_ideas:
        idea_text = normalize(item.get("idea", ""))
        if idea_text:
            seen.add(idea_text)
    return normalized_candidate in seen


def generate_ideas_via_openai() -> List[str]:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing. Set it in .env or environment.")

    client = OpenAI(api_key=api_key)

    # Use a capable but cost-effective model; user runs on 3.11
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Generate today's ideas."},
        ],
        temperature=1.0,
        max_tokens=400,
        n=1,
    )

    content = completion.choices[0].message.content.strip()
    # Split by blank line(s) to support 1-2 ideas
    blocks = [block.strip() for block in content.split("\n\n") if block.strip()]
    # If the model returned bullets or numbers, strip them
    cleaned: List[str] = []
    for block in blocks:
        line = block.strip()
        # Remove common bullet/number prefixes
        for prefix in ("- ", "* ", "1. ", "2. ", "3. "):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
        cleaned.append(line)
    # Limit to at most 2
    return cleaned[:2] if cleaned else []


def main() -> None:
    today = date.today().isoformat()
    all_ideas = load_ideas()

    # Build a set of today's existing ideas to avoid duplicates on same day
    todays_ideas = [i for i in all_ideas if i.get("date") == today]

    try:
        generated = generate_ideas_via_openai()
    except Exception as e:
        print(f"Error generating ideas: {e}")
        return

    added = 0
    for idea in generated:
        if contains_blacklisted_keyword(idea):
            continue
        if is_duplicate(all_ideas, idea):
            continue
        record = {"date": today, "idea": idea, "status": "new"}
        all_ideas.append(record)
        added += 1

    if added > 0:
        save_ideas(all_ideas)
        print(f"Added {added} idea(s). Saved to {IDEAS_FILE}.")
    else:
        print("No new ideas added (duplicates/blacklisted or generation empty).")


if __name__ == "__main__":
    main()
