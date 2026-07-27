from __future__ import annotations

import itertools
import ntpath
import random
from dataclasses import dataclass

import requests
from dateutil import relativedelta
from datetime import datetime
import os
import json
import logging
from typing import Optional


import constants
from data import all_move_json, pokedex
from fp.battle import Pokemon, Battler, Battle, StatRange
from fp.helpers import calculate_stats, natures
from fp.helpers import normalize_name

PWD = os.path.dirname(os.path.abspath(__file__))
SMOGON_CACHE_DIR = os.path.join(PWD, "smogon_stats_cache")
os.makedirs(SMOGON_CACHE_DIR, exist_ok=True)

OTHER_STRING = "other"
MOVES_STRING = "moves"
ITEM_STRING = "items"
SPREADS_STRING = "spreads"
ABILITY_STRING = "abilities"
TERA_TYPE_STRING = "tera_types"
EFFECTIVENESS = "effectiveness"
TEAMMATES = "teammates"
RAW_COUNT = "raw_count"


logger = logging.getLogger(__name__)
PWD = os.path.dirname(os.path.abspath(__file__))


def spreads_are_alike(s1, s2):
    if s1[0] != s2[0]:
        return False

    s1 = [int(v) for v in s1[1].split(",")]
    s2 = [int(v) for v in s2[1].split(",")]

    diff = [abs(i - j) for i, j in zip(s1, s2)]

    # 24 is arbitrarily chosen as the threshold for EVs to be "alike"
    return all(v <= 48 for v in diff)


def get_default_sets():
    natures = [
        "adamant",
        "jolly",
        "modest",
        "timid",
        "bold",
        "impish",
        "calm",
        "careful",
    ]
    evs = [
        # bulky
        (252, 0, 0, 0, 4, 252),
        (252, 0, 252, 0, 4, 0),
        (252, 0, 200, 0, 56, 0),
        (252, 0, 4, 0, 252, 0),
        (252, 0, 56, 0, 200, 0),
        (200, 0, 0, 0, 56, 252),
        (200, 0, 56, 0, 0, 252),
        (200, 0, 252, 0, 56, 0),
        (200, 0, 56, 0, 252, 0),
        # physically offensive
        (0, 252, 0, 0, 4, 252),
        (52, 252, 0, 0, 4, 200),
        (104, 252, 0, 0, 4, 200),
        (52, 200, 0, 0, 4, 252),
        (104, 200, 0, 0, 4, 200),
        (156, 200, 0, 0, 4, 200),
        # specially offensive
        (0, 0, 0, 252, 4, 252),
        (52, 0, 0, 252, 4, 200),
        (104, 0, 0, 252, 4, 148),
        (52, 0, 0, 200, 4, 252),
        (104, 0, 0, 200, 4, 200),
        (156, 0, 0, 200, 4, 148),
    ]

    ret = []
    for nature, ev in itertools.product(natures, evs):
        ret.append(
            PokemonSpread(
                nature=nature,
                evs=tuple(ev),
                count=1,
            )
        )
    return ret


@dataclass
class PokemonSpread:
    nature: str
    evs: tuple[int, ...] | list[int]
    count: int

    def spread_makes_sense(self, pkmn: Pokemon):
        if self.evs[3] > 50 or natures[self.nature]["plus"] == constants.SPECIAL_ATTACK:
            has_special_move = any(
                all_move_json.get(mv.name, {}).get(constants.CATEGORY, "")
                == constants.SPECIAL
                for mv in pkmn.moves
            )
            if not has_special_move:
                return False

        if self.evs[1] > 50 or natures[self.nature]["plus"] == constants.ATTACK:
            has_physical_move = any(
                all_move_json.get(mv.name, {}).get(constants.CATEGORY, "")
                == constants.PHYSICAL
                for mv in pkmn.moves
            )
            if not has_physical_move:
                return False

        stats = calculate_stats(
            pkmn.base_stats,
            pkmn.level,
            evs=self.evs,
            nature=self.nature,
        )
        return pkmn.speed_range.min <= stats[constants.SPEED] <= pkmn.speed_range.max


def find_pkmn(pkmn_name: str, pkmn_list: list[Pokemon]):
    for pkmn in pkmn_list:
        if pkmn.name == pkmn_name or normalize_name(pkmn.name) == normalize_name(
            pkmn_name
        ):
            return pkmn

    for pkmn in pkmn_list:
        if normalize_name(pokedex[pkmn.name].get("baseSpecies", "")) == normalize_name(
            pkmn_name
        ):
            return pkmn
        if normalize_name(pokedex[pkmn.name].get("battleOnly", "")) == normalize_name(
            pkmn_name
        ):
            return pkmn
        if pkmn_name in [
            normalize_name(n) for n in pokedex[pkmn.name].get("otherFormes", "")
        ]:
            return pkmn


