import unittest

import app as app_module
from game_engine import Game, PHASE_GAME_OVER, PHASE_LOBBY, PHASE_NIGHT
from roles import Villager


class ConnectionStateTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.socket_clients = []
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
        app_module.game_instance = Game("connection_state_test")
        app_module.join_attempts = {}
        app_module.last_message_time = {}
        app_module.game_loop_running = False

    def tearDown(self):
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
        return flask_client, socket_client

    def configure_active_game(self, player_ids):
        app_module.game_instance = Game("connection_state_active_test")
        for player_id in player_ids:
            wrapper = app_module.game["players"][player_id]
            app_module.game_instance.add_player(player_id, wrapper.name)
            engine_player = app_module.game_instance.players[player_id]
            engine_player.role = Villager()
            engine_player.role.on_assign(engine_player)
        app_module.game_instance.phase = PHASE_NIGHT
        app_module.game["game_state"] = "started"

    def player_list_payload(self, socket_client):
        socket_client.get_received()
        app_module.broadcast_player_list()
        updates = [
            event["args"][0]
            for event in socket_client.get_received()
            if event["name"] == "update_player_list"
        ]
        self.assertTrue(updates)
        return updates[-1]

    def test_initial_connect_exposes_connected_lobby_status(self):
        _, socket_client = self.connect_player("player", "Player")

        self.assertTrue(app_module.game["players"]["player"].connected)
        payload = self.player_list_payload(socket_client)
        self.assertEqual(
            "connected",
            payload["players"][0]["connection_state"],
        )

    def test_disconnect_clears_sid_preserves_engine_player_and_exposes_status(self):
        _, observer_socket = self.connect_player("observer", "Observer")
        _, player_socket = self.connect_player("player", "Player")
        self.configure_active_game(["observer", "player"])
        engine_player = app_module.game_instance.players["player"]
        engine_role = engine_player.role
        engine_player.is_alive = False

        player_socket.disconnect()

        wrapper = app_module.game["players"]["player"]
        self.assertFalse(wrapper.connected)
        self.assertIsNone(wrapper.sid)
        self.assertIs(engine_player, app_module.game_instance.players["player"])
        self.assertIs(engine_role, engine_player.role)
        self.assertFalse(engine_player.is_alive)

        public_players = {
            player["id"]: player
            for player in app_module.get_public_game_state()["all_players"]
        }
        self.assertEqual("disconnected", public_players["player"]["connection_state"])
        self.assertEqual("connected", public_players["observer"]["connection_state"])
        self.assertTrue(observer_socket.is_connected())

    def test_reconnect_replaces_sid_and_restores_connected_status(self):
        flask_client, old_socket = self.connect_player("player", "Player")
        old_sid = app_module.game["players"]["player"].sid
        old_socket.disconnect()

        new_socket = app_module.socketio.test_client(
            app_module.app,
            flask_test_client=flask_client,
        )
        self.socket_clients.append(new_socket)

        wrapper = app_module.game["players"]["player"]
        self.assertTrue(wrapper.connected)
        self.assertNotEqual(old_sid, wrapper.sid)
        self.assertTrue(new_socket.is_connected())

    def test_stale_old_sid_disconnect_keeps_newer_reconnect_connected(self):
        flask_client, old_socket = self.connect_player("player", "Player")
        new_socket = app_module.socketio.test_client(
            app_module.app,
            flask_test_client=flask_client,
        )
        self.socket_clients.append(new_socket)
        new_sid = app_module.game["players"]["player"].sid

        old_socket.disconnect()

        wrapper = app_module.game["players"]["player"]
        self.assertTrue(wrapper.connected)
        self.assertEqual(new_sid, wrapper.sid)

    def test_active_leave_is_left_and_excluded_from_rematch_denominator(self):
        leaving_client, _ = self.connect_player("leaving", "Leaving")
        self.connect_player("remaining", "Remaining")
        self.configure_active_game(["leaving", "remaining"])
        app_module.game_instance.rematch_votes = {"leaving"}

        response = leaving_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        public_state = app_module.get_public_game_state()
        public_players = {player["id"]: player for player in public_state["all_players"]}
        self.assertEqual("left", public_players["leaving"]["connection_state"])
        self.assertEqual("connected", public_players["remaining"]["connection_state"])
        self.assertEqual(1, public_state["rematch_eligible_count"])

    def test_rematch_vote_from_player_who_left_is_not_counted(self):
        self.connect_player("admin", "Admin")
        leaving_client, leaving_socket = self.connect_player("leaving", "Leaving")
        _, voter_socket = self.connect_player("voter", "Voter")
        self.connect_player("remaining", "Remaining")
        self.configure_active_game(["admin", "leaving", "voter", "remaining"])
        app_module.game_instance.phase = PHASE_GAME_OVER
        app_module.game["game_state"] = PHASE_GAME_OVER

        leaving_socket.emit("vote_for_rematch")
        response = leaving_client.post("/leave-room", json={})

        self.assertEqual(200, response.status_code)
        public_state = app_module.get_public_game_state()
        self.assertEqual(3, public_state["rematch_eligible_count"])
        self.assertEqual(0, public_state["rematch_vote_count"])

        voter_socket.get_received()
        voter_socket.emit("vote_for_rematch")
        updates = [
            event["args"][0]
            for event in voter_socket.get_received()
            if event["name"] == "rematch_vote_update"
        ]

        self.assertEqual(PHASE_GAME_OVER, app_module.game["game_state"])
        self.assertEqual({"count": 1, "total": 3}, updates[-1])

    def test_game_payload_exposes_connection_state_for_each_engine_player(self):
        _, connected_socket = self.connect_player("connected", "Connected")
        _, disconnected_socket = self.connect_player("disconnected", "Disconnected")
        self.configure_active_game(["connected", "disconnected"])

        disconnected_socket.disconnect()

        public_players = {
            player["id"]: player
            for player in app_module.get_public_game_state()["all_players"]
        }
        self.assertEqual("connected", public_players["connected"]["connection_state"])
        self.assertEqual(
            "disconnected",
            public_players["disconnected"]["connection_state"],
        )
        self.assertTrue(connected_socket.is_connected())


if __name__ == "__main__":
    unittest.main()
