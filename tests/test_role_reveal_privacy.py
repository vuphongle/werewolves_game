import importlib.util
import unittest
from unittest.mock import patch


FLASK_STACK_AVAILABLE = all(
    importlib.util.find_spec(module_name) is not None
    for module_name in ("flask", "flask_socketio", "dotenv")
)

if FLASK_STACK_AVAILABLE:
    import app as server
else:
    server = None


@unittest.skipUnless(
    FLASK_STACK_AVAILABLE,
    "Flask integration dependencies are not installed in this environment.",
)
class RoleRevealPrivacyTest(unittest.TestCase):
    def setUp(self):
        server.game_instance = server.Game("privacy_test", settings={})
        server.game_instance.add_player("victim", "Victim")
        server.game_instance.add_player("wolf", "Wolf")
        server.game_instance.players["victim"].role = server.AVAILABLE_ROLES["Seer"]()
        server.game_instance.players["wolf"].role = server.AVAILABLE_ROLES[
            "Werewolf"
        ]()

        server.game.clear()
        server.game.update(
            {
                "admin_sid": None,
                "game_code": "PRIVACY",
                "game_admin_code": "ADMIN",
                "game_state": "started",
                "players": {},
            }
        )

    def test_roles_are_hidden_by_default_for_every_public_death_message(self):
        for source_key, hidden_key in server.HIDDEN_ROLE_MESSAGE_KEYS.items():
            with self.subTest(source_key=source_key):
                source = {
                    "key": source_key,
                    "variables": {"name": "Victim", "role": "Seer"},
                }

                public = server.get_public_death_message(source)

                self.assertEqual(public["key"], hidden_key)
                self.assertNotIn("role", public["variables"])
                self.assertEqual(source["variables"]["role"], "Seer")

        fallback = server.get_public_death_message(
            {
                "key": "events.future_death_type",
                "variables": {"name": "Victim", "role": "Seer"},
            }
        )
        self.assertEqual(fallback["key"], "events.death_hidden")
        self.assertNotIn("role", fallback["variables"])

    def test_hidden_setting_removes_role_from_event_and_nested_reason(self):
        source = {
            "type": "death",
            "id": "victim",
            "name": "Victim",
            "role": "Seer",
            "reason": {
                "key": "events.lovers_pact",
                "variables": {"name": "Victim", "role": "Seer"},
            },
        }

        public = server.get_public_death_event(source)

        self.assertNotIn("role", public)
        self.assertNotIn("role", public["reason"]["variables"])
        self.assertEqual(public["reason"]["key"], "events.death_love_hidden")
        self.assertEqual(source["role"], "Seer")

    def test_reveal_setting_preserves_role_data(self):
        server.game_instance.settings["reveal_roles_on_death"] = True
        source_message = {
            "key": "events.death_wolf",
            "variables": {"name": "Victim", "role": "Seer"},
        }
        source_event = {
            "type": "death",
            "id": "victim",
            "name": "Victim",
            "role": "Seer",
            "reason": "Werewolf meat",
        }

        self.assertEqual(server.get_public_death_message(source_message), source_message)
        self.assertEqual(server.get_public_death_event(source_event), source_event)

    def test_night_result_payload_does_not_broadcast_role_when_hidden(self):
        death_event = {
            "type": "death",
            "id": "victim",
            "name": "Victim",
            "role": "Seer",
            "reason": "Werewolf meat",
        }

        with (
            patch.object(
                server.game_instance,
                "resolve_night_deaths",
                return_value=[death_event],
            ),
            patch.object(server.socketio, "emit") as emit_mock,
            patch.object(server.socketio, "sleep"),
            patch.object(server, "check_game_over_or_next_phase"),
            patch.object(server, "send_cupid_info"),
            patch.object(server, "send_werewolf_info"),
        ):
            server.resolve_night()

        night_calls = [
            call
            for call in emit_mock.call_args_list
            if call.args and call.args[0] == "night_result_kill"
        ]
        self.assertEqual(len(night_calls), 1)
        payload = night_calls[0].args[1]
        self.assertNotIn("role", payload["killed_player"])
        self.assertNotIn("role", payload["message"]["variables"])
        self.assertEqual(payload["message"]["key"], "events.death_wolf_hidden")
        self.assertEqual(
            server.game_instance.message_history[-1]["key"],
            "events.death_wolf_hidden",
        )

    def test_lynch_result_payload_does_not_broadcast_role_when_hidden(self):
        lynch_result = {
            "announcements": [],
            "armor_save": False,
            "killed_id": "victim",
            "summary": {"yes": ["Wolf"], "no": []},
            "secondary_deaths": [],
        }

        with (
            patch.object(
                server.game_instance,
                "resolve_lynch_vote",
                return_value=lynch_result,
            ),
            patch.object(server.socketio, "emit") as emit_mock,
            patch.object(server.socketio, "sleep"),
            patch.object(server, "check_game_over_or_next_phase"),
            patch.object(server, "send_werewolf_info"),
        ):
            server.resolve_lynch()

        lynch_calls = [
            call
            for call in emit_mock.call_args_list
            if call.args and call.args[0] == "lynch_vote_result"
        ]
        self.assertEqual(len(lynch_calls), 1)
        payload = lynch_calls[0].args[1]
        self.assertNotIn("role", payload["message"]["variables"])
        self.assertEqual(payload["message"]["key"], "events.lynch_success_hidden")


if __name__ == "__main__":
    unittest.main()
