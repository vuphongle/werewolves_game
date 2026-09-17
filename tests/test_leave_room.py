import unittest

import app as app_module
from game_engine import Game, PHASE_LOBBY, PHASE_NIGHT
from roles import Villager


class LeaveRoomTests(unittest.TestCase):
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
        app_module.game_instance = Game("leave_room_test")
        app_module.join_attempts = {}
        app_module.last_message_time = {}
        app_module.game_loop_running = False
        self.socket_clients = []

    def tearDown(self):
        for client in self.socket_clients:
            if client.is_connected():
                client.disconnect()

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

    def configure_active_game(self, player_ids, settings=None):
        app_module.game_instance = Game(
            "leave_room_active_test",
            settings=settings or {},
        )
        for player_id in player_ids:
            wrapper = app_module.game["players"][player_id]
            app_module.game_instance.add_player(player_id, wrapper.name)
            engine_player = app_module.game_instance.players[player_id]
            engine_player.role = Villager()
            engine_player.role.on_assign(engine_player)
        app_module.game_instance.phase = PHASE_NIGHT
        app_module.game["game_state"] = "started"

    def assert_identity_cleared_but_language_preserved(self, client):
        with client.session_transaction() as session_data:
            self.assertEqual("en", session_data.get("language"))
            self.assertNotIn("player_id", session_data)
            self.assertNotIn("name", session_data)
            self.assertNotIn("admin_code", session_data)

    def test_lobby_leave_removes_wrapper_engine_entry_and_session_identity(self):
        leaving_client, leaving_socket = self.connect_player(
            "leaving", "Leaving", admin_code=True
        )
        self.connect_player("remaining", "Remaining")
        app_module.game_instance.add_player("leaving", "Leaving")

        response = leaving_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertEqual({"redirect": "/"}, response.get_json())
        self.assertNotIn("leaving", app_module.game["players"])
        self.assertNotIn("leaving", app_module.game_instance.players)
        self.assertIn("remaining", app_module.game["players"])
        self.assertFalse(leaving_socket.is_connected())
        self.assert_identity_cleared_but_language_preserved(leaving_client)
        self.assertEqual(200, leaving_client.get("/").status_code)

    def test_lobby_admin_leave_prefers_first_connected_remaining_player(self):
        admin_client, _ = self.connect_player("admin", "Admin")
        _, disconnected_socket = self.connect_player("disconnected", "Disconnected")
        _, connected_socket = self.connect_player("connected", "Connected")
        disconnected_socket.disconnect()

        response = admin_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertIs(False, app_module.game["players"]["disconnected"].connected)
        self.assertTrue(app_module.game["players"]["connected"].is_admin)
        self.assertFalse(app_module.game["players"]["disconnected"].is_admin)
        self.assertEqual(
            app_module.game["players"]["connected"].sid,
            app_module.game["admin_sid"],
        )

    def test_admin_leave_selects_first_disconnected_player_as_pending_admin(self):
        admin_client, _ = self.connect_player("admin", "Admin")
        _, first_socket = self.connect_player("first", "First")
        _, second_socket = self.connect_player("second", "Second")
        first_socket.disconnect()
        second_socket.disconnect()

        response = admin_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertTrue(app_module.game["players"]["first"].is_admin)
        self.assertFalse(app_module.game["players"]["second"].is_admin)
        self.assertIsNone(app_module.game["admin_sid"])

    def test_last_lobby_player_leave_clears_admin_authority(self):
        client, _ = self.connect_player("only", "Only")

        response = client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertEqual({}, app_module.game["players"])
        self.assertIsNone(app_module.game["admin_sid"])

    def test_active_leave_preserves_exact_engine_player_and_submitted_state(self):
        leaving_client, leaving_socket = self.connect_player("leaving", "Leaving")
        self.connect_player("remaining", "Remaining")
        self.configure_active_game(["leaving", "remaining"])
        app_module.set_current_admin("remaining")

        engine_player = app_module.game_instance.players["leaving"]
        role = engine_player.role
        engine_player.is_alive = False
        engine_player.status_effects = ["poisoned", "2nd_life"]
        engine_player.linked_partner_id = "remaining"
        engine_player.visiting_id = "remaining"
        pending_actions = {"leaving": {"target_id": "remaining"}}
        turn_history = {"leaving"}
        end_day_votes = {"leaving"}
        rematch_votes = {"leaving"}
        app_module.game_instance.pending_actions = pending_actions
        app_module.game_instance.turn_history = turn_history
        app_module.game_instance.end_day_votes = end_day_votes
        app_module.game_instance.rematch_votes = rematch_votes

        response = leaving_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertNotIn("leaving", app_module.game["players"])
        self.assertIs(engine_player, app_module.game_instance.players["leaving"])
        self.assertIs(role, engine_player.role)
        self.assertFalse(engine_player.is_alive)
        self.assertEqual(["poisoned", "2nd_life"], engine_player.status_effects)
        self.assertEqual("remaining", engine_player.linked_partner_id)
        self.assertEqual("remaining", engine_player.visiting_id)
        self.assertIs(pending_actions, app_module.game_instance.pending_actions)
        self.assertIs(turn_history, app_module.game_instance.turn_history)
        self.assertIs(end_day_votes, app_module.game_instance.end_day_votes)
        self.assertIs(rematch_votes, app_module.game_instance.rematch_votes)
        self.assertFalse(leaving_socket.is_connected())

    def test_active_admin_leave_transfers_to_first_connected_player(self):
        admin_client, _ = self.connect_player("admin", "Admin")
        _, first_socket = self.connect_player("first", "First")
        self.connect_player("second", "Second")
        self.configure_active_game(["admin", "first", "second"])
        app_module.set_current_admin("admin")

        response = admin_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertTrue(app_module.game["players"]["first"].is_admin)
        self.assertFalse(app_module.game["players"]["second"].is_admin)
        self.assertEqual(
            app_module.game["players"]["first"].sid,
            app_module.game["admin_sid"],
        )
        self.assertTrue(first_socket.is_connected())

    def test_last_active_member_leave_stops_loop_and_resets_abandoned_room(self):
        client, _ = self.connect_player("only", "Only")
        settings = {
            "mode": "pass_and_play",
            "ghost_mode": True,
            "timers": {"timers_disabled": True},
        }
        app_module.lobby_state["settings"] = settings.copy()
        self.configure_active_game(["only"], settings=settings)
        old_game_instance = app_module.game_instance
        app_module.game["game_code"] = "KEEP-CODE"
        app_module.game["game_admin_code"] = "KEEP-ADMIN"
        app_module.game_loop_running = True

        response = client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        self.assertFalse(app_module.game_loop_running)
        self.assertEqual(PHASE_LOBBY, app_module.game["game_state"])
        self.assertEqual("KEEP-CODE", app_module.game["game_code"])
        self.assertEqual("KEEP-ADMIN", app_module.game["game_admin_code"])
        self.assertEqual(settings, app_module.lobby_state["settings"])
        self.assertIsNot(old_game_instance, app_module.game_instance)
        self.assertEqual(PHASE_LOBBY, app_module.game_instance.phase)
        self.assertEqual(settings, app_module.game_instance.settings)
        self.assertEqual({}, app_module.game_instance.players)

    def test_non_json_request_cannot_leave_payload_selected_player(self):
        attacker_client, _ = self.connect_player("attacker", "Attacker")
        self.connect_player("victim", "Victim")

        response = attacker_client.post(
            "/leave-room",
            data={"player_id": "victim"},
        )

        self.assertEqual(415, response.status_code)
        self.assertIn("attacker", app_module.game["players"])
        self.assertIn("victim", app_module.game["players"])

    def test_json_payload_identity_is_ignored_and_session_player_leaves(self):
        attacker_client, _ = self.connect_player("attacker", "Attacker")
        self.connect_player("victim", "Victim")

        response = attacker_client.post(
            "/leave-room",
            json={"player_id": "victim"},
        )

        self.assertEqual(200, response.status_code)
        self.assertNotIn("attacker", app_module.game["players"])
        self.assertIn("victim", app_module.game["players"])


if __name__ == "__main__":
    unittest.main()
