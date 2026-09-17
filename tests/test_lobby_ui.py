import subprocess
import unittest
from pathlib import Path


class LobbyUiTests(unittest.TestCase):
    def test_disconnected_player_keeps_exclude_control(self):
        script = Path(__file__).parent / "js" / "test_lobby_disconnected_actions.js"

        result = subprocess.run(
            ["node", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
