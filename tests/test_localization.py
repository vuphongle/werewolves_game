import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"


def flatten_keys(value, prefix=""):
    keys = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            keys.update(flatten_keys(child, path))
        else:
            keys.add(path)
    return keys


class LocalizationAuditTest(unittest.TestCase):
    def test_all_locales_match_english_key_set(self):
        english = json.loads((STATIC_DIR / "en.json").read_text(encoding="utf-8"))

        for locale_path in sorted(STATIC_DIR.glob("*.json")):
            locale = json.loads(locale_path.read_text(encoding="utf-8"))
            with self.subTest(locale=locale_path.stem):
                self.assertEqual(flatten_keys(english), flatten_keys(locale))

    def test_all_locales_preserve_template_placeholders(self):
        english = json.loads((STATIC_DIR / "en.json").read_text(encoding="utf-8"))

        def flatten_values(value, prefix=""):
            values = {}
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(child, dict):
                    values.update(flatten_values(child, path))
                else:
                    values[path] = str(child)
            return values

        english_values = flatten_values(english)
        placeholder_pattern = re.compile(r"\{[^{}]+\}")

        for locale_path in sorted(STATIC_DIR.glob("*.json")):
            locale = json.loads(locale_path.read_text(encoding="utf-8"))
            locale_values = flatten_values(locale)
            for key, english_value in english_values.items():
                with self.subTest(locale=locale_path.stem, key=key):
                    self.assertEqual(
                        sorted(placeholder_pattern.findall(english_value)),
                        sorted(placeholder_pattern.findall(locale_values[key])),
                    )

    def test_vietnamese_is_the_default_locale(self):
        config_source = (ROOT / "config.py").read_text(encoding="utf-8")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"DEFAULT_LANGUAGE": "vi"', config_source)
        self.assertIn('for lang in ["en", "es", "de", "zh", "vi"]', app_source)

    def test_user_interface_does_not_show_legacy_branding(self):
        user_interface = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(TEMPLATES_DIR.glob("*.html"))
        )

        self.assertNotIn("github.com/davidchilin/werewolves_game", user_interface)
        self.assertNotIn("source code:", user_interface.lower())

    def test_known_user_facing_english_literals_are_removed(self):
        audited_files = [
            *sorted(TEMPLATES_DIR.glob("*.html")),
            STATIC_DIR / "lobby.js",
            STATIC_DIR / "game.js",
        ]
        user_interface = "\n".join(
            path.read_text(encoding="utf-8") for path in audited_files
        )
        forbidden_literals = [
            "Make Admin",
            "You have been dropped from the lobby.",
            "New code set. Re-login required.",
            "Roles are not loaded yet. Please wait.",
            "Could not generate a valid role set.",
            "An error occurred generating roles. Check console.",
            "Please enter a new code.",
            "Exclude this player?",
            "Transfer Admin",
            "players have voted to return.",
        ]

        for literal in forbidden_literals:
            with self.subTest(literal=literal):
                self.assertNotIn(literal, user_interface)

    def test_engine_display_labels_use_translation_keys(self):
        roles_source = (ROOT / "roles.py").read_text(encoding="utf-8")
        engine_source = (ROOT / "game_engine.py").read_text(encoding="utf-8")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("Next mayor selected:", roles_source)
        self.assertNotIn("The Mayor is dead! Long live Mayor", roles_source)
        self.assertNotIn("Honeypot retaliation:", roles_source)
        self.assertNotIn('return "non-Magic User"', roles_source)
        self.assertIn('p_name = "ui.game.ghost_name"', engine_source)
        self.assertNotIn("<strong>ADMIN:</strong>", app_source)

if __name__ == "__main__":
    unittest.main()
