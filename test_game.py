"""Rule tests for the Trouble Brewing engine. Run: uv run --with pytest pytest -q"""

import random
import time

import pytest

import info
from game import Game, GameError
from roles import CHARACTERS, NIGHT_CHOICES, is_good

NAMES = ["Asha", "Ben", "Chen", "Dev", "Ema", "Finn", "Gita", "Hari", "Ines"]


def make(chars: list[str], seed: int = 1, phones: bool = False, dead_eyes: bool = False) -> Game:
    """Seat len(chars) players (joined from phones if phones), force their characters in seat order, start night 1."""
    g = Game(random.Random(seed))
    if dead_eyes:
        g.dead_eyes = True
    for n in NAMES[:len(chars)]:
        g.add_player(n, phone=phones)
    g.deal()
    for p, c in zip(g.players, chars):
        g.set_character(p.pid, c)
    # re-pick the Drunk's belief now that every real character is placed
    for p in g.players:
        if p.character == "drunk":
            g.set_character(p.pid, "drunk")
    g.red_herring = next(p.pid for p in g.players if p.character not in ("imp", "poisoner", "spy", "scarlet_woman", "baron"))
    held = {x for p in g.players for x in (p.character, p.believed)}
    g.bluffs = [c for c in CHARACTERS if is_good(c) and c not in held][:3]
    g.start_game()
    return g


def p(g: Game, name: str):
    return next(x for x in g.players if x.name == name)


def to_night2(g: Game) -> None:
    g.start_day()
    g.end_day()


def step(g: Game, key: str) -> int:
    return next(i for i, s in enumerate(g.steps) if s["key"] == key)


NINE = ["imp", "scarlet_woman", "monk", "soldier", "empath", "virgin", "slayer", "saint", "mayor"]


def test_first_night_order_and_evil_info():
    g = make(NINE)
    assert [s["key"] for s in g.steps] == ["minion_info", "demon_info", "empath"]
    g.resolve(0, [])
    assert "The Demon is Asha" in g.steps[0]["suggestion"]


def test_small_game_includes_evil_info():
    g = make(["imp", "poisoner", "empath", "chef", "saint"], dead_eyes=True)
    assert "minion_info" in [s["key"] for s in g.steps]
    assert "demon_info" in [s["key"] for s in g.steps]


def test_small_game_skips_evil_info_in_standard():
    g = make(["imp", "poisoner", "empath", "chef", "saint"])
    assert "minion_info" not in [s["key"] for s in g.steps]


def test_monk_protects_and_soldier_survives():
    g = make(NINE)
    to_night2(g)
    g.resolve(step(g, "monk"), [p(g, "Ema").pid])
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    assert p(g, "Ema").alive
    g.start_day(); g.end_day()
    g.resolve(step(g, "imp"), [p(g, "Dev").pid])
    assert p(g, "Dev").alive


def test_poisoned_soldier_dies():
    g = make(["imp", "poisoner", "soldier", "empath", "chef", "saint", "mayor"])
    to_night2(g)
    g.resolve(step(g, "poisoner"), [p(g, "Chen").pid])
    g.resolve(step(g, "imp"), [p(g, "Chen").pid])
    assert not p(g, "Chen").alive


def test_star_pass_prefers_scarlet_woman():
    g = make(NINE)
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Asha").pid])
    assert p(g, "Ben").character == "imp" and not p(g, "Asha").alive and g.winner is None


def test_executing_demon_promotes_scarlet_woman_then_good_wins():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    assert p(g, "Ben").character == "imp" and g.winner is None
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    assert g.winner == "good"


def test_virgin_executes_townsfolk_nominator_only_once():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Gita").pid, p(g, "Finn").pid)
    assert not p(g, "Gita").alive and g.executed_today == p(g, "Gita").pid
    with pytest.raises(GameError):
        g.nominate(p(g, "Ema").pid, p(g, "Dev").pid)


def test_virgin_ignores_minion_nominator():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Ben").pid, p(g, "Finn").pid)
    assert p(g, "Ben").alive and g.virgin_spent


def test_slayer_kills_demon_once():
    g = make(NINE)
    g.start_day()
    g.slayer_shot(p(g, "Gita").pid, p(g, "Chen").pid)
    assert g.slayer_spent and p(g, "Chen").alive
    g.slayer_shot(p(g, "Gita").pid, p(g, "Asha").pid)
    assert p(g, "Asha").alive


def test_saint_execution_loses():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Hari").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    assert g.winner == "evil"


def test_tie_means_no_execution():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Dev").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.nominate(p(g, "Dev").pid, p(g, "Ema").pid)
    g.record_votes(1, [x.pid for x in g.players[4:]])
    g.end_day()
    assert all(x.alive for x in g.players)


def test_ghost_vote_spent_and_refunded():
    g = make(NINE)
    g.start_day()
    g.kill(p(g, "Ema").pid)
    g.nominate(p(g, "Chen").pid, p(g, "Dev").pid)
    g.record_votes(0, [p(g, "Ema").pid])
    assert not p(g, "Ema").ghost_vote
    g.record_votes(0, [])
    assert p(g, "Ema").ghost_vote


def test_mayor_wins_at_three_without_execution():
    g = make(["imp", "poisoner", "mayor", "empath", "chef"])
    g.start_day()
    g.kill(p(g, "Dev").pid)
    g.kill(p(g, "Ema").pid)
    g.end_day()
    assert g.winner == "good"


def test_evil_wins_at_two_alive():
    g = make(["imp", "poisoner", "monk", "empath", "chef"])
    g.start_day()
    for n in ("Chen", "Dev"):
        g.kill(p(g, n).pid)
    assert g.winner is None
    g.kill(p(g, "Ema").pid)
    assert g.winner == "evil"


def test_empath_skips_dead_neighbours():
    g = make(NINE)
    g.kill(p(g, "Dev").pid)
    g.kill(p(g, "Finn").pid)
    assert {x.name for x in info.living_neighbours(g, p(g, "Ema"))} == {"Chen", "Gita"}


def test_drunk_monk_wakes_but_cannot_protect():
    g = make(["imp", "poisoner", "drunk", "empath", "chef", "saint", "mayor"])
    g.set_character(p(g, "Chen").pid, "drunk", believed="monk")
    to_night2(g)
    i = step(g, "monk")
    assert g.steps[i]["pids"] == [p(g, "Chen").pid]
    assert g.storyteller_view()["steps"][i]["impaired"]
    g.resolve(i, [p(g, "Dev").pid])
    g.resolve(step(g, "imp"), [p(g, "Dev").pid])
    assert not p(g, "Dev").alive


