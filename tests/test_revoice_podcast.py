import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("revoice_podcast", ROOT / "scripts/revoice_podcast.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class RevoiceTests(unittest.TestCase):
    def test_sentence_and_quote_boundaries_preserve_text(self):
        text = ('Первая фраза. Затем вопрос: «Как дела?»\n\n'
                'Ещё одна фраза! Последняя мысль.')
        parts = workflow.split_text(text, limit=48)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 48 for part in parts))
        self.assertEqual(workflow.canonical(" ".join(parts)), workflow.canonical(text))
        self.assertTrue(all(part[-1] in '.!?»' for part in parts))

    def test_oversized_sentence_splits_at_words(self):
        text = " ".join(["длинная мысль"] * 200) + "."
        parts = workflow.split_text(text)
        self.assertTrue(all(len(part) <= 1500 for part in parts))
        self.assertEqual(workflow.canonical(" ".join(parts)), workflow.canonical(text))

    def test_impossible_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            workflow.split_text("текст", limit=1501)
        with self.assertRaises(ValueError):
            workflow.split_text("неразрывноеслово", limit=5)

    def test_actual_plan_covers_all_chapters_without_changes(self):
        plan = workflow.load_plan()
        self.assertEqual(plan["voice_id"], "voice-00")
        self.assertEqual(len(plan["clips"]), 36)
        self.assertEqual(len(workflow.chapters(workflow.SCRIPT.read_text())), 12)
        self.assertEqual(plan["clips"][0]["file"], "lorielee_voice_preview.mp3")
        self.assertTrue(plan["clips"][0]["reused_preview"])
        self.assertTrue(all(len(c["text"]) <= 1500 for c in plan["clips"]))

    def test_changed_source_is_rejected(self):
        plan = workflow.load_plan()
        plan["script_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "source script changed"):
            workflow.validate_plan(plan)

    def test_reordered_chapters_are_rejected(self):
        plan = copy.deepcopy(workflow.load_plan())
        plan["clips"].reverse()
        for i, clip in enumerate(plan["clips"], 1):
            clip["id"] = i
        with self.assertRaisesRegex(ValueError, "out of order"):
            workflow.validate_plan(plan)

    def temporary_root(self):
        work = ROOT / ".podcast_work"
        work.mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(dir=work)

    def test_incomplete_assembly_preserves_previous_full_mp3(self):
        plan = copy.deepcopy(workflow.load_plan())
        with self.temporary_root() as temp:
            root = Path(temp)
            script = root / "podcast_full_script.md"
            script.write_bytes(workflow.SCRIPT.read_bytes())
            plan_path = root / "podcast_revoice/plan.json"
            previous = root / plan["final_output"]
            previous.write_bytes(b"previous full recording")
            with patch.multiple(workflow, ROOT=root, SCRIPT=script, PLAN=plan_path):
                workflow.save_plan(plan)
                with self.assertRaisesRegex(ValueError, "36 clips are still missing"):
                    workflow.assemble()
            self.assertEqual(previous.read_bytes(), b"previous full recording")

    def test_complete_assembly_adds_pause_and_chapter_tags(self):
        import imageio_ffmpeg
        from mutagen.mp3 import MP3

        with self.temporary_root() as temp:
            root = Path(temp)
            script = root / "podcast_full_script.md"
            script.write_text("Intro is not narrated.\n\n## Глава 1. Первая\n\nПервая глава.\n\n"
                              "## Глава 2. Вторая\n\nВторая глава.\n")
            source = workflow.chapters(script.read_text())
            clips = []
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            for chapter in source:
                file = f"part_{chapter['number']:03d}.mp3"
                subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                                f"sine=frequency={440 * chapter['number']}:duration=0.25",
                                "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame",
                                "-b:a", "64k", str(root / file)], check=True)
                clips.append({"id": chapter["number"], "chapter": chapter["number"],
                              "chapter_title": chapter["title"], "text": chapter["text"],
                              "characters": len(chapter["text"]), "file": file})
            plan = {"voice_id": "voice-00", "script_sha256": workflow.checksum(script),
                    "chapter_pause_seconds": 1.2, "final_output": "full.mp3", "clips": clips}
            plan_path = root / "podcast_revoice/plan.json"
            with patch.multiple(workflow, ROOT=root, SCRIPT=script, PLAN=plan_path):
                workflow.save_plan(plan)
                with contextlib.redirect_stdout(io.StringIO()):
                    workflow.assemble()
            audio = MP3(root / "full.mp3")
            result = json.loads(plan_path.read_text())
            self.assertEqual(audio.info.channels, 1)
            self.assertEqual(audio.info.sample_rate, 24000)
            self.assertAlmostEqual(audio.info.length, 1.7, delta=0.15)
            self.assertEqual(len(audio.tags.getall("CHAP")), 2)
            self.assertEqual(len(audio.tags.getall("CTOC")), 1)
            navigation = result["assembly"]["chapters"]
            self.assertEqual(navigation[0]["start_seconds"], 0)
            self.assertAlmostEqual(navigation[1]["start_seconds"], 1.45, delta=0.01)
            self.assertEqual(result["assembly"]["audio_sha256"], workflow.checksum(root / "full.mp3"))
            self.assertTrue((root / "podcast_revoice/chapters.json").is_file())

    def test_draft_builds_partial_preview_without_touching_full_mp3(self):
        import imageio_ffmpeg
        from mutagen.mp3 import MP3

        def tone(root, number):
            file = f"part_{number:03d}.mp3"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi",
                            "-i", f"sine=frequency={440 * number}:duration=0.25",
                            "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k",
                            str(root / file)], check=True)
            return file

        with self.temporary_root() as temp:
            root = Path(temp)
            script = root / "podcast_full_script.md"
            script.write_text("Intro is not narrated.\n\n## Глава 1. Первая\n\nПервая глава.\n\n"
                              "## Глава 2. Вторая\n\nВторая глава.\n\n"
                              "## Глава 3. Третья\n\nТретья глава.\n")
            source = workflow.chapters(script.read_text())
            clips = [{"id": chapter["number"], "chapter": chapter["number"],
                      "chapter_title": chapter["title"], "text": chapter["text"],
                      "characters": len(chapter["text"]),
                      "file": f"part_{chapter['number']:03d}.mp3"} for chapter in source]
            plan = {"voice_id": "voice-00", "script_sha256": workflow.checksum(script),
                    "chapter_pause_seconds": 1.2, "final_output": "full.mp3",
                    "draft_output": "draft.mp3", "clips": clips}
            plan_path = root / "podcast_revoice/plan.json"
            with patch.multiple(workflow, ROOT=root, SCRIPT=script, PLAN=plan_path):
                workflow.save_plan(plan)
                (root / "full.mp3").write_bytes(b"previous full recording")
                tone(root, 1)
                tone(root, 2)
                plan["draft_output"] = "full.mp3"
                workflow.save_plan(plan)
                with self.assertRaisesRegex(ValueError, "must not share the name"):
                    workflow.draft()
                plan["draft_output"] = "draft.mp3"
                workflow.save_plan(plan)
                with contextlib.redirect_stdout(io.StringIO()):
                    workflow.draft()
                audio = MP3(root / "draft.mp3")
                result = json.loads(plan_path.read_text())
                self.assertEqual((root / "full.mp3").read_bytes(), b"previous full recording")
                self.assertEqual(audio.info.channels, 1)
                self.assertEqual(audio.info.sample_rate, 24000)
                self.assertAlmostEqual(audio.info.length, 1.7, delta=0.15)
                self.assertEqual(len(audio.tags.getall("CHAP")), 2)
                self.assertEqual(len(audio.tags.getall("CTOC")), 1)
                self.assertEqual(result["draft"]["clips"], [1, 2])
                self.assertEqual(result["draft"]["clip_count"], 2)
                self.assertEqual(result["draft"]["complete_chapters"], [1, 2])
                self.assertEqual(result["draft"]["partial_chapters"], [])
                self.assertEqual(result["draft"]["audio_sha256"], workflow.checksum(root / "draft.mp3"))
                self.assertEqual(result["draft"]["chapters"][0]["start_seconds"], 0)
                self.assertNotIn("assembly", result)
                tone(root, 3)
                with self.assertRaisesRegex(ValueError, "run assemble"):
                    workflow.draft()


if __name__ == "__main__":
    unittest.main()
