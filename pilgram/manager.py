import json
import os
import pickle
from datetime import timedelta
from typing import List, Dict

from pilgram.classes import Quest, Player, AdventureContainer, Zone
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import ContentMeta
from ui.strings import Strings


MONEY = ContentMeta.get("money.name")


def _gain(xp: int, money: int) -> str:
    return f"\n\nYou gain {xp} xp & {money} {MONEY}"


class _HighestQuests:
    """ records highest reached quest by players per zone, useful to the generator to see what it has to generate """
    FILENAME = "questprogressdata.json"

    def __init__(self):
        self.__data: Dict[int, int] = {}
        if os.path.isfile(self.FILENAME):
            with open(self.FILENAME, "r") as f:
                self.__data = json.load(f)

    def save(self):
        with open(self.FILENAME, "w") as f:
            json.dump(self.__data, f)

    def update(self, zone_id: int, progress: int):
        if self.__data[zone_id] < progress:
            self.__data[zone_id] = progress
            self.save()


class QuestManager:
    """ helper class to neatly manage zone events & quests """

    def __init__(self, database: PilgramDatabase, notifier: PilgramNotifier, update_interval: timedelta):
        self.database = database
        self.notifier = notifier
        self.update_interval = update_interval
        self.highest_quests = _HighestQuests()

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def _complete_quest(self, ac: AdventureContainer):
        quest: Quest = ac.quest
        player: Player = ac.player
        if quest.finish_quest(player):
            xp, money = quest.get_rewards(player)
            player.add_xp(xp)
            player.money += money
            self.highest_quests.update(ac.zone().zone_id, ac.quest.number)
            self.db().update_player_data(player)
            if player.guild:
                player.guild.prestige += quest.get_prestige()
                self.db().update_guild(player.guild)
            self.notifier.notify(player, Strings.quest_success.format(name=quest.name) + _gain(xp, money))
        else:
            ac.quest = None
            self.db().update_quest_progress(ac)
            self.notifier.notify(player, Strings.quest_fail.format(name=quest.name))

    def _process_event(self, ac: AdventureContainer):
        zone = ac.quest.zone if ac.quest else None
        event = self.db().get_random_zone_event(zone)
        xp, money = event.get_rewards(ac.player)
        ac.player.add_xp(xp)
        ac.player.money += money
        self.db().update_player_data(ac.player)
        self.db().update_quest_progress(ac)
        text = f"{event.event_text}\n\n{_gain(xp, money)}"
        self.notifier.notify(ac.player, text)

    def process_update(self, ac: AdventureContainer):
        # TODO add interactions between players in same zone (post launch)
        if ac.is_on_a_quest() and ac.is_quest_finished():
            self._complete_quest(ac)
        else:
            self._process_event(ac)

    def get_updates(self) -> List[AdventureContainer]:
        return self.db().get_all_pending_updates(self.update_interval)


class GeneratorManager:

    def __init__(self, database: PilgramDatabase):
        self.database = database

    def db(self) -> PilgramDatabase:
        """ wrapper around the acquire method to make calling it less verbose """
        return self.database.acquire()

    def get_all_zones(self) -> List[Zone]:
        return self.db().get_all_zones()

    # TODO
