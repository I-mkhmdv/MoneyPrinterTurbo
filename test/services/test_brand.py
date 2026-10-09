import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import brand_plan
import cli
from app.services import brand

ROOT = Path(__file__).parent.parent.parent


class TestBrand(unittest.TestCase):
    def setUp(self):
        self.profile = brand.load_profile(str(ROOT / "brand.example.toml"))

    def test_example_profile_loads_with_rubrics_and_video_defaults(self):
        self.assertEqual(self.profile["brand"]["language"], "ru-RU")
        self.assertEqual(len(self.profile["rubrics"]), 3)
        self.assertEqual(self.profile["video"]["video_aspect"], "9:16")

    def test_short_video_length_limits_script_and_plan(self):
        profile = brand.load_profile(str(ROOT / "brand.travel.example.toml"))
        prompt = brand.build_script_prompt(profile, {"subject": "s"})
        self.assertIn("10 секунд", prompt)
        self.assertIn("не больше 25 слов", prompt)
        self.assertIn("до 10 секунд", brand.build_plan_prompt(profile, 5))
        self.assertIn("30–60 секунд", brand.build_plan_prompt(self.profile, 3))

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ValueError):
            brand.normalize_profile({"brand": {"niche": "x", "audience": "y"}})

    def test_script_prompt_carries_voice_and_hook_within_limit(self):
        prompt = brand.build_script_prompt(
            self.profile, {"rubric": "Польза", "subject": "s", "hook": "Стоп!"}
        )
        self.assertIn(self.profile["brand"]["tone"], prompt)
        self.assertIn("Стоп!", prompt)
        self.assertIn("лайфхак", prompt)
        self.assertLessEqual(len(prompt), brand.MAX_SCRIPT_PROMPT_LENGTH)

    def test_generate_plan_parses_fenced_json_and_caps_count(self):
        response = '```json\n[{"rubric":"Польза","subject":"Тема 1","hook":"h"},' \
            '{"subject":"Тема 2"},{"subject":""},{"subject":"Тема 3"}]\n```'
        topics = brand.generate_plan(self.profile, 2, generate=lambda _: response)
        self.assertEqual([t["subject"] for t in topics], ["Тема 1", "Тема 2"])

    def test_generate_plan_retries_then_fails_on_provider_error(self):
        calls = []

        def generate(prompt):
            calls.append(prompt)
            return "Error: quota"

        with self.assertRaises(ValueError):
            brand.generate_plan(self.profile, 3, generate=generate, retries=2)
        self.assertEqual(len(calls), 2)

    def test_topics_from_lines_rotates_rubrics(self):
        topics = brand.topics_from_lines(self.profile, ["a\n", "\n", "# skip\n", "b", "c", "d"])
        self.assertEqual([t["subject"] for t in topics], ["a", "b", "c", "d"])
        self.assertEqual(topics[0]["rubric"], topics[3]["rubric"])

    def test_manifest_from_topics_file_passes_cli_batch_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            topics_file = Path(tmp) / "topics.txt"
            topics_file.write_text("Как начать утро\nМоя главная ошибка\n", encoding="utf-8")
            code = brand_plan.main([
                "--profile", str(ROOT / "brand.example.toml"),
                "--topics", str(topics_file),
                "--out-dir", tmp,
            ])
            self.assertEqual(code, 0)
            manifest = Path(tmp) / "tasks.jsonl"
            entries = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(entries[0]["voice_name"], "ru-RU-SvetlanaNeural-Female")
            self.assertTrue((Path(tmp) / "plan.md").exists())

            args = cli.parse_args(["--batch-file", str(manifest), "--stop-at", "script"])
            tasks = cli._build_batch_tasks(args)
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[1].video_subject, "Моя главная ошибка")
            self.assertEqual(tasks[0].video_aspect, "9:16")


if __name__ == "__main__":
    unittest.main()
