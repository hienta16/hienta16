"""Rendering and the command line, end to end in a temporary copy of the repository."""

import json
import re
import shutil
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from io import StringIO

from catwalk.cli import main
from catwalk.config import SiteConfig
from catwalk.jsonio import read_json, write_json
from catwalk.render import render_all
from catwalk.render.readme import issue_link, replace_block
from catwalk.toys import load_rules

from helpers import ROOT, at, temp_root

NOW = at("2026-11-23T06:00:00Z")


def seeded(live=True):
    paths = temp_root()
    if live:
        cfg = read_json(paths.site_config)
        write_json(paths.site_config, {**cfg, "hub_public": True, "toys_live": True})
    shutil.copy(ROOT / "data" / "github.json", paths.root / "data.json")
    (paths.root / "data").mkdir(exist_ok=True)
    shutil.copy(ROOT / "data" / "github.json", paths.github_data)
    return paths


def run(*argv):
    out = StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class Render(unittest.TestCase):
    def test_every_svg_is_well_formed_and_honest(self):
        paths = seeded()
        written = render_all(paths, now=NOW)
        self.assertGreaterEqual(len(written), 15)
        for svg in paths.generated.glob("*.svg"):
            text = svg.read_text(encoding="utf-8")
            ET.fromstring(text)  # raises on broken XML
            visible = re.sub(r"<style>.*?</style>", "", text, flags=re.DOTALL)  # the embedded font is base64 noise
            self.assertIsNone(re.search(r"NaN|nan|None|inf", visible), svg.name)

    def test_iso_has_one_block_per_day(self):
        paths = seeded()
        render_all(paths, only={"site"}, now=NOW)
        snap = read_json(paths.github_data)
        root = ET.fromstring((paths.generated / "iso-site.svg").read_text(encoding="utf-8"))
        blocks = [g for g in root.iter("{http://www.w3.org/2000/svg}g") if g.get("data-date")]
        self.assertEqual(len(blocks), len(snap["calendar"]["days"]))
        self.assertEqual(sum(int(b.get("data-count")) for b in blocks), snap["calendar"]["total"])

    def test_column_height_is_linear_in_the_real_count(self):
        from catwalk.render.iso import MIN_H, column_height

        self.assertEqual(column_height(0, 120), 0.0)
        self.assertAlmostEqual(column_height(120, 120, 5.0), 5.0)
        self.assertAlmostEqual(column_height(60, 120, 5.0), 2.5)  # half the count, half the height
        self.assertAlmostEqual(column_height(30, 120, 5.0), 1.25)
        self.assertEqual(column_height(1, 120, 5.0), MIN_H)  # a quiet day still clears the slab
        # two days in the same colour level (41+) are not the same height
        self.assertNotEqual(column_height(45, 120, 5.0), column_height(110, 120, 5.0))

    def test_rendering_twice_changes_nothing(self):
        paths = seeded()
        render_all(paths, now=NOW)
        self.assertTrue(all(not changed for _, changed in render_all(paths, now=NOW)))

    def test_missing_counts_render_as_not_available(self):
        paths = seeded()
        snap = read_json(paths.github_data)
        snap["counts"] = None
        write_json(paths.github_data, snap)
        render_all(paths, only={"stats"}, now=NOW)
        self.assertIn("n/a", (paths.generated / "stats.svg").read_text(encoding="utf-8"))

    def test_toy_buttons_only_when_live(self):
        paths = seeded(live=False)
        render_all(paths, only={"readme"}, now=NOW)
        self.assertNotIn("issues/new", paths.readme.read_text(encoding="utf-8"))
        cfg = read_json(paths.site_config)
        write_json(paths.site_config, {**cfg, "hub_public": True, "toys_live": True})
        render_all(paths, only={"readme"}, now=NOW)
        readme = paths.readme.read_text(encoding="utf-8")
        self.assertIn("issues/new?title=%5Bcat-toy%5D%20yarn", readme)
        self.assertIn("&amp;body=", readme)

    def test_toys_live_requires_a_public_hub(self):
        cfg = json.loads((ROOT / "config" / "catwalk.json").read_text())
        with self.assertRaises(ValueError):
            SiteConfig.from_dict({**cfg, "toys_live": True, "hub_public": False})

    def test_replace_block_needs_markers(self):
        with self.assertRaises(ValueError):
            replace_block("no markers here", "toys", "x")
        self.assertIn("NEW", replace_block("a<!-- catwalk:x:start -->old<!-- catwalk:x:end -->b", "x", "NEW"))

    def test_issue_link_is_url_encoded(self):
        site = SiteConfig.from_dict(json.loads((ROOT / "config" / "catwalk.json").read_text()))
        link = issue_link(site, load_rules(ROOT / "config" / "toys.json"), "box")
        self.assertTrue(link.startswith("https://github.com/hienta16/hienta16/issues/new?title=%5Bcat-toy%5D%20box&body="))
        self.assertNotIn(" ", link)


