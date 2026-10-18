import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rinlib  # noqa: E402
from runtime import rin  # noqa: E402


class TestRender(unittest.TestCase):
    def setUp(self):
        self.cfg = rinlib.load_config(rinlib.example_config_path())
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_artifacts(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "render", ROOT / "tools" / "render.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        artifacts = module.build_artifacts(self.cfg)
        self.assertFalse(module.check_artifacts(artifacts))

        system = artifacts["system.md"]
        self.assertIn("生活记录员", system)
        self.assertIn(self.cfg["users"]["owner"]["name"], system)
        self.assertNotIn("{{", system)

        self.assertIn("mode: subagent", artifacts["opencode-agent.md"])
        self.assertIn("description:", artifacts["opencode-agent.md"])

        card = json.loads(artifacts["card.owner.json"])
        self.assertEqual(card["spec"], "chara_card_v2")
        self.assertEqual(card["data"]["name"], "Rin")
        self.assertTrue(card["data"]["system_prompt"])
        self.assertTrue(card["data"]["mes_example"])
        self.assertTrue(card["data"]["character_book"]["entries"])
        # 示例池不能串味
        self.assertIn("在在在", card["data"]["mes_example"])
        self.assertNotIn("先接住，再补刀", card["data"]["mes_example"])

        partner_card = json.loads(artifacts["card.partner.json"])
        self.assertIn("先接住，再补刀", partner_card["data"]["mes_example"])
        self.assertNotIn("在在在", partner_card["data"]["mes_example"])

        lore = json.loads(artifacts["lorebook.json"])
        self.assertGreaterEqual(len(lore["entries"]), 10)

    def test_partner_disabled(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["users"]["partner"]["enabled"] = False
        cfg = rinlib.normalize_config(cfg)
        system = rinlib.build_system_prompt(cfg)
        self.assertNotIn("锐利模式 · 对", system)
        self.assertNotIn("examples.partner", system)

    def test_partner_enabled(self):
        system = rinlib.build_system_prompt(self.cfg)
        self.assertIn("锐利模式 · 对", system)

    def test_static_prompt_has_no_placeholders(self):
        system = rinlib.build_system_prompt(self.cfg)
        self.assertNotIn("{{", system)
        self.assertNotIn("}}", system)


class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.cfg = rinlib.load_config(rinlib.example_config_path())
        self.tmp = tempfile.TemporaryDirectory()
        self.db = rin.init_db(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_notes_roundtrip(self):
        note_id = rin.add_note(
            self.db, self.cfg, "owner", "备忘", "今天把拖了三周的事做完了"
        )
        self.assertEqual(note_id, 1)
        rows = rin.search_notes(self.db, self.cfg, "owner", "三周")
        self.assertEqual(len(rows), 1)
        self.assertIn("三周", rows[0]["content"])

    def test_private_note_hidden_from_partner(self):
        rin.add_note(self.db, self.cfg, "owner", "日记", "只给自己看的秘密", "self")
        rin.add_note(self.db, self.cfg, "owner", "计划", "周末去看海", "shared")
        rin.add_note(self.db, self.cfg, "partner", "日记", "partner 自己的秘密", "self")

        owner_rows = rin.recent_notes(self.db, self.cfg, "owner")
        partner_rows = rin.recent_notes(self.db, self.cfg, "partner")

        self.assertEqual(len(owner_rows), 3)
        self.assertEqual(len(partner_rows), 2)
        contents = {row["content"] for row in partner_rows}
        self.assertIn("周末去看海", contents)
        self.assertIn("partner 自己的秘密", contents)
        self.assertNotIn("只给自己看的秘密", contents)

    def test_prompt_includes_state_and_memory(self):
        rin.add_note(self.db, self.cfg, "owner", "备忘", "买牛奶")
        prompt, state = rin.build_turn_system(self.db, self.cfg, "owner")
        self.assertIn("买牛奶", prompt)
        self.assertIn("心情", prompt)
        self.assertNotIn("{{", prompt)
        self.assertGreaterEqual(state["energy"], 0)

    def test_reminder_roundtrip(self):
        rid = rin.add_reminder(
            self.db, "owner", "交表", "2030-01-01T15:00:00+08:00"
        )
        self.assertEqual(rid, 1)
        rows = rin.list_reminders(self.db, "owner")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "交表")

    def test_parse_reminder_arg(self):
        due, content = rin.parse_reminder_arg("明天 15:00 交表", self.cfg)
        self.assertTrue(due)
        self.assertEqual(content, "交表")
        self.assertIn("T15:00:00", due)

        due, content = rin.parse_reminder_arg(
            "2030-01-01T15:00:00+08:00 交表", self.cfg
        )
        self.assertEqual(due, "2030-01-01T15:00:00+08:00")
        self.assertEqual(content, "交表")

        due, content = rin.parse_reminder_arg("2030-01-01 15:00 交表", self.cfg)
        self.assertTrue(due)
        self.assertIn("2030-01-01T15:00:00", due)


if __name__ == "__main__":
    unittest.main()
