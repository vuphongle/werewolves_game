"""
config.py
Version: 5.2.6.2
Central location for all game defaults and timer settings.
"""
import os


admin_code = os.environ.get("GAME_ADMIN_CODE", "").strip().upper() or None

GAME_DEFAULTS = {
    # Time (in seconds)
    "DEFAULT_CODE": "W",
    "DEFAULT_ADMIN_CODE": admin_code,
    "DEFAULT_LANGUAGE": "vi",
    "DEFAULT_ROLES": ["Villager", "Werewolf", "Seer"],
    "ENABLE_PASS_AND_PLAY": False,
    "MIN_PLAYERS": 4,
    "PAUSE_DURATION": 3,
    "TIME_NIGHT": 90,
    "TIME_ACCUSATION": 90,
    "TIME_LYNCH": 30,
    "WOLF_RATIO": 0.25,
}
