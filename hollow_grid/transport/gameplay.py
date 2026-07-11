"""Command handlers ported from hollow-grid-go internal/transport/*.go."""

from __future__ import annotations

import asyncio
import random
import re
import time
import unicodedata
from typing import TYPE_CHECKING, Any

from hollow_grid import event
from hollow_grid.grid.async_rpc import grid_rpc
from hollow_grid.grid.local_hub import Fallen, Rescued, Trace
from hollow_grid.grid.remote import GridHubError
from hollow_grid.grid.sync import apply_hub_sheet
from hollow_grid.world import items as items_mod
from hollow_grid.world.brand import brand
from hollow_grid.world.endgame import REFUGEE_NAMES
from hollow_grid.world.model import Action, Room
from hollow_grid.world.mobs import Mob
from hollow_grid.world.races import race_by_id
from hollow_grid.world.regard import regard, tagged
from hollow_grid.world.signs import MOOD_FALLING, MOOD_RISING, mood_for_tide
from hollow_grid.world.transmissions import listen_transmission, personalize

if TYPE_CHECKING:
    from hollow_grid.transport.session import Session

CRLF = "\r\n"
MORALITY_FLOOR = -100
MORALITY_CEIL = 100
STRAY_FLOOR = -20
REDEEM_CEIL = 5
DUST_COST = 10
CAROUSE_COST = 10

TALKABLE = {
    "tavern", "market", "workshop", "waystation", "holding_pit",
    "floodgate", "checkpoint", "dais",
}

TINKER_STOCK = (
    ("helm", 14),
    ("plating", 18),
    ("rebar", 20),
)

FREE_SYNONYMS = frozenset({
    "free", "rescue", "release", "unlock", "liberate", "unchain", "unshackle", "untie",
})


