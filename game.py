"""Game state and rules for Trouble Brewing and Bad Moon Rising: seating, setup, night steps,
nominations, deaths, wins.

Every public method is either a Storyteller action (called with pids) or a player action (called
with the player's secret token). Invalid actions raise GameError with a message for the user.
"""

from __future__ import annotations

import copy
import math
import random
import secrets
import time
from dataclasses import dataclass, field

import dealing
import info
from roles import (BAD_MOON_RISING, CHARACTER_CHOICES, CHARACTERS, DEMON, DEMON_KILLS, EVIL_INFO_MIN_PLAYERS,
                   FIRST_NIGHT_INFO_ONLY, MINION, NIGHT_CHOICES, OPTIONAL_CHOICES, OUTSIDER, PO_CHARGED_PROMPT,
                   SCRIPTS, SETUP_COUNTS, STORYTELLER_PICKS, TOWNSFOLK, TROUBLE_BREWING, expected_counts, is_good,
                   on_script)


class GameError(Exception):
    """Invalid action; the message is shown to whoever attempted it."""


@dataclass
class Player:
    """One seat at the table.

    pid is public (used by everyone to refer to the player); token is secret (the player's login).
    messages schema: list of {"label": str, "text": str}.
    prompt schema, one of (or None):
        real choice: {"kind": "choose", "text": str, "count": int, "allow_self": bool,
                      "optional": bool (may answer with nobody), "guess": list[str] | None (character ids
                      to pick one from, e.g. the Gambler's guess), "answer": list[str] | None,
                      "answer_guess": str | None, "step": int (index into Game.steps)}
        tap task:    {"kind": "tap", "text": str, "target": list[str] (3 character ids, in order),
                      "options": list[str] (6 character ids incl. the targets), "answer": list[str] | None,
                      "step": None}
    phone is False for players the Storyteller seated by hand; they never get tap tasks.
    evil is the player's current alignment: it starts from their character and the Goon can change it.
    """
    pid: str
    token: str
    name: str
    character: str | None = None
    believed: str | None = None
    alive: bool = True
    ghost_vote: bool = True
    messages: list[dict] = field(default_factory=list)
    prompt: dict | None = None
    phone: bool = False
    evil: bool = False


