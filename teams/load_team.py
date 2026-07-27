import random
import os
from .team_converter import export_to_packed, export_to_dict

TEAM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teams")


class TeamListIterator:
    def __init__(self, team_list_file):
        with open(os.path.join(TEAM_DIR, team_list_file), "r") as f:
            lines = f.readlines()
        self.team_names = [line.strip() for line in lines]
        self.index = 0

    def get_next_team(self):
        if not self.team_names:
            raise ValueError("Team list is empty")
        team_name = self.team_names[self.index]
        self.index = (self.index + 1) % len(self.team_names)
        return team_name


def load_team(name):
    if name is None:
        return "null", "", ""

    path = os.path.join(TEAM_DIR, "{}".format(name))
    if os.path.isdir(path):
        team_file_names = list()
        for f in os.listdir(path):
            full_path = os.path.join(path, f)
            if os.path.isfile(full_path) and not f.startswith("."):
                team_file_names.append(full_path)
        file_path = random.choice(team_file_names)

    elif os.path.isfile(path):
        file_path = path
    else:
        raise ValueError("Path must be file or dir: {}".format(name))

    with open(file_path, "r") as f:
        team_export = f.read()

    return (
        export_to_packed(team_export),
        export_to_dict(team_export),
        os.path.basename(file_path),
    )
