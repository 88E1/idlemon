import argparse
import logging
import os
import sys
from enum import Enum, auto
from logging.handlers import RotatingFileHandler
from typing import Optional


class CustomFormatter(logging.Formatter):
    def format(self, record):
        lvl = "{}".format(record.levelname)
        return "{} {}".format(lvl.ljust(8), record.getMessage())


class CustomRotatingFileHandler(RotatingFileHandler):
    def __init__(self, file_name, **kwargs):
        self.base_dir = "logs"
        if not os.path.exists(self.base_dir):
            os.mkdir(self.base_dir)

        kwargs.setdefault("encoding", "utf-8")
        super().__init__("{}/{}".format(self.base_dir, file_name), **kwargs)

    def do_rollover(self, new_file_name):
        new_file_name = new_file_name.replace("/", "_")
        self.baseFilename = "{}/{}".format(self.base_dir, new_file_name)
        self.doRollover()


def init_logging(level, log_to_file):
    websockets_logger = logging.getLogger("websockets")
    websockets_logger.setLevel(logging.INFO)
    requests_logger = logging.getLogger("urllib3")
    requests_logger.setLevel(logging.INFO)

    # Showdown can send non-cp1252 chars (e.g. the `‽` lock prefix); make sure
    # the Windows console stream won't crash the logger on them.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    # Gets the root logger to set handlers/formatters
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(CustomFormatter())
    logger.addHandler(stdout_handler)
    FoulPlayConfig.stdout_log_handler = stdout_handler

    if log_to_file:
        file_handler = CustomRotatingFileHandler("init.log")
        file_handler.setLevel(logging.DEBUG)  # file logs are always debug
        file_handler.setFormatter(CustomFormatter())
        logger.addHandler(file_handler)
        FoulPlayConfig.file_log_handler = file_handler


class BotModes(Enum):
    challenge_user = auto()
    accept_challenge = auto()
    search_ladder = auto()


class SaveReplay(Enum):
    always = auto()
    never = auto()
    on_loss = auto()


class DecisionMode(Enum):
    heuristic = auto()
    llm = auto()
    agent = auto()  # Cursor chat agent via llm_exchange/ file handoff


