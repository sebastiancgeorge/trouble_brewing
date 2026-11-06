"""Character data, setup table, and night order for the Trouble Brewing and Bad Moon Rising scripts.

CHARACTERS schema: dict[str, dict] keyed by character id (snake_case), each value:
    name     (str) display name
    type     (str) one of TOWNSFOLK / OUTSIDER / MINION / DEMON
    script   (str) script id the character belongs to (a key of SCRIPTS)
    icon     (str) file name under static/icons/
    summary  (str) one-line ability summary
    ability  (str) full ability text shown to the holder
    timing   (str) when the ability acts, e.g. "Every night except the first"
    flavour  (str) in-world quote shown in the almanac

SETUP_COUNTS schema: dict[int, tuple[int, int, int, int]]
    player count -> (townsfolk, outsiders, minions, demons), before the Baron's or Godfather's adjustment.

SCRIPTS schema: dict[str, dict] keyed by script id, each value:
    name         (str) display name
    first_night  (list[str]) night order on night 1
    other_nights (list[str]) night order on later nights

NIGHT_CHOICES schema: dict[str, tuple[int, bool, str]]
    step key -> (players to choose, may choose self, prompt shown on the player's phone).
"""

TOWNSFOLK, OUTSIDER, MINION, DEMON = "townsfolk", "outsider", "minion", "demon"
TROUBLE_BREWING, BAD_MOON_RISING = "trouble_brewing", "bad_moon_rising"

