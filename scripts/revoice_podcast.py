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
DEFAULT_SCRIPT = ROOT / "podcast_full_script.md"
DEFAULT_PLAN = ROOT / "podcast_revoice" / "plan.json"
DEFAULT_OUTPUT = "lorielee_full_podcast.mp3"
# Keep these module-level aliases for the existing command line and unit tests.
SCRIPT = DEFAULT_SCRIPT
PLAN = DEFAULT_PLAN
CHAPTER_RE = re.compile(r"^## Глава (\d+)\. (.+)\n", re.MULTILINE)
SAMPLE_RATE = 24000


def project_path(value: str | Path) -> Path:
    """Resolve a stored or CLI path relative to the repository root."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def path_reference(path: str | Path) -> str:
    """Store project paths portably and external paths as absolute references."""
    resolved = project_path(path)
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def default_output_for(script: Path) -> str:
    return DEFAULT_OUTPUT if script.name == DEFAULT_SCRIPT.name else f"{script.stem}.mp3"


def script_title(script: Path) -> str:
    for line in script.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Лори Ли. Дорога домой"


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


def make_plan(voice_id: str, preview: str | None = None,
              final_output: str | Path | None = None) -> None:
    if PLAN.exists():
        raise ValueError("A plan already exists; use status, do not overwrite it")
    source = chapters(SCRIPT.read_text())
    clips = []
    clip_directory = PLAN.parent
    preview_reference = None
    if preview:
        preview_path = project_path(preview)
        if not preview_path.is_file():
            raise ValueError("The selected-voice preview is missing")
        preview_reference = path_reference(preview_path)

    for chapter in source:
        body = chapter["text"]
        parts = []
        if chapter["number"] == 1 and preview_reference:
            first_paragraph = body.split("\n\n", 1)[0]
            if len(first_paragraph) > 1500:
                raise ValueError("Preview paragraph exceeds the TTS limit")
            parts.append((first_paragraph, preview_reference))
            body = body[len(first_paragraph):].strip()
        parts.extend((part, None) for part in split_text(body))
        for text, existing in parts:
            number = len(clips) + 1
            clip_path = clip_directory / f"part_{number:03d}.mp3"
            clips.append({"id": number, "chapter": chapter["number"],
                          "chapter_title": chapter["title"], "text": text,
                          "characters": len(text),
                          "file": existing or path_reference(clip_path),
                          "reused_preview": bool(existing)})
    output = path_reference(final_output) if final_output else default_output_for(SCRIPT)
    plan = {"version": 1, "voice_id": voice_id, "language": "ru",
            "script": path_reference(SCRIPT), "script_sha256": checksum(SCRIPT),
            "title": script_title(SCRIPT),
            "character_limit": 1500, "round_clip_limit": 10,
            "chapter_pause_seconds": 1.2, "final_output": output,
            "clips": clips}
    validate_plan(plan)
    save_plan(plan)
    if clips and clips[0]["reused_preview"]:
        note = "clip 001 reuses the selected-voice preview"
    else:
        note = "no preview clip reused"
    print(f"Planned {len(clips)} clips; {note}.")


def refresh(plan: dict) -> list[dict]:
    from mutagen.mp3 import MP3

    pending = []
    for clip in plan["clips"]:
        path = project_path(clip["file"])
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
                pcm = subprocess.run([ffmpeg, "-v", "error", "-i", str(project_path(clip["file"])),
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


def assemble(output: str | Path | None = None) -> None:
    plan = load_plan()
    if output:
        plan["final_output"] = path_reference(output)
    pending = refresh(plan)
    if pending:
        raise ValueError(f"Cannot assemble: {len(pending)} clips are still missing")
    destination = project_path(plan["final_output"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    title = plan.get("title", "Лори Ли. Дорога домой")
    navigation, duration = render(plan["clips"], plan, destination,
                                  title, "Синтетический рассказчик")
    plan["final_output"] = path_reference(destination)
    plan["assembly"] = {"output": plan["final_output"], "duration_seconds": round(duration, 3),
                        "audio_sha256": checksum(destination), "chapters": navigation}
    save_plan(plan)
    chapters_path = PLAN.parent / "chapters.json"
    chapters_path.parent.mkdir(parents=True, exist_ok=True)
    chapters_path.write_text(json.dumps(navigation, ensure_ascii=False, indent=2) + "\n")
    print(f"Assembled {plan['final_output']}: {duration:.1f} seconds")
    for chapter in navigation:
        seconds = int(chapter["start_seconds"])
        print(f"{seconds // 60:02d}:{seconds % 60:02d} | {chapter['title']}")


def draft(output: str | Path | None = None) -> None:
    """Build a preview MP3 from the clips that are ready; never replaces the full episode."""
    plan = load_plan()
    if output:
        plan["draft_output"] = path_reference(output)
    refresh(plan)
    clips = [clip for clip in plan["clips"] if clip["status"] == "generated"]
    if not clips:
        raise ValueError("Cannot build a draft: no clip is ready yet")
    if len(clips) == len(plan["clips"]):
        raise ValueError("Every clip is ready; run assemble to build the final episode instead")
    name = plan.get("draft_output", f"{Path(plan['final_output']).stem}_draft.mp3")
    if project_path(name) == project_path(plan["final_output"]):
        raise ValueError("The draft must not share the name of the final episode")
    first, last = clips[0]["id"], clips[-1]["id"]
    chapters = {clip["chapter"] for clip in clips}
    covered = sorted(chapters)
    complete = [number for number in covered
                if all(clip["chapter"] != number or clip["status"] == "generated"
                       for clip in plan["clips"])]
    title = (f"{plan.get('title', 'Лори Ли. Дорога домой')} — черновик, "
             f"фрагменты {first:03d}-{last:03d} (главы {covered[0]}-{covered[-1]})")
    destination = project_path(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    navigation, duration = render(clips, plan, destination, title, "Синтетический рассказчик (черновик)")
    name = path_reference(destination)
    plan["draft_output"] = name
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


def add_path_arguments(parser: argparse.ArgumentParser, *, child: bool = False) -> None:
    default = argparse.SUPPRESS if child else None
    parser.add_argument("--script", default=default,
                        help="source Markdown script (default: podcast_full_script.md)")
    parser.add_argument("--plan", default=default,
                        help="JSON plan file (default: podcast_revoice/plan.json)")
    parser.add_argument("--out", default=default,
                        help="assembled MP3 path; for plan, stores the output path in the plan")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_path_arguments(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser("plan")
    add_path_arguments(plan_parser, child=True)
    plan_parser.add_argument("--voice-id", required=True)
    plan_parser.add_argument("--preview", default=None,
                             help="optional existing first clip; defaults to the legacy preview for the original script")
    plan_parser.add_argument("--no-preview", action="store_true",
                             help="do not reuse an existing preview clip")

    status_parser = commands.add_parser("status")
    add_path_arguments(status_parser, child=True)
    status_parser.add_argument("--batch", type=int, choices=range(1, 11), default=10)
    status_parser.add_argument("--show-text", action="store_true")

    assemble_parser = commands.add_parser("assemble")
    add_path_arguments(assemble_parser, child=True)
    draft_parser = commands.add_parser("draft")
    add_path_arguments(draft_parser, child=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    global SCRIPT, PLAN
    args = build_parser().parse_args(argv)
    SCRIPT = project_path(args.script) if args.script else DEFAULT_SCRIPT
    PLAN = project_path(args.plan) if args.plan else DEFAULT_PLAN

    if args.command == "plan":
        if args.no_preview:
            preview = None
        elif args.preview:
            preview = args.preview
        elif SCRIPT.resolve() == DEFAULT_SCRIPT.resolve():
            preview = "lorielee_voice_preview.mp3"
        else:
            preview = None
        make_plan(args.voice_id, preview, args.out)
    elif args.command == "status":
        status(args.batch, args.show_text)
    elif args.command == "assemble":
        assemble(args.out)
    else:
        draft(args.out)


if __name__ == "__main__":
    main()