def test_fortune_teller_red_herring_reads_yes():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"])
    g.red_herring = p(g, "Ema").pid
    i = step(g, "fortune_teller")
    g.resolve(i, [p(g, "Ema").pid, p(g, "Dev").pid])
    assert "YES" in g.steps[i]["suggestion"]
    g.resolve(i, [p(g, "Dev").pid, p(g, "Finn").pid])
    assert "NO" in g.steps[i]["suggestion"]


def test_chef_counts_adjacent_pairs_around_circle():
    g = make(["imp", "empath", "chef", "saint", "mayor", "monk", "poisoner"])
    assert info.evil_pairs(g) == 1


# --- eyes-open nights ---

def test_night_start_prompts_every_living_chooser_and_buzzes():
    g = make(["imp", "poisoner", "fortune_teller", "butler", "chef", "saint", "ravenkeeper"])
    assert g.buzz == 1
    choosers = {x.name for x in g.players if x.prompt and x.prompt["kind"] == "choose"}
    assert choosers == {"Ben", "Chen", "Dev"}
    to_night2(g)
    choosers = {x.name for x in g.players if x.prompt and x.prompt["kind"] == "choose"}
    assert choosers == {"Asha", "Ben", "Chen", "Dev"}


def test_info_is_held_until_dawn_and_everyone_gets_a_slip():
    g = make(NINE)
    i = step(g, "empath")
    g.resolve(i, [])
    g.send(i, g.steps[i]["suggestion"])
    assert p(g, "Ema").messages == []
    before = g.buzz
    g.start_day()
    assert g.buzz == before + 1
    assert "neighbours" in p(g, "Ema").messages[-1]["text"]
    assert p(g, "Chen").messages[-1]["text"] == "Nothing to report tonight."
    assert all(x.messages for x in g.players)


def test_imp_kill_starts_second_round_and_prompts_dead_ravenkeeper():
    g = make(["imp", "poisoner", "ravenkeeper", "empath", "chef", "saint", "mayor"])
    to_night2(g)
    before = g.buzz
    g.resolve(step(g, "imp"), [p(g, "Chen").pid])
    assert g.buzz == before + 1 and g.second_round_done
    assert p(g, "Chen").prompt and not p(g, "Chen").alive


def test_second_round_buzzes_even_when_ravenkeeper_survives():
    g = make(["imp", "poisoner", "ravenkeeper", "empath", "chef", "saint", "mayor"], phones=True)
    finish_phones(g)
    to_night2(g)
    finish_phones(g)
    before = g.buzz
    g.resolve(step(g, "imp"), [p(g, "Dev").pid])
    assert g.buzz == before + 1 and p(g, "Chen").prompt["kind"] == "tap"
    assert p(g, "Chen").prompt["answer"], "a living Ravenkeeper means no second tap"
    assert g.phones_waiting() == []


def test_second_round_taps_cover_a_dead_ravenkeepers_pick():
    g = make(["imp", "poisoner", "ravenkeeper", "empath", "chef", "saint", "mayor"], phones=True)
    finish_phones(g)
    to_night2(g)
    finish_phones(g)
    g.resolve(step(g, "imp"), [p(g, "Chen").pid])
    assert p(g, "Chen").prompt["kind"] == "choose"
    others = [x for x in g.players if x.name != "Chen"]
    assert all(x.prompt["kind"] == "tap" and x.prompt["answer"] is None for x in others)


def test_drunk_believing_ravenkeeper_killed_gets_second_taps():
    g = make(["imp", "poisoner", "drunk", "empath", "chef", "saint", "mayor"], phones=True)
    p(g, "Chen").believed = "ravenkeeper"
    finish_phones(g)
    to_night2(g)
    finish_phones(g)
    g.resolve(step(g, "imp"), [p(g, "Chen").pid])
    assert p(g, "Chen").prompt["kind"] == "choose"
    assert p(g, "Ema").prompt["kind"] == "tap" and p(g, "Ema").prompt["answer"] is None


def test_star_pass_news_waits_for_dawn():
    g = make(NINE)
    to_night2(g)
    seen = len(p(g, "Ben").messages)
    g.resolve(step(g, "imp"), [p(g, "Asha").pid])
    assert len(p(g, "Ben").messages) == seen
    g.start_day()
    assert p(g, "Ben").messages[-1]["text"] == "You are now the Imp."


def test_phone_answer_only_shows_on_its_own_step():
    g = make(["imp", "poisoner", "empath", "chef", "saint", "mayor", "monk"])
    ben = p(g, "Ben")
    g.choose(ben.token, [p(g, "Ema").pid])
    view = g.storyteller_view()["steps"]
    assert view[step(g, "minion_info")]["answer"] is None
    assert view[step(g, "poisoner")]["answer"] == [p(g, "Ema").pid]


def test_holding_evil_info_keeps_poisoner_prompt_open():
    g = make(["imp", "poisoner", "empath", "chef", "saint", "mayor", "monk"])
    i = step(g, "minion_info")
    g.resolve(i, [])
    g.send(i, g.steps[i]["suggestion"])
    assert p(g, "Ben").prompt and p(g, "Ben").prompt["step"] == step(g, "poisoner")


def test_player_note_reaches_storyteller_only():
    g = make(NINE)
    g.note_to_storyteller(p(g, "Ema").token, "Can the Monk protect themselves?")
    st = g.storyteller_view()["inbox"]
    assert st[0]["pid"] == p(g, "Ema").pid and not st[0]["read"]
    assert g.player_view(p(g, "Ema").token)["me"]["notes"][0]["text"].startswith("Can the Monk")
    assert g.player_view(p(g, "Ben").token)["me"]["notes"] == []
    assert "inbox" not in g.public_view()
    g.read_inbox()
    assert g.storyteller_view()["inbox"][0]["read"]
    with pytest.raises(GameError):
        g.note_to_storyteller(p(g, "Ema").token, "   ")


def test_night_message_now_skips_dawn_queue():
    g = make(NINE)
    g.message(p(g, "Ema").pid, "Yes, the Monk cannot pick themselves.", now=True)
    assert p(g, "Ema").messages[-1]["text"].startswith("Yes")
    assert p(g, "Ema").pid not in g.queued


