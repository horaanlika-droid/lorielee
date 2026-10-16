#!/usr/bin/env python3
"""Build episodes.json for the GitHub Pages player from data already in the repo.

Durations are read from the MP3 files themselves, so the chapter timecodes shown
in the player can never drift from the audio that is actually published.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mutagen.mp3 import MP3

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "episodes.json"
CHAPTER_RE = re.compile(r"^## Глава (\d+)\. (.+)$", re.MULTILINE)


def duration(path: Path) -> float:
    return round(MP3(path).info.length, 2)


def script_chapters(script: Path) -> list[tuple[int, str]]:
    return [(int(n), t) for n, t in CHAPTER_RE.findall(script.read_text())]


def cut(starts: list[float], total: float) -> list[float]:
    """Chapter lengths from start offsets; the last one ends at the file end."""
    return [round((starts[i + 1] if i + 1 < len(starts) else total) - s, 2)
            for i, s in enumerate(starts)]


def build() -> list[dict]:
    episodes: list[dict] = []

    # 1. Полный выпуск подкаста-биографии: главы и таймкоды уже посчитаны в chapters.json.
    full_audio = "lorielee_full_podcast.mp3"
    full_total = duration(ROOT / full_audio)
    chapters_meta = json.loads((ROOT / "podcast_revoice" / "chapters.json").read_text())
    plan = json.loads((ROOT / "podcast_revoice" / "plan.json").read_text())
    starts = [float(c["start_seconds"]) for c in chapters_meta]
    if starts[0] != 0.0 or starts[-1] >= full_total:
        raise ValueError("podcast_revoice/chapters.json does not match the full episode")
    lengths = cut(starts, full_total)
    episodes.append({
        "id": "biography",
        "title": "Дорога домой: жизнь Лори Ли",
        "description": "Подкаст-биография по книге Валери Гроув «The Life and Loves of Laurie Lee»: "
                       "Слэд, скрипка, контора, дорога в Испанию, возвращение и дом, к которому он вернулся.",
        "status": "ready",
        "audio": full_audio,
        "duration": full_total,
        "characters": sum(c["characters"] for c in plan["clips"]),
        "chapters": [
            {"number": c["number"], "title": c["title"], "start": round(s, 2), "duration": d}
            for c, s, d in zip(chapters_meta, starts, lengths)
        ],
    })

    # 2. Черновик: главы 1–6 прежним голосом. Седьмая глава в нём обрывается,
    #    поэтому список глав берём из plan["draft"]["complete_chapters"], а не по времени.
    draft_meta = plan["draft"]
    draft_audio = draft_meta["output"]
    draft_total = duration(ROOT / draft_audio)
    if abs(draft_total - draft_meta["duration_seconds"]) > 0.5:
        raise ValueError("lorielee_draft.mp3 does not match the recorded draft plan")
    complete = list(draft_meta["complete_chapters"])
    partial = list(draft_meta["partial_chapters"])
    draft_starts = {c["number"]: float(c["start_seconds"]) for c in draft_meta["chapters"]}
    if partial:
        ends = [draft_starts[n + 1] for n in complete]
    else:
        ends = [draft_starts[n + 1] for n in complete[:-1]] + [draft_total]
    episodes.append({
        "id": "biography-draft",
        "title": "Черновик: главы 1–6 прежним голосом",
        "description": "Первые шесть глав тем голосом, которым подкаст записывался до смены голоса. "
                       "Текст тот же, что и в полном выпуске; седьмая глава в черновике обрывается, "
                       "поэтому в список не попала.",
        "status": "ready",
        "audio": draft_audio,
        "duration": draft_total,
        "characters": sum(c["characters"] for c in plan["clips"] if c["chapter"] in complete),
        "chapters": [
            {**{"number": n,
                "title": next(t for k, t in script_chapters(ROOT / plan["script"]) if k == n),
                "start": round(draft_starts[n], 2),
                "duration": round(e - draft_starts[n], 2)},
             **({"note": f"в записи дальше идёт начало {p}-й главы"
                 for p in partial[:1]} if i == len(complete) - 1 and partial else {})}
            for i, (n, e) in enumerate(zip(complete, ends))
        ],
    })

    # 3. Пересказ «Сидра с Рози» — появится, когда будет записано аудио.
    cider_script = ROOT / "cider_rosie" / "script.md"
    cider_audio = ROOT / "cider_rosie" / "cider_rosie_full.mp3"
    if cider_script.is_file():
        chapters = script_chapters(cider_script)
        recorded = cider_audio.is_file()
        total = duration(cider_audio) if recorded else 0.0
        episodes.append({
            "id": "cider-with-rosie",
            "title": "«Сидр с Рози»: книга по главам",
            "description": "Свободный русскоязычный пересказ книги Лори Ли 1959 года — двенадцать глав "
                           "о деревне Слэд, а не перевод: текст книги под копирайтом до 2068 года.",
            "status": "ready" if recorded else "planned",
            "audio": "cider_rosie/cider_rosie_full.mp3",
            "duration": total,
            "chapters": [
                {"number": n, "title": t, "start": 0, "duration": 0} for n, t in chapters
            ] if not recorded else [],
        })
    return episodes


def main() -> None:
    data = build()
    for ep in data:
        covered = sum(c["duration"] for c in ep["chapters"])
        if covered > ep["duration"] + 0.5:
            raise ValueError(f"{ep['id']}: chapters run past the end of the audio")
        if ep["status"] == "ready" and ep["duration"] - covered > 60:
            print(f"note: {ep['id']} — {ep['duration'] - covered:.1f}s аудио вне глав")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    for ep in data:
        print(f"{ep['id']:18s} {ep['status']:8s} {ep['duration']:8.2f}s  {len(ep['chapters'])} chapters")
    print("written:", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
