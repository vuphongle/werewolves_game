import unittest

import app as app_module
from game_engine import Game, PHASE_ACCUSATION, PHASE_LOBBY


class PrivateChannelTests(unittest.TestCase):
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
        app_module.game_instance = Game("private_channel_test")
        app_module.join_attempts = {}
        app_module.last_message_time = {}
        app_module.game_loop_running = False
        self.socket_clients = []

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
        return socket_client

    def configure_started_game(self, player_names, mode="standard"):
        app_module.game_instance = Game(
            "private_channel_test",
            settings={"mode": mode},
        )
        for player_id, player_name in player_names.items():
            app_module.game_instance.add_player(player_id, player_name)
        app_module.game["game_state"] = "started"
        app_module.set_current_admin("admin")

    def drain_clients(self):
        for client in self.socket_clients:
            client.get_received()

    @staticmethod
    def received_payloads(client, event_name):
        return [
            event["args"][0]
            for event in client.get_received()
            if event["name"] == event_name
        ]

    def test_non_admin_cannot_request_pass_and_play_private_state(self):
        admin_socket = self.connect_player("admin", "Admin")
        player_socket = self.connect_player("player", "Player")
        self.configure_started_game(
            {"admin": "Admin", "player": "Player"},
            mode="pass_and_play",
        )
        self.drain_clients()

        player_socket.emit("pnp_request_state", {"player_id": "admin"})

        event_names = [event["name"] for event in player_socket.get_received()]
        self.assertNotIn("pnp_state_sync", event_names)
        self.assertNotIn("werewolf_team_info", event_names)
        self.assertNotIn("cupid_info", event_names)
        self.assertEqual([], admin_socket.get_received())

    def test_admin_can_request_selected_pass_and_play_private_state(self):
        admin_socket = self.connect_player("admin", "Admin")
        self.connect_player("player", "Player")
        self.configure_started_game(
            {"admin": "Admin", "player": "Player"},
            mode="pass_and_play",
        )
        self.drain_clients()

        admin_socket.emit("pnp_request_state", {"player_id": "player"})

        payloads = self.received_payloads(admin_socket, "pnp_state_sync")
        self.assertEqual(1, len(payloads))
        self.assertEqual("player", payloads[0]["this_player_id"])

    def test_living_chat_is_delivered_only_to_living_players(self):
        admin_socket = self.connect_player("admin", "Admin")
        living_socket = self.connect_player("living", "Living")
        dead_socket = self.connect_player("dead", "Dead")
        self.configure_started_game(
            {"admin": "Admin", "living": "Living", "dead": "Dead"}
        )
        app_module.game_instance.phase = PHASE_ACCUSATION
        app_module.game_instance.players["dead"].is_alive = False
        self.drain_clients()

        living_socket.emit("send_message", {"message": "living only"})

        admin_messages = self.received_payloads(admin_socket, "new_message")
        living_messages = self.received_payloads(living_socket, "new_message")
        dead_messages = self.received_payloads(dead_socket, "new_message")
        self.assertEqual("living", admin_messages[0]["channel"])
        self.assertEqual("living", living_messages[0]["channel"])
        self.assertEqual([], dead_messages)

    def test_ghost_chat_is_delivered_only_to_dead_players(self):
        admin_socket = self.connect_player("admin", "Admin")
        first_dead_socket = self.connect_player("first-dead", "First Dead")
        second_dead_socket = self.connect_player("second-dead", "Second Dead")
        self.configure_started_game(
            {
                "admin": "Admin",
                "first-dead": "First Dead",
                "second-dead": "Second Dead",
            }
        )
        app_module.game_instance.phase = PHASE_ACCUSATION
        app_module.game_instance.players["first-dead"].is_alive = False
        app_module.game_instance.players["second-dead"].is_alive = False
        self.drain_clients()

        first_dead_socket.emit("send_message", {"message": "ghost only"})

        admin_messages = self.received_payloads(admin_socket, "new_message")
        first_dead_messages = self.received_payloads(first_dead_socket, "new_message")
        second_dead_messages = self.received_payloads(second_dead_socket, "new_message")
        self.assertEqual([], admin_messages)
        self.assertEqual("ghost", first_dead_messages[0]["channel"])
        self.assertEqual("ghost", second_dead_messages[0]["channel"])

    def test_admin_announcement_remains_room_wide(self):
        admin_socket = self.connect_player("admin", "Admin")
        living_socket = self.connect_player("living", "Living")
        dead_socket = self.connect_player("dead", "Dead")
        self.configure_started_game(
            {"admin": "Admin", "living": "Living", "dead": "Dead"}
        )
        app_module.game_instance.phase = PHASE_ACCUSATION
        app_module.game_instance.players["dead"].is_alive = False
        app_module.game_instance.admin_only_chat = True
        self.drain_clients()

        admin_socket.emit("send_message", {"message": "announcement"})

        for socket_client in (admin_socket, living_socket, dead_socket):
            messages = self.received_payloads(socket_client, "new_message")
            self.assertEqual("announcement", messages[0]["channel"])


if __name__ == "__main__":
    unittest.main()