def test_night_kill_hidden_from_phones_until_dawn():
    g = make(NINE)
    to_night2(g)
    ema = p(g, "Ema")
    g.resolve(step(g, "imp"), [ema.pid])
    assert not ema.alive
    seat = next(x for x in g.public_view()["seats"] if x["pid"] == ema.pid)
    assert seat["alive"] and g.player_view(ema.token)["me"]["alive"]
    assert not next(x for x in g.storyteller_view()["players"] if x["pid"] == ema.pid)["alive"]
    g.start_day()
    assert not next(x for x in g.public_view()["seats"] if x["pid"] == ema.pid)["alive"]


def test_scarlet_woman_gets_imp_kill_prompt_after_imp_executed():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    i = step(g, "imp")
    assert g.steps[i]["pids"] == [p(g, "Ben").pid]
    assert g.step_applies(g.steps[i]) and p(g, "Ben").prompt["step"] == i


def test_new_imp_after_star_pass_acts_next_night():
    g = make(NINE)
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Asha").pid])
    g.start_day()
    g.end_day()
    assert g.steps[step(g, "imp")]["pids"] == [p(g, "Ben").pid]


def test_undertaker_info_sent_automatically_at_dawn():
    g = make(["imp", "poisoner", "undertaker", "empath", "chef", "soldier", "mayor"])
    g.start_day()
    g.nominate(p(g, "Asha").pid, p(g, "Ben").pid)
    g.record_votes(0, [x.pid for x in g.players[:4]])
    g.end_day()
    g.start_day()
    assert p(g, "Chen").messages[-1]["text"] == "Ben, executed today, was the Poisoner."


def test_undertaker_manual_send_is_not_duplicated():
    g = make(["imp", "poisoner", "undertaker", "empath", "chef", "soldier", "mayor"])
    g.start_day()
    g.nominate(p(g, "Asha").pid, p(g, "Ben").pid)
    g.record_votes(0, [x.pid for x in g.players[:4]])
    g.end_day()
    i = step(g, "undertaker")
    g.send(i, "Ben was the Chef.")
    g.start_day()
    night_msgs = [m["text"] for m in p(g, "Chen").messages if m["label"] == "Night 2"]
    assert night_msgs == ["Ben was the Chef."]


def test_undertaker_sleeps_without_execution():
    g = make(["imp", "poisoner", "undertaker", "empath", "chef", "soldier", "mayor"])
    to_night2(g)
    g.start_day()
    assert p(g, "Chen").messages[-1]["text"] == "Nothing to report tonight."


def _setup(chars: list[str]) -> Game:
    g = Game(random.Random(1))
    for n in NAMES[:len(chars)]:
        g.add_player(n)
    g.deal()
    for pl, c in zip(g.players, chars):
        g.set_character(pl.pid, c)
    return g


def test_start_refuses_drunk_believing_in_play_character():
    g = _setup(["imp", "poisoner", "fortune_teller", "drunk", "chef", "saint", "mayor"])
    g.set_character(g.players[3].pid, "drunk", believed="fortune_teller")
    with pytest.raises(GameError, match="Fortune Teller is in play"):
        g.start_game()
    assert g.phase == "setup"


def test_start_refuses_duplicate_characters():
    g = _setup(["imp", "poisoner", "fortune_teller", "fortune_teller", "chef", "saint", "mayor"])
    with pytest.raises(GameError, match="only be dealt once"):
        g.start_game()


# --- tap tasks ---

def finish_phones(g: Game) -> None:
    """Every waiting phone completes its tap task or answers its real choice (first legal pick)."""
    for x in g.phones_waiting():
        if x.prompt["kind"] == "tap":
            g.tap(x.token, x.prompt["target"])
        else:
            pool = [q.pid for q in g.players if x.prompt["allow_self"] or q.pid != x.pid]
            g.choose(x.token, pool[:x.prompt["count"]], (x.prompt.get("guess") or [None])[0])


def test_everyone_without_a_choice_gets_a_tap_task():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"], phones=True)
    kinds = {x.name: x.prompt["kind"] for x in g.players}
    assert kinds == {"Asha": "tap", "Ben": "choose", "Chen": "choose", "Dev": "tap",
                     "Ema": "tap", "Finn": "tap", "Gita": "tap"}
    tap = p(g, "Dev").prompt
    assert len(set(tap["options"])) == 6 and set(tap["options"]) <= set(CHARACTERS)
    assert len(set(tap["target"])) == 3 and set(tap["target"]) <= set(tap["options"])


def test_players_without_a_phone_get_no_tap_task_and_are_not_waited_for():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"])
    assert all(x.prompt is None or x.prompt["kind"] == "choose" for x in g.players)
    assert g.phones_done() == (0, 0)
    g.start_day()


def test_tap_needs_the_icons_in_order():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"], phones=True)
    dev = p(g, "Dev")
    target = dev.prompt["target"]
    for wrong in (target[::-1], target[:2], [target[0], target[1], next(o for o in dev.prompt["options"] if o not in target)]):
        with pytest.raises(GameError, match="Start again"):
            g.tap(dev.token, wrong)
    assert g.phones_done() == (0, 7)
    g.tap(dev.token, target)
    assert dev.prompt["answer"] == target and g.phones_done() == (1, 7)


def test_dawn_waits_for_every_phone_with_no_override():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"], phones=True)
    with pytest.raises(GameError, match="before dawn"):
        g.start_day()
    finish_phones(g)
    dev = p(g, "Dev")
    g.ask(step(g, "poisoner"))
    with pytest.raises(GameError, match="Ben to finish"):
        g.start_day()
    assert g.phase == "night" and g.storyteller_view()["phones"] == [
        {"pid": x.pid, "name": x.name, "done": x.name != "Ben", "tap": False} for x in g.players]
    finish_phones(g)
    g.start_day()
    assert g.phase == "day" and dev.prompt is None


def test_second_buzz_waits_for_every_phone():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"], phones=True)
    finish_phones(g)
    to_night2(g)
    with pytest.raises(GameError, match="before the second buzz"):
        g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    assert p(g, "Ema").alive, "a refused Imp pick must not kill"
    with pytest.raises(GameError, match="before the second buzz"):
        g.second_round()
    finish_phones(g)
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    assert g.second_round_done and not p(g, "Ema").alive


