import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from game_engine import Game, PHASE_LOBBY, PHASE_NIGHT


class SocketAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.original_admin_code = app_module.GAME_DEFAULTS["DEFAULT_ADMIN_CODE"]
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app_module.GAME_DEFAULTS["DEFAULT_ADMIN_CODE"] = "ADMIN"
        app_module.game = {
            "admin_sid": None,
            "game_code": "W",
            "game_admin_code": "ADMIN",
            "game_state": PHASE_LOBBY,
            "players": {},
        }
        app_module.lobby_state = {
            "selected_roles": app_module.GAME_DEFAULTS["DEFAULT_ROLES"].copy(),
            "settings": {},
        }
        app_module.game_instance = Game("authorization_test")
        app_module.join_attempts = {}
        app_module.last_message_time = {}
        app_module.game_loop_running = False
        self.socket_clients = []

    def tearDown(self):
        for client in self.socket_clients:
            if client.is_connected():
                client.disconnect()
        app_module.GAME_DEFAULTS["DEFAULT_ADMIN_CODE"] = self.original_admin_code

    def make_flask_client(self, player_id=None, name=None, admin_code=False):
        client = app_module.app.test_client()
        with client.session_transaction() as session_data:
            if player_id is not None:
                session_data["player_id"] = player_id
            if name is not None:
                session_data["name"] = name
            session_data["language"] = "en"
            if admin_code:
                session_data["admin_code"] = True
        return client

    def connect_player(self, player_id, name, admin_code=False):
        flask_client = self.make_flask_client(player_id, name, admin_code)
        socket_client = app_module.socketio.test_client(
            app_module.app,
            flask_test_client=flask_client,
        )
        self.socket_clients.append(socket_client)
        socket_client.get_received()
        return flask_client, socket_client

    def test_socket_without_complete_identity_is_rejected(self):
        cases = (
            ("missing both", self.make_flask_client()),
            ("missing name", self.make_flask_client(player_id="player-only")),
            ("missing player id", self.make_flask_client(name="Name Only")),
        )
        for label, flask_client in cases:
            with self.subTest(case=label):
                socket_client = app_module.socketio.test_client(
                    app_module.app,
                    flask_test_client=flask_client,
                )
                self.socket_clients.append(socket_client)
                self.assertFalse(socket_client.is_connected())

    def test_join_game_event_cannot_join_an_arbitrary_room(self):
        _, socket_client = self.connect_player("player-1", "Player One")

        socket_client.emit("join_game", {"room": "other-room"})
        socket_client.get_received()
        app_module.socketio.emit("room_probe", {"room": "other-room"}, to="other-room")

        event_names = [event["name"] for event in socket_client.get_received()]
        self.assertNotIn("room_probe", event_names)

    def test_non_admin_cannot_start_game_with_pass_and_play_setting(self):
        _, admin_socket = self.connect_player("admin", "Admin")
        _, player_socket = self.connect_player("player", "Player")
        self.connect_player("third", "Third")
        self.connect_player("fourth", "Fourth")
        admin_socket.get_received()

        player_socket.emit(
            "start_game",
            {
                "settings": {"mode": "pass_and_play"},
                "roles": app_module.GAME_DEFAULTS["DEFAULT_ROLES"],
            },
        )

        self.assertEqual(PHASE_LOBBY, app_module.game["game_state"])
        error_keys = [
            event["args"][0]["message"]["key"]
            for event in player_socket.get_received()
            if event["name"] == "error"
        ]
        self.assertIn("ui.errors.admin_start_only", error_keys)

    def test_start_game_rejects_non_dict_payload(self):
        _, admin_socket = self.connect_player("admin", "Admin")

        try:
            admin_socket.emit("start_game", ["not", "a", "mapping"])
        except (AttributeError, TypeError) as exc:
            self.fail(f"Malformed payload raised instead of emitting an error: {exc}")

        self.assertEqual(PHASE_LOBBY, app_module.game["game_state"])
        error_keys = [
            event["args"][0]["message"]["key"]
            for event in admin_socket.get_received()
            if event["name"] == "error"
        ]
        self.assertIn("ui.errors.action_ignored", error_keys)

    def test_non_admin_cannot_advance_phase_with_pnp_flag(self):
        self.connect_player("admin", "Admin")
        _, player_socket = self.connect_player("player", "Player")
        app_module.game_instance.phase = PHASE_NIGHT

        with patch.object(app_module, "resolve_night") as resolve_night:
            player_socket.emit("admin_next_phase", {"is_pnp": True})

        resolve_night.assert_not_called()

    def test_pnp_add_player_and_transfer_keep_one_canonical_admin(self):
        _, first_socket = self.connect_player("first", "First")
        app_module.lobby_state["settings"] = {"mode": "pass_and_play"}
        _, second_socket = self.connect_player("second", "Second")

        admins = [
            player_id
            for player_id, wrapper in app_module.game["players"].items()
            if wrapper.is_admin
        ]
        self.assertEqual(["second"], admins)
        self.assertEqual(
            app_module.game["players"]["second"].sid,
            app_module.game["admin_sid"],
        )

        second_socket.emit("admin_transfer_admin", {"target_id": "first"})

        admins = [
            player_id
            for player_id, wrapper in app_module.game["players"].items()
            if wrapper.is_admin
        ]
        self.assertEqual(["first"], admins)
        self.assertEqual(
            app_module.game["players"]["first"].sid,
            app_module.game["admin_sid"],
        )
        self.assertTrue(first_socket.is_connected())

    def test_admin_code_elevation_demotes_previous_admin(self):
        self.connect_player("first", "First")
        self.connect_player("second", "Second", admin_code=True)

        admins = [
            player_id
            for player_id, wrapper in app_module.game["players"].items()
            if wrapper.is_admin
        ]
        self.assertEqual(["second"], admins)
        self.assertEqual(
            app_module.game["players"]["second"].sid,
            app_module.game["admin_sid"],
        )

    def test_public_login_clears_prior_admin_code_elevation(self):
        client = app_module.app.test_client()

        response = client.post(
            "/",
            data={"name": "Admin Login", "game_code": "ADMIN", "language": "en"},
        )
        self.assertEqual(302, response.status_code)
        with client.session_transaction() as session_data:
            self.assertTrue(session_data.get("admin_code"))

        app_module.join_attempts = {}
        response = client.post(
            "/?add_player=1",
            data={"name": "Public Login", "game_code": "W", "language": "en"},
        )

        self.assertEqual(302, response.status_code)
        with client.session_transaction() as session_data:
            self.assertNotIn("admin_code", session_data)

    def test_shutdown_route_is_not_exposed(self):
        with patch.object(app_module.socketio, "stop"):
            response = app_module.app.test_client().post("/shutdown")

        self.assertEqual(404, response.status_code)

    def test_admin_code_is_disabled_when_environment_value_is_unset_or_blank(self):
        config_path = Path(app_module.__file__).with_name("config.py")
        for label, value in (("unset", None), ("blank", "   ")):
            with self.subTest(case=label), patch.dict(os.environ, {}, clear=False):
                if value is None:
                    os.environ.pop("GAME_ADMIN_CODE", None)
                else:
                    os.environ["GAME_ADMIN_CODE"] = value
                spec = importlib.util.spec_from_file_location(
                    f"test_config_{label}", config_path
                )
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module)

                self.assertIsNone(
                    config_module.GAME_DEFAULTS["DEFAULT_ADMIN_CODE"]
                )

    def test_cors_origin_parser_uses_same_origin_unless_explicitly_configured(self):
        parser = getattr(app_module, "parse_cors_allowed_origins", None)
        self.assertIsNotNone(parser)
        if parser is None:
            return

        cases = (
            (None, None),
            ("", None),
            ("   ", None),
            ("*", "*"),
            (
                " http://localhost:8080, https://game.example:5000 ",
                ["http://localhost:8080", "https://game.example:5000"],
            ),
        )

        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                self.assertEqual(
                    expected,
                    parser(raw_value),
                )


if __name__ == "__main__":
    unittest.main()
