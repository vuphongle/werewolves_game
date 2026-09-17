import unittest
from copy import deepcopy
from unittest.mock import patch

import app as app_module
from game_engine import (
    Game,
    PHASE_ACCUSATION,
    PHASE_LOBBY,
    PHASE_LYNCH,
    PHASE_NIGHT,
)
from roles import Villager


class EventValidationTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
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
        app_module.game_instance = Game("event_validation_test")
        app_module.join_attempts = {}
        app_module.last_message_time = {}
        app_module.game_loop_running = False
        self.socket_clients = []

    def tearDown(self):
        app_module.game_loop_running = False
        for client in self.socket_clients:
            if client.is_connected():
                client.disconnect()

    def connect_player(self, player_id, name):
        flask_client = app_module.app.test_client()
        with flask_client.session_transaction() as session_data:
            session_data["player_id"] = player_id
            session_data["name"] = name
            session_data["language"] = "en"
        socket_client = app_module.socketio.test_client(
            app_module.app,
            flask_test_client=flask_client,
        )
        self.socket_clients.append(socket_client)
        socket_client.get_received()
        return socket_client

    def connect_minimum_players(self):
        admin_socket = self.connect_player("admin", "Admin")
        self.connect_player("player-2", "Player Two")
        self.connect_player("player-3", "Player Three")
        self.connect_player("player-4", "Player Four")
        return admin_socket

    def configure_started_game(self, mode="standard"):
        app_module.game_instance = Game(
            "event_validation_test",
            settings={"mode": mode},
        )
        for player_id, wrapper in app_module.game["players"].items():
            app_module.game_instance.add_player(player_id, wrapper.name)
            engine_player = app_module.game_instance.players[player_id]
            engine_player.role = Villager()
            engine_player.role.on_assign(engine_player)
        app_module.game_instance.timers_disabled = True
        app_module.game["game_state"] = "started"
        app_module.set_current_admin("admin")

    @staticmethod
    def received_error_keys(socket_client):
        return [
            event["args"][0]["message"]["key"]
            for event in socket_client.get_received()
            if event["name"] == "error"
        ]

    def assert_validation_error(self, socket_client):
        self.assertIn(
            "ui.errors.action_ignored",
            self.received_error_keys(socket_client),
        )

    def test_admin_events_reject_non_dict_payloads_without_mutation(self):
        admin_socket = self.connect_player("admin", "Admin")
        cases = (
            ("admin_update_roles", ["Villager"]),
            ("admin_update_roles", None),
            ("admin_update_settings", ["standard"]),
            ("admin_update_settings", None),
            ("admin_set_timers", ["30"]),
            ("admin_set_timers", None),
        )

        for event_name, payload in cases:
            with self.subTest(event=event_name):
                roles_before = app_module.lobby_state["selected_roles"].copy()
                settings_before = deepcopy(app_module.lobby_state["settings"])
                timers_before = app_module.game_instance.timer_durations.copy()
                admin_socket.get_received()

                try:
                    admin_socket.emit(event_name, payload)
                except (AttributeError, TypeError) as exc:
                    self.fail(
                        f"{event_name} raised instead of emitting validation error: {exc}"
                    )

                self.assertEqual(
                    roles_before,
                    app_module.lobby_state["selected_roles"],
                )
                self.assertEqual(settings_before, app_module.lobby_state["settings"])
                self.assertEqual(timers_before, app_module.game_instance.timer_durations)
                self.assert_validation_error(admin_socket)

    def test_settings_updates_reject_unknown_mode_and_non_boolean_options(self):
        admin_socket = self.connect_player("admin", "Admin")
        cases = (
            {"mode": "unknown"},
            {"mode": []},
            {"ghost_mode": 1},
            {"pg_mode": "false"},
            {"solo_win_continues": 0},
        )

        for payload in cases:
            with self.subTest(payload=payload):
                app_module.lobby_state["settings"] = {}
                app_module.game_instance.pg_mode = False
                settings_before = deepcopy(app_module.lobby_state["settings"])
                pg_mode_before = app_module.game_instance.pg_mode
                admin_socket.get_received()

                try:
                    admin_socket.emit("admin_update_settings", payload)
                except TypeError as exc:
                    self.fail(
                        f"Malformed setting raised instead of emitting an error: {exc}"
                    )

                self.assertEqual(settings_before, app_module.lobby_state["settings"])
                self.assertEqual(pg_mode_before, app_module.game_instance.pg_mode)
                self.assert_validation_error(admin_socket)

    def test_role_updates_require_a_list_of_known_role_keys(self):
        admin_socket = self.connect_player("admin", "Admin")
        invalid_roles = ("Villager", ["Not_A_Role"], ["Villager", 7])

        for roles in invalid_roles:
            with self.subTest(roles=roles):
                app_module.lobby_state["selected_roles"] = (
                    app_module.GAME_DEFAULTS["DEFAULT_ROLES"].copy()
                )
                roles_before = app_module.lobby_state["selected_roles"].copy()
                admin_socket.get_received()

                admin_socket.emit("admin_update_roles", {"roles": roles})

                self.assertEqual(
                    roles_before,
                    app_module.lobby_state["selected_roles"],
                )
                self.assert_validation_error(admin_socket)

        admin_socket.emit(
            "admin_update_roles",
            {"roles": ["Demented_Villager"]},
        )
        self.assertEqual(
            ["Demented_Villager"],
            app_module.lobby_state["selected_roles"],
        )

    def test_timer_updates_reject_invalid_values_without_partial_mutation(self):
        admin_socket = self.connect_player("admin", "Admin")
        invalid_values = ("not-a-number", "9", "3601", True)

        for value in invalid_values:
            with self.subTest(value=value):
                app_module.lobby_state["settings"] = {}
                app_module.game_instance = Game("event_validation_test")
                settings_before = deepcopy(app_module.lobby_state["settings"])
                timers_before = app_module.game_instance.timer_durations.copy()
                disabled_before = app_module.game_instance.timers_disabled
                admin_socket.get_received()

                admin_socket.emit(
                    "admin_set_timers",
                    {"timers_disabled": False, "night": value},
                )

                self.assertEqual(settings_before, app_module.lobby_state["settings"])
                self.assertEqual(timers_before, app_module.game_instance.timer_durations)
                self.assertEqual(
                    disabled_before,
                    app_module.game_instance.timers_disabled,
                )
                self.assert_validation_error(admin_socket)

    def test_timer_updates_accept_inclusive_numeric_string_boundaries(self):
        admin_socket = self.connect_player("admin", "Admin")

        admin_socket.emit(
            "admin_set_timers",
            {"night": "10", "accusation": "3600", "lynch_vote": "30"},
        )

        self.assertEqual(10, app_module.game_instance.timer_durations[PHASE_NIGHT])
        self.assertEqual(
            3600,
            app_module.game_instance.timer_durations[PHASE_ACCUSATION],
        )
        self.assertEqual(30, app_module.game_instance.timer_durations[PHASE_LYNCH])
        self.assertEqual(
            10,
            app_module.lobby_state["settings"]["timers"]["night"],
        )
        self.assertEqual([], self.received_error_keys(admin_socket))

    def test_start_game_rejects_invalid_settings_and_roles_before_mutation(self):
        admin_socket = self.connect_minimum_players()
        invalid_payloads = (
            {
                "roles": app_module.GAME_DEFAULTS["DEFAULT_ROLES"],
                "settings": {"mode": "unknown"},
            },
            {
                "roles": app_module.GAME_DEFAULTS["DEFAULT_ROLES"],
                "settings": {"ghost_mode": 1},
            },
            {
                "roles": app_module.GAME_DEFAULTS["DEFAULT_ROLES"],
                "settings": {"timers": {"night": "9"}},
            },
            {
                "roles": ["Not_A_Role"],
                "settings": {"mode": "standard"},
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                app_module.game_instance = Game("event_validation_test")
                app_module.game["game_state"] = PHASE_LOBBY
                app_module.lobby_state["settings"] = {}
                app_module.lobby_state["selected_roles"] = (
                    app_module.GAME_DEFAULTS["DEFAULT_ROLES"].copy()
                )
                app_module.set_current_admin("admin")
                admin_socket.get_received()

                with (
                    patch.object(app_module.socketio, "start_background_task"),
                    patch.object(app_module, "broadcast_game_state"),
                ):
                    admin_socket.emit("start_game", payload)

                self.assertEqual(PHASE_LOBBY, app_module.game["game_state"])
                self.assertEqual({}, app_module.lobby_state["settings"])
                self.assert_validation_error(admin_socket)

    def test_night_actions_reject_missing_unknown_and_malformed_targets(self):
        self.connect_player("admin", "Admin")
        actor_socket = self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game()
        app_module.game_instance.phase = PHASE_NIGHT
        invalid_payloads = (
            None,
            {},
            {"target_id": "missing"},
            {"target_id": 42},
            {"target_id": "target", "metadata": []},
            {"target_id": "target", "metadata": {"potion": []}},
            {
                "target_id": "target",
                "metadata": {"target_id2": "missing"},
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                app_module.game_instance.pending_actions = {}
                app_module.game_instance.turn_history = set()
                actor_socket.get_received()

                try:
                    actor_socket.emit("hero_choice", payload)
                except TypeError as exc:
                    self.fail(
                        f"Malformed night action raised instead of emitting an error: {exc}"
                    )

                self.assertEqual({}, app_module.game_instance.pending_actions)
                self.assertEqual(set(), app_module.game_instance.turn_history)
                self.assert_validation_error(actor_socket)

    def test_night_action_keeps_existing_nobody_sentinel_support(self):
        self.connect_player("admin", "Admin")
        actor_socket = self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game()
        app_module.game_instance.phase = PHASE_NIGHT

        actor_socket.emit("hero_choice", {"target_id": "Nobody"})

        self.assertEqual(
            "Nobody",
            app_module.game_instance.pending_actions.get("actor"),
        )
        self.assertEqual([], self.received_error_keys(actor_socket))

    def test_accusations_reject_missing_unknown_and_literal_nobody_targets(self):
        self.connect_player("admin", "Admin")
        actor_socket = self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game()
        app_module.game_instance.phase = PHASE_ACCUSATION

        for payload in ({}, {"target_id": "missing"}, {"target_id": "Nobody"}):
            with self.subTest(payload=payload):
                app_module.game_instance.pending_actions = {}
                actor_socket.get_received()

                actor_socket.emit("accuse_player", payload)

                self.assertEqual({}, app_module.game_instance.pending_actions)
                self.assert_validation_error(actor_socket)

    def test_accusation_keeps_existing_empty_nobody_choice_support(self):
        self.connect_player("admin", "Admin")
        actor_socket = self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game()
        app_module.game_instance.phase = PHASE_ACCUSATION

        actor_socket.emit("accuse_player", {"target_id": ""})

        self.assertIn("actor", app_module.game_instance.pending_actions)
        self.assertEqual("", app_module.game_instance.pending_actions["actor"])
        self.assertEqual([], self.received_error_keys(actor_socket))

    def test_lynch_votes_reject_values_outside_existing_enum(self):
        self.connect_player("admin", "Admin")
        actor_socket = self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game()
        app_module.game_instance.phase = PHASE_LYNCH

        for payload in ({}, {"vote": "maybe"}, {"vote": True}, {"vote": []}):
            with self.subTest(payload=payload):
                app_module.game_instance.pending_actions = {}
                actor_socket.get_received()

                try:
                    actor_socket.emit("cast_lynch_vote", payload)
                except TypeError as exc:
                    self.fail(
                        f"Malformed lynch vote raised instead of emitting an error: {exc}"
                    )

                self.assertEqual({}, app_module.game_instance.pending_actions)
                self.assert_validation_error(actor_socket)

    def test_pnp_night_action_rejects_unknown_target(self):
        admin_socket = self.connect_player("admin", "Admin")
        self.connect_player("actor", "Actor")
        self.connect_player("target", "Target")
        self.configure_started_game(mode="pass_and_play")
        app_module.game_instance.phase = PHASE_NIGHT
        admin_socket.get_received()

        admin_socket.emit(
            "pnp_submit_action",
            {"actor_id": "actor", "target_id": "missing"},
        )

        self.assertEqual({}, app_module.game_instance.pending_actions)
        self.assert_validation_error(admin_socket)


if __name__ == "__main__":
    unittest.main()
