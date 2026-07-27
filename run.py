import asyncio
import json
import logging
import traceback
from copy import deepcopy
from config import FoulPlayConfig, init_logging, BotModes

from teams import load_team, TeamListIterator
from fp.run_battle import pokemon_battle
from fp.websocket_client import PSWebsocketClient

from data import all_move_json
from data import pokedex
from data.mods.apply_mods import apply_mods


logger = logging.getLogger(__name__)


def check_dictionaries_are_unmodified(original_pokedex, original_move_json):
    # The bot should not modify the data dictionaries
    # This is a "just-in-case" check to make sure and will stop the bot if it mutates either of them
    if original_move_json != all_move_json:
        logger.critical(
            "Move JSON changed!\nDumping modified version to `modified_moves.json`"
        )
        with open("modified_moves.json", "w") as f:
            json.dump(all_move_json, f, indent=4)
        exit(1)
    else:
        logger.debug("Move JSON unmodified!")

    if original_pokedex != pokedex:
        logger.critical(
            "Pokedex JSON changed!\nDumping modified version to `modified_pokedex.json`"
        )
        with open("modified_pokedex.json", "w") as f:
            json.dump(pokedex, f, indent=4)
        exit(1)
    else:
        logger.debug("Pokedex JSON unmodified!")


async def run_foul_play():
    FoulPlayConfig.configure()
    init_logging(FoulPlayConfig.log_level, FoulPlayConfig.log_to_file)
    apply_mods(FoulPlayConfig.pokemon_format)

    original_pokedex = deepcopy(pokedex)
    original_move_json = deepcopy(all_move_json)

    ps_websocket_client = await PSWebsocketClient.create(
        FoulPlayConfig.username, FoulPlayConfig.password, FoulPlayConfig.websocket_uri
    )
    await ps_websocket_client.login()

    if FoulPlayConfig.avatar is not None:
        await ps_websocket_client.avatar(FoulPlayConfig.avatar)

    team_iterator = (
        None
        if FoulPlayConfig.team_list is None
        else TeamListIterator(FoulPlayConfig.team_list)
    )
    battles_run = 0
    wins = 0
    losses = 0
    while True:
        team_name = (
            team_iterator.get_next_team()
            if team_iterator is not None
            else FoulPlayConfig.team_name
        )
        team_export, team_dict, file_name = load_team(team_name)
        if FoulPlayConfig.bot_mode == BotModes.challenge_user:
            await ps_websocket_client.challenge_user(
                FoulPlayConfig.user_to_challenge,
                FoulPlayConfig.pokemon_format,
                team_export,
            )
        elif FoulPlayConfig.bot_mode == BotModes.accept_challenge:
            await ps_websocket_client.accept_challenge(
                FoulPlayConfig.pokemon_format, team_export, FoulPlayConfig.room_name
            )
        elif FoulPlayConfig.bot_mode == BotModes.search_ladder:
            await ps_websocket_client.search_for_match(
                FoulPlayConfig.pokemon_format, team_export
            )
        else:
            raise ValueError("Invalid Bot Mode: {}".format(FoulPlayConfig.bot_mode))

        best_of_3_wins = 0
        best_of_3_loss = 0
        is_bo3 = "bo3" in FoulPlayConfig.pokemon_format.lower()
        if is_bo3:
            best_of_3_room_name = await _get_best_of_3_room_name(ps_websocket_client)
            logger.info("Bo3 room name: {}".format(best_of_3_room_name))
        else:
            best_of_3_room_name = None
            logger.info("Non-Bo3 format; skipping bo3 room wait")
        first_battle = True
        while best_of_3_wins < 2 and best_of_3_loss < 2:
            winner, bo3_done = await pokemon_battle(
                ps_websocket_client,
                FoulPlayConfig.pokemon_format,
                best_of_3_room_name,
                first_battle,
            )
            first_battle = False
            if winner == FoulPlayConfig.username:
                best_of_3_wins += 1
                logger.info("Won with team: {}".format(file_name))
            else:
                best_of_3_loss += 1
                logger.info("Lost with team: {}".format(file_name))

            logger.info("This Set W: {}\tL: {}".format(best_of_3_wins, best_of_3_loss))
            check_dictionaries_are_unmodified(original_pokedex, original_move_json)

            if bo3_done or not is_bo3:
                break

            if best_of_3_wins == 2 or best_of_3_loss == 2:
                break
            await ps_websocket_client.send_message(
                best_of_3_room_name, [f"/msgroom {best_of_3_room_name},/confirmready"]
            )

        logger.info("Set complete W: {}\tL: {}".format(best_of_3_wins, best_of_3_loss))
        if best_of_3_room_name is not None:
            await ps_websocket_client.leave_battle(best_of_3_room_name)

        if best_of_3_wins > best_of_3_loss:
            wins += 1
        else:
            losses += 1
        logger.info("Total Wins: {}".format(wins))
        logger.info("Total Losses: {}".format(losses))

        battles_run += 1
        if battles_run >= FoulPlayConfig.run_count:
            break
    await ps_websocket_client.close()


async def _get_best_of_3_room_name(ps_websocket_client: PSWebsocketClient):
    s = ">game-bestof3-"
    while True:
        msg = await ps_websocket_client.receive_message()
        if msg.startswith(s):
            return msg.split("\n")[0][1:].strip()


if __name__ == "__main__":
    try:
        asyncio.run(run_foul_play())
    except Exception:
        logger.error(traceback.format_exc())
        raise
