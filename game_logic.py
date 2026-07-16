import os
import re
import random

FILENAME_RE = re.compile(r"^(?P<name>.+?)(?P<num>\d+)\.png$", re.IGNORECASE)


def scan_characters(images_path: str) -> dict[str, list[str]]:
    characters: dict[str, list[str]] = {}
    if not os.path.isdir(images_path):
        return characters
    for fname in os.listdir(images_path):
        match = FILENAME_RE.match(fname)
        if not match:
            continue
        name = match.group("name")
        characters.setdefault(name, []).append(fname)
    return characters


def pick_daily_character(images_path: str, history: dict[str, str]):
    characters = scan_characters(images_path)
    if not characters:
        return None, None

    names = list(characters.keys())
    never_used = [n for n in names if n not in history]

    if never_used:
        chosen = random.choice(never_used)
    else:
        oldest_date = min(history.get(n, "") for n in names)
        candidates = [n for n in names if history.get(n, "") == oldest_date]
        chosen = random.choice(candidates)

    image_file = random.choice(characters[chosen])
    return chosen, image_file