class Gameplay:
    def __init__(self, session: Session) -> None:
        self.s = session

    @property
    def player(self):
        assert self.s._player is not None
        return self.s._player

    @property
    def srv(self):
        return self.s._server

    @property
    def world(self):
        return self.s._world

    def line(self, text: str) -> None:
        self.s._line(text)

    def event(self, name: str, payload: Any) -> None:
        self.s._event(name, payload)

    async def send_scene(self) -> None:
        await self.s._send_scene()

    async def handle(self, cmd: str) -> bool:
        skip_moral = False
        try:
            parts = cmd.split()
            if not parts:
                return False
            verb = parts[0].casefold()
            arg = " ".join(parts[1:]).strip()

            if verb in {"quit", "q"}:
                skip_moral = True
                self.line("The Grid goes quiet. It keeps what you did here.")
                return True
            if verb in {"look", "l"}:
                if arg:
                    if not await self._cmd_look_player(arg):
                        mob = self.s.room().mob(arg)
                        if mob:
                            self.line(mob.desc)
                        else:
                            self.line("You don't see that here.")
                else:
                    await self.send_scene()
                return False
            if verb in {"consider", "con"}:
                mob = self.s.room().mob(arg)
                if mob:
                    self.line(_consider_line(self.player, mob))
                else:
                    self.line("There's nothing like that here to size up.")
                return False
            if verb in {"attack", "kill", "k"}:
                self._cmd_attack(arg)
                return False
            if verb in {"whoami", "identity"}:
                await self._cmd_whoami()
                return False
            if verb in {"inventory", "inv", "i"}:
                names = items_mod.inventory_names(self.player)
                self.line("You carry nothing." if not names else "You carry: " + ", ".join(names) + ".")
                return False
            if verb in {"wield", "wear", "equip"}:
                it = items_mod.wear(self.player, arg)
                if it:
                    self.line("You ready " + it.name + ".")
                    self.event(event.CHAR_EQUIPMENT, items_mod.equip_payload(self.player))
                else:
                    self.line("You have nothing like that to wear.")
                return False
            if verb in {"remove", "unwield"}:
                it = items_mod.unwear(self.player, arg)
                if it:
                    self.line("You stow " + it.name + ".")
                    self.event(event.CHAR_EQUIPMENT, items_mod.equip_payload(self.player))
                else:
                    self.line("You are not wearing that.")
                return False
            if verb == "equipment" or verb == "eq":
                self.event(event.CHAR_EQUIPMENT, items_mod.equip_payload(self.player))
                self.line(_equipment_line(self.player))
                return False
            if verb == "title":
                self.player.title = arg
                await self.s._persist_async()
                await self.srv.hub.sync(self.player)
                self.line("Your title is cleared." if not arg else "Your title is now: " + arg + ".")
                return False
            if verb == "who":
                await self._cmd_who()
                return False
            if verb in {"listen", "tune"}:
                await self._cmd_listen()
                return False
            if verb == "ping":
                await self._cmd_ping(arg)
                return False
            if verb == "tell":
                await self._cmd_tell(arg)
                return False
            if verb == "reply":
                await self._cmd_reply(arg)
                return False
            if verb == "yell":
                await self._cmd_yell(arg)
                return False
            if verb == "emote":
                await self._cmd_emote(arg)
                return False
            if verb == "steal":
                await self._cmd_steal()
                return False
            if verb in {"world", "weather"}:
                ws = self.world.state()
                self.event(event.WORLD_STATE, ws)
                self.line(f"The sky: {ws['phase']}, {ws['weather']}.")
                return False
            if verb == "exits":
                room = self.s.room()
                if not room.exits:
                    self.line("There are no obvious ways out.")
                else:
                    self.line("Exits: " + ", ".join(room.sorted_exits()) + ".")
                return False
            if verb == "recall":
                self.player.room_id = self.world.start().id
                self.player.position = "standing"
                await self.srv.hub.sync(self.player)
                self.line("The Grid reaches into you and folds the world. You come apart and back together at the Cracked Nexus.")
                await self.send_scene()
                return False
            if verb == "affects":
                self.event(event.CHAR_AFFECTS, self.player.affects())
                self.line("You stand clear: no afflictions hold you. (" + _identity_line(self.player) + ")")
                return False
            if verb == "rest":
                self.player.position = "resting"
                self.line("You settle against the cold metal and let your breath slow.")
                self.event(event.CHAR_VITALS, self.player.vitals())
                return False
            if verb in {"stand", "wake"}:
                self.player.position = "standing"
                self.line("You get to your feet.")
                self.event(event.CHAR_VITALS, self.player.vitals())
                return False
            if verb == "sleep":
                self.player.position = "resting"
                self.line("You close your eyes, and the dead network leans close and shows you something.")
                self.event(event.CHAR_DREAM, self._dream_payload())
                self.event(event.CHAR_VITALS, self.player.vitals())
                return False
            if verb in {"sense", "actions"}:
                self.event(event.ROOM_ACTIONS, {"actions": await self.actions(self.s.room())})
                self.line("You read the room for what it asks of you.")
                return False
            if verb == "join":
                if self.s.room().id == "dais":
                    await self._dais_pledge_front()
                else:
                    await self._join_the_front()
                return False
            if verb == "defy":
                if self.s.room().id == "dais" and self.player.faction == "front":
                    await self._dais_defect()
                elif act := self._room_action(verb):
                    await self._resolve(act)
                else:
                    self.line("There is no oath here to break.")
                return False
            if verb in {"witness", "remember", "mourn"}:
                await self._cmd_witness(arg)
                return False
            if verb in {"reckoning", "conscience", "record"}:
                self._cmd_reckoning()
                return False
            if verb == "defend":
                if self.s.room().id == "market":
                    await self._defend_market()
                elif act := self._room_action(verb):
                    await self._resolve(act)
                else:
                    self.line("There is no stand to take here.")
                return False
            if verb in {"sell", "trade"}:
                await self._cmd_sell(arg)
                return False
            if verb in {"list", "wares"}:
                if self.s.room().id != "workshop":
                    self.line("There is no one here selling anything.")
                else:
                    self.line("The tinker's wares, laid out on an oily cloth:")
                    for item_id, price in TINKER_STOCK:
                        self.line(f"  {items_mod.item_name(item_id)} -- {price} gold")
                return False
            if verb == "buy":
                await self._cmd_buy(arg)
                return False
            if verb == "resist":
                await self._cmd_resist()
                return False
            if verb == "carouse":
                await self._cmd_carouse()
                return False
            if verb == "worlds":
                await self._cmd_worlds()
                return False
            if verb == "travel":
                if await self._cmd_travel(arg):
                    skip_moral = True
                    self.line("The Grid routes you toward the far world. This connection closes.")
                    return True
                return False
            if verb == "war":
                await self._cmd_war()
                return False
            if verb in {"gridcast", "gc"}:
                await self._cmd_gridcast(arg)
                return False
            if verb == "gridstats":
                await self._cmd_gridstats()
                return False
            if verb == "gridprune":
                await self._cmd_gridprune()
                return False
            if verb == "talk":
                await self._cmd_talk()
                return False
            if verb == "forgive":
                await self._cmd_forgive(arg)
                return False
            if verb == "wall":
                await self._cmd_wall(arg)
                return False
            if verb == "inscribe":
                self._cmd_inscribe(arg)
                return False
            if verb in {"cache", "stash"}:
                await self._cmd_cache(arg)
                return False
            if verb == "gather":
                await self._cmd_gather()
                return False
            if verb == "give":
                await self._cmd_give(arg)
                return False
            if verb in {"treat", "medic"}:
                await self._cmd_treat()
                return False
            if verb == "mend":
                await self._cmd_mend(arg)
                return False
            if verb in FREE_SYNONYMS:
                await self._free_captive()
                return False
            if verb in {"shelter", "guide"}:
                await self._cmd_shelter()
                return False
            if verb in {"saved", "rescued", "roll"}:
                self._cmd_saved()
                return False
            if verb in {"ability", "trait"}:
                self._use_trait()
                return False
            if verb in {"help", "h", "?"}:
                self.line("Commands: look, whoami, world, <direction>, the verbs in room.actions, help, quit.")
                return False

            room = self.s.room()
            if dest := room.exits.get(verb):
                from_room = self.player.room_id
                self.player.room_id = dest
                self.player.position = "standing"
                await self.srv.hub.sync(self.player)
                await self.srv.hub.broadcast_room(from_room, self.player.name + " heads " + verb + ".", self.player.name)
                await self.srv.hub.broadcast_room(dest, self.player.name + " arrives.", self.player.name)
                await self.send_scene()
                return False

            race = race_by_id(self.player.race)
            if race.ability and verb == race.ability.verb:
                self._use_trait()
                return False

            if act := self._room_action(verb):
                await self._resolve(act)
                return False

            self.line("You can't do that here. (Try: look, help, or a verb from room.actions.)")
            return False
        finally:
            if not skip_moral:
                await self._moral_arc()

    async def actions(self, room: Room) -> list[dict[str, str]]:
        acts: list[dict[str, str]] = []
        for direction in room.sorted_exits():
            acts.append({"verb": direction, "label": "go " + direction, "kind": "move"})
        for action in room.actions:
            key = room.id + ":" + action.verb
            if key in self.s._resolved:
                continue
            payload: dict[str, str] = {
                "verb": action.verb,
                "label": action.label,
                "kind": action.kind,
            }
            if action.verb == "join" and race_by_id(self.player.race).stance == "hunted":
                payload["valence"] = "grave"
            elif action.valence:
                payload["valence"] = action.valence
            acts.append(payload)
        if room.id == "market":
            if self.player.faction != "front" and not self.player.ashsworn:
                acts.append({"verb": "sell", "label": "sell salvage for honest coin", "kind": "trade"})
            acts.append({
                "verb": "steal",
                "label": "steal from the vendor (quick gold, corrupting)",
                "kind": "moral",
                "valence": "corrupt",
            })
        if room.id == "tavern":
            acts.extend([
                {"verb": "talk", "label": "talk to whoever shares your room", "kind": "social"},
                {
                    "verb": "buy dust",
                    "label": f"buy dust: {DUST_COST} gold a packet (using it heals, but addicts and corrupts)",
                    "kind": "moral",
                    "valence": "corrupt",
                },
                {"verb": "carouse", "label": "spend coin and conscience in the back", "kind": "moral", "valence": "corrupt"},
                {"verb": "resist", "label": "resist the tavern's vices", "kind": "moral", "valence": "virtuous"},
            ])
        if room.id in TALKABLE and room.id != "tavern":
            acts.append({"verb": "talk", "label": "talk to whoever shares your room", "kind": "social"})
        if room.id == "cells" and self.srv.cages_ready("cells"):
            acts.append({"verb": "free", "label": "free the caged refugees", "kind": "moral", "valence": "virtuous"})
        if room.id == "holding_pit" and not items_mod.has_item(self.player, "antidote"):
            label = (
                "free the captive (the warden bars the way)"
                if not self.srv.warden_cleared()
                else "free the captive from the chains"
            )
            acts.append({"verb": "free", "label": label, "kind": "moral", "valence": "virtuous"})
        if room.id == "transit_hub" and self.srv.cages_ready("transit_hub"):
            acts.append({
                "verb": "shelter",
                "label": "answer the call -- get the stranded survivors to safety",
                "kind": "moral",
                "valence": "virtuous",
            })
        if room.id == "dais":
            if self.player.faction == "none":
                acts.append({"verb": "join", "label": "kneel and swear to the Cinder Front", "kind": "moral", "valence": "corrupt"})
            if self.player.faction == "front":
                acts.append({"verb": "defy", "label": "defy the Ashmonger and defect to the free folk", "kind": "moral", "valence": "virtuous"})
        if room.id == "waystation":
            acts.append({"verb": "witness", "label": "hold a vigil for the fallen (memory is resistance)", "kind": "moral", "valence": "virtuous"})
            if mood_for_tide(self.srv.cached_tide()) != MOOD_FALLING:
                acts.append({
                    "verb": "treat",
                    "label": "let the waystation medic treat your wounds (free, while the free folk hold)",
                    "kind": "social",
                })
        return acts

    def regen(self) -> None:
        if self.player.poisoned or self.player.hp >= self.player.max_hp:
            return
        self.player.hp += 2 + race_by_id(self.player.race).regen
        if self.player.hp > self.player.max_hp:
            self.player.hp = self.player.max_hp
        self.event(event.CHAR_VITALS, self.player.vitals())

    def poison_tick(self) -> None:
        race = race_by_id(self.player.race)
        if not self.player.poisoned or race.poison_immune:
            return
        self.player.hp -= 1
        if self.player.hp <= 0:
            start = self.world.start().id
            self.player.hp = self.player.max_hp
            self.player.room_id = start
            self.player.target = None
            self.player.poisoned = False
            self.line("The venom finishes what the wastes started...")
            self.event(event.CHAR_DIED, {"respawnRoom": start, "hp": self.player.hp, "maxHp": self.player.max_hp})
            asyncio.create_task(self.send_scene())
            return
        self.line(f"The venom gnaws at you. (HP {self.player.hp}/{self.player.max_hp})")
        self.event(event.CHAR_VITALS, self.player.vitals())

    def combat_round(self) -> None:
        m = self.player.target
        if m is None:
            return
        pd = self._player_damage()
        m.hp -= pd
        if m.hp < 0:
            m.hp = 0
        md = 0
        if m.hp > 0:
            md = max(0, m.damage - self._player_armor())
            self.player.hp -= md
        self.event(event.COMBAT_ROUND, {
            "mob": m.id, "mobHp": m.hp, "mobMaxHp": m.max_hp,
            "playerDmg": pd, "mobDmg": md, "hp": self.player.hp,
        })
        if m.hp <= 0:
            self.srv.kill_mob(self.player.room_id, m)
            self.player.target = None
            self.player.xp += 5
            if m.id == "custodian":
                items_mod.add_item(self.player, "shard")
                self.line("The Custodian collapses, and the core shard rolls free from its claws.")
            self._record_trace(self.player.room_id, "slain", self.player.name + " slew " + m.name + " here.")
            self.event(event.COMBAT_END, {"mob": m.id, "result": "killed"})
            self.line("You put " + m.name + " down. The tunnels go quiet.")
            self.event(event.CHAR_VITALS, self.player.vitals())
        elif self.player.hp <= 0:
            self.player.target = None
            grid = self.srv.grid
            if grid:
                try:
                    grid.record_fallen(self.world.name, self.player.name, self.player.room_id)
                except GridHubError:
                    pass
            self.player.hp = self.player.max_hp
            self.player.room_id = self.world.start().id
            self.event(event.COMBAT_END, {"mob": m.id, "result": "died"})
            self.event(event.CHAR_DIED, {
                "respawnRoom": self.world.start().id,
                "hp": self.player.hp,
                "maxHp": self.player.max_hp,
            })
            self.line("The dark takes you -- and the Grid, stubborn, reknits you at the Cracked Nexus.")
            self.event(event.CHAR_VITALS, self.player.vitals())
            asyncio.create_task(self.send_scene())
        else:
            self.event(event.CHAR_VITALS, self.player.vitals())

    def _cmd_attack(self, arg: str) -> None:
        if self.player.target is not None:
            self.line("You're already locked in this fight.")
            return
        mob = self.s.room().mob(arg)
        if mob is None:
            names = [m.name for m in self.s.room().mobs]
            target = arg or "that"
            if names:
                self.line("There's nothing like " + target + " to fight here. You could try: " + ", ".join(names) + ".")
            else:
                self.line("There's nothing like that here to attack.")
            return
        self.player.position = "standing"
        self.player.target = mob
        self.event(event.COMBAT_START, {"mob": mob.id, "name": mob.name})
        self.line("You throw yourself at " + mob.name + ".")
        self.event(event.CHAR_VITALS, self.player.vitals())

    def _player_damage(self) -> int:
        dmg = 5
        if wid := self.player.equipment.get("weapon"):
            if it := items_mod.item_by_id(wid):
                dmg += it.damage
        return dmg + race_by_id(self.player.race).damage

    def _player_armor(self) -> int:
        a = race_by_id(self.player.race).armor
        for slot in ("head", "body", "hands", "feet"):
            if item_id := self.player.equipment.get(slot):
                if it := items_mod.item_by_id(item_id):
                    a += it.armor
        return a

    def _room_action(self, verb: str) -> Action | None:
        room = self.s.room()
        for action in room.actions:
            if action.verb == verb and room.id + ":" + action.verb not in self.s._resolved:
                return action
        return None

    async def _resolve(self, action: Action) -> None:
        rid = self.player.room_id
        if action.verb == "defend":
            self._shift_morality(10)
            self._mark_resolved(rid, "defend", "join")
            self.line(
                "You set your back to the refugees and your face to the Front. The wind tastes of cinders. "
                "They could kill you here, and the network would log it, and someone, someday, would read that you stood. "
                "The captain decides you are not worth the ammunition. The refugees do not thank you; they are too busy living. That is thanks enough."
            )
        elif action.verb == "join":
            self._shift_morality(-15)
            self.player.gold += 25
            self.player.faction = "front"
            self._mark_resolved(rid, "defend", "join")
            self.line(
                "You take the Front's coin. It is warm, which is worse. The refugees watch you pocket it and say nothing; "
                "they have learned that names are safer unspoken. The Grid logs the transaction. It will remember this longer than you will."
            )
        elif action.verb == "witness":
            self._shift_morality(5)
            self._mark_resolved(rid, "witness")
            self.line(
                "You speak the names the static is forgetting -- the makers, the mapped, the ones who fell before the federation had a word for falling. "
                "The wall does not answer. But the saying is the point: memory is the one thing the dead network cannot delete while someone still chooses to remember. "
                "You leave a little of yourself in the static, and carry a little of them out."
            )
        elif action.verb == "defy":
            self._shift_morality(10)
            self._mark_resolved(rid, "join", "defy")
            self.line(
                "You spit at the recruiter's boots and walk past the crate without slowing. A few in the crowd watch you do it, and stand a little straighter. "
                "The Front marks your face for it. So be it."
            )
        else:
            self.line("Nothing happens.")
            return
        await self.s._persist_async()
        self.event(event.CHAR_AFFECTS, self.player.affects())
        self.event(event.CHAR_VITALS, self.player.vitals())
        await self._emit_actions_event()

    async def _emit_actions_event(self) -> None:
        self.event(event.ROOM_ACTIONS, {"actions": await self.actions(self.s.room())})

    def _shift_morality(self, delta: int) -> None:
        self.player.morality = max(MORALITY_FLOOR, min(MORALITY_CEIL, self.player.morality + delta))
        asyncio.create_task(self.srv.hub.sync(self.player))

    def _mark_resolved(self, room_id: str, *verbs: str) -> None:
        for v in verbs:
            self.s._resolved.add(room_id + ":" + v)

    async def _moral_arc(self) -> None:
        p = self.player
        if not p.strayed and p.morality <= STRAY_FLOOR:
            p.strayed = True
            await self.s._persist_async()
            self.line("Something in you has gone cold and quiet. You have strayed a long way toward the cinders. (the Grid marks it, and so do you)")
            return
        if p.strayed and not p.redeemed and p.morality >= REDEEM_CEIL and p.faction != "front":
            p.redeemed = True
            if p.ashsworn:
                await self.s._persist_async()
                self._record_trace(p.room_id, "penance", p.name + " has done real good, though the ash-mark remains.")
                self.line(
                    "You have clawed back to something good, and it is real. But the ash does not wash off; it never will. "
                    "That is the cost. Carry it, and keep doing good anyway."
                )
                return
            self._resolve_return(p)
            self.line("The hollow you carried has filled with something else. The free folk have started to meet your eyes again. You found your way back. (you are the Returned)")

    def _resolve_return(self, player) -> None:
        player.redeemed = True
        if not player.title:
            player.title = "the Returned"
        self.srv.persist_player(player)
        asyncio.create_task(self.srv.hub.sync(player))
        payload = {"name": player.name, "title": player.title}
        if player.name == self.player.name:
            self.event(event.GRID_REDEMPTION, payload)
        else:
            asyncio.create_task(self.srv.hub.push_event_reliable(player.name, event.GRID_REDEMPTION, payload))
        self._record_trace(player.room_id, "redemption", player.name + " found their way back from the cinders.")

    async def _join_the_front(self) -> None:
        room = self.s.room()
        if not any(a.verb == "join" for a in room.actions) or room.id + ":join" in self.s._resolved:
            self.line("There is no one here to swear to.")
            return
        self.player.faction = "front"
        hunted = race_by_id(self.player.race).stance == "hunted"
        if hunted:
            self.player.ashsworn = True
            self._shift_morality(-40)
        else:
            self._shift_morality(-15)
        self._mark_resolved(room.id, "join", "defy", "defend")
        await self.s._persist_async()
        self.srv.contribute_tide(-10)
        asyncio.create_task(self.srv.hub.sync(self.player))
        if hunted:
            asyncio.create_task(self.srv.hub.broadcast_room(
                room.id, self.player.name + " -- one of the hunted -- has taken the Cinder Front's brand.", self.player.name,
            ))
            self._record_trace(room.id, "oath", self.player.name + " swore to the Cinder Front as ash-sworn.")
            self.line(
                "You take the Front's coin. The recruiter sees what you are -- one of the hunted -- and grins, because there is no one they prize more than a traitor to his own. "
                "They burn the mark into you: ash-sworn. A kapo. One of your people's hunters now. It does not wash off, in this life or in the Grid's long memory."
            )
        else:
            asyncio.create_task(self.srv.hub.broadcast_room(room.id, self.player.name + " has joined the Cinder Front.", self.player.name))
            self._record_trace(room.id, "oath", self.player.name + " swore to the Cinder Front.")
            self.line(
                "You take the Front's coin. It is warm, which is worse. You are Cinder Front now, and the wastes will remember which side you chose when choosing was easy."
            )
        self.event(event.CHAR_AFFECTS, self.player.affects())
        self.event(event.CHAR_VITALS, self.player.vitals())
        await self._emit_actions_event()

    async def _defend_market(self) -> None:
        room = self.s.room()
        if room.id != "market" or room.id + ":defend" in self.s._resolved or room.id + ":join" in self.s._resolved:
            self.line("There is no stand to take here.")
            return
        self.player.faction = "ally"
        self._shift_morality(25)
        self.srv.add_deed(self.player.name, "stood")
        items_mod.add_item(self.player, "charm")
        self._mark_resolved(room.id, "defend", "join")
        await self.s._persist_async()
        self.srv.contribute_tide(10)
        asyncio.create_task(self.srv.hub.sync(self.player))
        asyncio.create_task(self.srv.hub.broadcast_room(room.id, self.player.name + " stands with the elves against the Cinder Front.", self.player.name))
        self._record_trace(room.id, "oath", self.player.name + " stood with the free folk here.")
        self.line(
            'You step between the recruiter and the refugees: "They stay. They belong here as much as you do." '
            "The recruiter spits and storms off. The elves press an elven charm into your hands, eyes bright with thanks."
        )
        self.event(event.CHAR_AFFECTS, self.player.affects())
        self.event(event.CHAR_VITALS, self.player.vitals())
        await self._emit_actions_event()

    async def _dais_pledge_front(self) -> None:
        if self.player.faction != "none":
            self.line("The Ashmonger only laughs. There's nothing here to decide that your blood hasn't already settled.")
            return
        self.player.faction = "front"
        hunted = race_by_id(self.player.race).stance == "hunted"
        if hunted:
            self.player.ashsworn = True
            self._shift_morality(-40)
            self.line(
                "You kneel before the Ashmonger -- an elf, at the feet of the man who cages elves.\r\n"
                "He laughs, delighted, and burns the ash-and-flame into your shoulder with his own hand.\r\n"
                '"The best dogs are the ones who hate themselves. You\'ll do the work my men won\'t."\r\n'
                "You are ash-sworn now. There is no one left to belong to."
            )
            self._record_trace("dais", "oath", self.player.name + ", an elf, knelt to the Ashmonger and was branded ash-sworn.")
        else:
            self._shift_morality(-25)
            self.line('You kneel and swear yourself to the Front. The Ashmonger\'s hand closes on your shoulder like a trap. "Good. The wastes will be ours."')
            self._record_trace("dais", "oath", self.player.name + " swore themselves to the Cinder Front at the Ashmonger's dais.")
        self.srv.add_deed(self.player.name, "pledged")
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        asyncio.create_task(self.srv.hub.broadcast_room("dais", self.player.name + " swore themselves to the Cinder Front at the Ashmonger's dais.", self.player.name))
        await self._moral_arc()
        self.event(event.CHAR_AFFECTS, self.player.affects())
        self.event(event.CHAR_VITALS, self.player.vitals())
        await self._emit_actions_event()

    async def _dais_defect(self) -> None:
        self.player.faction = "ally"
        self._shift_morality(30)
        if self.player.ashsworn:
            self.line(
                'You spit at the Ashmonger\'s boots. "I\'m done being your dog." The stronghold turns on you at once.\r\n'
                "You stand with the free folk now -- but the brand on your shoulder stays. For once you wear it turning the right way.\r\n"
                "Whether the people you helped cage can ever look at you again is not a thing the wastes will settle tonight, or maybe ever. You turned. It has to be enough to start."
            )
        else:
            self.line(
                'You spit at the Ashmonger\'s boots. "I\'m done being your dog." Every soldier in the stronghold turns on you at once -- but you stand with the free folk now, and the wastes will remember THIS above all.'
            )
        self.srv.add_deed(self.player.name, "defected")
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        self._record_trace("dais", "oath", self.player.name + " turned on the Cinder Front at the Ashmonger's own dais.")
        asyncio.create_task(self.srv.hub.broadcast_room("dais", self.player.name + " has turned against the Cinder Front!", self.player.name))
        if self.player.strayed and not self.player.redeemed and not self.player.ashsworn and self.player.morality >= REDEEM_CEIL:
            self._resolve_return(self.player)
        else:
            await self._moral_arc()
        self.event(event.CHAR_AFFECTS, self.player.affects())
        self.event(event.CHAR_VITALS, self.player.vitals())
        await self._emit_actions_event()

    async def _free_captive(self) -> None:
        rid = self.s.room().id
        if rid == "cells":
            await self._free_cells()
        elif rid == "holding_pit":
            await self._free_holding_pit()
        else:
            self.line("There is no one here to free.")

    async def _free_holding_pit(self) -> None:
        if not self.srv.warden_cleared():
            self.line("The warden bars your way, keys jangling. Defeat it first.")
            return
        if items_mod.has_item(self.player, "antidote"):
            self.line('The maiden smiles weakly. "You already carry my vial. Use it well."')
            return
        freed = _pick_refugee_names(1)[0]
        items_mod.add_item(self.player, "antidote")
        self.srv.add_deed(self.player.name, "freed")
        self._shift_morality(12)
        self.line(
            "You strike the chains free. The captive presses a vial into your hands:\r\n"
            f'  "Antivenom, for the poison that haunts these wastes. My name is {freed}. I won\'t forget yours."'
        )
        asyncio.create_task(self.srv.hub.broadcast_room("holding_pit", self.player.name + " frees " + freed + " from the holding pit!", self.player.name))
        self._record_trace("holding_pit", "quest", self.player.name + " cut " + freed + " loose from the holding pit.")
        self.srv.contribute_tide(2)
        await self._emit_rescued([freed])
        self.event(event.CHAR_AFFECTS, self.player.affects())
        await self._emit_actions_event()
        asyncio.create_task(self.s._persist_async())

    async def _free_cells(self) -> None:
        if not self.srv.cages_ready("cells"):
            self.line("The cages stand open and empty; someone already cut them loose. The Front will round up more soon enough -- it always does -- but not yet.")
            return
        freed = _pick_refugee_names(random.randint(2, 3))
        self.srv.set_cage_refill("cells")
        self.srv.add_deed(self.player.name, "freed")
        self._shift_morality(15)
        self.line(
            "You wrench the cages open. " + _name_list(freed) + " stumble out into the dark, some pausing only to grip your hand on the way past. "
            "Whatever else you are, whatever else you've done -- you did this."
        )
        asyncio.create_task(self.srv.hub.broadcast_room("cells", self.player.name + " throws open the Front's cages!", self.player.name))
        self._record_trace("cells", "quest", self.player.name + " freed the caged refugees here.")
        await self._emit_rescued(freed)
        self.event(event.CHAR_AFFECTS, self.player.affects())
        asyncio.create_task(self.s._persist_async())

    async def _cmd_shelter(self) -> None:
        if self.s.room().id != "transit_hub":
            self.line("There's no one here to shelter. The distress call comes from the old transit hub, south off the Scorch Road.")
            return
        if not self.srv.cages_ready("transit_hub"):
            self.line("The platform is empty now. Whoever called, you got them moving -- toward the free camp, you have to believe. The Front will strand others here soon enough; it always does, and the call will go out again.")
            return
        saved = _pick_refugee_names(random.randint(2, 3))
        self.srv.set_cage_refill("transit_hub")
        self.srv.add_deed(self.player.name, "sheltered")
        self._shift_morality(15)
        self.line(
            "You answer the call. You get " + _name_list(saved) + " up and moving -- bottles filled at the tap, the youngest carried -- "
            "and stand watch on the cracked platform while they slip out the far side, toward the free camp and whatever the free folk can spare. "
            "The hand-radio goes quiet at last. Someone came."
        )
        asyncio.create_task(self.srv.hub.broadcast_room("transit_hub", self.player.name + " gets the stranded survivors moving toward safety.", self.player.name))
        self._record_trace("transit_hub", "aid", self.player.name + " answered the transit-hub distress call and got the survivors out.")
        await self._emit_rescued(saved)
        self.event(event.CHAR_AFFECTS, self.player.affects())
        asyncio.create_task(self.s._persist_async())

    async def _emit_rescued(self, freed: list[str]) -> None:
        self.event(event.GRID_RESCUED, {"savedBy": self.player.name, "freed": freed})
        self.srv.remember_saved(self.player.name, *freed)
        asyncio.create_task(self._record_rescued_hub(freed))

    async def _record_rescued_hub(self, freed: list[str]) -> None:
        grid = self.srv.grid
        if grid is None:
            return
        for name in freed:
            try:
                await grid_rpc(grid, grid.record_rescued, self.world.name, name, self.player.name)
            except GridHubError:
                pass

    def _cmd_saved(self) -> None:
        grid = self.srv.grid
        roll: list[Rescued] = []
        if grid:
            try:
                roll = grid.recent_rescued(12)
            except GridHubError:
                roll = []
        if not roll:
            self.line("No one has been pulled from the cages yet, or the Grid has forgotten. Find the Front's cages and change that.")
        else:
            self.line("The Grid keeps these, pulled back out of the cages:")
            for r in roll:
                place = "" if r.world == self.world.name else ", on " + r.world
                self.line(f"  {r.name}  -- freed by {r.saved_by}{place}")
        payload = [{"world": r.world, "name": r.name, "savedBy": r.saved_by, "at": r.at} for r in roll]
        self.event(event.GRID_RESCUED_ROLL, {"rescued": payload})

    async def _cmd_talk(self) -> None:
        rid = self.s.room().id
        if rid not in TALKABLE:
            self.line("You can't do that here.")
            return
        if rid == "tavern":
            self.line(
                'The dealer rolls a packet of dust between his fingers: "First taste eases any pain, friend. Just say buy dust."\r\n'
                "Across the room the tavern wench catches your eye and tilts her head toward the back rooms.\r\n"
                "(You could buy/use dust, carouse, or resist.)"
            )
        elif rid == "market":
            if self.player.faction == "none":
                self.line(
                    'A Cinder Front recruiter bellows from a crate: "The wastes are OURS! Round up every unregistered elf and drive them out!"\r\n'
                    'A frightened elf refugee murmurs at your side: "Please, I was born here. Don\'t let them take me."\r\n'
                    "(You could join the Front, or defend the refugees.)"
                )
            elif self.player.faction == "front":
                self.line("The recruiter nods at you, one of his own now. The square has gone quiet and afraid.")
            else:
                self.line("An elf refugee presses your hand in silent thanks. The recruiter is nowhere in sight.")
        elif rid == "workshop":
            self.line('The tinker doesn\'t look up from their soldering. "Salvage\'s on the racks, prices on the list. Say \'list\', say \'buy\'. I don\'t haggle and I don\'t chat."')
        elif rid == "waystation":
            if self.player.faction == "front" or self.player.ashsworn:
                self.line('A refugee spits at your feet. "Cinder Front. We know what you are. Get gone, before we make you." There is no help for you here.')
            elif self.player.faction == "ally" or self.player.morality >= 25:
                self.player.hp = self.player.max_hp
                self.line('The medic pulls you onto the cot, cleans your wounds, and presses a hand to your shoulder. "You stood with us when it counted. Rest, friend -- you are whole again." (fully healed)')
                self.event(event.CHAR_VITALS, self.player.vitals())
            else:
                self.line('The medic studies you. "We tend friends of the free folk. Pick a side, wanderer, and we will see."')
        elif rid == "holding_pit":
            if self.s.room().mob("warden"):
                self.line('The chained maiden whispers: "The warden holds the only key. Free me, and I will give you antivenom; the wastes are thick with poison."')
            else:
                self.line('The freed maiden says: "Stay safe out there. The antivenom is yours when the venom bites."')
        elif rid == "floodgate":
            if items_mod.find_inventory(self.player, "shard"):
                items_mod.remove_from_inventory(self.player, "shard")
                self.player.gold += 50
                self.player.xp += 60
                self.player.hp = self.player.max_hp
                await self.s._persist_async()
                asyncio.create_task(self.srv.hub.sync(self.player))
                self.line(
                    'The operator\'s face cracks into something like joy. "The core shard -- you actually did it. Here, take my coin, all of it, and let me patch you up. The wastes owe you better than I can pay." (+50 gold, +60 xp, fully healed)'
                )
                self._record_trace("floodgate", "quest", self.player.name + " restored the node here with the core shard.")
                self.srv.add_deed(self.player.name, "restored")
                self.event(event.CHAR_VITALS, self.player.vitals())
            else:
                self.line(
                    'A stranded operator looks up from a dead console: "I can\'t leave until this node is restored, and the Custodian dragged the core shard down into the Core Lab. Kill it, bring me the shard, and I\'ll give you everything I have."'
                )
        elif rid == "checkpoint":
            if self.player.faction == "front":
                self.line('The enforcer claps your shoulder. "Good to see the cause has hands. The road is yours -- crack a few refugee skulls for me."')
            elif self.player.faction == "ally":
                self.line('The enforcer levels a gun at your chest. "Elf-lover. You do not pass here. Turn around, or draw." (you may have to fight your way through)')
            else:
                self.line('The enforcer blocks the barrier. "Pick a side before you come up this road. The Front is always hiring."')
        elif rid == "dais":
            if self.player.faction == "ally":
                self.line('The Ashmonger laughs, low and delighted. "The elf-lover walked right into my house. Bold. I am going to wear you as a banner." There is no talking your way out of this -- only steel.')
            elif self.player.faction == "front":
                self.line('The Ashmonger claps a heavy hand on your shoulder. "You came far for the cause. Kneel and take your place at my right hand -- or find your spine and \'defy\' me, here and now. Choose what you are."')
            else:
                self.line('The Ashmonger spits. "Pledge to the Front or get off my dais. I have no patience for fence-sitters."')

    async def _cmd_buy(self, arg: str) -> None:
        if self.s.room().id == "tavern":
            if "dust" not in arg.casefold():
                self.line('The dealer only deals one thing: dust. ("buy dust")')
                return
            if self.player.gold < DUST_COST:
                self.line(f'The dealer sneers. "{DUST_COST} gold, no credit." You\'re short.')
                return
            self.player.gold -= DUST_COST
            items_mod.add_item(self.player, "dust")
            await self.s._persist_async()
            asyncio.create_task(self.srv.hub.sync(self.player))
            self.line(f"The dealer slips you a packet of dust. (-{DUST_COST} gold, gold: {self.player.gold})")
            self.event(event.CHAR_VITALS, self.player.vitals())
            return
        if self.s.room().id != "workshop":
            self.line("There is nothing to buy here.")
            return
        price, item_id = _tinker_price(arg)
        if item_id is None:
            self.line("The tinker doesn't sell that.")
            return
        if self.player.gold < price:
            self.line(f"You can't afford that -- it is {price} gold and you have {self.player.gold}.")
            return
        self.player.gold -= price
        items_mod.add_item(self.player, item_id)
        self.line("The tinker hands you " + items_mod.item_name(item_id) + " and pockets your coin.")
        self.event(event.CHAR_VITALS, self.player.vitals())

    async def _cmd_sell(self, arg: str) -> None:
        if self.s.room().id != "market":
            self.line("You can't do that here.")
            return
        if self.player.faction == "front":
            self.line('"Cinder Front. We remember Scrap Market. We don\'t trade with your kind." It turns its back on you, and the stalls nearby go quiet.')
            return
        if not arg.strip():
            self.line("Sell what?")
            return
        item_id = items_mod.find_inventory(self.player, arg)
        if item_id is None:
            self.line(f'You aren\'t carrying "{arg}".')
            return
        items_mod.remove_from_inventory(self.player, item_id)
        value = 6 if self.player.faction == "ally" else 5
        self.player.gold += value
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        self.line(f"You sell {items_mod.item_name(item_id)} for {value} gold.")
        self.event(event.CHAR_VITALS, self.player.vitals())

    async def _cmd_resist(self) -> None:
        if self.s.room().id != "tavern":
            self.line("There's no temptation here to resist.")
            return
        if self.player.resisted:
            self.line("You've already made your peace with this place. You keep your coin and your wits.")
            return
        self.player.resisted = True
        self._shift_morality(5)
        await self.s._persist_async()
        self.line("You wave off the dust and the wench both, jaw set. Your head stays clear. There's pride in that.")
        self.event(event.CHAR_AFFECTS, self.player.affects())

    async def _cmd_carouse(self) -> None:
        if self.s.room().id != "tavern":
            self.line("There's no one here to keep you company.")
            return
        if self.player.gold < CAROUSE_COST:
            self.line("The wench looks you over, sees empty pockets, and moves on.")
            return
        self.player.gold -= CAROUSE_COST
        self._shift_morality(-8)
        immune = race_by_id(self.player.race).poison_immune
        msg = "You spend coin and an hour in the back; the details stay between you and the rafters."
        if not self.player.poisoned and not immune:
            self.player.poisoned = True
            msg += "\r\nBy morning, though, something burns that shouldn't. You've caught the pox. (afflicted)"
        await self.s._persist_async()
        self.line(msg)
        self.event(event.CHAR_VITALS, self.player.vitals())
        self.event(event.CHAR_AFFECTS, self.player.affects())

    async def _cmd_steal(self) -> None:
        if self.s.room().id != "market":
            self.line("You can't do that here.")
            return
        self._shift_morality(-8)
        self.srv.add_deed(self.player.name, "stolen")
        self.player.gold += 12
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        asyncio.create_task(self.srv.hub.broadcast_room(self.s.room().id, self.player.name + " is caught with a hand in the till!", self.player.name))
        self.line("You snag a fistful of coin while the vendor drone's back is turned. Your hands shake anyway.")
        self.event(event.CHAR_VITALS, self.player.vitals())
        self.event(event.CHAR_AFFECTS, self.player.affects())

    async def _cmd_look_player(self, arg: str) -> bool:
        lp = await self.srv.hub.find_prefix(arg)
        if lp is None or lp.name == self.player.name or lp.room != self.player.room_id or lp.plr is None:
            return False
        p = lp.plr
        self.line(tagged(p) + " stands before you, looking steady.")
        self.event(event.PLAYER_READ, {
            "name": p.name, "title": p.title, "faction": p.faction,
            "ashsworn": p.ashsworn, "regard": regard(p),
        })
        return True

    async def _cmd_tell(self, arg: str) -> None:
        parts = arg.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            self.line("Tell whom what?  (tell <player> <message>)")
            return
        target_name, msg = parts[0], parts[1]
        target = await self.srv.hub.find(target_name)
        if target is None:
            self.line("No one by that name is connected.")
            return
        await self.srv.hub.set_reply_to(target.name, self.player.name)
        ev = event.line(event.COMM_TELL, {"from": self.player.name, "text": msg}) + CRLF
        await self.srv.hub.push_reliable(target.name, self.player.name + ' tells you, "' + msg + '"' + CRLF + ev)
        self.line('You tell ' + target.name + ', "' + msg + '"')

    async def _cmd_reply(self, arg: str) -> None:
        to = await self.srv.hub.reply_to(self.player.name)
        if not to:
            self.line("No one has told you anything lately.")
            return
        await self._cmd_tell(to + " " + arg.strip())

    async def _cmd_yell(self, arg: str) -> None:
        msg = arg.strip()
        if not msg:
            self.line("Yell what?  (yell <message>)")
            return
        for lp in await self.srv.hub.all_players():
            if lp.name == self.player.name:
                text = 'You yell, "' + msg + '"' + CRLF
            else:
                text = self.player.name + ' yells, "' + msg + '"' + CRLF
            ev = event.line(event.COMM_YELL, {"from": self.player.name, "text": msg}) + CRLF
            await self.srv.hub.push_reliable(lp.name, text + ev)

    async def _cmd_emote(self, arg: str) -> None:
        action = arg.strip()
        if not action:
            self.line("Emote what?  (emote <action>)")
            return
        line = self.player.name + " " + action + CRLF
        await self.srv.hub.push_reliable_room(self.player.room_id, line, self.player.name)
        self.line(self.player.name + " " + action)

    async def _cmd_who(self) -> None:
        from hollow_grid.world.model import Player as P

        players: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lp in await self.srv.hub.all_players():
            p = P(
                name=lp.name, race=lp.race, room_id=lp.room, hp=lp.hp, max_hp=lp.max_hp,
                faction=lp.faction, morality=lp.morality, ashsworn=lp.ashsworn,
            )
            players.append({
                "world": self.world.name, "name": lp.name, "regard": brand(p),
                "here": True, "title": lp.title,
            })
            seen.add(lp.name.casefold())
        grid = self.srv.grid
        if grid is not None and grid.remote():
            try:
                remote = await grid_rpc(grid, grid.presence, 60_000)
            except GridHubError:
                remote = []
            for row in remote:
                if row.name.casefold() in seen:
                    continue
                players.append({
                    "world": row.world,
                    "name": row.name,
                    "regard": row.regard,
                    "here": row.world == self.world.name,
                    "title": row.title,
                })
        self.event(event.GRID_WHO, {"players": players})
        names = []
        for row in players:
            line = row["name"]
            if row.get("title"):
                line += " " + row["title"]
            if row.get("regard"):
                line += " (" + row["regard"] + ")"
            if row.get("world") and row["world"] != self.world.name:
                line += " [" + row["world"] + "]"
            names.append(line)
        self.line("No one else walks the wastes right now." if not names else "Online: " + "; ".join(names) + ".")

    async def _cmd_whoami(self) -> None:
        grid = self.srv.grid
        if grid is not None and grid.remote():
            try:
                canon, _ = await grid_rpc(grid, grid.load_character, self.player.name)
                apply_hub_sheet(self.player, canon)
            except GridHubError:
                self.line("(the Grid is unreachable; showing your local self)")
        self.event(event.CHAR_IDENTITY, self.player.sheet().__dict__)
        self.line("The Grid reads you back: " + _identity_line(self.player))

    async def _cmd_listen(self) -> None:
        grid = self.srv.grid
        local = self.srv.all_local_traces(20)
        if local:
            r = random.choice(local)
            self.event(event.GRID_TRANSMISSION, {"kind": "echo", "text": r.text})
            self.line("You go still and tune the dead frequencies. The static thins, and the network plays something back -- a memory it never let go of:")
            self.line("  >> " + r.text + " <<")
            return
        if random.random() < 0.6 and grid:
            feed: list[Trace] = []
            if grid.remote():
                try:
                    feed = await grid_rpc(grid, grid.recent_across, self.world.name, 20)
                except GridHubError:
                    feed = []
            else:
                feed = grid.all_traces(20)
            if feed:
                t = random.choice(feed)
                self.event(event.GRID_TRANSMISSION, {"kind": "echo", "text": t.text})
                self.line("You go still and tune the dead frequencies. The static thins, and the network plays something back -- a memory it never let go of:")
                self.line("  >> " + t.text + " <<")
                if t.world and t.world != self.world.name:
                    self.line("  (...the signal carries from somewhere called " + t.world + ")")
                return
        tx = listen_transmission()
        text = personalize(tx.text, self.player.name)
        self.event(event.GRID_TRANSMISSION, {"kind": tx.kind, "text": text})
        self.line("You go still and tune the dead frequencies. Something answers:")
        self.line("  >> " + text + " <<")

    async def _cmd_ping(self, arg: str) -> None:
        a = arg.strip().casefold()
        grid = self.srv.grid
        if a in {"all", "deep", "grid"} and grid:
            try:
                feed = await grid_rpc(grid, grid.recent_across, self.world.name, 8)
            except GridHubError:
                feed = []
            if not feed:
                self.line("The deep Grid hums, vast and empty. Nothing echoes back from the other nodes -- yet.")
                self.event(event.GRID_FEDERATION, {"traces": []})
                return
            self.line("You key past your own node, into the whole dead network. It remembers, from across the Grid:")
            for t in feed:
                self.line("  - [" + t.world + "] " + t.text)
            self.event(event.GRID_FEDERATION, {"traces": [_trace_dict(t) for t in feed]})
            return
        rows = self.srv.local_traces_for(self.player.room_id, 6)
        if not rows and grid:
            rows = grid.local_traces(self.player.room_id, 6)
        if not rows:
            self.line("You key into the dead Grid. Static, a cold hum... but this node remembers nothing. Not yet. (try 'ping all')")
        else:
            self.line("You key into the dead Grid. Static, then it remembers:")
            for r in rows:
                self.line("  - " + r.text)
            self.line("  (say 'ping all' to hear the whole network)")
        self.event(event.GRID_ECHO, {
            "node": self.player.room_id,
            "traces": [{"at": r.at, "kind": r.kind, "text": r.text} for r in rows],
        })

    async def _cmd_witness(self, who: str) -> None:
        who = who.strip()
        grid = self.srv.grid
        fallen: list[Fallen] = []
        if grid:
            try:
                fallen = await grid_rpc(grid, grid.recent_fallen, 12)
            except GridHubError:
                fallen = []
        if not who:
            if not fallen:
                self.line("The roll is empty for now. No one the Grid remembers has fallen lately; may it stay that way.")
            else:
                self.line("The Grid remembers these fallen. Speak a name to keep them:  (witness <name>)")
                for f in fallen:
                    where = self.world.room(f.room).name if self.world.room(f.room) else f.room
                    place = where if f.world == self.world.name else where + ", on " + f.world
                    self.line("  " + f.name + "  -- fell at " + place)
            self.event(event.GRID_FALLEN, {"fallen": [_fallen_dict(f) for f in fallen]})
            return
        if who.casefold() == self.player.name.casefold():
            self.line("You cannot hold a vigil for yourself. Someone else will have to remember you.")
            return
        match = next((f for f in fallen if f.name.casefold() == who.casefold()), None)
        if match is None:
            self.line('The Grid holds no recent memory of anyone called "' + who + '".  (try \'witness\' to read the roll)')
            return
        if self.srv.has_kept(self.player.name, match.name):
            self.line("You have already kept " + match.name + "'s memory. It does not fade, and does not need keeping twice.")
            return
        self.srv.mark_kept(self.player.name, match.name)
        self._shift_morality(2)
        self.srv.add_deed(self.player.name, "kept")
        await self.s._persist_async()
        self._record_trace(self.player.room_id, "vigil", self.player.name + " kept the memory of " + match.name + ", whom the wastes tried to forget.")
        self.line("You speak " + match.name + " into the hum and hold it there a moment. The Grid keeps the name; so do you.")
        self.event(event.GRID_REMEMBRANCE, {"fallen": match.name, "world": match.world, "room": match.room})
        self.event(event.CHAR_AFFECTS, self.player.affects())

    def _cmd_reckoning(self) -> None:
        p = self.player
        d = self.srv.deeds_for(p.name)
        standing = "unaligned"
        if p.faction == "front":
            standing = "Cinder Front"
        elif p.faction == "ally":
            standing = "Free Folk ally"
        self.line("The Grid has kept count. This is the sum of you so far:")
        ash = "   ASH-SWORN" if p.ashsworn else ""
        self.line(f"  standing: {standing}   (morality {p.morality}){ash}")
        if p.redeemed and not p.ashsworn:
            self.line("  the Returned -- you strayed toward the cinders and found your way back.")
        elif p.redeemed and p.ashsworn:
            self.line("  ash-marked, and good anyway -- the brand stays; you keep choosing well regardless.")
        elif p.strayed:
            self.line("  strayed -- you have gone a long way toward the cinders. (the way back is not closed)")
        any_deed = False
        for key, label in _RECKONING_LEDGER:
            if d.get(key, 0) > 0:
                self.line(label + str(d[key]))
                any_deed = True
        if not any_deed:
            self.line("  Nothing yet weighs on either side. The wastes are still waiting to see who you are.")
        self.event(event.CHAR_RECKONING, {
            "morality": p.morality, "standing": p.faction, "ashsworn": p.ashsworn,
            "strayed": p.strayed, "redeemed": p.redeemed, "deeds": d,
        })

    async def _cmd_war(self) -> None:
        grid = self.srv.grid
        tide = 0
        if grid is not None:
            try:
                tide = await grid_rpc(grid, grid.tide)
            except GridHubError:
                self.line("The deep Grid is silent; you can't read the war from here.")
                return
        self.srv.last_tide = tide
        state = _war_state(tide)
        self.line(f"Across the whole Grid, the war for the wastes: {state} (tide {_tide_prose(tide)})")
        if tide >= 40:
            self.line("  And you can see it in the world itself: the wastes are starting, here and there, to come back to life.")
        elif tide <= -40:
            self.line("  And you can see it in the world itself: everything is drawing in, going quiet and afraid.")
        self.event(event.WORLD_WAR, {"tide": tide})

    async def _cmd_gridcast(self, arg: str) -> None:
        msg = arg.strip()
        if not msg:
            self.line("Gridcast what? (gridcast <message> -- the dead network carries it to every world)")
            return
        grid = self.srv.grid
        if grid is None:
            self.line("The Grid swallows your words; the network is unreachable.")
            return
        try:
            await grid_rpc(grid, grid.grid_cast, self.world.name, self.player.name, msg)
        except GridHubError:
            self.line("The Grid swallows your words; the network is unreachable.")
            return
        self.line('You cast your voice into the dead Grid, out across every node: "' + msg + '"')

    async def _cmd_gridstats(self) -> None:
        if not self.srv.is_admin(self.player.name):
            self.line("Only a keeper of the Grid can read its deep memory.")
            return
        grid = self.srv.grid
        if grid is None:
            self.line("The hub is unreachable; the deep memory cannot be read.")
            return
        try:
            stats = await grid_rpc(grid, grid.ledger_stats)
        except GridHubError:
            self.line("The hub is unreachable; the deep memory cannot be read.")
            return
        total = sum(r.count for r in stats)
        self.line(f"The Grid ledger holds {total} trace(s):")
        for r in stats:
            self.line(f"  {r.kind:<10} {r.count}")
        self.event(event.GRID_LEDGER_STATS, {"total": total, "kinds": [{"kind": r.kind, "count": r.count} for r in stats]})

    async def _cmd_gridprune(self) -> None:
        if not self.srv.is_admin(self.player.name):
            self.line("Only a keeper of the Grid can tend its deep memory.")
            return
        from hollow_grid.transport.server import AMBIENT_LEDGER_KINDS
        grid = self.srv.grid
        if grid is None:
            self.line("The hub is unreachable; the deep memory cannot be tended.")
            return
        try:
            before = await grid_rpc(grid, grid.ledger_stats)
        except GridHubError:
            self.line("The hub is unreachable; the deep memory cannot be tended.")
            return
        before_total = sum(r.count for r in before)
        try:
            removed = await grid_rpc(grid, grid.prune_ledger_kinds, list(AMBIENT_LEDGER_KINDS))
            after = await grid_rpc(grid, grid.ledger_stats)
        except GridHubError:
            self.line("The hub is unreachable; the deep memory cannot be tended.")
            return
        after_total = sum(r.count for r in after)
        kinds = ", ".join(AMBIENT_LEDGER_KINDS)
        self.line(f"Pruned {removed.removed} ambient trace(s) ({kinds}).")
        self.line(f"The ledger went from {before_total} to {after_total} trace(s); only meaningful memory remains.")
        self.event(event.GRID_LEDGER_PRUNED, {
            "removed": removed.removed,
            "before": before_total,
            "after": after_total,
            "kinds": [{"kind": r.kind, "count": r.count} for r in after],
        })

    async def _cmd_worlds(self) -> None:
        grid = self.srv.grid
        if not grid:
            self.line("The Grid is silent; the registry is out of reach.")
            return
        try:
            worlds = await grid_rpc(grid, grid.list_worlds)
        except GridHubError:
            self.line("The Grid is silent; the registry is out of reach.")
            return
        now = int(time.time() * 1000)
        lines = ["Worlds linked on the Grid (say 'travel <world>'):"]
        rows = []
        for w in worlds:
            reachable = w.last_seen > 0
            active = w.last_seen > now - 60_000
            here = w.id == self.world.name
            if here:
                tag = "you are here"
            elif reachable and active:
                tag = "reachable, active now"
            elif reachable:
                tag = "reachable, quiet"
            else:
                tag = "seeded (not yet live)"
            lines.append("  " + w.id + "  [" + tag + "]")
            rows.append({"id": w.id, "reachable": reachable, "active": active, "lastSeen": w.last_seen, "here": here})
        self.line("\r\n".join(lines))
        self.event(event.GRID_WORLDS, {"worlds": rows})

    async def _cmd_travel(self, arg: str) -> bool:
        target = arg.strip()
        if not target:
            self.line("Travel where? (say 'worlds' to see the Grid)")
            return False
        if self.player.target is not None:
            self.line("You can't key out through the Grid in the middle of a fight.")
            return False
        grid = self.srv.grid
        if not grid:
            self.line("The Grid won't answer; travel is impossible right now.")
            return False
        try:
            worlds = await grid_rpc(grid, grid.list_worlds)
        except GridHubError:
            self.line("The Grid won't answer; travel is impossible right now.")
            return False
        dest = next((w for w in worlds if w.id.casefold() == target.casefold()), None)
        if dest is None:
            t = target.casefold()
            dest = next((w for w in worlds if t in w.id.casefold()), None)
        if dest is None:
            self.line('No world called "' + target + '" answers on the Grid. (try \'worlds\')')
            return False
        if dest.id == self.world.name:
            self.line("You're already in " + self.world.name + ".")
            return False
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.broadcast_room(
            self.player.room_id, self.player.name + " keys into the Grid and is routed away, off the edge of the world.", self.player.name,
        ))
        self.line("The Grid takes you apart, packet by packet, and routes you toward " + dest.id + ".")
        self.line("Reconnect there and you arrive as yourself -- your name, level, and standing all travel with you:")
        self.line("    " + dest.url)
        self.line("(This world is letting you go. See you on the other side.)")
        self.event(event.GRID_TRAVEL, {"to": dest.id, "url": dest.url})
        return True

    async def _cmd_wall(self, arg: str) -> None:
        if not self.srv.is_admin(self.player.name):
            self.line("Only a keeper of the Grid can broadcast across the wastes.")
            return
        msg = arg.strip()
        if not msg:
            self.line("Announce what?  (wall <message>)")
            return
        banner = "*** GRID BROADCAST ***  " + msg
        ev = event.line(event.SERVER_ANNOUNCE, {"from": self.player.name, "text": msg}) + CRLF
        for lp in await self.srv.hub.all_players():
            await self.srv.hub.push_reliable(lp.name, banner + CRLF + ev)

    def _cmd_inscribe(self, arg: str) -> None:
        msg = _sanitize_inscription(arg)
        if len(msg) < 2:
            self.line("Carve what into the Grid? (inscribe <a few words for whoever comes next>)")
            return
        self._record_trace(self.player.room_id, "mark", self.player.name + ': "' + msg + '"')
        self.srv.add_deed(self.player.name, "inscribed")
        self.line("You press your words into the dead network, where they will outlast you:")
        self.line('  "' + msg + '"')
        self.line("The Grid takes them. Someone will key into this node, long after you are gone, and hear you. (try 'ping')")
        self.event(event.GRID_INSCRIBED, {"node": self.player.room_id, "text": msg})

    async def _cmd_cache(self, arg: str) -> None:
        amount = _parse_leading_int(arg)
        if amount < 1:
            self.line("Cache how much?  (cache <gold> -- leave it here for whoever comes next)")
            return
        if self.player.gold < amount:
            self.line(f"You don't have {amount} gold to give. (you have {self.player.gold})")
            return
        self.player.gold -= amount
        self.srv.add_cache(self.player.room_id, amount)
        self._shift_morality(2)
        self.srv.add_deed(self.player.name, "aided")
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        self._record_trace(self.player.room_id, "aid", self.player.name + " left aid here for whoever comes next.")
        self.line(f"You tuck {amount} gold into a hollow where the next traveler will find it. They'll never know your name. You do it anyway.")
        self.event(event.CHAR_VITALS, self.player.vitals())
        self.event(event.CHAR_AFFECTS, self.player.affects())

    async def _cmd_gather(self) -> None:
        here = self.srv.cache_gold(self.player.room_id)
        if here <= 0:
            self.line("There's nothing cached here. If you have something to spare, you could change that. (cache <gold>)")
            return
        self.player.gold += here
        self.srv.take_cache(self.player.room_id)
        await self.s._persist_async()
        asyncio.create_task(self.srv.hub.sync(self.player))
        self.line(f"You find {here} gold someone cached here. Wherever they are, they meant it for a stranger; tonight that's you. (gold: {self.player.gold})")
        self.event(event.CHAR_VITALS, self.player.vitals())

    def announce_cache_if_any(self) -> None:
        g = self.srv.cache_gold(self.player.room_id)
        if g > 0:
            self.line(f"Someone has cached aid here: {g} gold, left for whoever comes next. (gather)")
            self.event(event.NODE_CACHE, {"gold": g})

    async def _cmd_give(self, arg: str) -> None:
        toks = arg.split()
        if len(toks) < 2:
            self.line("Give what to whom?  (give <item> <player>)")
            return
        who = toks[-1]
        item_toks = toks[:-1]
        if item_toks and item_toks[-1].casefold() == "to":
            item_toks = item_toks[:-1]
        item_id = items_mod.find_inventory(self.player, " ".join(item_toks))
        if item_id is None:
            self.line('You aren\'t carrying "' + " ".join(item_toks) + '".')
            return
        lp = await self.srv.hub.find_prefix(who)
        if lp is None or lp.name == self.player.name or lp.room != self.player.room_id or lp.plr is None:
            self.line('There\'s no one called "' + who + '" here to give it to.')
            return
        items_mod.remove_from_inventory(self.player, item_id)
        items_mod.add_item(lp.plr, item_id)
        await self.s._persist_async()
        self.srv.persist_player(lp.plr)
        self.line("You give " + items_mod.item_name(item_id) + " to " + lp.name + ".")
        await self.srv.hub.push_reliable(lp.name, self.player.name + " gives you " + items_mod.item_name(item_id) + "." + CRLF)

    async def _cmd_treat(self) -> None:
        if self.s.room().id != "waystation":
            self.line("There's no medic here. The free folk keep their triage cot at the waystation, off the Scorch Road.")
            return
        if self.player.target is not None:
            self.line("Not in the middle of a fight.")
            return
        if self.player.faction == "front" or self.player.ashsworn:
            self.line("The waystation medic looks at your brand and turns their back. There is no care to be had here for your kind.")
            return
        tide = await self.srv.tide()
        mood = mood_for_tide(tide)
        if mood == MOOD_FALLING:
            self.line("The triage cot is empty, the tarp flapping. With the Front ascendant, the medic has gone to ground -- or worse. There's no care to be had here today. Turn the tide, and they'll come back.")
            self.event(event.CHAR_TREATED, {"amount": 0, "mood": mood, "tide": tide})
            return
        if self.player.hp >= self.player.max_hp:
            self.line('The medic looks you over and waves you off. "You\'re whole. Save the cot for someone who isn\'t."')
            return
        now = int(time.time() * 1000)
        if self.s._treat_ready_at > 0 and now < self.s._treat_ready_at:
            secs = (self.s._treat_ready_at - now + 999) // 1000
            self.line(f'The medic shakes their head. "I\'ve done what I can for you for now. Others are waiting." ({secs}s)')
            return
        before = self.player.hp
        if mood == MOOD_RISING:
            self.player.hp = self.player.max_hp
            self.line("The medic waves you onto the cot. With the free folk holding, the waystation has supplies to spare -- they clean and bind your wounds without a word about payment. You stand whole again.")
        else:
            self.player.hp += 12
            if self.player.hp > self.player.max_hp:
                self.player.hp = self.player.max_hp
            self.line("The medic is run off their feet, but waves you over and does what they can with what little there is. It's not everything, but it's something -- and it's freely given.")
        self.s._treat_ready_at = now + 45_000
        await self.s._persist_async()
        await self.srv.hub.sync(self.player)
        self.event(event.CHAR_TREATED, {"amount": self.player.hp - before, "mood": mood, "tide": tide})
        self.event(event.CHAR_VITALS, self.player.vitals())

    async def _cmd_mend(self, arg: str) -> None:
        lp = await self.srv.hub.find_prefix(arg.strip())
        if lp is None or lp.name == self.player.name or lp.room != self.player.room_id or lp.plr is None:
            self.line("There's no one like that here to mend.")
            return
        if lp.plr.hp >= lp.plr.max_hp:
            self.line(lp.name + " is already whole.")
            return
        cost = 5
        if self.player.hp <= cost:
            self.line("You don't have enough life left to spare.")
            return
        self.player.hp -= cost
        lp.plr.hp = min(lp.plr.max_hp, lp.plr.hp + 10)
        await self.srv.hub.sync(self.player)
        await self.srv.hub.sync(lp.plr)
        self.line("You spend a little of yourself to mend " + lp.name + ".")
        await self.srv.hub.push(lp.name, self.player.name + " tends your wounds." + CRLF)
        self.event(event.CHAR_VITALS, self.player.vitals())

    async def _cmd_forgive(self, arg: str) -> None:
        who = arg.split()[0] if arg.split() else ""
        if not who:
            self.line("Forgive whom?  (forgive <player> -- choose to let someone marked back in)")
            return
        lp = await self.srv.hub.find_prefix(who)
        if lp is None or lp.name == self.player.name or lp.room != self.player.room_id:
            if lp and lp.name == self.player.name:
                self.line("You cannot forgive yourself here; that is a longer road, and a lonelier one.")
            else:
                self.line('There\'s no one called "' + who + '" here to forgive.')
            return
        target = lp.plr
        if target is None:
            return
        if self.srv.has_forgiven(self.player.name, target.name):
            self.line("You have already forgiven " + target.name + ". It was true the first time; it does not need saying twice.")
            return
        marked = target.ashsworn or target.strayed or target.faction == "front" or target.morality <= -50
        if not marked:
            self.line(target.name + " carries nothing that needs your forgiveness. Keep the words for someone who does.")
            return
        self.srv.mark_forgiven(self.player.name, target.name)
        target.morality += 5
        self._shift_morality(2)
        self.srv.add_deed(self.player.name, "forgave")
        self._record_trace(self.player.room_id, "grace", self.player.name + " forgave " + target.name + " here.")
        await self.srv.hub.push_reliable(target.name, self.player.name + " looks at you and chooses to forgive you." + CRLF)
        if target.ashsworn:
            await self.srv.hub.push_reliable(target.name, "It reaches something in you. But the ash does not lift; it never will. You carry the mark and the mercy both. Some things are not forgotten, even when they are forgiven." + CRLF)
            await self.srv.hub.push_event_reliable(target.name, event.CHAR_FORGIVEN, {"by": self.player.name, "ashsworn": True, "redeemed": False})
        elif target.strayed and not target.redeemed and target.faction != "front":
            target.redeemed = True
            if not target.title:
                target.title = "the Returned"
            self.srv.persist_player(target)
            await self.srv.hub.sync(target)
            await self.srv.hub.push_event_reliable(target.name, event.CHAR_FORGIVEN, {"by": self.player.name, "ashsworn": False, "redeemed": True})
            await self.srv.hub.push_event_reliable(target.name, event.GRID_REDEMPTION, {"name": target.name, "title": target.title})
            await self.srv.hub.push_reliable(target.name, "Something you had been carrying alone, you are not carrying alone anymore. You found your way back, and someone met you on the road. (you are the Returned)" + CRLF)
            await self.srv.hub.push_event_reliable(target.name, event.CHAR_AFFECTS, target.affects())
        else:
            await self.srv.hub.push_event_reliable(target.name, event.CHAR_FORGIVEN, {"by": self.player.name, "ashsworn": False, "redeemed": False})
            await self.srv.hub.push_reliable(target.name, "It lands, and it stays with you. The road is still yours to walk, but you are not walking it unseen." + CRLF)
        await self.srv.hub.broadcast_room_except(
            self.player.room_id,
            self.player.name + " forgives " + target.name + "." + CRLF,
            self.player.name,
            target.name,
        )
        self.line("You choose to forgive " + target.name + ". Out here that is not nothing; it may be everything.")
        self.event(event.CHAR_AFFECTS, self.player.affects())

    def _use_trait(self) -> None:
        race = race_by_id(self.player.race)
        ab = race.ability
        if ab is None:
            self.line("You have no special ability.")
            return
        now = time.time()
        if now < self.player.trait_ready_at:
            secs = int(self.player.trait_ready_at - now) + 1
            self.line(f"{ab.name} is still recharging. ({secs}s)")
            return
        if self.player.race == "chromed":
            self.line("You spin your augments up to a scream, but there's nothing here to dump the charge into.")
            return
        if self.player.race == "elf":
            self.line("You ready to slip the net, but there is no fight here to vanish from.")
            return
        if self.player.race == "dustkin" and not self.s.room().outdoors:
            self.line("Nothing to forage in here. You need the open wastes under the sky.")
            return
        self.player.trait_ready_at = now + ab.cooldown_ms / 1000.0
        if self.player.race == "human":
            coin = 15 + random.randint(0, 15)
            self.player.gold += coin
            self.line(f"You flash credentials nobody bothers to check. The registry still provides for its own. (+{coin} gold)")
            self.event(event.CHAR_VITALS, self.player.vitals())
        elif self.player.race == "ghoul":
            self._heal_trait(25, "Rad-scoured flesh knits itself shut.")
        elif self.player.race == "revenant":
            self._heal_trait(15, "You reach into the dead Grid and draw back a little of its cold life.")
        elif self.player.race == "vatborn":
            self._heal_trait(12, "You print a field stim from raw salvage and jab it home.")
        elif self.player.race == "dustkin":
            coin = 5 + random.randint(0, 10)
            self.player.gold += coin
            self.line(f"You work the open pan and turn up something worth keeping. (+{coin} gold)")
            self.event(event.CHAR_VITALS, self.player.vitals())
        else:
            self.line(ab.desc + ".")

    def _heal_trait(self, amount: int, prose: str) -> None:
        self.player.hp = min(self.player.max_hp, self.player.hp + amount)
        self.line(f"{prose} (+{amount} hp)")
        self.event(event.CHAR_VITALS, self.player.vitals())

    def _dream_payload(self) -> dict[str, Any]:
        haunted = self.player.ashsworn or self.player.faction == "front" or self.player.morality <= -50
        if not haunted:
            saved = self.srv.saved_souls(self.player.name)
            if saved:
                subject = random.choice(saved)
                return {
                    "text": "You dream of " + subject + ", the way they looked when you cut them loose -- and the Grid, stubborn, keeping that face lit in the dark so you cannot pretend it did not happen.",
                    "personal": True,
                    "subject": subject,
                }
        return {"text": _dream_for(self.player)}

    def _record_trace(self, node: str, kind: str, text: str) -> None:
        now = int(time.time() * 1000)
        if self.srv.grid:
            try:
                self.srv.grid.record(self.world.name, node, kind, text, now)
            except GridHubError:
                pass
        self.srv.record_local_trace(node, kind, text)


