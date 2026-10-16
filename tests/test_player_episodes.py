"""Checks for the GitHub Pages player data (episodes.json)."""

import json
import re
import unittest
from pathlib import Path

from mutagen.mp3 import MP3

ROOT = Path(__file__).resolve().parents[1]
EPISODES = ROOT / "episodes.json"
ALLOWED_STATUS = {"ready", "planned", "partial"}


class EpisodesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.episodes = json.loads(EPISODES.read_text())

    def test_file_is_a_non_empty_list(self):
        self.assertIsInstance(self.episodes, list)
        self.assertTrue(self.episodes)

    def test_ids_are_unique(self):
        ids = [ep["id"] for ep in self.episodes]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_ready_episode_has_audio_that_exists(self):
        for ep in self.episodes:
            if ep["status"] == "ready":
                path = ROOT / ep["audio"]
                self.assertTrue(path.is_file(), f"missing audio for {ep['id']}: {path}")

    def test_durations_match_the_mp3_files(self):
        for ep in self.episodes:
            if ep["status"] != "ready":
                continue
            real = MP3(ROOT / ep["audio"]).info.length
            self.assertLess(abs(real - ep["duration"]), 0.5,
                            f"{ep['id']}: json {ep['duration']} vs file {real:.2f}")

    def test_chapters_are_ordered_and_inside_the_audio(self):
        for ep in self.episodes:
            chapters = ep["chapters"]
            if not chapters:
                continue
            self.assertEqual(chapters[0]["start"], 0.0, f"{ep['id']} must start at zero")
            for previous, current in zip(chapters, chapters[1:]):
                self.assertLess(previous["start"], current["start"],
                                f"{ep['id']}: chapter order broken")
                self.assertAlmostEqual(previous["start"] + previous["duration"],
                                       current["start"], places=1,
                                       msg=f"{ep['id']}: gap between chapters")
            covered = sum(ch["duration"] for ch in chapters)
            self.assertLessEqual(covered, ep["duration"] + 0.5,
                                 f"{ep['id']}: chapters run past the end of the audio")

    def test_chapter_titles_match_the_script(self):
        script = (ROOT / "podcast_full_script.md").read_text()
        titles = {int(n): t for n, t in re.findall(r"^## Глава (\d+)\. (.+)$", script, re.M)}
        for ep in self.episodes:
            for chapter in ep["chapters"]:
                self.assertEqual(titles[chapter["number"]], chapter["title"],
                                 f"{ep['id']}: chapter {chapter['number']} title differs")

    def test_status_values_are_known(self):
        for ep in self.episodes:
            self.assertIn(ep["status"], ALLOWED_STATUS)

    def test_full_episode_covers_all_twelve_chapters(self):
        full = next(ep for ep in self.episodes if ep["id"] == "biography")
        self.assertEqual([ch["number"] for ch in full["chapters"]], list(range(1, 13)))


class SiteFilesTests(unittest.TestCase):
    def test_page_references_its_assets(self):
        html = (ROOT / "index.html").read_text()
        for name in ("style.css", "player.js", "episode-list", "chapter-list"):
            self.assertIn(name, html)

    def test_player_reads_the_data_file(self):
        self.assertIn("episodes.json", (ROOT / "player.js").read_text())


if __name__ == "__main__":
    unittest.main()
