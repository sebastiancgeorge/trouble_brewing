# Blood on the Clocktower on the local Wi-Fi

A digital grimoire for Blood on the Clocktower: Trouble Brewing and Bad Moon Rising. The Storyteller runs a small server on
their laptop; every player joins from their phone on the same Wi-Fi.

## Run

```
uv run server.py            # optional: --port 8000
```

The terminal prints a QR code and two URLs:

- **Players join** at `http://<laptop-ip>:8000/` (the QR code is also shown on the Storyteller screen).
- **Storyteller** opens `http://localhost:8000/st?key=...` on the laptop. Keep that key private: it shows
  every character.

If phones cannot connect, allow incoming connections for Python in the laptop's firewall.

## Flow

1. **Lobby**: pick the script (Trouble Brewing or Bad Moon Rising) and whether to play Dead Eyes Only;
   both can still be changed during setup (changing the script deals again). Players scan and enter their name. Drag each token onto the right seat until the circle
   matches the real table clockwise. Players without a phone can be seated by the Storyteller.
2. **Deal**: a random rules-valid setup for 5-15 players, with the Drunk's fake character, the Fortune
   Teller's red herring and three Demon bluffs. Tap any token to change it, then start.
3. **Night** (eyes open): every phone buzzes at once. Players with a night choice get it on their phone
   automatically; everyone else gets a tap challenge (tap three character icons in the order shown), so
   every player taps and real choices do not stand out. The ledger shows which phones are still going;
   the second buzz and dawn are refused until every living player with a phone has finished (players
   seated without a phone are not waited for). If someone's phone is stuck, tap **skip** next to their
   name (or skip every unfinished challenge at once); their phone shows the normal "Done" slip. Work down the ledger in
   order: *Apply their pick* / *Work out their info* (the truthful answer is filled in), edit if they
   are drunk or poisoned, then *Hold until dawn*. Applying the Imp's kill buzzes every phone a second
   time; a Ravenkeeper killed tonight picks then. When the Ravenkeeper (or a Drunk who believes they
   are one) was killed tonight, everyone else gets a second tap challenge while they pick; otherwise
   each player taps once a night. Kills, Monk, Soldier, Mayor, star-pass and Scarlet
   Woman are handled automatically.
   At dawn every phone buzzes and every player gets a slip: their info, or "Nothing to report tonight".
4. **Day**: record nominations and tap who voted. Virgin, Slayer, Saint, ghost votes, ties and the
   Mayor are resolved; *End the day* executes and starts the next night.
5. Win conditions are checked after every death.

### Bad Moon Rising

Handled automatically: every Demon (Zombuul's false death, Pukka's delayed kill, Shabaloth's two kills,
Po's charge), the Exorcist stopping the Demon, Innkeeper / Sailor / Tea Lady / Fool / Devil's Advocate
saves, the Assassin, Godfather kills after an Outsider dies, Gambler, Courtier and Minstrel drunkenness,
the Professor (resurrection announced at dawn), the Goon's alignment, the Grandmother, the Mastermind's
extra day, and the Lunatic (their picks do nothing and the real Demon is told them). The Storyteller
decides: whether the Gossip's statement was true (then picks who dies), the Moonchild's public choice,
whether the Pacifist spares an executed good player, Shabaloth regurgitation and Tinker deaths
(tap a token to bring back or kill). Dead players can be nominated, so a Zombuul who seemed to die can be
executed. Players see all characters when the game ends.

Tap any token during play to kill, revive, poison, send a private message or change a character.

**Undo** (top of the Storyteller screen, or Ctrl/Cmd+Z) reverses the last Storyteller action, up to 30 back. It
warns when phones already showed the result or when picks made on phones since would be cleared.

## Files

- `roles.py` character data, setup table and night order
- `dealing.py` random setup
- `info.py` truthful information for each night step
- `game.py` game state and rules
- `server.py` FastAPI server
- `static/` phone page, Storyteller page, theme and bundled fonts
- `test_game.py` rule tests: `uv run --with pytest pytest -q`
- `trouble-brewing-almanac.pdf` player almanac for the script, by Rithwik aka BlazeReceptor
- `bad-moon-rising-script.pdf` Bad Moon Rising character sheet, by Rithwik (its icons are in `static/icons/*.png`)
- `static/fonts/OFL-*.txt` licences for the bundled Grenze Gotisch and Alegreya Sans fonts

Game state is in memory: restarting the server ends the game.
