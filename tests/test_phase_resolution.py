import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, Thread
from unittest.mock import patch

import app as app_module
from game_engine import Game, PHASE_ACCUSATION, PHASE_LYNCH, PHASE_NIGHT


class PhaseResolutionClaimTests(unittest.TestCase):
    def test_only_one_concurrent_caller_claims_the_phase(self):
        game = Game("claim_test")
        game.phase = PHASE_NIGHT
        barrier = Barrier(8)

        def claim_phase():
            barrier.wait()
            return game.begin_phase_resolution(PHASE_NIGHT)

        with ThreadPoolExecutor(max_workers=8) as executor:
            tokens = list(executor.map(lambda _: claim_phase(), range(8)))

        claimed_tokens = [token for token in tokens if token is not None]
        self.assertEqual(1, len(claimed_tokens))

    def test_only_matching_phase_and_token_can_control_the_claim(self):
        game = Game("claim_test")
        game.phase = PHASE_NIGHT

        token = game.begin_phase_resolution(PHASE_NIGHT)

        self.assertIsNotNone(token)
        self.assertIsNone(game.begin_phase_resolution(PHASE_NIGHT))
        self.assertIsNone(game.begin_phase_resolution(PHASE_ACCUSATION))
        game.finish_phase_resolution(object())
        self.assertTrue(game.is_phase_resolving(PHASE_NIGHT))
        self.assertIsNone(game.begin_phase_resolution(PHASE_NIGHT))

        game.finish_phase_resolution(token)

        self.assertFalse(game.is_phase_resolving())
        self.assertIsNotNone(game.begin_phase_resolution(PHASE_NIGHT))

    def test_actions_do_not_mutate_a_phase_being_resolved(self):
        cases = (
            (PHASE_NIGHT, "receive_night_action", ("actor", "target"), "IGNORED"),
            (
                PHASE_ACCUSATION,
                "process_accusation",
                ("actor", "target"),
                "IGNORED",
            ),
            (PHASE_LYNCH, "cast_lynch_vote", ("actor", "yes"), False),
        )

        for phase, method_name, args, expected_result in cases:
            with self.subTest(phase=phase):
                game = Game("action_rejection_test")
                game.add_player("actor", "Actor")
                game.add_player("target", "Target")
                game.phase = phase
                token = game.begin_phase_resolution(phase)

                result = getattr(game, method_name)(*args)

                self.assertEqual(expected_result, result)
                self.assertEqual({}, game.pending_actions)
                self.assertEqual(set(), game.turn_history)
                game.finish_phase_resolution(token)


class AppResolverSerializationTests(unittest.TestCase):
    def test_phase_transition_allows_new_phase_actions_and_resolution_claim(self):
        app_module.game_instance = Game("phase_transition_claim_test")
        app_module.game_instance.add_player("actor", "Actor")
        app_module.game_instance.add_player("target", "Target")
        app_module.game_instance.phase = PHASE_ACCUSATION
        app_module.game_instance.timers_disabled = True
        app_module.game = {
            "admin_sid": None,
            "game_code": "W",
            "game_admin_code": "ADMIN",
            "game_state": "started",
            "players": {},
        }
        phase_changed = Event()
        release_old_resolver = Event()
        errors = []

        def hold_after_phase_change(_seconds):
            phase_changed.set()
            release_old_resolver.wait(2)

        def run_old_resolver():
            try:
                app_module.perform_tally_accusations()
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        with (
            patch.object(app_module.socketio, "emit"),
            patch.object(
                app_module.socketio,
                "sleep",
                side_effect=hold_after_phase_change,
            ),
            patch.object(app_module, "broadcast_game_state"),
        ):
            old_resolver = Thread(target=run_old_resolver)
            old_resolver.start()
            self.assertTrue(phase_changed.wait(1))

            action_result = app_module.game_instance.receive_night_action(
                "actor", "target"
            )
            new_token = app_module.game_instance.begin_phase_resolution(PHASE_NIGHT)

            release_old_resolver.set()
            old_resolver.join(2)

        self.assertEqual([], errors)
        self.assertFalse(old_resolver.is_alive())
        self.assertEqual("WAITING", action_result)
        self.assertEqual("target", app_module.game_instance.pending_actions["actor"])
        self.assertIsNotNone(new_token)
        self.assertTrue(app_module.game_instance.is_phase_resolving(PHASE_NIGHT))
        app_module.game_instance.finish_phase_resolution(new_token)

    def test_duplicate_resolver_invocations_produce_one_result(self):
        cases = (
            (PHASE_NIGHT, "resolve_night", "resolve_night_deaths", []),
            (
                PHASE_ACCUSATION,
                "perform_tally_accusations",
                "tally_accusations",
                {
                    "result": "night",
                    "message": {
                        "key": "events.accusation_none",
                        "variables": {},
                    },
                },
            ),
            (
                PHASE_LYNCH,
                "resolve_lynch",
                "resolve_lynch_vote",
                {
                    "summary": {"yes": [], "no": []},
                    "killed_id": None,
                    "armor_save": False,
                    "announcements": [],
                    "secondary_deaths": [],
                },
            ),
        )

        for phase, resolver_name, engine_method_name, engine_result in cases:
            with self.subTest(phase=phase):
                app_module.game_instance = Game("resolver_serialization_test")
                app_module.game_instance.phase = phase
                app_module.game = {
                    "admin_sid": None,
                    "game_code": "W",
                    "game_admin_code": "ADMIN",
                    "game_state": "started",
                    "players": {},
                }
                entered = Event()
                duplicate_entered = Event()
                release = Event()
                counter_lock = Lock()
                errors = []
                call_count = 0

                def blocking_resolution():
                    nonlocal call_count
                    with counter_lock:
                        call_count += 1
                        if call_count > 1:
                            duplicate_entered.set()
                    entered.set()
                    release.wait(2)
                    return engine_result

                resolver = getattr(app_module, resolver_name)

                def run_resolver():
                    try:
                        resolver()
                    except Exception as exc:  # pragma: no cover - asserted below
                        errors.append(exc)

                with (
                    patch.object(
                        app_module.game_instance,
                        engine_method_name,
                        side_effect=blocking_resolution,
                    ),
                    patch.object(app_module.socketio, "emit"),
                    patch.object(app_module.socketio, "sleep"),
                    patch.object(app_module, "broadcast_game_state"),
                    patch.object(app_module, "check_game_over_or_next_phase"),
                ):
                    first = Thread(target=run_resolver)
                    second = Thread(target=run_resolver)
                    first.start()
                    self.assertTrue(entered.wait(1))
                    second.start()
                    duplicate_entered.wait(0.2)
                    release.set()
                    first.join(2)
                    second.join(2)

                self.assertEqual([], errors)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertFalse(duplicate_entered.is_set())
                self.assertEqual(1, call_count)
                self.assertEqual(1, len(app_module.game_instance.message_history))


if __name__ == "__main__":
    unittest.main()