CHARACTERS = {
    # --- townsfolk ---
    "washerwoman": {
        "name": "Washerwoman", "type": TOWNSFOLK,
        "summary": "Learns that one of two players is a specific Townsfolk.",
        "ability": "On the first night, you are shown a Townsfolk character, then shown two players. "
                   "One of those two players is that character.",
        "timing": "First night only",
        "flavour": "I've done his laundry for years — I know his habits better than he does.",
    },
    "librarian": {
        "name": "Librarian", "type": TOWNSFOLK,
        "summary": "Learns that one of two players is a specific Outsider.",
        "ability": "On the first night, you are shown an Outsider character, then shown two players. "
                   "One of those two players is that character - or, if there are no Outsiders in this "
                   "game, you are told that instead.",
        "timing": "First night only",
        "flavour": "The card catalogue never lies. The people who read it, on the other hand...",
    },
    "investigator": {
        "name": "Investigator", "type": TOWNSFOLK,
        "summary": "Learns that one of two players is a specific Minion.",
        "ability": "On the first night, you are shown a Minion character, then shown two players. "
                   "One of those two players is that character.",
        "timing": "First night only",
        "flavour": "Somewhere in this town, someone is lying to everyone they know.",
    },
    "chef": {
        "name": "Chef", "type": TOWNSFOLK,
        "summary": "Learns how many pairs of evil players are sitting next to each other.",
        "ability": "On the first night, you learn how many pairs of evil players there are. A pair is two "
                   "evil players seated directly beside one another; three evil players in a row counts "
                   "as two pairs.",
        "timing": "First night only",
        "flavour": "You can tell a lot about two people by whether they'll sit next to each other.",
    },
    "empath": {
        "name": "Empath", "type": TOWNSFOLK,
        "summary": "Learns how many of their living neighbours are evil.",
        "ability": "Every night, you learn how many of your two living neighbours are evil. Your neighbours "
                   "are the nearest living players seated to your left and right - this can change as "
                   "players die during the game.",
        "timing": "Every night",
        "flavour": "I don't need to hear a confession. I can just feel it, sitting this close.",
    },
    "fortune_teller": {
        "name": "Fortune Teller", "type": TOWNSFOLK,
        "summary": "Each night, checks two players for the Demon.",
        "ability": "Every night, choose two players - you learn whether either of them is the Demon. "
                   "At the start of the game, the Storyteller secretly chooses one good player who will always "
                   "register as the Demon to you, for the rest of the game.",
        "timing": "Every night",
        "flavour": "The cards show me many things. Some of them, I suspect, are lies too.",
    },
    "undertaker": {
        "name": "Undertaker", "type": TOWNSFOLK,
        "summary": "Learns the character of whoever was executed that day.",
        "ability": "Every night except the first, if a player was executed that day, you learn their character.",
        "timing": "Every night, if an execution happened",
        "flavour": "By the time they reach me, everyone tells the truth.",
    },
    "monk": {
        "name": "Monk", "type": TOWNSFOLK,
        "summary": "Protects one player from the Demon each night.",
        "ability": "Every night except the first, choose a player other than yourself. They cannot be "
                   "killed by the Demon that night.",
        "timing": "Every night except the first",
        "flavour": "Vigilance is a form of devotion.",
    },
    "ravenkeeper": {
        "name": "Ravenkeeper", "type": TOWNSFOLK,
        "summary": "If killed at night, learns one player's character.",
        "ability": "If you are killed during the night, you wake immediately to choose a player, and you "
                   "learn their character.",
        "timing": "Triggered on death at night",
        "flavour": "Even in my last moment, I'll know something you don't.",
    },
    "virgin": {
        "name": "Virgin", "type": TOWNSFOLK,
        "summary": "The first Townsfolk to nominate them is executed instantly.",
        "ability": "The first time you are nominated, if your nominator is a Townsfolk, they are executed "
                   "immediately. Your ability is spent on that first nomination, whatever the outcome.",
        "timing": "Triggered on nomination",
        "flavour": "They should have asked someone else first.",
    },
    "slayer": {
        "name": "Slayer", "type": TOWNSFOLK,
        "summary": "Once per game, can publicly attempt to kill the Demon.",
        "ability": "Once per game, during the day, publicly choose a player. If they are the Demon, they die. "
                   "Your ability is spent either way, whether or not you chose correctly.",
        "timing": "Once per game, during the day",
        "flavour": "One shot. I intend to make it count.",
    },
    "soldier": {
        "name": "Soldier", "type": TOWNSFOLK,
        "summary": "Cannot be killed by the Demon.",
        "ability": "You cannot be killed by the Demon. You can still be executed, and you can still be "
                   "killed by other means.",
        "timing": "Always active",
        "flavour": "I've survived worse nights than this.",
    },
    "mayor": {
        "name": "Mayor", "type": TOWNSFOLK,
        "summary": "May win the game outright, and may survive the Demon's attack.",
        "ability": "If only three players are alive and no execution happens that day, your team wins. If the "
                   "Demon tries to kill you at night, the Storyteller may choose for a different player to die instead.",
        "timing": "Always active / triggered",
        "flavour": "This town survives because I refuse to let it fall.",
    },
    # --- outsiders ---
    "butler": {
        "name": "Butler", "type": OUTSIDER,
        "summary": "Can only vote when their chosen Master also votes.",
        "ability": "Every night, choose another player to be your Master for the next day. The next day, you may "
                   "only vote on a nomination if your Master also votes on it. You may still nominate freely - the restriction "
                   "is only on voting.",
        "timing": "Every night",
        "flavour": "I go where I'm told. It's simpler that way.",
    },
    "drunk": {
        "name": "Drunk", "type": OUTSIDER,
        "summary": "Believes they're a Townsfolk, but their ability doesn't work.",
        "ability": "You do not know you are the Drunk. You believe you are a specific Townsfolk character, and you "
                   "play the game thinking that is who you are - but that character's ability does not work, and anything it seems to tell you may be false.",
        "timing": "Always active",
        "flavour": "Of course I remember what I saw last night. Mostly.",
    },
    "recluse": {
        "name": "Recluse", "type": OUTSIDER,
        "summary": "May appear evil to other players' abilities.",
        "ability": "You may appear evil, and even as a specific Minion or Demon, to other players' abilities, "
                   "even though you are good. This may happen or not happen each time.",
        "timing": "Always active",
        "flavour": "They watch me from a distance and assume the worst. Good.",
    },
    "saint": {
        "name": "Saint", "type": OUTSIDER,
        "summary": "If executed, good instantly loses the game.",
        "ability": "If you are executed, your team loses the game immediately. Dying any other way is harmless.",
        "timing": "Triggered on execution",
        "flavour": "Be certain before you point that finger at me.",
    },
    # --- minions ---
    "poisoner": {
        "name": "Poisoner", "type": MINION,
        "summary": "Each night, makes one player's ability malfunction.",
        "ability": "Every night, choose a player. Their ability malfunctions for the rest of that night and the "
                   "following day - anything they learn may be false, and they will not be told.",
        "timing": "Every night",
        "flavour": "A single drop, and their certainty becomes doubt.",
    },
    "spy": {
        "name": "Spy", "type": MINION,
        "summary": "Sees the full truth of every player, every night.",
        "ability": "Every night, you may look at the Grimoire - the Storyteller's private book that shows "
                   "everyone's character and current status. You may also appear as good, and as a specific Townsfolk "
                   "or Outsider, to other players' abilities.",
        "timing": "Every night",
        "flavour": "I already know your secret. I'm just deciding what to do with it.",
    },
    "scarlet_woman": {
        "name": "Scarlet Woman", "type": MINION,
        "summary": "May inherit the Demon's power if it dies.",
        "ability": "If the Demon dies while five or more players are alive, you become the new Demon.",
        "timing": "Triggered if the Demon dies",
        "flavour": "Someone has to carry on the work.",
    },
    "baron": {
        "name": "Baron", "type": MINION,
        "summary": "Adds extra Outsiders to the game.",
        "ability": "There are two extra Outsiders in this game, in place of two Townsfolk.",
        "timing": "Setup only",
        "flavour": "Chaos is so much easier to fund than order.",
    },
    # --- demon ---
    "imp": {
        "name": "Imp", "type": DEMON,
        "summary": "Kills a player each night - and can pass on the role.",
        "ability": "Every night except the first, choose a player to kill. You may choose yourself instead - "
                   "if you do, a Minion becomes the new Imp.",
        "timing": "Every night except the first",
        "flavour": "This body was never the point. The hunger is.",
    },
}
for _c in CHARACTERS.values():
    _c["script"] = TROUBLE_BREWING