def test_second_round_hands_out_no_new_taps():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"], phones=True)
    finish_phones(g)
    g.start_day()
    g.kill(p(g, "Finn").pid)
    g.end_day()
    assert p(g, "Finn").prompt is None
    chen = p(g, "Chen")
    g.choose(chen.token, [p(g, "Asha").pid, p(g, "Dev").pid])
    finish_phones(g)
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    assert chen.prompt["kind"] == "choose" and chen.prompt["answer"], "a finished pick is not replaced by a tap"
    assert g.storyteller_view()["steps"][step(g, "fortune_teller")]["answer"] == [p(g, "Asha").pid, p(g, "Dev").pid]
    ema = p(g, "Ema").prompt
    assert ema["kind"] == "tap" and ema["answer"], "the nightfall tap stays done, no second one"
    assert p(g, "Finn").prompt is None
    assert g.phones_waiting() == []


def test_unanswered_real_choice_survives_second_round():
    g = make(["imp", "poisoner", "fortune_teller", "empath", "chef", "saint", "mayor"])
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    assert p(g, "Chen").prompt["kind"] == "choose"


# --- demon bluffs ---

def dealt(n: int = 7, seed: int = 3) -> Game:
    """A freshly dealt game in setup, not yet started."""
    g = Game(random.Random(seed))
    for name in NAMES[:n]:
        g.add_player(name)
    g.deal()
    return g


def test_dealt_bluffs_are_legal():
    for seed in range(50):
        g = dealt(seed=seed)
        assert g.bluff_problems(g.bluffs) == []


@pytest.mark.parametrize("pick, message", [
    (lambda g, free: [free[0], free[0], free[1]], "different"),
    (lambda g, free: [free[0], free[1], "baron"], "good characters"),
    (lambda g, free: [free[0], free[1], next(p.character for p in g.players if is_good(p.character))], "in play"),
    (lambda g, free: [free[0], free[1], "nobody"], "exactly three"),
    (lambda g, free: free[:2], "exactly three"),
])
def test_illegal_bluffs_rejected(pick, message):
    g = dealt()
    held = {p.character for p in g.players}
    free = [c for c in CHARACTERS if is_good(c) and c not in held]
    with pytest.raises(GameError, match=message):
        g.set_setup(g.red_herring, pick(g, free))


def test_drunk_belief_cannot_be_a_bluff():
    g = dealt()
    g.set_character(g.players[0].pid, "drunk")
    believed = g.players[0].believed
    with pytest.raises(GameError, match="Drunk believes"):
        g.set_setup(g.red_herring, [believed] + [b for b in g.bluffs if b != believed][:2])


def test_start_refuses_bluff_put_in_play_after_saving():
    g = dealt()
    g.set_character(g.players[0].pid, g.bluffs[0])
    assert g.storyteller_view()["bluff_problems"]
    with pytest.raises(GameError, match="must not be in play"):
        g.start_game()


# --- undo ---

def undoable(g: Game, action: str, *args, label: str = "x", **kwargs) -> None:
    """Run a Storyteller action the way the server does: snapshot first, push on success."""
    before = g.snapshot()
    getattr(g, action)(*args, **kwargs)
    g.push_undo(label, before, seen=False)


def test_undo_reverses_a_kill_and_logs_it():
    g = make(["imp", "baron", "chef", "empath", "monk", "saint", "soldier"])
    to_night2(g)
    asha = p(g, "Asha")
    undoable(g, "kill", asha.pid, label="Kill Asha")
    assert not p(g, "Asha").alive
    assert g.undo_info()["label"] == "Kill Asha"
    g.undo()
    assert p(g, "Asha").alive
    assert g.undo_info() is None
    assert g.log[-1].endswith("Storyteller undid: Kill Asha")


def test_undo_with_empty_history_refuses():
    with pytest.raises(GameError, match="Nothing to undo"):
        Game().undo()


def test_undo_keeps_buzz_notes_and_counts_lost_phone_picks():
    g = make(["imp", "baron", "chef", "empath", "monk", "saint", "soldier"])
    buzz = g.buzz
    undoable(g, "start_day")
    g.note_to_storyteller(p(g, "Ben").token, "Is the Saint safe?")
    g.undo()
    assert g.phase == "night"
    assert g.buzz == buzz + 1, "undo must not lower the buzz, or phones would buzz again"
    assert g.inbox[-1]["text"] == "Is the Saint safe?"

    g2 = make(["imp", "baron", "chef", "empath", "monk", "saint", "soldier"], phones=True)
    undoable(g2, "kill", p(g2, "Gita").pid)
    tapper = next(x for x in g2.players if x.prompt and x.prompt["kind"] == "tap" and not x.prompt["answer"])
    g2.tap(tapper.token, tapper.prompt["target"])
    assert g2.undo_info()["phone_picks"] == 1


def test_undo_in_lobby_keeps_players_who_joined_since():
    g = Game(random.Random(1))
    for n in NAMES[:5]:
        g.add_player(n)
    undoable(g, "move_player", g.players[0].pid, 1)
    late = g.add_player("Zed")
    g.undo()
    assert [x.name for x in g.players] == NAMES[:5] + ["Zed"]
    assert g.add_player("Yan").pid != late.pid


def test_undo_history_is_capped():
    g = Game(random.Random(1))
    for n in NAMES[:5]:
        g.add_player(n)
    for _ in range(Game.UNDO_DEPTH + 5):
        undoable(g, "move_player", g.players[0].pid, 1)
    assert g.undo_info()["depth"] == Game.UNDO_DEPTH


def test_night_kill_does_not_move_public_threshold():
    g = make(["imp", "baron", "chef", "empath", "monk", "saint", "soldier"])
    before = g.public_view()["threshold"]
    g.kill(p(g, "Gita").pid)
    assert g.public_view()["threshold"] == before
    g.start_day()
    assert g.public_view()["threshold"] == g.threshold()


# --- Dead Eyes Only ---

def test_alive_player_view_hides_role():
    g = make(NINE, dead_eyes=True)
    for x in g.players:
        view = g.player_view(x.token)["me"]
        assert view["role"] is None, f"living {x.name} should not see their role"


def test_dead_player_view_reveals_true_character():
    g = make(NINE, dead_eyes=True)
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    ema = p(g, "Ema")
    view = g.player_view(ema.token)["me"]
    assert view["role"] is not None, "dead player should see their role"
    assert view["role"]["id"] == ema.character, "dead player should see their TRUE character"