class _SmogonSets:
    def __init__(self):
        self.current_pkmn_sets_url = ""
        self.raw_pkmn_sets = {}
        self.all_pkmn_counts = {}
        self.pkmn_sets = {}
        self.pkmn_speed_ranges = {}
        self.pkmn_mode = "uninitialized"

    def _pokemon_is_similar(self, normalized_name, list_of_pkmn_names):
        return any(normalized_name.startswith(n) for n in list_of_pkmn_names) or any(
            n.startswith(normalized_name) for n in list_of_pkmn_names
        )

    def _get_smogon_stats_json(self, smogon_stats_url):
        cache_file_name = ntpath.basename(smogon_stats_url)
        cache_file = os.path.join(SMOGON_CACHE_DIR, cache_file_name)
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                infos = json.load(f)
        else:
            r = requests.get(smogon_stats_url)
            if r.status_code == 404:
                r = requests.get(
                    self._get_smogon_stats_file_name(
                        ntpath.basename(smogon_stats_url.replace("-0.json", "")),
                        month_delta=2,
                    )
                )
            infos = r.json()["data"]
            with open(cache_file, "w") as f:
                json.dump(infos, f)

        return infos

    def _get_pokemon_information(self, smogon_stats_url, pkmn_names) -> dict:
        infos = self._get_smogon_stats_json(smogon_stats_url)
        self.all_pkmn_counts.clear()

        final_infos = {}
        final_effectiveness = {}
        for pkmn_name, pkmn_information in infos.items():
            normalized_name = normalize_name(pkmn_name)
            self.all_pkmn_counts[normalized_name] = {}
            self.all_pkmn_counts[normalized_name][RAW_COUNT] = pkmn_information[
                "Raw count"
            ]
            self.all_pkmn_counts[normalized_name][TEAMMATES] = {}
            for teammate_name, teammate_count in pkmn_information["Teammates"].items():
                self.all_pkmn_counts[normalized_name][TEAMMATES][
                    normalize_name(teammate_name)
                ] = teammate_count

            # if `pkmn_names` is provided, only find data on pkmn in that list
            if (
                pkmn_names
                and normalized_name not in pkmn_names
                and not self._pokemon_is_similar(normalized_name, pkmn_names)
            ):
                continue
            else:
                logger.debug(
                    "Adding {} to sets lookup for this battle".format(normalized_name)
                )

            spreads = []
            total_count = pkmn_information["Raw count"]
            final_infos[normalized_name] = {}

            for counter_name, counter_information in pkmn_information[
                "Checks and Counters"
            ].items():
                counter_name = normalize_name(counter_name)
                if counter_name in pkmn_names:
                    if counter_name not in final_effectiveness:
                        final_effectiveness[counter_name] = {}
                    final_effectiveness[counter_name][normalize_name(pkmn_name)] = (
                        round(counter_information["p"], 2)
                    )

            for spread, count in sorted(
                pkmn_information["Spreads"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = count / total_count
                if percentage > 0:
                    nature, evs = [normalize_name(i) for i in spread.split(":")]
                    evs = evs.replace("/", ",")
                    for sp in spreads:
                        if spreads_are_alike(sp, (nature, evs)):
                            sp[2] += percentage
                            break
                    else:
                        spreads.append([nature, evs, percentage])

            final_infos[normalized_name][SPREADS_STRING] = sorted(
                spreads, key=lambda x: x[2], reverse=True
            )[:100]

        for k, v in final_infos.items():
            v[EFFECTIVENESS] = final_effectiveness.get(k, {})

        for k in list(final_infos.keys()):
            v = final_infos[k]
            for other_forme in pokedex[k].get("otherFormes", []):
                if normalize_name(other_forme) not in final_infos:
                    final_infos[normalize_name(other_forme)] = v
            for other_forme in pokedex[k].get("cosmeticFormes", []):
                if normalize_name(other_forme) not in final_infos:
                    final_infos[normalize_name(other_forme)] = v

        return final_infos

    def _get_smogon_stats_file_name(self, game_mode, month_delta=1):
        """
        Gets the smogon stats url based on the game mode
        Uses the previous-month's statistics
        """

        if game_mode.endswith("blitz"):
            game_mode = game_mode[:-5]

        # always use the `-0` file - the higher ladder is for noobs
        smogon_url = "https://www.smogon.com/stats/{}-{}/chaos/{}-0.json"

        previous_month = datetime.now() - relativedelta.relativedelta(
            months=month_delta
        )
        year = previous_month.year
        month = "{:02d}".format(previous_month.month)

        return smogon_url.format(year, month, game_mode)

    def _pokemon_set_makes_sense(self, pkmn: Pokemon, pkmn_set: PokemonSpread):
        # without a large amount in an offensive stat life orb and expert belt don't make sense
        if pkmn.item in ["lifeorb", "expertbelt"] and (
            pkmn_set.evs[1] < 200 and pkmn_set.evs[3] < 200
        ):
            return False

        return True

    def _initialize(self, raw_pkmn_sets: dict, opponent: Battler):
        for pkmn in opponent.reserve:
            pkmn_name = normalize_name(pkmn.name)
            if pkmn_name not in raw_pkmn_sets:
                logger.warning("No sets found for {} in smogon stats".format(pkmn_name))
                continue
            sets = raw_pkmn_sets[pkmn_name]
            pkmn = find_pkmn(pkmn_name, opponent.reserve)
            self.pkmn_sets[pkmn_name] = []
            for spread in sets[SPREADS_STRING]:
                pkmn_set = PokemonSpread(
                    nature=spread[0],
                    evs=tuple(int(i) for i in spread[1].split(",")),
                    count=spread[2],
                )
                if self._pokemon_set_makes_sense(pkmn, pkmn_set):
                    self.pkmn_sets[pkmn_name].append(pkmn_set)
            self.pkmn_sets[pkmn_name].sort(key=lambda x: x.count, reverse=True)
            self.pkmn_speed_ranges[pkmn_name] = StatRange(min=0, max=float("inf"))

    def save_speed_ranges(self, battle: Battle):
        for pkmn in battle.opponent.reserve + [
            battle.opponent.slot_a.active,
            battle.opponent.slot_b.active,
        ]:
            if pkmn is None:
                continue
            pkmn_name = normalize_name(pkmn.name)
            if pkmn_name not in self.pkmn_speed_ranges:
                continue
            speed_range = self.pkmn_speed_ranges[pkmn_name]
            if pkmn.speed_range.min > speed_range.min:
                logger.info(
                    "Remembering min speed for {}: {}".format(
                        pkmn_name, pkmn.speed_range.min
                    )
                )
                speed_range.min = pkmn.speed_range.min
            if pkmn.speed_range.max < speed_range.max:
                logger.info(
                    "Remembering max speed for {}: {}".format(
                        pkmn_name, pkmn.speed_range.max
                    )
                )
                speed_range.max = pkmn.speed_range.max

    def load_speed_ranges(self, battle: Battle):
        for pkmn in battle.opponent.reserve + [
            battle.opponent.slot_a.active,
            battle.opponent.slot_b.active,
        ]:
            if pkmn is None:
                continue
            pkmn_name = normalize_name(pkmn.name)
            if pkmn_name not in self.pkmn_speed_ranges:
                continue
            speed_range = self.pkmn_speed_ranges[pkmn_name]
            pkmn.speed_range.min = speed_range.min
            pkmn.speed_range.max = speed_range.max
            logger.debug(
                "Remembered speed range for {}: {}-{}".format(
                    pkmn_name, pkmn.speed_range.min, pkmn.speed_range.max
                )
            )

    def initialize(self, pkmn_mode: str, battle: Battle):
        opponent = battle.opponent
        pkmn_names = set(
            p.name
            for p in battle.opponent.reserve
            + battle.user.reserve
            + [battle.user.slot_a.active, battle.user.slot_b.active]
        )
        self.pkmn_mode = pkmn_mode
        smogon_stats_url = self._get_smogon_stats_file_name(pkmn_mode)
        if self.current_pkmn_sets_url != smogon_stats_url:
            self.raw_pkmn_sets = self._get_pokemon_information(
                smogon_stats_url, pkmn_names
            )
            self.current_pkmn_sets_url = smogon_stats_url
        else:
            new_pkmn_names = [p for p in pkmn_names if p not in self.raw_pkmn_sets]
            if new_pkmn_names:
                self.raw_pkmn_sets = self._get_pokemon_information(
                    smogon_stats_url, pkmn_names
                )

        self._initialize(self.raw_pkmn_sets, opponent)

    def get_random_spread(self, pkmn: Pokemon) -> Optional[PokemonSpread]:
        if not self.pkmn_sets:
            logger.warning("Called `predict_set` when pkmn_sets was empty")

        spreads = self.get_pokemon_from_sets(pkmn.name)
        if not spreads:
            return None

        tries = 0
        while tries < 20:
            pkmn_spread = random.choices(
                spreads, weights=[s.count for s in spreads], k=1
            )[0]
            if pkmn_spread.spread_makes_sense(pkmn):
                return pkmn_spread
            tries += 1

        return random.choices(spreads, weights=[s.count for s in spreads], k=1)[0]

    def get_pokemon_from_sets(self, pkmn_name: str):
        pkmn_sets = self.pkmn_sets.get(pkmn_name)
        if pkmn_sets:
            return pkmn_sets

        battle_only = normalize_name(pokedex[pkmn_name].get("battleOnly", ""))
        pkmn_sets = self.pkmn_sets.get(battle_only)
        if pkmn_sets:
            return pkmn_sets

        base_species = normalize_name(pokedex[pkmn_name].get("baseSpecies", ""))
        pkmn_sets = self.pkmn_sets.get(base_species)
        if pkmn_sets:
            return pkmn_sets

        logger.warning("No sets found for {}, setting default sets".format(pkmn_name))
        self.pkmn_sets[pkmn_name] = get_default_sets()
        return self.pkmn_sets[pkmn_name]


SmogonSets = _SmogonSets()