_BMR = {
    # --- townsfolk ---
    "grandmother": {
        "name": "Grandmother", "type": TOWNSFOLK,
        "summary": "Knows one good player's character, and dies if the Demon kills them.",
        "ability": "You start knowing a good player and their character. If the Demon kills them, you die too.",
        "timing": "First night / triggered",
        "flavour": "I knew that child before they could walk. I'd know them anywhere.",
    },
    "sailor": {
        "name": "Sailor", "type": TOWNSFOLK,
        "summary": "Can't die while sober; each night someone gets drunk.",
        "ability": "Each night, choose an alive player: either you or they are drunk until dusk. You can't die.",
        "timing": "Every night",
        "flavour": "One more round! The sea hasn't taken me yet, and neither will you.",
    },
    "chambermaid": {
        "name": "Chambermaid", "type": TOWNSFOLK,
        "summary": "Learns how many of two players woke tonight because of their ability.",
        "ability": "Each night, choose 2 alive players (not yourself): you learn how many woke tonight due to their ability.",
        "timing": "Every night",
        "flavour": "Beds are made, but somebody's sheets are still warm.",
    },
    "exorcist": {
        "name": "Exorcist", "type": TOWNSFOLK,
        "summary": "Each night, may stop the Demon from waking.",
        "ability": "Each night*, choose a player (different to last night): the Demon, if chosen, learns who you are "
                   "then doesn't wake tonight.",
        "timing": "Every night except the first",
        "flavour": "Begone. This house is not yours tonight.",
    },
    "innkeeper": {
        "name": "Innkeeper", "type": TOWNSFOLK,
        "summary": "Each night, two players can't die, but one gets drunk.",
        "ability": "Each night*, choose 2 players: they can't die tonight, but 1 is drunk until dusk.",
        "timing": "Every night except the first",
        "flavour": "Stay the night, friends. The ale is strong and the doors are locked.",
    },
    "gambler": {
        "name": "Gambler", "type": TOWNSFOLK,
        "summary": "Each night, guesses a player's character, and dies if wrong.",
        "ability": "Each night*, choose a player and guess their character: if you guess wrong, you die.",
        "timing": "Every night except the first",
        "flavour": "Double or nothing. It's always double or nothing.",
    },
    "gossip": {
        "name": "Gossip", "type": TOWNSFOLK,
        "summary": "Makes a public statement each day; if true, someone dies tonight.",
        "ability": "Each day, you may make a public statement. Tonight, if it was true, a player dies.",
        "timing": "Each day / that night",
        "flavour": "Did you hear? Of course you didn't. That's why I'm telling you.",
    },
    "courtier": {
        "name": "Courtier", "type": TOWNSFOLK,
        "summary": "Once per game, makes a character drunk for three nights and days.",
        "ability": "Once per game, at night, choose a character: they are drunk for 3 nights and 3 days.",
        "timing": "Once per game, at night",
        "flavour": "A toast to your health! And another. And another.",
    },
    "professor": {
        "name": "Professor", "type": TOWNSFOLK,
        "summary": "Once per game, may bring a dead Townsfolk back to life.",
        "ability": "Once per game, at night*, choose a dead player: if they are a Townsfolk, they are resurrected.",
        "timing": "Once per game, nights except the first",
        "flavour": "Death is merely a problem of insufficient voltage.",
    },
    "minstrel": {
        "name": "Minstrel", "type": TOWNSFOLK,
        "summary": "When a Minion is executed, everyone else gets drunk.",
        "ability": "When a Minion dies by execution, all other players (except Travellers) are drunk until dusk tomorrow.",
        "timing": "Triggered on a Minion's execution",
        "flavour": "Sing, friends! The wicked have swung, and the wine is flowing.",
    },
    "tea_lady": {
        "name": "Tea Lady", "type": TOWNSFOLK,
        "summary": "Their neighbours can't die while both are good.",
        "ability": "If both your alive neighbours are good, they can't die.",
        "timing": "Always active",
        "flavour": "Nobody comes to harm at my table. Milk or lemon?",
    },
    "pacifist": {
        "name": "Pacifist", "type": TOWNSFOLK,
        "summary": "Executed good players might survive.",
        "ability": "Executed good players might not die.",
        "timing": "Always active",
        "flavour": "There has been enough killing. Put down the rope.",
    },
    "fool": {
        "name": "Fool", "type": TOWNSFOLK,
        "summary": "Survives their first death.",
        "ability": "The first time you die, you don't.",
        "timing": "Triggered on death",
        "flavour": "Ha! You'll have to try harder than that.",
    },
    # --- outsiders ---
    "goon": {
        "name": "Goon", "type": OUTSIDER,
        "summary": "Whoever picks them first each night is drunk, and the Goon joins their side.",
        "ability": "Each night, the 1st player to choose you with their ability is drunk until dusk. "
                   "You become their alignment.",
        "timing": "Every night, triggered",
        "flavour": "I work for whoever pays. Tonight, that's you.",
    },
    "lunatic": {
        "name": "Lunatic", "type": OUTSIDER,
        "summary": "Thinks they are the Demon, but isn't.",
        "ability": "You think you are a Demon, but you are not. The Demon knows who you are and who you choose at night.",
        "timing": "Always active",
        "flavour": "The voices tell me I'm in charge. They've never been wrong.",
    },
    "tinker": {
        "name": "Tinker", "type": OUTSIDER,
        "summary": "Might die at any time.",
        "ability": "You might die at any time.",
        "timing": "Any time",
        "flavour": "Just one more adjustment and it'll be perfectly saf-",
    },
    "moonchild": {
        "name": "Moonchild", "type": OUTSIDER,
        "summary": "On death, publicly picks someone, who dies that night if good.",
        "ability": "When you learn that you died, publicly choose 1 alive player. Tonight, if it was a good player, they die.",
        "timing": "Triggered on death",
        "flavour": "If I go, I'm taking someone with me. Choose wisely, I will.",
    },
    # --- minions ---
    "godfather": {
        "name": "Godfather", "type": MINION,
        "summary": "Knows the Outsiders; kills at night when one dies.",
        "ability": "You start knowing which Outsiders are in play. If 1 died today, choose a player tonight: "
                   "they die. [-1 or +1 Outsider]",
        "timing": "First night / nights after an Outsider dies",
        "flavour": "Nobody touches my family. Nobody.",
    },
    "devils_advocate": {
        "name": "Devil's Advocate", "type": MINION,
        "summary": "Each night, saves a player from tomorrow's execution.",
        "ability": "Each night, choose a living player (different to last night): if executed tomorrow, they don't die.",
        "timing": "Every night",
        "flavour": "My client is innocent, and I can prove it. Eventually.",
    },
    "assassin": {
        "name": "Assassin", "type": MINION,
        "summary": "Once per game, kills a player no matter what.",
        "ability": "Once per game, at night*, choose a player: they die, even if for some reason they could not.",
        "timing": "Once per game, nights except the first",
        "flavour": "No lock, no guard, no prayer. Just a quiet blade.",
    },
    "mastermind": {
        "name": "Mastermind", "type": MINION,
        "summary": "If the Demon is executed, the game goes on for one more day.",
        "ability": "If the Demon dies by execution (ending the game), play for 1 more day. If a player is then "
                   "executed, their team loses.",
        "timing": "Triggered when the Demon is executed",
        "flavour": "You've won a battle. The war was always mine.",
    },
    # --- demons ---
    "zombuul": {
        "name": "Zombuul", "type": DEMON,
        "summary": "Kills only after a quiet day, and survives their first death.",
        "ability": "Each night*, if no-one died today, choose a player: they die. The 1st time you die, you live "
                   "but register as dead.",
        "timing": "Nights except the first, if nobody died today",
        "flavour": "Dead? I've been dead for years. It hardly slows me down.",
    },
    "pukka": {
        "name": "Pukka", "type": DEMON,
        "summary": "Poisons a player each night, who dies the night after.",
        "ability": "Each night, choose a player: they are poisoned. The previously poisoned player dies then becomes healthy.",
        "timing": "Every night",
        "flavour": "One little bite. You won't even feel it until tomorrow.",
    },
    "shabaloth": {
        "name": "Shabaloth", "type": DEMON,
        "summary": "Kills two players each night, and might bring one back.",
        "ability": "Each night*, choose 2 players: they die. A dead player you chose last night might be regurgitated.",
        "timing": "Every night except the first",
        "flavour": "Hungry. Always hungry. Sometimes I give a little back.",
    },
    "po": {
        "name": "Po", "type": DEMON,
        "summary": "May skip a kill to kill three the next night.",
        "ability": "Each night*, you may choose a player: they die. If your last choice was no-one, choose 3 players tonight.",
        "timing": "Every night except the first",
        "flavour": "Patience. The longer I wait, the more I eat.",
    },
}
for _id, _c in _BMR.items():
    _c["script"] = BAD_MOON_RISING
    _c["icon"] = f"{_id}.png"