def test_drunk_death_reveals_drunk_not_believed():
    g = _setup(["imp", "poisoner", "drunk", "empath", "chef", "saint", "mayor"])
    g.dead_eyes = True
    g.set_character(g.players[2].pid, "drunk", believed="monk")
    held = {x for pl in g.players for x in (pl.character, pl.believed)}
    g.bluffs = [c for c in CHARACTERS if is_good(c) and c not in held][:3]
    g.start_game()
    g.start_day()
    g.nominate(p(g, "Dev").pid, p(g, "Chen").pid)
    g.record_votes(0, [x.pid for x in g.players[:4]])
    g.end_day()
    chen = p(g, "Chen")
    view = g.player_view(chen.token)["me"]
    assert view["role"]["id"] == "drunk", "dead Drunk should see 'drunk', not their believed character"
    death_msg = next(m for m in chen.messages if "You were the" in m["text"])
    assert "Drunk" in death_msg["text"]
    assert "Monk" in death_msg["text"], "death reveal should mention the believed character"


def test_death_reveal_on_execution():
    g = make(NINE, dead_eyes=True)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    asha = p(g, "Asha")
    death_msg = next(m for m in asha.messages if "You were the" in m["text"])
    assert "Imp" in death_msg["text"]
    assert "evil" in death_msg["text"]


def test_death_reveal_on_night_kill_arrives_at_dawn():
    g = make(NINE, dead_eyes=True)
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Ema").pid])
    ema = p(g, "Ema")
    assert not any("You were the" in m["text"] for m in ema.messages), "night reveal should be held"
    g.start_day()
    death_msg = next(m for m in ema.messages if "You were the" in m["text"])
    assert "Empath" in death_msg["text"]
    assert "good" in death_msg["text"]


def test_generic_prompt_for_alive_player():
    g = make(["imp", "poisoner", "fortune_teller", "butler", "chef", "saint", "ravenkeeper"], dead_eyes=True)
    for x in g.players:
        if x.prompt and x.prompt["kind"] == "choose":
            assert "Storyteller" in x.prompt["text"], f"alive {x.name} should get a generic prompt"
            assert x.prompt["text"] != NIGHT_CHOICES.get(x.believed, (0, True, ""))[2], \
                f"alive {x.name}'s prompt should not reveal their ability"


def test_ravenkeeper_dead_gets_specific_prompt():
    g = make(["imp", "poisoner", "ravenkeeper", "empath", "chef", "saint", "mayor"], dead_eyes=True)
    to_night2(g)
    g.resolve(step(g, "imp"), [p(g, "Chen").pid])
    chen = p(g, "Chen")
    assert chen.prompt and chen.prompt["kind"] == "choose"
    assert "died tonight" in chen.prompt["text"], "dead Ravenkeeper should get the specific prompt"


def test_evil_info_reveals_team_not_specific_roles():
    g = make(NINE, dead_eyes=True)
    mi = step(g, "minion_info")
    g.resolve(mi, [])
    text = g.steps[mi]["suggestion"]
    assert "You are a Minion" in text
    assert "Asha" in text, "evil meeting should list the Demon's player name"
    assert "Imp" not in text, "evil meeting should not reveal specific role names"
    di = step(g, "demon_info")
    g.resolve(di, [])
    text = g.steps[di]["suggestion"]
    assert "You are the Demon" in text
    assert "bluffs" in text.lower()


def test_game_over_reveals_all_characters():
    g = make(NINE, dead_eyes=True)
    alive_view = g.player_view(p(g, "Ema").token)["me"]
    assert alive_view["role"] is None
    g.declare_winner("good")
    over_view = g.player_view(p(g, "Ema").token)["me"]
    assert over_view["role"] is not None
    assert over_view["role"]["id"] == p(g, "Ema").character


# --- standard variant ---

def test_standard_mode_shows_role_to_alive_player():
    g = make(NINE)
    assert not g.dead_eyes
    for x in g.players:
        view = g.player_view(x.token)["me"]
        assert view["role"] is not None, f"living {x.name} should see their role in standard mode"
        assert view["role"]["id"] == x.believed


def test_standard_mode_no_death_reveal_message():
    g = make(NINE)
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players[:5]])
    g.end_day()
    asha = p(g, "Asha")
    assert not any("You were the" in m["text"] for m in asha.messages)


def test_standard_mode_specific_prompts():
    g = make(["imp", "poisoner", "fortune_teller", "butler", "chef", "saint", "ravenkeeper"])
    for x in g.players:
        if x.prompt and x.prompt["kind"] == "choose":
            assert "Storyteller" not in x.prompt["text"], f"{x.name} should get a specific prompt"


def test_standard_evil_info_reveals_specific_roles():
    g = make(NINE)
    mi = step(g, "minion_info")
    g.resolve(mi, [])
    text = g.steps[mi]["suggestion"]
    assert "The Demon is" in text
    assert "The Minions are" in text


def test_set_variant_requires_lobby_or_setup():
    g = make(NINE)
    with pytest.raises(GameError, match="Not allowed"):
        g.set_variant(True)


def test_set_variant_toggles():
    g = Game(random.Random(1))
    for n in NAMES[:7]:
        g.add_player(n)
    assert not g.dead_eyes
    g.set_variant(True)
    assert g.dead_eyes
    g.set_variant(False)
    assert not g.dead_eyes


def test_dead_eyes_in_public_view():
    g = make(NINE, dead_eyes=True)
    assert g.public_view()["dead_eyes"] is True
    g2 = make(NINE)
    assert g2.public_view()["dead_eyes"] is False


# --- day timer ---

def test_start_timer_during_day():
    g = make(NINE)
    g.start_day()
    g.start_timer(5)
    assert g.timer_end is not None
    view = g.public_view()
    assert view["timer"] is not None and view["timer"] > 0


def test_timer_requires_day():
    g = make(NINE)
    with pytest.raises(GameError, match="Not allowed"):
        g.start_timer(5)


def test_timer_range():
    g = make(NINE)
    g.start_day()
    with pytest.raises(GameError, match="between 1 and 15"):
        g.start_timer(0)
    with pytest.raises(GameError, match="between 1 and 15"):
        g.start_timer(16)


def test_stop_timer():
    g = make(NINE)
    g.start_day()
    g.start_timer(5)
    g.stop_timer()
    assert g.timer_end is None
    assert g.public_view()["timer"] is None