class Cli(unittest.TestCase):
    def test_toys_handle_end_to_end(self):
        paths = seeded()
        ev = paths.root / "event.json"
        result = paths.root / "result.json"
        payload = {
            "action": "opened",
            "repository": {"full_name": "hienta16/hienta16"},
            "issue": {"number": 12, "title": "[cat-toy] box", "created_at": "2026-11-23T05:00:00Z", "user": {"login": "kind-visitor", "id": 77, "type": "User"}},
        }
        ev.write_text(json.dumps(payload), encoding="utf-8")
        code, out = run("--root", str(paths.root), "toys", "handle", "--event", str(ev), "--result", str(result), "--now", "2026-11-23T05:01:00Z")
        self.assertEqual(code, 0, out)
        r = read_json(result)
        self.assertEqual((r["outcome"], r["toy"], r["close"]), ("accepted", "box", "completed"))
        self.assertIn("Your cardboard box has arrived", r["reply"])
        state = read_json(paths.toy_state)
        self.assertEqual(state["active"][0]["expiresAt"], "2026-12-07T05:00:00Z")
        # the same event again: nothing changes; the answer is rebuilt in case the first run never sent it
        # (respond skips an issue that is already closed, so nobody is answered twice)
        code, _ = run("--root", str(paths.root), "toys", "handle", "--event", str(ev), "--result", str(result), "--now", "2026-11-23T05:02:00Z")
        again = read_json(result)
        self.assertEqual((code, again["outcome"], again["close"]), (0, "duplicate", "completed"))
        self.assertIn("Your cardboard box has arrived", again["reply"])
        self.assertEqual(read_json(paths.toy_state), state)
        code, out = run("--root", str(paths.root), "toys", "commit-message", "--result", str(result))
        self.assertIn("#12", out)

    def test_nothing_is_accepted_while_the_toy_box_is_not_live(self):
        paths = seeded(live=False)
        ev = paths.root / "event.json"
        result = paths.root / "result.json"
        payload = {
            "action": "opened",
            "repository": {"full_name": "hienta16/hienta16"},
            "issue": {"number": 3, "title": "[cat-toy] yarn", "created_at": "2026-11-23T05:00:00Z", "user": {"login": "early-bird", "id": 9, "type": "User"}},
        }
        ev.write_text(json.dumps(payload), encoding="utf-8")
        code, out = run("--root", str(paths.root), "toys", "handle", "--event", str(ev), "--result", str(result))
        self.assertEqual((code, read_json(result)["outcome"]), (0, "ignored"))
        self.assertIn("not live", out)
        self.assertFalse(paths.toy_state.exists())

    def test_bad_event_exits_2_and_writes_nothing(self):
        paths = seeded()
        ev = paths.root / "event.json"
        ev.write_text(json.dumps({"action": "opened", "repository": {"full_name": "hienta16/hienta16"}, "issue": {"title": "[cat-toy] yarn"}}), encoding="utf-8")
        code, _ = run("--root", str(paths.root), "toys", "handle", "--event", str(ev))
        self.assertEqual(code, 2)
        self.assertFalse(paths.toy_state.exists())

    def test_respond_without_a_token_only_prints(self):
        paths = seeded()
        result = paths.root / "result.json"
        write_json(result, {"outcome": "accepted", "issue": 3, "login": "x", "reply": "hello", "close": "completed"})
        code, out = run("--root", str(paths.root), "toys", "respond", "--result", str(result))
        self.assertEqual(code, 0)
        self.assertIn("hello", out)

    def test_demo_and_check(self):
        paths = seeded()
        code, out = run("--root", str(paths.root), "toys", "demo", "--write", "--now", "2026-11-23T06:00:00Z")
        self.assertEqual(code, 0)
        for outcome in ("accepted", "cooldown", "unknown_toy", "not_a_person", "duplicate", "ignored"):
            self.assertIn(outcome, out)
        self.assertTrue(read_json(paths.toy_demo_state)["demo"])
        self.assertEqual(run("--root", str(paths.root), "check")[0], 0)


if __name__ == "__main__":
    unittest.main()