CHARACTERS.update(_BMR)
for _id, _c in CHARACTERS.items():
    _c.setdefault("icon", f"{_id}.svg")

SETUP_COUNTS = {
    5: (3, 0, 1, 1), 6: (3, 1, 1, 1), 7: (5, 0, 1, 1), 8: (5, 1, 1, 1), 9: (5, 2, 1, 1),
    10: (7, 0, 2, 1), 11: (7, 1, 2, 1), 12: (7, 2, 2, 1),
    13: (9, 0, 3, 1), 14: (9, 1, 3, 1), 15: (9, 2, 3, 1),
}

# evil info steps only exist in games of this size or larger (standard rules);
# Dead Eyes Only ignores this and always runs the evil meeting
EVIL_INFO_MIN_PLAYERS = 7

FIRST_NIGHT = ["minion_info", "demon_info", "poisoner", "washerwoman", "librarian", "investigator",
               "chef", "empath", "fortune_teller", "butler", "spy"]
OTHER_NIGHTS = ["poisoner", "monk", "imp", "ravenkeeper", "empath", "fortune_teller", "undertaker",
                "butler", "spy"]

# a Lunatic's turn sits at the slot of the Demon they believe they are
BMR_FIRST_NIGHT = ["minion_info", "demon_info", "lunatic_info", "sailor", "courtier", "godfather",
                   "devils_advocate", "pukka", "grandmother", "chambermaid"]