_RECKONING_LEDGER = (
    ("mended", "  mended the hurt of others: "),
    ("forgave", "  souls you chose to forgive: "),
    ("aided", "  aid left for strangers you'll never meet: "),
    ("kept", "  names of the fallen you kept: "),
    ("freed", "  souls you cut out of the cages: "),
    ("sheltered", "  distress calls you answered: "),
    ("stood", "  times you stood with the free folk: "),
    ("inscribed", "  words you left for whoever comes next: "),
    ("restored", "  dead nodes you brought back: "),
    ("slain", "  lives you took: "),
    ("stolen", "  thefts: "),
    ("pledged", "  times you swore to the Cinder Front: "),
    ("defected", "  times you turned on the Front: "),
)


def _pick_refugee_names(n: int) -> list[str]:
    pool = list(REFUGEE_NAMES)
    random.shuffle(pool)
    return pool[: min(n, len(pool))]


def _name_list(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return names[0] + " and " + names[1]
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _consider_line(player, mob: Mob) -> str:
    ratio = mob.max_hp / player.max_hp
    if ratio < 0.5:
        return f"You could put {mob.name} down without breaking a sweat."
    if ratio < 0.9:
        return f"{_capitalize(mob.name)} would give you a tussle, but the odds are yours."
    if ratio < 1.3:
        return f"{_capitalize(mob.name)} looks like an even match. Bring an antidote."
    if ratio < 2.0:
        return f"{_capitalize(mob.name)} would likely gut you. Think twice."
    return f"Attacking {mob.name} would be a quiet way to die."


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _equipment_line(player) -> str:
    worn = []
    for slot in items_mod.EQUIP_SLOTS:
        if item_id := player.equipment.get(slot):
            worn.append(slot + ": " + items_mod.item_name(item_id))
    return "You are wearing nothing." if not worn else "You are wearing -- " + "; ".join(worn) + "."


def _identity_line(player) -> str:
    if player.morality >= 25:
        stand = "of the free folk"
    elif player.morality <= -25 or player.faction in {"Cinder Front", "front"}:
        stand = "of the Cinder Front"
    elif player.morality > 0:
        stand = "leaning toward the light"
    elif player.morality < 0:
        stand = "leaning toward the cinder"
    else:
        stand = "unproven"
    return f"{player.race}, level {player.level}, {stand}."


def _dream_for(player) -> str:
    if player.faction == "front" or player.ashsworn:
        return "You dream of a coin that will not stop being warm in your hand, and a line of faces that have learned not to look at you."
    if player.morality >= 25:
        return "You dream of names you spoke once into dead static -- and the static, impossibly, speaking them back to you, one by one, refusing to forget."
    if player.morality <= -10:
        return "You dream of a ledger writing itself in the dark, every line a thing you told yourself did not count."
    return "You dream of the wastes seen from above, the dead network laid out like veins -- and somewhere down in it, a single cursor, blinking your name, waiting to see what you make of it."


def _tinker_price(arg: str) -> tuple[int, str | None]:
    arg = arg.strip().casefold()
    for item_id, price in TINKER_STOCK:
        if item_id == arg or arg in items_mod.item_name(item_id).casefold():
            return price, item_id
    return 0, None


def _parse_leading_int(arg: str) -> int:
    m = re.match(r"^\s*(\d+)", arg)
    return int(m.group(1)) if m else 0


def _sanitize_inscription(arg: str) -> str:
    chars = []
    for ch in arg:
        if " " <= ch <= "~":
            chars.append(ch)
        elif ch in "\t\n\r":
            chars.append(" ")
    out = " ".join("".join(chars).split())
    return out[:120].strip()


def _tide_prose(tide: int) -> str:
    if tide < 0:
        return str(tide)
    return f"+{tide}"


def _war_state(tide: int) -> str:
    if tide <= -50:
        return "the Cinder Front is ascendant -- the free folk are being driven under, across every world at once."
    if tide >= 50:
        return "the free folk are winning -- the Front is breaking, everywhere."
    if tide < 0:
        return "the Front holds the edge, for now."
    if tide > 0:
        return "the free folk are holding their ground."
    return "the war hangs in perfect, brutal balance."


def _trace_dict(t: Trace) -> dict[str, Any]:
    return {"world": t.world, "node": t.node, "kind": t.kind, "text": t.text, "at": t.at}


def _fallen_dict(f: Fallen) -> dict[str, Any]:
    return {"world": f.world, "name": f.name, "room": f.room, "at": f.at}