class _FoulPlayConfig:
    battle_bot_module: str
    websocket_uri: str
    username: str
    password: str
    avatar: str
    bot_mode: BotModes
    pokemon_format: str = ""
    smogon_stats: str = None
    search_time_ms: int
    parallelism: int
    run_count: int
    team_name: str
    team_list: str = None
    user_to_challenge: str
    save_replay: SaveReplay
    room_name: str
    damage_calc_type: str
    log_level: str
    log_to_file: bool
    decision_mode: DecisionMode
    cursor_api_key: Optional[str]
    llm_model: str
    llm_timeout_ms: int
    stdout_log_handler: logging.StreamHandler
    file_log_handler: Optional[CustomRotatingFileHandler]

    def configure(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--websocket-uri",
            required=True,
            help="The PokemonShowdown websocket URI, e.g. wss://sim3.psim.us/showdown/websocket",
        )
        parser.add_argument("--ps-username", required=True)
        parser.add_argument("--ps-password", required=True)
        parser.add_argument("--ps-avatar", default=None)
        parser.add_argument(
            "--bot-mode", required=True, choices=[e.name for e in BotModes]
        )
        parser.add_argument(
            "--user-to-challenge",
            default=None,
            help="If bot_mode is `challenge_user`, this is required",
        )
        parser.add_argument(
            "--pokemon-format", required=True, help="e.g. gen9randombattle"
        )
        parser.add_argument(
            "--smogon-stats-format",
            default=None,
            help="Overwrite which smogon stats are used to infer unknowns. If not set, defaults to the --pokemon-format value.",
        )
        parser.add_argument(
            "--search-time-ms",
            type=int,
            default=100,
            help="Time to search per battle in milliseconds",
        )
        parser.add_argument(
            "--search-parallelism",
            type=int,
            default=1,
            help="Number of states to search in parallel (unused unless MCTS is re-enabled)",
        )
        parser.add_argument(
            "--run-count",
            type=int,
            default=1,
            help="Number of PokemonShowdown battles to run",
        )
        parser.add_argument(
            "--team-name",
            default=None,
            help="Which team to use. Can be a filename or a foldername relative to ./teams/teams/. "
            "If a foldername, a random team from that folder will be chosen each battle. "
            "If not set, defaults to the --pokemon-format value.",
        )
        parser.add_argument(
            "--save-replay",
            default="never",
            choices=[e.name for e in SaveReplay],
            help="When to save replays",
        )
        parser.add_argument(
            "--team-list",
            default=None,
            help="A path to a text file containing a list of team names to choose from in order. Takes precedence over --team-name.",
        )
        parser.add_argument(
            "--room-name",
            default=None,
            help="If bot_mode is `accept_challenge`, the room to join while waiting",
        )
        parser.add_argument("--log-level", default="DEBUG", help="Python logging level")
        parser.add_argument(
            "--log-to-file",
            action="store_true",
            help="When enabled, DEBUG logs will be written to a file in the logs/ directory",
        )
        parser.add_argument(
            "--decision-mode",
            default="heuristic",
            choices=[e.name for e in DecisionMode],
            help=(
                "How to choose moves: heuristic (default), llm (Cursor SDK), "
                "or agent (this Cursor chat via llm_exchange/ files)"
            ),
        )
        parser.add_argument(
            "--cursor-api-key",
            default=None,
            help="Cursor API key for --decision-mode llm. Falls back to CURSOR_API_KEY env.",
        )
        parser.add_argument(
            "--llm-model",
            default="gemini-3.5-flash",
            help="Cursor model id used when --decision-mode llm (SDK only)",
        )
        parser.add_argument(
            "--llm-timeout-ms",
            type=int,
            default=None,
            help=(
                "Max wait for an LLM/agent decision before heuristic fallback. "
                "Defaults: 12000 (llm), 180000 (agent)"
            ),
        )

        args = parser.parse_args()
        self.websocket_uri = args.websocket_uri
        self.username = args.ps_username
        self.password = args.ps_password
        self.avatar = args.ps_avatar
        self.bot_mode = BotModes[args.bot_mode]
        self.pokemon_format = args.pokemon_format
        self.smogon_stats = args.smogon_stats_format
        self.search_time_ms = args.search_time_ms
        self.parallelism = args.search_parallelism
        self.run_count = args.run_count
        self.team_name = args.team_name or self.pokemon_format
        self.team_list = args.team_list
        self.user_to_challenge = args.user_to_challenge
        self.save_replay = SaveReplay[args.save_replay]
        self.room_name = args.room_name
        self.log_level = args.log_level
        self.log_to_file = args.log_to_file
        self.decision_mode = DecisionMode[args.decision_mode]
        self.cursor_api_key = args.cursor_api_key or os.environ.get("CURSOR_API_KEY")
        self.llm_model = args.llm_model
        if args.llm_timeout_ms is not None:
            self.llm_timeout_ms = args.llm_timeout_ms
        elif self.decision_mode == DecisionMode.agent:
            self.llm_timeout_ms = 180000
        else:
            self.llm_timeout_ms = 12000
        self.validate_config()

    def validate_config(self):
        if self.bot_mode == BotModes.challenge_user:
            assert (
                self.user_to_challenge is not None
            ), "If bot_mode is `CHALLENGE_USER, you must declare USER_TO_CHALLENGE"
        if self.decision_mode == DecisionMode.llm:
            assert self.cursor_api_key, (
                "decision-mode llm requires --cursor-api-key or CURSOR_API_KEY"
            )


FoulPlayConfig = _FoulPlayConfig()