BMR_OTHER_NIGHTS = ["sailor", "innkeeper", "courtier", "gambler", "devils_advocate", "exorcist", "zombuul",
                    "pukka", "shabaloth", "po", "assassin", "godfather", "gossip", "professor", "moonchild",
                    "chambermaid"]

SCRIPTS = {
    TROUBLE_BREWING: {"name": "Trouble Brewing", "first_night": FIRST_NIGHT, "other_nights": OTHER_NIGHTS},
    BAD_MOON_RISING: {"name": "Bad Moon Rising", "first_night": BMR_FIRST_NIGHT, "other_nights": BMR_OTHER_NIGHTS},
}

NIGHT_CHOICES = {
    "poisoner": (1, True, "Choose a player to poison."),
    "monk": (1, False, "Choose a player to protect from the Demon tonight."),
    "imp": (1, True, "Choose a player to kill (choosing yourself passes the Imp to a Minion)."),
    "ravenkeeper": (1, True, "You died tonight. Choose a player to learn their character."),
    "fortune_teller": (2, True, "Choose two players to check for the Demon."),
    "butler": (1, False, "Choose your Master for tomorrow."),
    # Bad Moon Rising
    "sailor": (1, False, "Choose a living player to drink with: one of you is drunk until dusk."),
    "chambermaid": (2, False, "Choose two living players (not yourself) to learn how many woke tonight."),
    "exorcist": (1, False, "Choose a player (different to last night) to exorcise."),
    "innkeeper": (2, True, "Choose two players who can't die tonight. One of them is drunk until dusk."),
    "gambler": (1, False, "Choose a player and guess their character. If you guess wrong, you die."),
    "courtier": (0, True, "You may choose a character to make drunk for 3 nights and 3 days (once per game)."),
    "professor": (1, True, "You may choose a dead player to resurrect if they are a Townsfolk (once per game)."),
    "godfather": (1, True, "An Outsider died today. Choose a player to kill."),
    "devils_advocate": (1, True, "Choose a living player (different to last night) to survive execution tomorrow."),
    "assassin": (1, True, "You may choose a player to kill, even if they could not die (once per game)."),
    "zombuul": (1, True, "Nobody died today. Choose a player to kill."),
    "pukka": (1, True, "Choose a player to poison. Last night's victim dies."),
    "shabaloth": (2, True, "Choose two players to kill."),
    "po": (1, True, "You may choose a player to kill, or choose nobody to kill three tomorrow night."),
    # picked by the Storyteller in the grimoire, never on a phone
    "gossip": (1, True, ""),
    "moonchild": (1, True, ""),
}
# the player may answer with nobody
OPTIONAL_CHOICES = {"courtier", "professor", "assassin", "po"}
# the player also picks a character (the Courtier picks only a character)
CHARACTER_CHOICES = {"gambler", "courtier"}
# the Storyteller makes the pick; the player is not woken to choose
STORYTELLER_PICKS = {"gossip", "moonchild"}
# night steps that give information only and have no player choice on these nights
FIRST_NIGHT_INFO_ONLY = {"godfather"}
DEMON_KILLS = {"imp", "zombuul", "pukka", "shabaloth", "po"}
PO_CHARGED_PROMPT = "Your last choice was nobody. Choose three players to kill."


