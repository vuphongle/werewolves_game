import importlib.util
import unittest


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
class AdminCancelGameTest(unittest.TestCase):
    def setUp(self):
        self.clients = []
        self.settings = {
            "mode": "standard",
            "ghost_mode": True,
            "timers": {"night": 60, "accusation": 90, "lynch_vote": 45},
        }

        server.game_loop_running = False
        server.game_instance = server.Game("test_game", settings=self.settings)
        server.game_instance.add_player("admin", "Admin")
        server.game_instance.add_player("player", "Player")
        server.game_instance.set_phase(server.PHASE_NIGHT)
        server.game_instance.pending_actions["player"] = "admin"
        server.game_instance.players["admin"].role = server.AVAILABLE_ROLES[
            "Villager"
        ]()

        self.admin_wrapper = server.PlayerWrapper("Admin", None, language="vi")
        self.admin_wrapper.is_admin = True
        self.player_wrapper = server.PlayerWrapper("Player", None, language="vi")

        server.game.clear()
        server.game.update(
            {
                "admin_sid": None,
                "game_code": "ROOM1",
                "game_admin_code": "ADMIN1",
                "game_state": "started",
                "game_over_data": {"stale": True},
                "players": {
                    "admin": self.admin_wrapper,
                    "player": self.player_wrapper,
                },
            }
        )
        server.lobby_state.clear()
        server.lobby_state.update(
            {
                "selected_roles": ["Villager", "Werewolf"],
                "settings": self.settings,
            }
        )

        self.admin_client = self.connect_player("admin", "Admin")
        self.player_client = self.connect_player("player", "Player")
        self.drain_events()

    def tearDown(self):
        for client in self.clients:
            if client.is_connected():
                client.disconnect()
        server.game_loop_running = False

    def connect_player(self, player_id, name):
        flask_client = server.app.test_client()
        with flask_client.session_transaction() as session:
            session["player_id"] = player_id
            session["name"] = name
            session["language"] = "vi"

        client = server.socketio.test_client(
            server.app,
            flask_test_client=flask_client,
        )
        self.assertTrue(client.is_connected())
        self.clients.append(client)
        return client

    def drain_events(self):
        for client in self.clients:
            client.get_received()

    def test_admin_can_cancel_active_game_without_disbanding_room(self):
        previous_game = server.game_instance
        previous_admin_timer_id = previous_game.current_timer_id

        self.admin_client.emit("admin_cancel_game")

        self.assertIsNot(server.game_instance, previous_game)
        self.assertEqual(server.game["game_state"], server.PHASE_LOBBY)
        self.assertEqual(server.game_instance.phase, server.PHASE_LOBBY)
        self.assertIsNone(server.game["game_over_data"])
        self.assertEqual(server.game["game_code"], "ROOM1")
        self.assertEqual(server.game["admin_sid"], self.admin_wrapper.sid)
        self.assertEqual(server.game_instance.settings, self.settings)
        self.assertEqual(server.lobby_state["settings"], self.settings)
        self.assertEqual(
            server.lobby_state["selected_roles"], ["Villager", "Werewolf"]
        )
        self.assertEqual(set(server.game_instance.players), {"admin", "player"})
        self.assertIs(server.game["players"]["admin"], self.admin_wrapper)
        self.assertIs(server.game["players"]["player"], self.player_wrapper)
        self.assertTrue(self.admin_wrapper.is_admin)
        self.assertIsNone(server.game_instance.players["admin"].role)
        self.assertEqual(server.game_instance.pending_actions, {})

        self.assertTrue(previous_game.timers_disabled)
        self.assertEqual(previous_game.phase_end_time, 0)
        self.assertEqual(
            previous_game.current_timer_id,
            previous_admin_timer_id + 1,
        )

        for client in (self.admin_client, self.player_client):
            event_names = {packet["name"] for packet in client.get_received()}
            self.assertIn("redirect_to_lobby", event_names)

    def test_non_admin_cannot_cancel_active_game(self):
        previous_game = server.game_instance

        self.player_client.emit("admin_cancel_game")

        self.assertIs(server.game_instance, previous_game)
        self.assertEqual(server.game["game_state"], "started")
        for client in (self.admin_client, self.player_client):
            event_names = {packet["name"] for packet in client.get_received()}
            self.assertNotIn("redirect_to_lobby", event_names)

    def test_admin_cannot_cancel_outside_active_game(self):
        for state in (server.PHASE_LOBBY, server.PHASE_GAME_OVER):
            with self.subTest(state=state):
                previous_game = server.game_instance
                server.game["game_state"] = state
                self.drain_events()

                self.admin_client.emit("admin_cancel_game")

                self.assertIs(server.game_instance, previous_game)
                self.assertEqual(server.game["game_state"], state)
                event_names = {
                    packet["name"] for packet in self.admin_client.get_received()
                }
                self.assertNotIn("redirect_to_lobby", event_names)


if __name__ == "__main__":
    unittest.main()
