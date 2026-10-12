#!/usr/bin/env python3
"""Plan/check TTS rounds and assemble the completed podcast; never synthesize speech.

Speech must be generated separately with the registered voice recorded in plan.json.
Only assemble replaces the existing full MP3, and only when every clip is present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "podcast_full_script.md"
PLAN = ROOT / "podcast_revoice" / "plan.json"
CHAPTER_RE = re.compile(r"^## Глава (\d+)\. (.+)\n", re.MULTILINE)
SAMPLE_RATE = 24000


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(text: str) -> str:
    return " ".join(text.split())


def chapters(text: str) -> list[dict]:
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        raise ValueError("No chapters found in the script")
    result = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result.append({"number": int(match[1]), "title": match[2],
                       "text": text[match.end():end].strip()})
    return result


def split_text(text: str, limit: int = 1500) -> list[str]:
    """Keep sentence boundaries, falling back to words for an oversized sentence."""
    if not 1 <= limit <= 1500:
        raise ValueError("TTS limit must be between 1 and 1500 characters")
    parts = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        ends = [m.end() for m in re.finditer(r'[.!?…][»”"]?(?=\s|$)', remaining)
                if m.end() <= limit]
        end = max(ends) if ends else remaining.rfind(" ", 0, limit + 1)
        if end <= 0:
            raise ValueError("A word is longer than the TTS character limit")
        parts.append(remaining[:end].strip())
        remaining = remaining[end:].strip()
    assert all(0 < len(part) <= limit for part in parts)
    assert canonical(" ".join(parts)) == canonical(text)
    return parts


def save_plan(plan: dict) -> None:
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")


def validate_plan(plan: dict) -> None:
    if plan["script_sha256"] != checksum(SCRIPT):
        raise ValueError("The source script changed; do not continue with this plan")
    source = chapters(SCRIPT.read_text())
    clips = plan["clips"]
    if [clip["id"] for clip in clips] != list(range(1, len(clips) + 1)):
        raise ValueError("Clip numbering is not consecutive")
    if any(not 0 < len(clip["text"]) <= 1500 or clip["characters"] != len(clip["text"])
           for clip in clips):
        raise ValueError("Invalid TTS clip length")
    if {clip["chapter"] for clip in clips} != {ch["number"] for ch in source}:
        raise ValueError("Chapter coverage differs from the source")
    order = {chapter["number"]: i for i, chapter in enumerate(source)}
    clip_order = [order[clip["chapter"]] for clip in clips]
    if clip_order != sorted(clip_order):
        raise ValueError("Chapters are out of order")
    titles = {chapter["number"]: chapter["title"] for chapter in source}
    if any(clip["chapter_title"] != titles[clip["chapter"]] for clip in clips):
        raise ValueError("Chapter titles differ from the source")
    for chapter in source:
        actual = " ".join(clip["text"] for clip in clips
                          if clip["chapter"] == chapter["number"])
        if canonical(actual) != canonical(chapter["text"]):
            raise ValueError(f"Incomplete or altered chapter {chapter['number']}")


def load_plan() -> dict:
    plan = json.loads(PLAN.read_text())
    validate_plan(plan)
    return plan


def make_plan(voice_id: str, preview: str) -> None:
    if PLAN.exists():
        raise ValueError("A plan already exists; use status, do not overwrite it")
    source = chapters(SCRIPT.read_text())
    clips = []
    for chapter in source:
        body = chapter["text"]
        parts = []
        if chapter["number"] == 1:
            if not (ROOT / preview).is_file():
                raise ValueError("The selected-voice preview is missing")
            first_paragraph = body.split("\n\n", 1)[0]
            if len(first_paragraph) > 1500:
                raise ValueError("Preview paragraph exceeds the TTS limit")
            parts.append((first_paragraph, preview))
            body = body[len(first_paragraph):].strip()
        parts.extend((part, None) for part in split_text(body))
        for text, existing in parts:
            number = len(clips) + 1
            clips.append({"id": number, "chapter": chapter["number"],
                          "chapter_title": chapter["title"], "text": text,
                          "characters": len(text),
                          "file": existing or f"podcast_revoice/part_{number:03d}.mp3",
                          "reused_preview": bool(existing)})
    plan = {"version": 1, "voice_id": voice_id, "language": "ru",
            "script": str(SCRIPT.relative_to(ROOT)), "script_sha256": checksum(SCRIPT),
            "character_limit": 1500, "round_clip_limit": 10,
            "chapter_pause_seconds": 1.2, "final_output": "lorielee_full_podcast.mp3",
            "clips": clips}
    validate_plan(plan)
    save_plan(plan)
    print(f"Planned {len(clips)} clips; clip 001 reuses the selected-voice preview.")


def refresh(plan: dict) -> list[dict]:
    from mutagen.mp3 import MP3

    pending = []
    for clip in plan["clips"]:
        path = ROOT / clip["file"]
        if not path.is_file():
            clip["status"] = "pending"
            clip.pop("duration_seconds", None)
            clip.pop("audio_sha256", None)
            pending.append(clip)
            continue
        audio = MP3(path)
        if audio.info.length <= 0:
            raise ValueError(f"Invalid audio: {path}")
        clip["status"] = "generated"
        clip["duration_seconds"] = round(audio.info.length, 3)
        clip["audio_sha256"] = checksum(path)
    save_plan(plan)
    return pending


def status(batch: int, show_text: bool) -> None:
    plan = load_plan()
    pending = refresh(plan)
    complete = len(plan["clips"]) - len(pending)
    total_chars = sum(c["characters"] for c in plan["clips"])
    done_chars = sum(c["characters"] for c in plan["clips"] if c["status"] == "generated")
    duration = sum(c.get("duration_seconds", 0) for c in plan["clips"])
    print(f"Voice: {plan['voice_id']}; ready: {complete}/{len(plan['clips'])} clips")
    print(f"Text covered: {done_chars}/{total_chars} characters; raw audio: {duration:.1f} s")
    print("Next round:")
    for clip in pending[:batch]:
        print(f"{clip['id']:03d} | chapter {clip['chapter']} | {clip['characters']} chars | {clip['file']}")
        if show_text:
            print(clip["text"] + "\n")
    if not pending:
        print("All clips are ready. Run assemble to create the single full MP3.")


def render(clips: list[dict], plan: dict, destination: Path, title: str, artist: str) -> tuple[list[dict], float]:
    """Concatenate the given clips into one tagged MP3 without touching the final episode."""
    import imageio_ffmpeg
    from mutagen.id3 import CHAP, CTOC, TIT2
    from mutagen.mp3 import MP3

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    work = ROOT / ".podcast_work"
    work.mkdir(exist_ok=True)
    navigation = []
    sample_count = 0
    previous_chapter = None
    with tempfile.TemporaryDirectory(dir=work) as temp:
        wav_path = Path(temp) / "podcast.wav"
        mp3_path = Path(temp) / "podcast.mp3"
        with wave.open(str(wav_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            for clip in clips:
                if clip["chapter"] != previous_chapter:
                    if previous_chapter is not None:
                        pause_samples = round(plan["chapter_pause_seconds"] * SAMPLE_RATE)
                        output.writeframesraw(b"\0\0" * pause_samples)
                        sample_count += pause_samples
                    navigation.append({"number": clip["chapter"], "title": clip["chapter_title"],
                                       "start_seconds": sample_count / SAMPLE_RATE})
                    previous_chapter = clip["chapter"]
                pcm = subprocess.run([ffmpeg, "-v", "error", "-i", str(ROOT / clip["file"]),
                                      "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"],
                                     check=True, capture_output=True).stdout
                if not pcm or len(pcm) % 2:
                    raise ValueError(f"Empty or invalid PCM for clip {clip['id']}")
                output.writeframesraw(pcm)
                sample_count += len(pcm) // 2
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav_path),
                        "-af", "loudnorm=I=-18:TP=-1.5:LRA=7", "-ar", str(SAMPLE_RATE),
                        "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k",
                        "-metadata", f"title={title}",
                        "-metadata", f"artist={artist}", str(mp3_path)], check=True)
        audio = MP3(mp3_path)
        if abs(audio.info.length - sample_count / SAMPLE_RATE) > 1:
            raise ValueError("The final duration does not match the assembled PCM")
        if audio.tags is None:
            audio.add_tags()
        chapter_ids = []
        for i, chapter in enumerate(navigation):
            element_id = f"chapter-{chapter['number']:02d}"
            chapter_ids.append(element_id)
            end_seconds = navigation[i + 1]["start_seconds"] if i + 1 < len(navigation) else audio.info.length
            audio.tags.add(CHAP(element_id=element_id,
                                start_time=round(chapter["start_seconds"] * 1000),
                                end_time=round(end_seconds * 1000),
                                start_offset=0xFFFFFFFF, end_offset=0xFFFFFFFF,
                                sub_frames=[TIT2(encoding=3, text=chapter["title"])]))
        audio.tags.add(CTOC(element_id="toc", flags=3, child_element_ids=chapter_ids,
                            sub_frames=[TIT2(encoding=3, text="Главы")]))
        audio.save()
        subprocess.run([ffmpeg, "-v", "error", "-i", str(mp3_path), "-f", "null", "-"], check=True)
        mp3_path.replace(destination)
    return navigation, audio.info.length


def assemble() -> None:
    plan = load_plan()
    pending = refresh(plan)
    if pending:
        raise ValueError(f"Cannot assemble: {len(pending)} clips are still missing")
    destination = ROOT / plan["final_output"]
    navigation, duration = render(plan["clips"], plan, destination,
                                  "Лори Ли. Дорога домой", "Синтетический рассказчик")
    plan["assembly"] = {"output": plan["final_output"], "duration_seconds": round(duration, 3),
                        "audio_sha256": checksum(destination), "chapters": navigation}
    save_plan(plan)
    (PLAN.parent / "chapters.json").write_text(json.dumps(navigation, ensure_ascii=False, indent=2) + "\n")
    print(f"Assembled {plan['final_output']}: {duration:.1f} seconds")
    for chapter in navigation:
        seconds = int(chapter["start_seconds"])
        print(f"{seconds // 60:02d}:{seconds % 60:02d} | {chapter['title']}")


def draft() -> None:
    """Build a preview MP3 from the clips that are ready; never replaces the full episode."""
    plan = load_plan()
    refresh(plan)
    clips = [clip for clip in plan["clips"] if clip["status"] == "generated"]
    if not clips:
        raise ValueError("Cannot build a draft: no clip is ready yet")
    if len(clips) == len(plan["clips"]):
        raise ValueError("Every clip is ready; run assemble to build the final episode instead")
    name = plan.get("draft_output", "lorielee_draft.mp3")
    if name == plan["final_output"]:
        raise ValueError("The draft must not share the name of the final episode")
    first, last = clips[0]["id"], clips[-1]["id"]
    chapters = {clip["chapter"] for clip in clips}
    covered = sorted(chapters)
    complete = [number for number in covered
                if all(clip["chapter"] != number or clip["status"] == "generated"
                       for clip in plan["clips"])]
    title = (f"Лори Ли. Дорога домой — черновик, фрагменты {first:03d}-{last:03d} "
             f"(главы {covered[0]}-{covered[-1]})")
    destination = ROOT / name
    navigation, duration = render(clips, plan, destination, title, "Синтетический рассказчик (черновик)")
    plan["draft"] = {"output": name, "clips": [first, last], "clip_count": len(clips),
                     "complete_chapters": complete, "partial_chapters":
                     [number for number in covered if number not in complete],
                     "duration_seconds": round(duration, 3),
                     "audio_sha256": checksum(destination), "chapters": navigation}
    save_plan(plan)
    print(f"Draft {name}: {duration:.1f} seconds, {len(clips)}/{len(plan['clips'])} clips")
    print(f"Complete chapters: {complete}; partial: "
          f"{[number for number in covered if number not in complete]}")
    for chapter in navigation:
        seconds = int(chapter["start_seconds"])
        print(f"{seconds // 60:02d}:{seconds % 60:02d} | {chapter['title']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--voice-id", required=True)
    plan_parser.add_argument("--preview", default="lorielee_voice_preview.mp3")
    status_parser = commands.add_parser("status")
    status_parser.add_argument("--batch", type=int, choices=range(1, 11), default=10)
    status_parser.add_argument("--show-text", action="store_true")
    commands.add_parser("assemble")
    commands.add_parser("draft")
    args = parser.parse_args()
    if args.command == "plan":
        make_plan(args.voice_id, args.preview)
    elif args.command == "status":
        status(args.batch, args.show_text)
    elif args.command == "assemble":
        assemble()
    else:
        draft()


if __name__ == "__main__":
    main()