def ids_of(char_type: str, script: str = TROUBLE_BREWING) -> list[str]:
    """Character ids of one type (TOWNSFOLK / OUTSIDER / MINION / DEMON) on a script, in almanac order."""
    return [cid for cid, c in CHARACTERS.items() if c["type"] == char_type and c["script"] == script]


def on_script(script: str) -> list[str]:
    """Every character id on a script, in almanac order."""
    return [cid for cid, c in CHARACTERS.items() if c["script"] == script]


def is_good(character: str) -> bool:
    """True for Townsfolk and Outsiders (the character's starting alignment)."""
    return CHARACTERS[character]["type"] in (TOWNSFOLK, OUTSIDER)


def expected_counts(players: int, chars: list[str] | bool) -> list[tuple[int, int, int, int]]:
    """Legal (townsfolk, outsiders, minions, demons) counts for a player count and the characters in play.

    The Baron swaps two Townsfolk for Outsiders; the Godfather swaps one either way (at least
    one Outsider is needed to take one away). chars may be a bool meaning "the Baron is in play".
    """
    tf, out, mn, dm = SETUP_COUNTS[players]
    if chars is True or (not isinstance(chars, bool) and "baron" in chars):
        return [(tf - 2, out + 2, mn, dm)]
    if not isinstance(chars, bool) and "godfather" in chars:
        return [(tf - 1, out + 1, mn, dm)] + ([(tf + 1, out - 1, mn, dm)] if out else [])
    return [(tf, out, mn, dm)]


if __name__ == "__main__":
    for script, meta in SCRIPTS.items():
        print(meta["name"])
        for t in (TOWNSFOLK, OUTSIDER, MINION, DEMON):
            print(f"  {t:10} {', '.join(CHARACTERS[c]['name'] for c in ids_of(t, script))}")
    print("9 players:", expected_counts(9, []), "with Baron:", expected_counts(9, ["baron"]),
          "with Godfather:", expected_counts(9, ["godfather"]))
