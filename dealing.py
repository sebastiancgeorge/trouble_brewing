"""Random, rules-valid role dealing for a Trouble Brewing or Bad Moon Rising game."""

import random

from roles import (CHARACTERS, DEMON, MINION, OUTSIDER, SCRIPTS, SETUP_COUNTS, TOWNSFOLK, TROUBLE_BREWING,
                   ids_of, is_good)


def pick_characters(players: int, rng: random.Random, script: str = TROUBLE_BREWING) -> list[str]:
    """Choose which characters are in play for a player count.

    Algorithm: look up the base (townsfolk, outsiders, minions, demons) counts, draw the Minions
    first, and adjust the Outsider count for setup Minions: the Baron swaps two Townsfolk slots
    for Outsiders; the Godfather swaps one either way, at random (always +1 when there are no
    Outsiders to take away). Then draw that many Townsfolk and Outsiders without replacement, and
    one Demon from the script.

    Args:
        players (int): 5-15.
        rng (random.Random): randomness source.
        script (str): script id, a key of SCRIPTS.

    Returns:
        list[str]: character ids, one per player, unshuffled.
    """
    if players not in SETUP_COUNTS:
        raise ValueError(f"{SCRIPTS[script]['name']} supports 5-15 players, got {players}")
    tf, out, mn, _ = SETUP_COUNTS[players]
    minions = rng.sample(ids_of(MINION, script), mn)
    if "baron" in minions:
        tf, out = tf - 2, out + 2
    if "godfather" in minions:
        shift = 1 if out == 0 else rng.choice((1, -1))
        tf, out = tf - shift, out + shift
    return (rng.sample(ids_of(TOWNSFOLK, script), tf) + rng.sample(ids_of(OUTSIDER, script), out) + minions
            + [rng.choice(ids_of(DEMON, script))])


def deal(pids: list[str], rng: random.Random, script: str = TROUBLE_BREWING) -> dict:
    """Deal characters to players and make the Storyteller's hidden setup choices.

    Algorithm: pick the characters in play and shuffle them onto the players. If the Drunk is in
    play, give them a random Townsfolk that is not in play to believe in; a Lunatic believes they
    are a random Demon from the script. On Trouble Brewing pick a random good player as the Fortune
    Teller's red herring; with a Grandmother, pick a random other good player as her grandchild.
    Pick three good characters from the script that are not in play, not the Drunk's fake role,
    and not the Drunk itself as the Demon's bluffs.

    Args:
        pids (list[str]): public player ids in seat order.
        rng (random.Random): randomness source.
        script (str): script id, a key of SCRIPTS.

    Returns:
        dict with keys:
            characters  (dict[str, str]) pid -> true character id
            believed    (dict[str, str]) pid -> character the player is told (differs for the Drunk and Lunatic)
            red_herring (str | None) pid, Trouble Brewing only
            grandchild  (str | None) pid, only with a Grandmother in play
            bluffs      (list[str]) three character ids
    """
    chars = pick_characters(len(pids), rng, script)
    rng.shuffle(chars)
    characters = dict(zip(pids, chars))
    in_play = set(chars)

    drunk_as = None
    if "drunk" in in_play:
        drunk_as = rng.choice([t for t in ids_of(TOWNSFOLK, script) if t not in in_play])
    lunatic_as = rng.choice(ids_of(DEMON, script)) if "lunatic" in in_play else None
    believed = {pid: drunk_as if c == "drunk" else lunatic_as if c == "lunatic" else c
                for pid, c in characters.items()}

    good = [pid for pid, c in characters.items() if is_good(c)]
    red_herring = rng.choice(good) if script == TROUBLE_BREWING else None
    grandchild = None
    if "grandmother" in in_play:
        grandchild = rng.choice([pid for pid in good if characters[pid] != "grandmother"])
    # nobody knowingly claims Drunk, so it is never a useful bluff
    bluff_pool = [c for c in CHARACTERS
                  if CHARACTERS[c]["script"] == script and is_good(c) and c not in in_play | {drunk_as, "drunk"}]
    return {
        "characters": characters,
        "believed": believed,
        "red_herring": red_herring,
        "grandchild": grandchild,
        "bluffs": rng.sample(bluff_pool, 3),
    }


if __name__ == "__main__":
    for script in SCRIPTS:
        result = deal([f"p{i}" for i in range(1, 10)], random.Random(), script)
        print(SCRIPTS[script]["name"])
        for pid, c in result["characters"].items():
            shown = result["believed"][pid]
            note = f" (thinks {CHARACTERS[shown]['name']})" if shown != c else ""
            print(f"  {pid}: {CHARACTERS[c]['name']}{note}")
        print("  red herring:", result["red_herring"], "grandchild:", result["grandchild"])
        print("  bluffs:", [CHARACTERS[b]["name"] for b in result["bluffs"]])