def test_stop_timer_when_none():
    g = make(NINE)
    g.start_day()
    with pytest.raises(GameError, match="No timer"):
        g.stop_timer()


def test_timer_fires_on_check():
    g = make(NINE)
    g.start_day()
    g.timer_end = time.time() - 1
    assert g.check_timer() is True
    assert g.timer_end is None
    assert any("Time is up" in a for a in g.announcements)


def test_timer_clears_on_night():
    g = make(NINE)
    g.start_day()
    g.start_timer(5)
    g.end_day()
    assert g.timer_end is None


def test_timer_no_op_when_not_expired():
    g = make(NINE)
    g.start_day()
    g.start_timer(10)
    assert g.check_timer() is False
    assert g.timer_end is not None


# --- Bad Moon Rising ---

from roles import BAD_MOON_RISING, SCRIPTS, expected_counts, on_script  # noqa: E402


def make_bmr(chars: list[str], seed: int = 1, phones: bool = False, believed: dict | None = None) -> Game:
    """Like make(), on Bad Moon Rising. believed maps seat index -> believed Demon for a Lunatic."""
    g = Game(random.Random(seed))
    g.set_script(BAD_MOON_RISING)
    for n in NAMES[:len(chars)]:
        g.add_player(n, phone=phones)
    g.deal()
    for i, (pl, c) in enumerate(zip(g.players, chars)):
        g.set_character(pl.pid, c, (believed or {}).get(i))
    held = {x for pl in g.players for x in (pl.character, pl.believed)}
    g.bluffs = [c for c in on_script(BAD_MOON_RISING) if is_good(c) and c not in held][:3]
    if "grandmother" in chars:
        g.grandchild = next(pl.pid for pl in g.players if is_good(pl.character) and pl.character != "grandmother")
    g.start_game()
    return g


def night_n(g: Game) -> None:
    """Dawn then dusk with no execution."""
    g.start_day()
    g.end_day()


def bstep(g: Game, key: str, pid: str | None = None) -> int:
    return next(i for i, s in enumerate(g.steps) if s["key"] == key and (pid is None or s["pids"] == [pid]))


BMR9 = ["po", "godfather", "lunatic", "grandmother", "sailor", "chambermaid", "fool", "tea_lady", "innkeeper"]


@pytest.mark.parametrize("seed", range(40))
def test_bmr_deal_is_on_script_and_legal(seed):
    g = Game(random.Random(seed))
    g.set_script(BAD_MOON_RISING)
    for n in NAMES:
        g.add_player(n)
    g.deal()
    chars = [x.character for x in g.players]
    assert all(CHARACTERS[c]["script"] == BAD_MOON_RISING for c in chars)
    assert all(CHARACTERS[b]["script"] == BAD_MOON_RISING for b in g.bluffs)
    assert not [w for w in g.setup_warnings() if "Counts" in w]
    for x in g.players:
        if x.character == "lunatic":
            assert CHARACTERS[x.believed]["type"] == "demon"
    assert g.red_herring is None


def test_godfather_counts():
    assert (6, 1, 1, 1) in expected_counts(9, ["godfather"]) and (4, 3, 1, 1) in expected_counts(9, ["godfather"])
    assert expected_counts(7, ["godfather"]) == [(4, 1, 1, 1)]


def test_script_change_in_setup_redeals_and_rejects_off_script():
    g = Game(random.Random(2))
    for n in NAMES:
        g.add_player(n)
    g.deal()
    g.set_script(BAD_MOON_RISING)
    assert g.phase == "setup"
    assert all(CHARACTERS[x.character]["script"] == BAD_MOON_RISING for x in g.players)
    with pytest.raises(GameError):
        g.set_character(g.players[0].pid, "imp")


def test_bmr_first_night_order_and_lunatic():
    g = make_bmr(BMR9, believed={2: "pukka"})
    keys = [s["key"] for s in g.steps]
    # the Lunatic believes they are the Pukka, so they wake at the Pukka's slot
    assert keys == ["minion_info", "demon_info", "lunatic_info", "sailor", "godfather", "pukka", "grandmother",
                    "chambermaid"]
    assert g.steps[keys.index("pukka")]["pids"] == [p(g, "Chen").pid]
    assert "The Lunatic is Chen" in info.suggest(g, "demon_info", None, [])
    g.resolve(bstep(g, "godfather"), [])
    assert "Outsiders in play: Lunatic" in g.steps[bstep(g, "godfather")]["suggestion"]
    g.resolve(bstep(g, "grandmother"), [])
    assert "Your grandchild is" in g.steps[bstep(g, "grandmother")]["suggestion"]


def test_lunatic_gets_own_demon_step_and_demon_learns_pick():
    g = make_bmr(BMR9, believed={2: "po"})
    night_n(g)
    lun, po = p(g, "Chen"), p(g, "Asha")
    assert bstep(g, "po", lun.pid) != bstep(g, "po", po.pid)
    g.resolve(bstep(g, "po", lun.pid), [p(g, "Hari").pid])
    assert p(g, "Hari").alive
    assert any("The Lunatic (Chen) chose Hari" in t for t in g.queued[po.pid])


def test_sailor_cannot_die_and_innkeeper_shelters():
    g = make_bmr(BMR9)
    night_n(g)
    g.resolve(bstep(g, "sailor"), [p(g, "Finn").pid])  # Finn (Chambermaid) is drunk, the Sailor sober
    g.resolve(bstep(g, "innkeeper"), [p(g, "Gita").pid, p(g, "Ines").pid], drunk=p(g, "Gita").pid)
    g.resolve(bstep(g, "po"), [p(g, "Ema").pid])
    assert p(g, "Ema").alive
    assert g.impaired(p(g, "Finn")) and g.impaired(p(g, "Gita"))
    g.start_day()
    g.end_day()
    assert not g.impaired(p(g, "Finn")), "drunk until dusk only"