class Game:
    """Single game in memory. Seat order is the order of self.players."""

    def __init__(self, rng: random.Random | None = None):
        """Empty lobby. rng is injectable for reproducible games."""
        self.rng = rng or random.Random()
        self.players: list[Player] = []
        self.version = 0
        self._next_pid = 1
        self.dead_eyes = False
        self.script = TROUBLE_BREWING
        # storyteller undo stack: [{"label", "seen", "state", "phone_inputs"}], newest last
        self.history: list[dict] = []
        # picks and taps made on phones; undo reports how many it throws away
        self.phone_inputs = 0
        self._reset_round()

    def _reset_round(self) -> None:
        """Clear everything except the seated players."""
        self.phase = "lobby"  # lobby | setup | night | day | over
        self.night = 0
        self.day = 0
        self.red_herring: str | None = None
        self.bluffs: list[str] = []
        self.counts: dict[str, int] = {}
        self.poisoned: str | None = None
        self.protected: str | None = None
        self.master: str | None = None
        self.virgin_spent = False
        self.slayer_spent = False
        self.executed_today: str | None = None
        self.night_deaths: list[str] = []
        self.steps: list[dict] = []
        self.nominations: list[dict] = []
        self.announcements: list[str] = []
        self.winner: str | None = None
        self.win_reason = ""
        self.log: list[str] = []
        # every phone vibrates when this rises, so a buzz never singles anyone out
        self.buzz = 0
        # pid -> private texts held until the next table-wide buzz
        self.queued: dict[str, list[str]] = {}
        self.second_round_done = False
        # notes from players to the Storyteller: [{"pid", "text", "label", "read"}]
        self.inbox: list[dict] = []
        # day timer: absolute time.time() when it fires, or None
        self.timer_end: float | None = None
        # --- Bad Moon Rising ---
        self.grandchild: str | None = None
        # pid -> number of the night at whose start their drunkenness wears off
        self.drunk: dict[str, int] = {}
        # Innkeeper's guests: cannot die tonight
        self.safe: list[str] = []
        self.pukka_poisoned: str | None = None
        self.po_charged = False
        self.exorcist_last: str | None = None
        self.exorcised: str | None = None
        self.da_target: str | None = None
        self.da_last: str | None = None
        self.goon_chosen = False
        self.spent: set[str] = set()  # once-per-game abilities used: assassin, professor, courtier, fool, zombuul
        self.zombuul_fake: str | None = None  # a Zombuul who survived their first death, registering as dead
        self.gossip_true = False
        self.moonchild_target: str | None = None
        self.mastermind_day: int | None = None
        self.deaths_today: list[str] = []
        self.dawn_news: list[str] = []
        self.night_revived: list[str] = []  # resurrected tonight: still dead to the table until dawn
        self._executing = False
        for p in self.players:
            p.character = p.believed = None
            p.alive, p.ghost_vote, p.messages, p.prompt, p.evil = True, True, [], None, False

    # --- lookups ---

    def get(self, pid: str | None) -> Player:
        """Player by public id."""
        for p in self.players:
            if p.pid == pid:
                return p
        raise GameError(f"No player {pid!r}")

    def by_token(self, token: str) -> Player:
        """Player by secret token."""
        for p in self.players:
            if p.token == token:
                return p
        raise GameError("Unknown player - please join again")

    def alive_count(self) -> int:
        """Number of living players."""
        return sum(p.alive for p in self.players)

    def threshold(self) -> int:
        """Votes needed to put a nominee up for execution: half the living, rounded up."""
        return math.ceil(self.alive_count() / 2)

    def impaired(self, p: Player) -> bool:
        """True if the player's ability does not work: the Drunk, poisoned, or drunk for now."""
        return (p.character == "drunk" or self.poisoned == p.pid or self.pukka_poisoned == p.pid
                or p.pid in self.drunk)

    def _working(self, p: Player, character: str) -> bool:
        """True if p is alive, truly holds character, and is not poisoned."""
        return p.alive and p.character == character and not self.impaired(p)

    def _alive_demon(self) -> Player | None:
        """The living Demon, if any (a Zombuul registering as dead still counts)."""
        return next((p for p in self.players if (p.alive or p.pid == self.zombuul_fake)
                     and CHARACTERS[p.character]["type"] == DEMON), None)

    def _acting(self, p: Player) -> bool:
        """Alive for their own ability: living, or a Zombuul registering as dead."""
        return p.alive or p.pid == self.zombuul_fake

    def _bmr(self) -> bool:
        return self.script == BAD_MOON_RISING

    def script_name(self) -> str:
        return SCRIPTS[self.script]["name"]

    def woke_tonight(self, p: Player) -> bool:
        """Chambermaid count: p has a night step tonight for their own ability that wakes them.

        Info-only steps for the evil team, Storyteller-only picks and an exorcised Demon do not count.
        """
        for s in self.steps:
            if p.pid in s["pids"] and s["key"] not in ("minion_info", "demon_info", "lunatic_info") \
                    and s["key"] not in STORYTELLER_PICKS and not s.get("exorcised") and self.step_applies(s):
                return True
        return False

    def _type_of(self, p: Player) -> str:
        return CHARACTERS[p.character]["type"]

    def _require(self, *phases: str) -> None:
        if self.phase not in phases:
            raise GameError(f"Not allowed during {self.phase}")

    def _log(self, text: str) -> None:
        self.log.append(f"[{self._stamp()}] {text}")

    def _stamp(self) -> str:
        return f"Night {self.night}" if self.phase == "night" else f"Day {self.day}" if self.phase == "day" else self.phase

    def _announce(self, text: str) -> None:
        self.announcements.append(text)
        self._log(text)

    # --- lobby ---

    def add_player(self, name: str, phone: bool = False) -> Player:
        """Seat a new player at the end of the circle (lobby only). Returns the player incl. token.

        phone is True when the player joined from their own phone, so night rounds wait for them.
        """
        self._require("lobby")
        name = name.strip()
        if not name:
            raise GameError("Name required")
        if any(p.name.lower() == name.lower() for p in self.players):
            raise GameError(f"{name} is already taken")
        if len(self.players) >= max(SETUP_COUNTS):
            raise GameError("Table is full")
        p = Player(pid=f"p{self._next_pid}", token=secrets.token_urlsafe(12), name=name, phone=phone)
        self._next_pid += 1
        self.players.append(p)
        return p

    def remove_player(self, pid: str) -> None:
        """Remove a player from the lobby."""
        self._require("lobby")
        self.players.remove(self.get(pid))

    def move_player(self, pid: str, delta: int) -> None:
        """Shift a player's seat by delta (lobby/setup), to match the real seating circle."""
        self._require("lobby", "setup")
        p = self.get(pid)
        i = self.players.index(p)
        j = max(0, min(len(self.players) - 1, i + delta))
        self.players.insert(j, self.players.pop(i))

    def set_variant(self, dead_eyes: bool) -> None:
        """Toggle the Dead Eyes Only variant (lobby or setup only)."""
        self._require("lobby", "setup")
        self.dead_eyes = bool(dead_eyes)
        self._log(f"Variant set: {'Dead Eyes Only' if self.dead_eyes else 'Standard rules'}")

    def set_script(self, script: str) -> None:
        """Pick the script to play (lobby or setup). Changing it during setup deals again."""
        self._require("lobby", "setup")
        if script not in SCRIPTS:
            raise GameError(f"Unknown script {script!r}")
        if script == self.script:
            return
        self.script = script
        self._log(f"Script set: {self.script_name()}")
        if self.phase == "setup":
            self.deal()

    # --- setup ---

    def deal(self) -> None:
        """Randomly deal a valid setup to the seated players (lobby or re-deal during setup)."""
        self._require("lobby", "setup")
        if len(self.players) not in SETUP_COUNTS:
            raise GameError(f"{self.script_name()} needs 5-15 players")
        result = dealing.deal([p.pid for p in self.players], self.rng, self.script)
        for p in self.players:
            p.character = result["characters"][p.pid]
            p.believed = result["believed"][p.pid]
            p.evil = not is_good(p.character)
        self.red_herring = result["red_herring"]
        self.grandchild = result["grandchild"]
        self.bluffs = result["bluffs"]
        self.phase = "setup"

    def set_character(self, pid: str, character: str, believed: str | None = None) -> None:
        """Storyteller override of a player's character (any time before the game ends).

        For the Drunk, believed must be a Townsfolk; it defaults to a random Townsfolk not in play.
        For the Lunatic, believed must be a Demon; it defaults to a random Demon on the script.
        For everyone else, believed always equals character. The player's alignment follows the
        new character.
        """
        self._require("setup", "night", "day")
        if character not in CHARACTERS or CHARACTERS[character]["script"] != self.script:
            raise GameError(f"{info.char_name(character) if character in CHARACTERS else repr(character)} "
                            f"is not on {self.script_name()}")
        p = self.get(pid)
        script_ids = on_script(self.script)
        if character == "drunk":
            in_play = {q.character for q in self.players}
            believed = believed or self.rng.choice(
                [c for c in script_ids if CHARACTERS[c]["type"] == TOWNSFOLK and c not in in_play])
            if CHARACTERS[believed]["type"] != TOWNSFOLK:
                raise GameError("The Drunk must believe they are a Townsfolk")
        elif character == "lunatic":
            believed = believed or self.rng.choice([c for c in script_ids if CHARACTERS[c]["type"] == DEMON])
            if believed not in CHARACTERS or CHARACTERS[believed]["type"] != DEMON:
                raise GameError("The Lunatic must believe they are a Demon")
        else:
            believed = character
        p.character, p.believed = character, believed
        p.evil = not is_good(character)
        if self.phase != "setup":
            self._log(f"Storyteller set {p.name} to {info.char_name(character)}")

    def set_setup(self, red_herring: str | None, bluffs: list[str], grandchild: str | None = None) -> None:
        """Set the Demon's three bluffs (character ids), the Fortune Teller red herring and the
        Grandmother's grandchild (pids; each left as it was when not given)."""
        self._require("setup")
        problems = self.bluff_problems(bluffs)
        if problems:
            raise GameError(problems[0])
        if red_herring:
            self.red_herring = self.get(red_herring).pid
        if grandchild:
            child = self.get(grandchild)
            if child.character == "grandmother" or not is_good(child.character):
                raise GameError("The grandchild must be another good player")
            self.grandchild = child.pid
        self.bluffs = bluffs

    def bluff_problems(self, bluffs: list[str]) -> list[str]:
        """Reasons the Demon's bluffs are illegal for the current seating; empty when they are fine.

        Algorithm: require exactly three known character ids, all different, each on the good team
        (Townsfolk or Outsider), none held by a player, and none the Drunk believes they are (the
        Drunk openly claims that character, so the Demon would be caught out by a double claim).

        Args:
            bluffs (list[str]): character ids proposed as bluffs.

        Returns:
            list[str]: one sentence per problem, in the order checked.
        """
        if len(bluffs) != 3 or any(b not in CHARACTERS for b in bluffs):
            return ["Pick exactly three bluff characters"]
        problems = []
        off = sorted({info.char_name(b) for b in bluffs if CHARACTERS[b]["script"] != self.script})
        if off:
            problems.append(f"Demon bluffs must be on {self.script_name()}, not {', '.join(off)}")
        if len(set(bluffs)) != 3:
            problems.append("The three Demon bluffs must be different characters")
        evil = sorted({info.char_name(b) for b in bluffs if not is_good(b)})
        if evil:
            problems.append(f"Demon bluffs must be good characters, not {', '.join(evil)}")
        in_play = sorted({info.char_name(b) for b in bluffs if any(p.character == b for p in self.players)})
        if in_play:
            problems.append(f"Demon bluffs must not be in play: {', '.join(in_play)}")
        drunk = next((p for p in self.players if p.character == "drunk"), None)
        if drunk and drunk.believed in bluffs:
            problems.append(f"The Drunk believes they are the {info.char_name(drunk.believed)}, so it cannot be a bluff")
        return problems

    def setup_warnings(self) -> list[str]:
        """Soft problems with the current setup; the Storyteller may start anyway."""
        if self.phase != "setup":
            return []
        chars = [p.character for p in self.players]
        warnings = []
        counts = tuple(sum(CHARACTERS[c]["type"] == t for c in chars) for t in (TOWNSFOLK, OUTSIDER, MINION, DEMON))
        want = expected_counts(len(chars), chars)
        if counts not in want:
            warnings.append(f"Counts (townsfolk, outsiders, minions, demons) are {counts}; rules say "
                            f"{' or '.join(map(str, want))}")
        dupes = {c for c in chars if chars.count(c) > 1}
        if dupes:
            warnings.append("Duplicate characters: " + ", ".join(info.char_name(c) for c in dupes))
        drunk = next((p for p in self.players if p.character == "drunk"), None)
        if drunk and drunk.believed in chars:
            warnings.append("The Drunk believes they are a character that is in play")
        if self.red_herring and not is_good(self.get(self.red_herring).character):
            warnings.append("The red herring should be a good player")
        if "grandmother" in chars and not self.grandchild:
            warnings.append("Pick the Grandmother's grandchild")
        return warnings

    def start_game(self) -> None:
        """Lock the setup, publish type counts, and begin the first night.

        Refuses duplicate characters, counting the Drunk's believed character: two holders of one
        character would share a single night step, so only one of them would ever be prompted.
        Refuses illegal Demon bluffs, since character changes after the deal can put a bluff in play.
        """
        self._require("setup")
        if not any(CHARACTERS[p.character]["type"] == DEMON for p in self.players):
            raise GameError("There must be a Demon")
        chars = [p.character for p in self.players]
        dupes = sorted({info.char_name(c) for c in chars if chars.count(c) > 1})
        if dupes:
            raise GameError(f"Each character can only be dealt once: {', '.join(dupes)}")
        drunk = next((p for p in self.players if p.character == "drunk"), None)
        if drunk and drunk.believed in chars:
            raise GameError(f"The Drunk must believe they are a Townsfolk not in play, "
                            f"and the {info.char_name(drunk.believed)} is in play")
        problems = self.bluff_problems(self.bluffs)
        if problems:
            raise GameError(problems[0])
        self.counts = {t: sum(CHARACTERS[p.character]["type"] == t for p in self.players)
                       for t in (TOWNSFOLK, OUTSIDER, MINION, DEMON)}
        self._log("Game started: " + ", ".join(f"{p.name}={info.char_name(p.character)}" for p in self.players))
        self.start_night()

    # --- night ---

    def start_night(self) -> None:
        """Begin the next night with every phone buzzing at once.

        Algorithm: expire poison, protection, Master and drunkenness that ends at this dusk; build
        the night order; push each living chooser's prompt (except the Ravenkeeper, who waits for
        the second round, and steps the Storyteller picks for); deliver anything held since the
        day (e.g. a Scarlet Woman who became the Imp); buzz every phone.
        """
        self._require("setup", "day")
        self.phase = "night"
        self.night += 1
        self.poisoned = self.protected = self.master = None
        self.drunk = {pid: until for pid, until in self.drunk.items() if until > self.night}
        self.safe, self.exorcised, self.da_target, self.goon_chosen = [], None, None, False
        self.night_revived = []
        self.night_deaths = []
        self.second_round_done = False
        self.timer_end = None
        for p in self.players:
            p.prompt = None
        self.steps = self._build_steps()
        for i, s in enumerate(self.steps):
            if s["key"] == "moonchild":
                s["answer"] = [self.moonchild_target]
            if s["choose"] or s["guess"]:
                if s["key"] != "ravenkeeper" and s["key"] not in STORYTELLER_PICKS and self.step_applies(s):
                    self.ask(i)
        self._hand_out_tap_tasks()
        self._log("Night falls")
        self._flush()
        self.buzz += 1

    def second_round(self) -> None:
        """Buzz every phone again (nights 2+); the Ravenkeeper gets their prompt only if killed tonight.

        Runs every night regardless, so the second buzz never reveals that a Ravenkeeper died.
        A second round of tap tasks goes out only when a Ravenkeeper (or a Drunk who believes
        they are one) was killed tonight and is picking, so everyone is busy while they pick.
        """
        self._require("night")
        if self.second_round_done:
            return
        self._require_phones_done("the second buzz")
        self.second_round_done = True
        raven_picks = False
        for i, s in enumerate(self.steps):
            if s["key"] == "ravenkeeper" and self.step_applies(s):
                self.ask(i)
                raven_picks = True
        if raven_picks:
            self._hand_out_tap_tasks()
        self.buzz += 1
        self._log("Second round: every phone buzzes")

    def _tap_task(self) -> dict:
        """A fresh tap task: six different icons from the script, three of them asked for in order."""
        options = self.rng.sample(on_script(self.script), 6)
        target = self.rng.sample(options, 3)
        return {"kind": "tap", "text": "Tap these three, in this order.", "target": target,
                "options": options, "answer": None, "step": None}

    def _hand_out_tap_tasks(self) -> None:
        """Give a tap task to every publicly alive phone player not busy with an unanswered real choice.

        Algorithm: draw six different character icons, and ask for three of them in a set order;
        the phone shows the three in order above a shuffled grid of all six. A random guess passes
        1 time in 120, so a player has to look. Tonight's victims count as alive so they tap like
        everyone else; players known dead since an earlier day, and players without a phone, are
        left alone.
        """
        for p in self.players:
            if not p.phone or not self._publicly_alive(p):
                continue
            if p.prompt and p.prompt["kind"] == "choose" and p.prompt["answer"] is None:
                continue
            p.prompt = self._tap_task()

    def _phone_players(self) -> list[Player]:
        """Publicly alive players with a phone: everyone a night round waits for."""
        return [p for p in self.players if p.phone and self._publicly_alive(p)]

    def phones_waiting(self) -> list[Player]:
        """Phone players who still have an unanswered prompt (tap task or real choice)."""
        return [p for p in self._phone_players() if p.prompt and p.prompt["answer"] is None]

    def phones_done(self) -> tuple[int, int]:
        """(phone players with nothing left to tap, phone players)."""
        phones = self._phone_players()
        return len(phones) - len(self.phones_waiting()), len(phones)

    def _require_phones_done(self, before: str) -> None:
        """Refuse to go on while any phone player has not finished; there is no override."""
        waiting = [p.name for p in self.phones_waiting()]
        if waiting:
            raise GameError(f"Waiting for {' and '.join(waiting) if len(waiting) < 3 else ', '.join(waiting)} "
                            f"to finish on their phone before {before}")

    def _notify(self, pid: str, text: str) -> None:
        """Hold a private text for the next table-wide buzz."""
        self.queued.setdefault(pid, []).append(text)

    def _flush(self, filler: str | None = None) -> None:
        """Deliver held texts; with filler, every player without one gets filler instead."""
        for p in self.players:
            texts = self.queued.pop(p.pid, []) or ([filler] if filler else [])
            for text in texts:
                p.messages.append({"label": self._stamp(), "text": text})

    def _build_steps(self) -> list[dict]:
        """Night order for this night, limited to characters that are in play.

        Each living player who believes they hold a character gets their own step, so a Lunatic and
        the real Demon each have one. A dead Moonchild gets a step on the night after their choice.

        Step schema: {"key": str, "pids": list[str], "choose": int, "allow_self": bool,
                      "optional": bool, "guess": bool (pick a character too),
                      "prompt": str, "choices": list[str], "answer": list[str] | None (phone pick),
                      "answer_guess": str | None, "suggestion": str | None,
                      "sent": str | None (text held for dawn), "done": bool}
        """
        steps = []
        order = SCRIPTS[self.script]["first_night" if self.night == 1 else "other_nights"]
        for key in order:
            if key in ("minion_info", "demon_info", "lunatic_info"):
                min_players = 0 if self.dead_eyes else EVIL_INFO_MIN_PLAYERS
                if len(self.players) < min_players:
                    continue
                if key == "lunatic_info":
                    groups = [[p.pid] for p in self.players if p.character == "lunatic"]
                else:
                    wanted = MINION if key == "minion_info" else DEMON
                    groups = [[p.pid for p in self.players if CHARACTERS[p.character]["type"] == wanted]]
            elif key == "moonchild":
                groups = [[p.pid] for p in self.players if p.character == "moonchild"] if self.moonchild_target else []
            else:
                # living only: a dead Imp still holds the token after the Scarlet Woman or a star-pass takes over
                groups = [[p.pid] for p in self.players if p.believed == key and self._acting(p)]
            for pids in groups:
                if not pids:
                    continue
                count, allow_self, prompt = NIGHT_CHOICES.get(key, (0, True, ""))
                if self.night == 1 and key in FIRST_NIGHT_INFO_ONLY:
                    count, prompt = 0, ""
                if key == "po" and self.po_charged:
                    count, prompt = 3, PO_CHARGED_PROMPT
                steps.append({"key": key, "pids": pids, "choose": count, "allow_self": allow_self, "prompt": prompt,
                              "optional": key in OPTIONAL_CHOICES, "guess": key in CHARACTER_CHOICES,
                              "choices": [], "answer": None, "answer_guess": None, "suggestion": None,
                              "sent": None, "done": False})
        return steps

    def _step(self, index: int) -> dict:
        self._require("night")
        if not 0 <= index < len(self.steps):
            raise GameError("No such step")
        return self.steps[index]

    def step_applies(self, step: dict) -> bool:
        """Whether a step's player should be woken now.

        Alive (or a Zombuul registering as dead), with these exceptions: the Ravenkeeper only if
        killed tonight; the Undertaker only after an execution; once-per-game abilities only while
        unspent; the Godfather after night 1 only if an Outsider died today; the Zombuul only if
        nobody died today; the Gossip only after a true statement; the Moonchild only after their
        choice; the Demon not once exorcised.
        """
        key = step["key"]
        actor = self.get(step["pids"][0])
        if key == "ravenkeeper":
            return step["pids"][0] in self.night_deaths
        if key == "undertaker" and not self.executed_today:
            return False
        if key == "moonchild":
            return bool(self.moonchild_target)
        if step.get("exorcised"):
            return False
        if key in ("assassin", "professor", "courtier") and key in self.spent and actor.character == key:
            return False
        if key == "godfather" and self.night > 1 and not any(
                CHARACTERS[self.get(pid).character]["type"] == OUTSIDER for pid in self.deaths_today):
            return False
        if key == "zombuul" and self.deaths_today:
            return False
        if key == "gossip" and not self.gossip_true:
            return False
        return all(self._acting(self.get(pid)) for pid in step["pids"])

    def ask(self, step: int) -> None:
        """Push a step's choice prompt to the woken player's phone.

        Dead Eyes Only: living players see a generic prompt that does not reveal their character;
        dead players (e.g. the Ravenkeeper) already know their role and see the specific prompt.
        In the standard variant every player sees the full prompt.
        """
        s = self._step(step)
        if not s["choose"] and not s["guess"]:
            raise GameError("This step has no choice to make")
        if s["key"] in STORYTELLER_PICKS:
            raise GameError("You make this pick yourself")
        player = self.get(s["pids"][0])
        if self.dead_eyes and player.alive:
            n = s["choose"]
            what = "two players" if n == 2 else "three players" if n == 3 else \
                "another player" if not s["allow_self"] else "a player"
            if s["guess"]:
                what = f"{what} and a character" if n else "a character"
            text = f"The Storyteller needs you to choose {what}."
            if s["optional"]:
                text += " You may choose nobody."
        else:
            text = s["prompt"]
        player.prompt = {"kind": "choose", "text": text, "count": s["choose"], "allow_self": s["allow_self"],
                         "optional": s["optional"], "guess": on_script(self.script) if s["guess"] else None,
                         "answer": None, "answer_guess": None, "step": step}
        s["answer"], s["answer_guess"] = None, None

    def resolve(self, step: int, choices: list[str], redirect: str | None = None,
                new_demon: str | None = None, guess: str | None = None, drunk: str | None = None) -> None:
        """Apply a step's effect and compute the truthful info suggestion.

        Algorithm: validate the chosen pids against the step's choice count (an optional step may
        choose nobody); if the Goon is chosen for the first time tonight, make the chooser drunk
        and give the Goon their alignment; apply the effect if the chooser's ability works; then
        store the info suggestion. Steps with no info to give are marked done.

        Args:
            step (int): index into self.steps.
            choices (list[str]): chosen pids, in order.
            redirect (str | None): Imp only - pid that dies instead when the Mayor is attacked.
            new_demon (str | None): Imp only - Minion pid who becomes the Imp on a self-kill.
            guess (str | None): character id - the Gambler's guess, or the Courtier's pick.
            drunk (str | None): Sailor / Innkeeper - which pid is drunk (defaults: the Sailor's pick,
                a random one of the Innkeeper's two).
        """
        s = self._step(step)
        if not (len(choices) == s["choose"] or (s["optional"] and not choices)):
            raise GameError(f"Choose exactly {s['choose']} player(s)" + (" or nobody" if s["optional"] else ""))
        if len(set(choices)) != len(choices):
            raise GameError("Choose different players")
        # the Gambler must guess; the Courtier may pick nobody
        if s["guess"] and (guess or not s["optional"]) and guess not in on_script(self.script):
            raise GameError("Pick a character on this script")
        targets = [self.get(c) for c in choices]
        actor = self.get(s["pids"][0])
        if not s["allow_self"] and actor in targets:
            raise GameError("This character cannot choose themselves")
        key = s["key"]
        if key == "exorcist" and choices and choices[0] == self.exorcist_last:
            raise GameError("The Exorcist must choose a different player to last night")
        if key == "devils_advocate" and choices and choices[0] == self.da_last:
            raise GameError("The Devil's Advocate must choose a different player to last night")
        # a Demon's pick triggers the second buzz, so check before anything is applied
        is_demon_kill = key in DEMON_KILLS and actor.character == key
        if is_demon_kill and not self.second_round_done and self.night > 1:
            self._require_phones_done("the second buzz")
        if key not in STORYTELLER_PICKS:
            self._goon_check(actor, targets)
        working = not self.impaired(actor)
        if actor.character == "lunatic" and key in DEMON_KILLS:
            self._lunatic_pick(actor, targets)
        elif key == "poisoner":
            self.poisoned = targets[0].pid
            self._log(f"Poisoner poisons {targets[0].name}")
        elif key == "monk":
            self.protected = None if self.impaired(actor) else targets[0].pid
            self._log(f"Monk protects {targets[0].name}{' (no effect: impaired)' if self.impaired(actor) else ''}")
        elif key == "butler":
            self.master = targets[0].pid
            self._log(f"Butler chooses {targets[0].name} as Master")
        elif key == "imp":
            self._demon_attack(actor, targets[0], redirect, new_demon)
        elif key in DEMON_KILLS or key in ("sailor", "innkeeper", "gambler", "exorcist", "courtier", "professor",
                                           "godfather", "devils_advocate", "assassin", "gossip", "moonchild"):
            self._resolve_bmr(key, actor, targets, working, guess, drunk)
        if is_demon_kill and self.phase == "night" and self.night > 1:
            self.second_round()
        s["choices"] = choices
        if guess:
            s["answer_guess"] = guess
        s["suggestion"] = info.suggest(self, key, actor if len(s["pids"]) == 1 else None, targets)
        if s["suggestion"] is None:
            s["done"] = True
            self._close_prompt(actor, step)

    def _goon_check(self, actor: Player, targets: list[Player]) -> None:
        """The first player each night to choose a sober Goon is drunk until dusk; the Goon takes their alignment."""
        goon = next((t for t in targets if t.character == "goon" and t is not actor), None)
        if not goon or self.goon_chosen or self.impaired(goon):
            return
        self.goon_chosen = True
        self.drunk[actor.pid] = max(self.drunk.get(actor.pid, 0), self.night + 1)
        goon.evil = actor.evil
        self._log(f"{actor.name} chose the Goon ({goon.name}): {actor.name} is drunk until dusk, "
                  f"the Goon turns {'evil' if goon.evil else 'good'}")

    def _lunatic_pick(self, lunatic: Player, targets: list[Player]) -> None:
        """A Lunatic's 'kill' does nothing; the real Demon learns whom they chose."""
        names = " and ".join(t.name for t in targets) or "nobody"
        self._log(f"Lunatic {lunatic.name} chooses {names}: no effect")
        demon = self._alive_demon()
        if demon:
            self._notify(demon.pid, f"The Lunatic ({lunatic.name}) chose {names} tonight.")

    def _resolve_bmr(self, key: str, actor: Player, targets: list[Player], working: bool,
                     guess: str | None, drunk: str | None) -> None:
        """Apply a Bad Moon Rising night ability. working is False when the actor is drunk or poisoned."""
        t = targets[0] if targets else None
        note = "" if working else " (no effect: drunk or poisoned)"
        if key == "sailor":
            loser = self.get(drunk) if drunk else t
            if loser not in (actor, t):
                raise GameError("Either the Sailor or their pick is drunk")
            if working:
                self.drunk[loser.pid] = max(self.drunk.get(loser.pid, 0), self.night + 1)
            self._log(f"Sailor drinks with {t.name}: {loser.name} is drunk until dusk{note}")
        elif key == "innkeeper":
            loser = self.get(drunk) if drunk else self.rng.choice(targets)
            if loser not in targets:
                raise GameError("One of the Innkeeper's two guests is drunk")
            if working:
                self.safe = [x.pid for x in targets]
                self.drunk[loser.pid] = max(self.drunk.get(loser.pid, 0), self.night + 1)
            self._log(f"Innkeeper shelters {targets[0].name} and {targets[1].name}; {loser.name} is drunk{note}")
        elif key == "exorcist":
            self.exorcist_last = t.pid
            self._log(f"Exorcist chooses {t.name}{note}")
            if working and t.character in DEMON_KILLS and CHARACTERS[t.character]["type"] == DEMON:
                self._exorcise(actor, t)
        elif key == "gambler":
            right = guess == t.character
            self._log(f"Gambler guesses {t.name} is the {info.char_name(guess)}: {'right' if right else 'wrong'}{note}")
            if working and not right:
                self._try_kill(actor, "guessed wrong as the Gambler")
        elif key == "courtier":
            if not guess:
                self._log("Courtier chooses nobody")
                return
            self.spent.add("courtier")
            victim = next((p for p in self.players if p.character == guess), None)
            if working and victim:
                self.drunk[victim.pid] = max(self.drunk.get(victim.pid, 0), self.night + 3)
            self._log(f"Courtier chooses the {info.char_name(guess)}"
                      f"{': ' + victim.name + ' is drunk for 3 nights and 3 days' if victim and working else ''}{note}")
        elif key == "professor":
            if not t:
                self._log("Professor chooses nobody")
                return
            self.spent.add("professor")
            if t.alive:
                raise GameError("The Professor must choose a dead player")
            self._log(f"Professor chooses {t.name}{note}")
            if working and CHARACTERS[t.character]["type"] == TOWNSFOLK:
                t.alive, t.ghost_vote = True, True
                self.night_revived.append(t.pid)
                self.dawn_news.append(f"{t.name} has been brought back to life.")
                self._log(f"{t.name} is resurrected")
        elif key == "assassin":
            if not t:
                self._log("Assassin chooses nobody")
                return
            self.spent.add("assassin")
            self._log(f"Assassin chooses {t.name}{note}")
            if working:
                self._try_kill(t, "killed by the Assassin", kind="assassin")
        elif key in ("godfather", "gossip", "moonchild"):
            if not t:
                return  # the Godfather's first night is information only
            if key == "moonchild":
                self.moonchild_target = None
                if not t.evil and working:
                    self._try_kill(t, "chosen by the Moonchild")
                else:
                    self._log(f"Moonchild's choice {t.name} survives ({'evil' if t.evil else 'drunk or poisoned'})")
            elif working:
                self._try_kill(t, f"killed by the {info.char_name(key)}")
            else:
                self._log(f"{info.char_name(key)} picks {t.name}{note}")
        elif key == "devils_advocate":
            self.da_last = t.pid
            self.da_target = t.pid if working else None
            self._log(f"Devil's Advocate protects {t.name} from execution tomorrow{note}")
        elif key in DEMON_KILLS:
            self._bmr_demon(key, actor, targets, working)

    def _exorcise(self, exorcist: Player, demon: Player) -> None:
        """The Demon learns who the Exorcist is and does not wake: their steps are skipped and their prompt taken back."""
        self.exorcised = demon.pid
        for i, s in enumerate(self.steps):
            if s["key"] in DEMON_KILLS and s["pids"] == [demon.pid]:
                s["exorcised"], s["done"] = True, True
                if demon.prompt and demon.prompt.get("step") == i:
                    demon.prompt = self._tap_task() if demon.phone else None
        self._notify(demon.pid, f"The Exorcist ({exorcist.name}) chose you. You did not wake tonight.")
        self._log(f"{demon.name} is exorcised and does not wake")

    def _bmr_demon(self, key: str, demon: Player, targets: list[Player], working: bool) -> None:
        """Zombuul, Pukka, Shabaloth and Po kills."""
        names = " and ".join(t.name for t in targets) or "nobody"
        if key == "pukka":
            previous = self.get(self.pukka_poisoned) if self.pukka_poisoned else None
            self._log(f"Pukka poisons {names}{'' if working else ' (no effect: drunk or poisoned)'}")
            self.pukka_poisoned = None
            if previous and previous.alive:
                self._try_kill(previous, "killed by the Pukka's poison", kind="demon")
            if working:
                self.pukka_poisoned = targets[0].pid
            return
        if key == "po":
            if not targets:
                self.po_charged = True
                self._log("Po chooses nobody: three kills next time")
                return
            self.po_charged = False
        self._log(f"{info.char_name(key)} attacks {names}{'' if working else ': no effect, drunk or poisoned'}")
        if working:
            for t in targets:
                self._try_kill(t, f"killed by the {info.char_name(key)}", kind="demon")

    def _saved_by(self, p: Player, kind: str) -> str | None:
        """What stops p dying, or None. kind: demon / night (other night kills) / day / execution / assassin.

        The Fool's save is spent when it is used, so it is checked last.
        """
        if kind == "assassin":
            return None
        if p.pid in self.safe and self.phase == "night":
            return "sheltered by the Innkeeper"
        if kind == "demon" and self.protected == p.pid:
            return "saved by the Monk"
        if kind == "demon" and self._working(p, "soldier"):
            return "the Soldier survives"
        if self._working(p, "sailor"):
            return "the Sailor can't die"
        if self._tea_lady_protects(p):
            return "protected by the Tea Lady"
        if kind == "execution" and self.da_target == p.pid:
            return "protected by the Devil's Advocate"
        if self._working(p, "fool") and "fool" not in self.spent:
            self.spent.add("fool")
            return "the Fool's first death does not happen"
        return None

    def _tea_lady_protects(self, p: Player) -> bool:
        """p is a living neighbour of a working Tea Lady whose two living neighbours are both good."""
        for lady in self.players:
            if lady is p or not self._working(lady, "tea_lady"):
                continue
            neighbours = info.living_neighbours(self, lady)
            if p in neighbours and len(neighbours) == 2 and not any(n.evil for n in neighbours):
                return True
        return False

    def _try_kill(self, p: Player, cause: str, kind: str = "night") -> bool:
        """Kill p unless something saves them. Returns True if p died (or a Zombuul seemed to).

        Night deaths are announced at dawn. A Demon kill of the Grandmother's grandchild takes her too.
        """
        if not self._acting(p):
            self._log(f"{p.name} is already dead ({cause})")
            return False
        saved = self._saved_by(p, kind)
        if saved:
            self._log(f"{p.name} would die ({cause}): {saved}")
            return False
        if self.phase == "night":
            self.night_deaths.append(p.pid)
        self._die(p, cause)
        if kind == "demon" and p.pid == self.grandchild and self.phase != "over":
            granny = next((g for g in self.players if self._working(g, "grandmother")), None)
            if granny:
                self._try_kill(granny, "her grandchild was killed by the Demon")
        return True

    def _demon_attack(self, imp: Player, target: Player, redirect: str | None, new_demon: str | None) -> None:
        """Imp kill: poisoned Imp fails; self-target star-passes; Monk, Soldier and Mayor may save."""
        if self.impaired(imp):
            self._log(f"Imp attacks {target.name}: no effect, Imp is poisoned")
            return
        if target is imp:
            self._star_pass(imp, new_demon)
            return
        if redirect:
            if not self._working(target, "mayor"):
                raise GameError("Only an attack on a working Mayor can be redirected")
            self._log(f"Imp attacks the Mayor; Storyteller redirects to {self.get(redirect).name}")
            target = self.get(redirect)
        if self.protected == target.pid:
            self._log(f"Imp attacks {target.name}: saved by the Monk")
        elif self._working(target, "soldier"):
            self._log(f"Imp attacks {target.name}: the Soldier survives")
        elif not target.alive:
            self._log(f"Imp attacks {target.name}: already dead")
        else:
            self.night_deaths.append(target.pid)
            self._die(target, "killed by the Demon")

    def _star_pass(self, imp: Player, new_demon: str | None) -> None:
        """Imp kills themselves: a living Minion (Scarlet Woman preferred) becomes the Imp."""
        minions = [p for p in self.players if p.alive and self._type_of(p) == MINION]
        heir = self.get(new_demon) if new_demon else (
            next((p for p in minions if p.character == "scarlet_woman"), None)
            or (self.rng.choice(minions) if minions else None))
        if heir and heir not in minions:
            raise GameError("The new Imp must be a living Minion")
        if heir:
            self._promote(heir, f"{imp.name} killed themselves")
        self.night_deaths.append(imp.pid)
        self._die(imp, "killed themselves as the Imp")

    def _promote(self, heir: Player, why: str) -> None:
        heir.character = heir.believed = "imp"
        self._notify(heir.pid, "You are now the Imp.")
        self._log(f"{heir.name} becomes the Imp ({why})")

    def _close_prompt(self, p: Player, step: int) -> None:
        """Clear p's prompt only if it belongs to this step (a Minion may hold their own prompt)."""
        if p.prompt and p.prompt.get("step") == step:
            p.prompt = None

    def send(self, step: int, text: str) -> None:
        """Hold info text for every player in a step until dawn, and mark the step done."""
        s = self._step(step)
        if not text.strip():
            raise GameError("Message is empty")
        for pid in s["pids"]:
            self._notify(pid, text.strip())
            self._close_prompt(self.get(pid), step)
        s["sent"] = text.strip()
        s["done"] = True
        self._log(f"For {', '.join(self.get(pid).name for pid in s['pids'])} at dawn: {text.strip()}")

    def finish_step(self, step: int, done: bool = True) -> None:
        """Mark a step done (e.g. skipped) or reopen it."""
        self._step(step)["done"] = done

    # --- messages and player actions ---

    def message(self, pid: str, text: str, now: bool = False) -> None:
        """Private message to one player: held until dawn at night unless now, delivered at once by day.

        Delivery never vibrates the phone (only table-wide buzzes do), so now is safe for rules answers.
        """
        p = self.get(pid)
        if not text.strip():
            raise GameError("Message is empty")
        if self.phase == "night" and not now:
            self._notify(pid, text.strip())
            self._log(f"For {p.name} at dawn: {text.strip()}")
        else:
            p.messages.append({"label": self._stamp(), "text": text.strip()})
            self._log(f"To {p.name}: {text.strip()}")

    def choose(self, token: str, choices: list[str], guess: str | None = None) -> None:
        """Player answers their current prompt with a list of pids, plus a character id when the prompt asks for one.

        An optional prompt may be answered with nobody (no pids and no character).
        """
        p = self.by_token(token)
        if not p.prompt or p.prompt["kind"] != "choose":
            raise GameError("Nothing to choose right now")
        pr = p.prompt
        nobody = pr.get("optional") and not choices and not guess
        if not nobody:
            if len(choices) != pr["count"] or len(set(choices)) != len(choices):
                raise GameError(f"Choose exactly {pr['count']} different player(s)")
            if pr.get("guess") and guess not in pr["guess"]:
                raise GameError("Choose a character too")
        for c in choices:
            self.get(c)
        if not pr["allow_self"] and p.pid in choices:
            raise GameError("You cannot choose yourself")
        pr["answer"] = choices
        pr["answer_guess"] = guess if pr.get("guess") else None
        if pr["step"] is not None:
            self.steps[pr["step"]]["answer"] = choices
            self.steps[pr["step"]]["answer_guess"] = pr["answer_guess"]
        self.phone_inputs += 1

    def tap(self, token: str, sequence: list[str]) -> None:
        """Player completes their tap task by tapping the three shown icons in order."""
        p = self.by_token(token)
        if not p.prompt or p.prompt["kind"] != "tap":
            raise GameError("Nothing to tap right now")
        if sequence != p.prompt["target"]:
            raise GameError("Not quite. Start again from the first one.")
        p.prompt["answer"] = sequence
        self.phone_inputs += 1

    def skip_tap(self, pid: str | None = None) -> None:
        """Storyteller completes a player's unfinished tap challenge for them (every waiting one when pid is None).

        The phone then shows the same "Done" slip as a finished challenge, so nobody can tell it was skipped.
        Unanswered real choices are left alone: the Storyteller answers those in the night step instead.
        """
        self._require("night")
        players = [self.get(pid)] if pid else self.players
        skipped = [p for p in players if p.prompt and p.prompt["kind"] == "tap" and p.prompt["answer"] is None]
        if not skipped:
            raise GameError("No tap challenge to skip" + (f" for {players[0].name}" if pid else ""))
        for p in skipped:
            p.prompt["answer"] = list(p.prompt["target"])
        self._log(f"Storyteller skipped the tap challenge for {', '.join(p.name for p in skipped)}")

    def note_to_storyteller(self, token: str, text: str) -> None:
        """Player sends a private note to the Storyteller (any phase, alive or dead)."""
        p = self.by_token(token)
        text = text.strip()
        if not text:
            raise GameError("Write something first")
        if len(text) > 500:
            raise GameError("Keep it under 500 characters")
        self.inbox.append({"pid": p.pid, "text": text, "label": self._stamp(), "read": False})
        self._log(f"Note from {p.name}: {text}")

    def read_inbox(self) -> None:
        """Storyteller marks every note as read."""
        for note in self.inbox:
            note["read"] = True

    # --- day ---

    def start_day(self) -> None:
        """Dawn: every player gets their held info (or a blank slip), every phone buzzes, nominations open.

        An Undertaker step the Storyteller did not send is worked out and sent automatically first.
        """
        self._require("night")
        self._require_phones_done("dawn")
        self._auto_undertaker()
        self._flush(filler="Nothing to report tonight.")
        self.buzz += 1
        self.phase = "day"
        self.day += 1
        self.nominations = []
        self.announcements = []
        self.executed_today = None
        self.deaths_today = []
        self.safe = []
        self.gossip_true = False
        self.moonchild_target = None
        for p in self.players:
            p.prompt = None
        dead = [self.get(pid).name for pid in self.night_deaths]
        self._announce(f"Dawn. {' and '.join(dead) + ' died' if dead else 'Nobody died'} in the night.")
        for news in self.dawn_news:
            self._announce(news)
        self.dawn_news = []

    def _auto_undertaker(self) -> None:
        """Hold the truthful Undertaker info for dawn unless the Storyteller already sent or skipped it."""
        for s in self.steps:
            if s["key"] != "undertaker" or s["done"] or not self.step_applies(s):
                continue
            actor = self.get(s["pids"][0])
            text = info.suggest(self, "undertaker", actor, [])
            self._notify(actor.pid, text)
            s["suggestion"], s["sent"], s["done"] = text, text, True
            impaired = " (sent true info although they are drunk or poisoned)" if self.impaired(actor) else ""
            self._log(f"Undertaker info sent automatically to {actor.name}: {text}{impaired}")

    def nominate(self, nominator: str, nominee: str, spy_as_townsfolk: bool = False) -> None:
        """Record a nomination; triggers the Virgin on their first nomination.

        Args:
            nominator (str): pid, must be alive and not have nominated today.
            nominee (str): pid, must be alive and not have been nominated today.
            spy_as_townsfolk (bool): if the nominator is the Spy, whether they register as Townsfolk.
        """
        self._require("day")
        if self.executed_today:
            raise GameError("There has already been an execution today")
        a, b = self.get(nominator), self.get(nominee)
        if not a.alive:
            raise GameError("Only living players nominate")
        # Bad Moon Rising: a dead player may be nominated, which is how a Zombuul who seemed to die is found
        if not b.alive and not self._bmr():
            raise GameError("Only living players nominate and can be nominated")
        if any(n["nominator"] == a.pid for n in self.nominations):
            raise GameError(f"{a.name} has already nominated today")
        if any(n["nominee"] == b.pid for n in self.nominations):
            raise GameError(f"{b.name} has already been nominated today")
        self.nominations.append({"nominator": a.pid, "nominee": b.pid, "voters": [], "votes": None})
        self._announce(f"{a.name} nominates {b.name}.")
        if b.character == "virgin" and not self.virgin_spent:
            self.virgin_spent = True
            townsfolk = self._type_of(a) == TOWNSFOLK or (a.character == "spy" and spy_as_townsfolk)
            if townsfolk and not self.impaired(b):
                self._execute(a)

    def record_votes(self, nomination: int, voters: list[str]) -> None:
        """Set who voted on a nomination; dead voters spend their one ghost vote (refunded on re-record)."""
        self._require("day")
        if not 0 <= nomination < len(self.nominations):
            raise GameError("No such nomination")
        n = self.nominations[nomination]
        previous = set(n["voters"])
        for pid in voters:
            p = self.get(pid)
            if not p.alive and not p.ghost_vote and pid not in previous:
                raise GameError(f"{p.name} is dead and has used their vote")
        for pid in previous:
            if not self.get(pid).alive:
                self.get(pid).ghost_vote = True
        for pid in voters:
            if not self.get(pid).alive:
                self.get(pid).ghost_vote = False
        n["voters"], n["votes"] = list(voters), len(voters)
        self._announce(f"{len(voters)} vote(s) to execute {self.get(n['nominee']).name} "
                       f"(needs {self.threshold()}).")

    def slayer_shot(self, shooter: str, target: str, recluse_as_demon: bool = False) -> None:
        """Public Slayer claim: kills the target only if shooter is a working, unspent Slayer and target is the Demon."""
        self._require("day")
        s, t = self.get(shooter), self.get(target)
        self._announce(f"{s.name} claims Slayer and shoots {t.name}.")
        hit = False
        if s.alive and s.character == "slayer" and not self.slayer_spent:
            self.slayer_spent = True
            is_demon = self._type_of(t) == DEMON or (t.character == "recluse" and recluse_as_demon)
            hit = not self.impaired(s) and is_demon and t.alive
        if hit:
            self._announce(f"{t.name} dies.")
            self._die(t, "shot by the Slayer")
        else:
            self._announce("Nothing happens.")

    def set_gossip(self, true: bool) -> None:
        """Storyteller rules on today's Gossip statement: true means a player dies tonight (the Storyteller picks)."""
        self._require("day")
        self.gossip_true = bool(true)
        self._log(f"Gossip's statement today is {'true' if self.gossip_true else 'not true'}")

    def moonchild_pick(self, target: str | None) -> None:
        """Record the dead Moonchild's public choice; tonight it dies if it is good (or clear it with None)."""
        self._require("day")
        if not target:
            self.moonchild_target = None
            return
        moonchild = next((p for p in self.players if p.character == "moonchild"), None)
        if not moonchild or moonchild.alive:
            raise GameError("Only a dead Moonchild makes this choice")
        t = self.get(target)
        if not t.alive:
            raise GameError("The Moonchild must choose a living player")
        self.moonchild_target = t.pid
        self._announce(f"{moonchild.name}, the Moonchild, chooses {t.name}.")

    def end_day(self, spare: bool = False) -> None:
        """Dusk: execute the unique top nominee at or above threshold, check the Mayor, then start the night.

        spare: a working Pacifist lets an executed good player live (the Storyteller decides).
        Mastermind's extra day: if nobody is executed, evil wins.
        """
        self._require("day")
        if not self.executed_today:
            t = self.threshold()
            eligible = [n for n in self.nominations if n["votes"] is not None and n["votes"] >= t]
            if eligible:
                top = max(n["votes"] for n in eligible)
                leaders = [n for n in eligible if n["votes"] == top]
                if len(leaders) == 1:
                    self._execute(self.get(leaders[0]["nominee"]), spare=spare)
                else:
                    self._announce("Tied vote: nobody is executed.")
            else:
                self._announce("Nobody is executed.")
        if not self.winner and not self.executed_today and self.alive_count() == 3 \
                and any(self._working(p, "mayor") for p in self.players):
            self._win("good", "Three players remain with no execution, and the Mayor lives.")
        if not self.winner and self.mastermind_day == self.day and not self.executed_today:
            self._win("evil", "Nobody was executed on the Mastermind's extra day.")
        if not self.winner:
            self.start_night()

    def _execute(self, p: Player, spare: bool = False) -> None:
        """Execute a player.

        A working Saint loses the game for good. On the Mastermind's extra day the executed
        player's team loses. Otherwise the player dies unless saved (Sailor, Tea Lady, Devil's
        Advocate, Fool, or a Pacifist sparing a good player). A Minion dying by execution makes
        everyone else drunk until dusk tomorrow while a Minstrel works.
        """
        self.executed_today = p.pid
        self._announce(f"{p.name} is executed.")
        if self._working(p, "saint"):
            self._win("evil", "The Saint was executed.")
        if self.mastermind_day == self.day and not self.winner:
            loser = "evil" if p.evil else "good"
            self._win("good" if loser == "evil" else "evil",
                      f"{p.name} was executed on the Mastermind's extra day, so the {loser} team loses.")
        if self.winner:
            self._die(p, "executed")
            return
        if spare and not p.evil and any(self._working(q, "pacifist") for q in self.players):
            self._announce(f"{p.name} does not die.")
            self._log(f"{p.name} is spared by the Pacifist")
            return
        saved = self._saved_by(p, "execution") if self._acting(p) else None
        if saved:
            self._announce(f"{p.name} does not die.")
            self._log(f"{p.name} survives execution: {saved}")
            return
        if not self._acting(p):
            return
        self._executing = True
        try:
            self._die(p, "executed")
        finally:
            self._executing = False
        if self._type_of(p) == MINION and not self.winner:
            minstrel = next((q for q in self.players if self._working(q, "minstrel")), None)
            if minstrel:
                for q in self.players:
                    if q is not minstrel:
                        self.drunk[q.pid] = max(self.drunk.get(q.pid, 0), self.night + 2)
                self._log("A Minion died by execution: everyone but the Minstrel is drunk until dusk tomorrow")

    # --- deaths and wins ---

    def _die(self, p: Player, cause: str) -> None:
        """Kill a player: ends Poisoner's poison, may promote the Scarlet Woman, then checks for a win.

        Dead Eyes Only: the dying player is privately shown their true character token.
        """
        if p.pid == self.zombuul_fake:
            # the Zombuul who registered as dead dies for real
            self.zombuul_fake = None
            self._log(f"{p.name} (Zombuul) dies for real: {cause}")
            self._check_win()
            return
        if not p.alive:
            return
        alive_before = self.alive_count()
        p.alive = False
        if self.phase == "day":
            self.deaths_today.append(p.pid)
        if p.character == "zombuul" and not self.impaired(p) and "zombuul" not in self.spent:
            self.spent.add("zombuul")
            self.zombuul_fake = p.pid
            self._log(f"{p.name} (Zombuul) seems to die ({cause}) but lives on, registering as dead")
            return
        self._log(f"{p.name} ({info.char_name(p.character)}) dies: {cause}")
        if self.dead_eyes:
            char = CHARACTERS[p.character]
            team_name = "evil" if char["type"] in (MINION, DEMON) else "good"
            if p.evil != (team_name == "evil"):
                team_name = "evil" if p.evil else "good"
            reveal = f"You were the {char['name']} ({char['type'].title()}, {team_name} team)."
            if p.believed and p.believed != p.character:
                reveal += (f" You believed you were the {info.char_name(p.believed)},"
                           f" but your ability did not work.")
            if self.phase == "night":
                self._notify(p.pid, reveal)
            else:
                p.messages.append({"label": self._stamp(), "text": reveal})
        if p.character == "poisoner":
            self.poisoned = None
        if p.character == "pukka":
            self.pukka_poisoned = None
        if self._type_of(p) == DEMON and not self._alive_demon() and alive_before >= 5:
            sw = next((q for q in self.players if self._working(q, "scarlet_woman")), None)
            if sw:
                self._promote(sw, "the Demon died")
        self._check_win()

    def _check_win(self) -> None:
        if self.winner:
            return
        if self.mastermind_day is not None:
            return  # the extra day decides the game
        if not self._alive_demon():
            if self._executing and any(self._working(q, "mastermind") for q in self.players):
                self.mastermind_day = self.day + 1
                self._log("The Demon died by execution, but the Mastermind lives: play one more day")
                return
            self._win("good", "The Demon is dead.")
        elif self.alive_count() <= 2:
            self._win("evil", "Only two players remain and the Demon is one of them.")

    def _win(self, team: str, reason: str) -> None:
        self.winner, self.win_reason, self.phase = team, reason, "over"
        self._log(f"{team.upper()} WINS: {reason}")

    # --- storyteller overrides ---

    def kill(self, pid: str) -> None:
        """Storyteller kills a player directly (win checks still apply)."""
        self._require("night", "day")
        p = self.get(pid)
        if self.phase == "night" and p.alive:
            self.night_deaths.append(pid)
        self._die(p, "Storyteller")

    def revive(self, pid: str) -> None:
        """Storyteller undoes a death."""
        self._require("night", "day")
        p = self.get(pid)
        p.alive = True
        if pid == self.zombuul_fake:
            self.zombuul_fake = None
        if pid in self.night_deaths:
            self.night_deaths.remove(pid)
        self._log(f"Storyteller revives {p.name}")

    def set_poisoned(self, pid: str | None) -> None:
        """Storyteller sets or clears the poisoned player."""
        self._require("night", "day")
        self.poisoned = pid and self.get(pid).pid
        self._log(f"Storyteller sets poisoned: {self.get(pid).name if pid else 'nobody'}")

    def set_ghost_vote(self, pid: str, value: bool) -> None:
        """Storyteller sets whether a dead player still has their vote."""
        self.get(pid).ghost_vote = value

    def declare_winner(self, team: str) -> None:
        """Storyteller ends the game."""
        if team not in ("good", "evil"):
            raise GameError("Team must be good or evil")
        self._win(team, "Declared by the Storyteller.")

    # --- day timer ---

    def start_timer(self, minutes: int) -> None:
        """Start a discussion timer for the current day (1-15 minutes)."""
        self._require("day")
        minutes = int(minutes)
        if not 1 <= minutes <= 15:
            raise GameError("Timer must be between 1 and 15 minutes")
        self.timer_end = time.time() + minutes * 60
        self._announce(f"Discussion timer started: {minutes} minute{'s' if minutes != 1 else ''}.")

    def stop_timer(self) -> None:
        """Cancel the running day timer."""
        self._require("day")
        if self.timer_end is None:
            raise GameError("No timer is running")
        self.timer_end = None
        self._announce("Discussion timer cancelled.")

    def check_timer(self) -> bool:
        """Fire the timer if it expired. Returns True if it just fired (state changed)."""
        if self.timer_end is not None and self.phase == "day" and time.time() >= self.timer_end:
            self.timer_end = None
            self._announce("Time is up!")
            self.buzz += 1
            return True
        return False

    def reset(self) -> None:
        """Back to the lobby with the same seated players."""
        self._reset_round()

    # --- undo ---

    UNDO_DEPTH = 30
    # survive an undo: counters phones compare, notes players wrote, the record of what happened
    _KEPT_ON_UNDO = ("version", "buzz", "inbox", "log", "history", "_next_pid", "phone_inputs", "dead_eyes")

    def snapshot(self) -> dict:
        """Deep copy of everything an undo restores (all state except _KEPT_ON_UNDO)."""
        return copy.deepcopy({k: v for k, v in self.__dict__.items() if k not in self._KEPT_ON_UNDO})

    def push_undo(self, label: str, state: dict, seen: bool) -> None:
        """Record the state from before a Storyteller action so undo() can return to it.

        Args:
            label (str): what the action did, e.g. "Kill Asta".
            state (dict): snapshot() taken just before the action ran.
            seen (bool): the action already reached phones (buzz, dawn slips, a sent message).
        """
        self.history.append({"label": label, "seen": seen, "state": state, "phone_inputs": self.phone_inputs})
        del self.history[:-self.UNDO_DEPTH]

    def undo_info(self) -> dict | None:
        """The action undo() would reverse.

        Schema: {"label": str, "seen": bool, "phone_picks": int (picks and taps made since), "depth": int}
        or None when there is nothing to undo.
        """
        if not self.history:
            return None
        top = self.history[-1]
        return {"label": top["label"], "seen": top["seen"],
                "phone_picks": self.phone_inputs - top["phone_inputs"], "depth": len(self.history)}

    def undo(self) -> None:
        """Reverse the most recent Storyteller action.

        Algorithm: pop the newest history entry and restore its snapshot over the current state.
        Fields in _KEPT_ON_UNDO are left alone, so phones do not buzz again, player notes stay and
        pids are never reused. Players who joined the lobby since the snapshot are re-seated at the
        end rather than dropped. Picks and taps made on phones since then are lost; undo_info()
        reports how many beforehand.
        """
        if not self.history:
            raise GameError("Nothing to undo")
        entry = self.history.pop()
        restored = {p.pid for p in entry["state"]["players"]}
        joined = [p for p in self.players if p.pid not in restored]
        self.__dict__.update(entry["state"])
        if self.phase == "lobby":
            self.players += joined
        self._log(f"Storyteller undid: {entry['label']}")

    # --- views ---

    def public_view(self) -> dict:
        """What every player may see. Characters are revealed only once the game is over.

        Schema: {version, phase, night, day, counts: {type: int}, threshold, buzz,
                 seats: [{pid, name, alive, ghost_vote, character|None}],
                 announcements: [str], nominations: [{nominator, nominee, votes}],
                 winner: str|None, win_reason: str}
        Tonight's deaths stay hidden (seat still alive) until dawn is announced.
        """
        over = self.phase == "over"
        timer = max(0, round(self.timer_end - time.time())) if self.timer_end else None
        return {
            "version": self.version, "phase": self.phase, "night": self.night, "day": self.day,
            "counts": self.counts, "buzz": self.buzz, "dead_eyes": self.dead_eyes, "timer": timer,
            "script": self.script, "script_name": self.script_name(),
            # from the public alive count, so a night kill does not show early
            "threshold": math.ceil(sum(self._publicly_alive(p) for p in self.players) / 2),
            "seats": [{"pid": p.pid, "name": p.name, "alive": self._publicly_alive(p), "ghost_vote": p.ghost_vote,
                       "character": p.character if over else None} for p in self.players],
            "announcements": self.announcements,
            "nominations": [{"nominator": self.get(n["nominator"]).name, "nominee": self.get(n["nominee"]).name,
                             "votes": n["votes"]} for n in self.nominations],
            "winner": self.winner, "win_reason": self.win_reason,
        }

    def _publicly_alive(self, p: Player) -> bool:
        """Alive as the table knows it: a player killed tonight still looks alive until dawn."""
        if self.phase == "night":
            return (p.alive or p.pid in self.night_deaths) and p.pid not in self.night_revived
        return p.alive

    def player_view(self, token: str) -> dict:
        """Public view plus the player's own role, messages and prompt.

        Dead Eyes Only: living players do not see their character. Dead players see their true
        character (not what they believed). Everyone sees all characters when the game is over.
        Standard: every player sees the character they believe they hold once the game starts.
        """
        p = self.by_token(token)
        started = self.phase in ("night", "day", "over")
        over = self.phase == "over"
        if self.dead_eyes:
            if over:
                role = {"id": p.character, **CHARACTERS[p.character]} if p.character else None
            elif started and not p.alive:
                role = {"id": p.character, **CHARACTERS[p.character]} if p.character else None
            else:
                role = None
        else:
            role = {"id": p.believed, **CHARACTERS[p.believed]} if started and p.believed else None
        return {**self.public_view(), "me": {
            "pid": p.pid, "name": p.name, "alive": self._publicly_alive(p),
            "role": role,
            "messages": p.messages, "prompt": p.prompt,
            "notes": [{"text": n["text"], "label": n["label"]} for n in self.inbox if n["pid"] == p.pid],
        }}

    def storyteller_view(self) -> dict:
        """Everything: grimoire, hidden setup choices, night steps with live answers, warnings, log.

        Extra keys over public_view: players [{pid, name, character, believed, alive, ghost_vote, evil,
        impaired, answer}], Bad Moon Rising state (grandchild, drunk {pid: night it wears off}, safe,
        pukka_poisoned, po_charged, exorcised, exorcist_last, da_target, da_last, spent, zombuul_fake,
        gossip_true, moonchild_target, mastermind_day, deaths_today), red_herring, bluffs, poisoned, protected, master, virgin_spent,
        slayer_spent, executed_today, night_deaths, steps (with applies / impaired / answer added),
        nominations_full, queued {pid: [text]}, second_round_done, inbox [{pid, text, label, read}],
        phones_done [done, total], phones [{pid, name, done, tap}] (phone players a round waits for; tap: stuck on a tap challenge),
        warnings, log, bluff_problems [str], undo (see undo_info).
        """
        steps = []
        for i, s in enumerate(self.steps):
            actor = self.get(s["pids"][0])
            asked = bool(actor.prompt and actor.prompt.get("step") == i)
            steps.append({**s, "applies": self.step_applies(s), "impaired": self.impaired(actor), "asked": asked})
        return {
            **self.public_view(),
            "players": [{"pid": p.pid, "name": p.name, "character": p.character, "believed": p.believed,
                         "alive": p.alive, "ghost_vote": p.ghost_vote, "evil": p.evil,
                         "impaired": bool(p.character) and self.impaired(p)} for p in self.players],
            "red_herring": self.red_herring, "bluffs": self.bluffs, "poisoned": self.poisoned,
            "protected": self.protected, "master": self.master, "virgin_spent": self.virgin_spent,
            "slayer_spent": self.slayer_spent, "executed_today": self.executed_today,
            "night_deaths": self.night_deaths, "steps": steps, "nominations_full": self.nominations,
            "queued": {pid: texts for pid, texts in self.queued.items()}, "second_round_done": self.second_round_done,
            "inbox": self.inbox, "phones_done": list(self.phones_done()),
            "phones": [{"pid": p.pid, "name": p.name, "done": p not in self.phones_waiting(),
                        "tap": bool(p.prompt and p.prompt["kind"] == "tap" and p.prompt["answer"] is None)}
                       for p in self._phone_players()],
            "warnings": self.setup_warnings(), "log": self.log, "undo": self.undo_info(),
            "bluff_problems": self.bluff_problems(self.bluffs) if self.phase == "setup" else [],
            # Bad Moon Rising
            "grandchild": self.grandchild, "drunk": self.drunk, "safe": self.safe,
            "pukka_poisoned": self.pukka_poisoned, "po_charged": self.po_charged, "exorcised": self.exorcised,
            "exorcist_last": self.exorcist_last, "da_target": self.da_target, "da_last": self.da_last,
            "spent": sorted(self.spent), "zombuul_fake": self.zombuul_fake, "gossip_true": self.gossip_true,
            "moonchild_target": self.moonchild_target, "mastermind_day": self.mastermind_day,
            "deaths_today": self.deaths_today,
        }


if __name__ == "__main__":
    g = Game(random.Random(3))
    for name in ["Asha", "Ben", "Chen", "Dev", "Ema", "Finn", "Gita", "Hari", "Ines"]:
        g.add_player(name)
    g.deal()
    print("warnings:", g.setup_warnings())
    g.start_game()
    for i, s in enumerate(g.steps):
        picks = [p.pid for p in g.players if s["allow_self"] or p.pid != s["pids"][0]][:s["choose"]]
        g.resolve(i, picks, guess="imp" if s["guess"] else None)
        print(f"{s['key']:15} -> {s['suggestion']}")
    g.start_day()
    g.nominate(g.players[0].pid, g.players[1].pid)
    g.record_votes(0, [p.pid for p in g.players[:6]])
    g.end_day()
    print("\n".join(g.log))