def test_fool_survives_once():
    g = make_bmr(["po", "godfather", "fool", "sailor", "chambermaid", "gambler", "tinker"])
    night_n(g)
    g.resolve(bstep(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive
    night_n(g)
    g.resolve(bstep(g, "po"), [p(g, "Chen").pid])
    assert not p(g, "Chen").alive


def test_tea_lady_protects_good_neighbours():
    g = make_bmr(["po", "godfather", "sailor", "tea_lady", "fool", "gambler", "tinker"])
    night_n(g)
    g.resolve(bstep(g, "po"), [p(g, "Ema").pid])  # Ema sits next to the Tea Lady; Chen is the other good neighbour
    assert p(g, "Ema").alive


def test_exorcist_stops_demon():
    g = make_bmr(["po", "godfather", "exorcist", "sailor", "chambermaid", "gambler", "tinker"], phones=True)
    finish_phones(g)
    night_n(g)
    po = p(g, "Asha")
    g.resolve(bstep(g, "exorcist"), [po.pid])
    s = g.steps[bstep(g, "po")]
    assert s["done"] and not g.step_applies(s)
    assert po.prompt["kind"] == "tap"
    assert any("The Exorcist (Chen) chose you" in t for t in g.queued[po.pid])
    finish_phones(g)
    night_n(g)
    with pytest.raises(GameError):
        g.resolve(bstep(g, "exorcist"), [po.pid])


def test_po_charges_then_kills_three():
    g = make_bmr(["po", "godfather", "chambermaid", "sailor", "gambler", "tinker", "minstrel", "fool"])
    night_n(g)
    g.resolve(bstep(g, "po"), [])
    assert g.po_charged
    night_n(g)
    s = g.steps[bstep(g, "po")]
    assert s["choose"] == 3
    g.resolve(bstep(g, "po"), [p(g, "Chen").pid, p(g, "Ema").pid, p(g, "Finn").pid])
    assert not any(p(g, n).alive for n in ("Chen", "Ema", "Finn"))


def test_pukka_poisons_then_kills_next_night():
    g = make_bmr(["pukka", "godfather", "chambermaid", "gambler", "tinker", "minstrel", "exorcist"])
    g.resolve(bstep(g, "pukka"), [p(g, "Chen").pid])
    assert g.impaired(p(g, "Chen"))
    night_n(g)
    assert g.impaired(p(g, "Chen")), "still poisoned the next day and night"
    g.resolve(bstep(g, "pukka"), [p(g, "Dev").pid])
    assert not p(g, "Chen").alive and g.impaired(p(g, "Dev"))


def test_shabaloth_kills_two():
    g = make_bmr(["shabaloth", "godfather", "chambermaid", "gambler", "tinker", "minstrel", "exorcist"])
    night_n(g)
    g.resolve(bstep(g, "shabaloth"), [p(g, "Chen").pid, p(g, "Dev").pid])
    assert not p(g, "Chen").alive and not p(g, "Dev").alive


def test_zombuul_seems_to_die_then_dies_when_executed_dead():
    g = make_bmr(["zombuul", "godfather", "chambermaid", "gambler", "tinker", "minstrel", "exorcist"])
    g.start_day()
    z = p(g, "Asha")
    g.nominate(p(g, "Ben").pid, z.pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day()
    assert not z.alive and g.zombuul_fake == z.pid and g.phase == "night"
    assert g.public_view()["seats"][0]["alive"] is False
    assert not g.step_applies(g.steps[bstep(g, "zombuul")]), "someone died today"
    g.start_day()
    g.end_day()
    assert g.step_applies(g.steps[bstep(g, "zombuul")]), "a dead-looking Zombuul still wakes"
    g.resolve(bstep(g, "zombuul"), [p(g, "Chen").pid])
    g.start_day()
    g.nominate(p(g, "Ben").pid, z.pid)
    g.record_votes(0, [x.pid for x in g.players if x.alive][:4])
    g.end_day()
    assert g.winner == "good"


def test_gambler_dies_on_wrong_guess():
    g = make_bmr(["po", "godfather", "gambler", "sailor", "chambermaid", "tinker", "minstrel"])
    night_n(g)
    g.resolve(bstep(g, "gambler"), [p(g, "Asha").pid], guess="pukka")
    assert not p(g, "Chen").alive
    night_n(g)  # dead: no step
    g2 = make_bmr(["po", "godfather", "gambler", "sailor", "chambermaid", "tinker", "minstrel"])
    night_n(g2)
    g2.resolve(bstep(g2, "gambler"), [p(g2, "Asha").pid], guess="po")
    assert p(g2, "Chen").alive


def test_professor_resurrects_townsfolk_at_dawn():
    g = make_bmr(["po", "godfather", "professor", "sailor", "chambermaid", "tinker", "minstrel"])
    night_n(g)
    g.resolve(bstep(g, "po"), [p(g, "Ema").pid])
    g.start_day(); g.end_day()
    g.resolve(bstep(g, "professor"), [p(g, "Ema").pid])
    assert p(g, "Ema").alive
    assert not g.public_view()["seats"][4]["alive"], "hidden from the table until dawn"
    g.start_day()
    assert any("Ema has been brought back" in a for a in g.announcements)
    g.end_day()
    assert not any(s["key"] == "professor" and g.step_applies(s) for s in g.steps), "once per game"


def test_courtier_drunk_three_nights():
    g = make_bmr(["po", "godfather", "courtier", "sailor", "chambermaid", "tinker", "minstrel"])
    g.resolve(bstep(g, "courtier"), [], guess="godfather")
    assert g.impaired(p(g, "Ben"))
    for _ in range(2):
        night_n(g)
        assert g.impaired(p(g, "Ben"))
    night_n(g)
    assert not g.impaired(p(g, "Ben"))
    assert not any(s["key"] == "courtier" and g.step_applies(s) for s in g.steps)


def test_godfather_kills_after_outsider_death():
    g = make_bmr(["po", "godfather", "tinker", "sailor", "chambermaid", "gambler", "minstrel"])
    night_n(g)
    assert not g.step_applies(g.steps[bstep(g, "godfather")])
    g.start_day()
    g.kill(p(g, "Chen").pid)  # the Tinker dies
    g.end_day()
    s = bstep(g, "godfather")
    assert g.step_applies(g.steps[s])
    g.resolve(s, [p(g, "Finn").pid])
    assert not p(g, "Finn").alive


def test_assassin_ignores_protection():
    g = make_bmr(["po", "assassin", "sailor", "chambermaid", "gambler", "tinker", "minstrel"])
    night_n(g)
    g.resolve(bstep(g, "assassin"), [p(g, "Chen").pid])
    assert not p(g, "Chen").alive, "the Sailor can't die, but the Assassin kills anyway"


def test_devils_advocate_saves_from_execution():
    g = make_bmr(["po", "devils_advocate", "sailor", "chambermaid", "gambler", "tinker", "minstrel"])
    g.resolve(bstep(g, "devils_advocate"), [p(g, "Dev").pid])
    g.start_day()
    g.nominate(p(g, "Ben").pid, p(g, "Dev").pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day()
    assert p(g, "Dev").alive
    with pytest.raises(GameError):
        g.resolve(bstep(g, "devils_advocate"), [p(g, "Dev").pid])


def test_minstrel_makes_everyone_drunk_after_minion_execution():
    g = make_bmr(["po", "godfather", "minstrel", "sailor", "chambermaid", "gambler", "tinker"])
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Ben").pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day()
    assert not p(g, "Ben").alive
    assert g.impaired(p(g, "Dev")) and not g.impaired(p(g, "Chen"))
    night_n(g)
    assert not g.impaired(p(g, "Dev")), "drunk until dusk tomorrow"


def test_mastermind_extra_day():
    g = make_bmr(["po", "mastermind", "minstrel", "sailor", "chambermaid", "gambler", "tinker"])
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day()
    assert not g.winner and g.phase == "night"
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Dev").pid)  # the Sailor is good, so good loses
    g.record_votes(0, [x.pid for x in g.players if x.alive][:5])
    g.end_day()
    assert g.winner == "evil"


def test_mastermind_extra_day_without_execution_evil_wins():
    g = make_bmr(["po", "mastermind", "minstrel", "sailor", "chambermaid", "gambler", "tinker"])
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Asha").pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day()
    g.start_day()
    g.end_day()
    assert g.winner == "evil"


def test_goon_drunks_first_chooser_and_takes_alignment():
    g = make_bmr(["po", "godfather", "goon", "sailor", "chambermaid", "gambler", "minstrel"])
    night_n(g)
    g.resolve(bstep(g, "po"), [p(g, "Chen").pid])
    assert p(g, "Chen").alive, "the Po was drunk by choosing the Goon"
    assert p(g, "Chen").evil


def test_grandmother_dies_with_grandchild():
    g = make_bmr(["po", "godfather", "grandmother", "chambermaid", "gambler", "tinker", "minstrel"])
    night_n(g)
    child = g.get(g.grandchild)
    g.resolve(bstep(g, "po"), [child.pid])
    assert not child.alive and not p(g, "Chen").alive


def test_moonchild_choice_kills_good_player_that_night():
    g = make_bmr(["po", "godfather", "moonchild", "sailor", "chambermaid", "gambler", "minstrel"])
    g.start_day()
    g.kill(p(g, "Chen").pid)
    g.moonchild_pick(p(g, "Ema").pid)
    g.end_day()
    i = bstep(g, "moonchild")
    assert g.steps[i]["answer"] == [p(g, "Ema").pid]
    g.resolve(i, [p(g, "Ema").pid])
    assert not p(g, "Ema").alive


def test_gossip_step_only_after_true_statement():
    g = make_bmr(["po", "godfather", "gossip", "sailor", "chambermaid", "gambler", "minstrel"])
    night_n(g)
    assert not g.step_applies(g.steps[bstep(g, "gossip")])
    g.start_day()
    g.set_gossip(True)
    g.end_day()
    i = bstep(g, "gossip")
    assert g.step_applies(g.steps[i]) and not p(g, "Chen").prompt or p(g, "Chen").prompt["kind"] != "choose"
    g.resolve(i, [p(g, "Ema").pid])
    assert not p(g, "Ema").alive


def test_pacifist_spares_good_player():
    g = make_bmr(["po", "godfather", "pacifist", "chambermaid", "gambler", "tinker", "minstrel"])
    g.start_day()
    g.nominate(p(g, "Chen").pid, p(g, "Dev").pid)
    g.record_votes(0, [x.pid for x in g.players][:5])
    g.end_day(spare=True)
    assert p(g, "Dev").alive


def test_chambermaid_counts_wakers():
    g = make_bmr(BMR9)
    i = bstep(g, "chambermaid")
    g.resolve(i, [p(g, "Ema").pid, p(g, "Gita").pid])  # Sailor wakes, Fool does not
    assert "1 of them woke" in g.steps[i]["suggestion"]


def test_phone_gambler_guess_and_optional_nobody():
    g = make_bmr(["po", "assassin", "gambler", "sailor", "chambermaid", "tinker", "minstrel"], phones=True)
    finish_phones(g)
    night_n(g)
    gam, ass = p(g, "Chen"), p(g, "Ben")
    with pytest.raises(GameError):
        g.choose(gam.token, [p(g, "Asha").pid])
    g.choose(gam.token, [p(g, "Asha").pid], "po")
    assert g.steps[bstep(g, "gambler")]["answer_guess"] == "po"
    g.choose(ass.token, [])
    assert g.steps[bstep(g, "assassin")]["answer"] == []


def test_tap_tasks_use_script_icons():
    g = make_bmr(BMR9, phones=True)
    tasks = [x.prompt for x in g.players if x.prompt and x.prompt["kind"] == "tap"]
    assert tasks and all(CHARACTERS[c]["script"] == BAD_MOON_RISING for t in tasks for c in t["options"])


def test_script_names():
    assert {m["name"] for m in SCRIPTS.values()} == {"Trouble Brewing", "Bad Moon Rising"}


def test_storyteller_skips_tap_challenges():
    g = make(NINE, phones=True)
    tappers = [x for x in g.players if x.prompt and x.prompt["kind"] == "tap"]
    g.skip_tap(tappers[0].pid)
    assert tappers[0].prompt["answer"] == tappers[0].prompt["target"]
    assert tappers[0] not in g.phones_waiting()
    with pytest.raises(GameError):
        g.skip_tap(tappers[0].pid)
    g.skip_tap()
    assert all(x.prompt["kind"] == "choose" for x in g.phones_waiting()), "real choices are not skipped"
    inputs = g.phone_inputs
    assert inputs == 0, "a skip is not a pick made on a phone"


def test_skip_tap_unblocks_dawn():
    g = make(NINE, phones=True)
    for x in g.phones_waiting():
        if x.prompt["kind"] == "choose":
            pool = [q.pid for q in g.players if x.prompt["allow_self"] or q.pid != x.pid]
            g.choose(x.token, pool[:x.prompt["count"]])
    with pytest.raises(GameError):
        g.start_day()
    g.skip_tap()
    g.start_day()
    assert g.phase == "day"
