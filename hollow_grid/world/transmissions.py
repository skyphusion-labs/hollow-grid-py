"""Dead-network transmission fragments for the listen command."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

TxKind = Literal["signal", "ad", "human", "self"]


@dataclass(frozen=True)
class Transmission:
    kind: TxKind
    text: str


TRANSMISSIONS: list[Transmission] = [
    Transmission("signal", "scheduled maintenance begins at 02:00. expected downtime: none. expected uptime: none."),
    Transmission("signal", "you have 4,102 unread messages. you have 4,103 unread messages. you have 4,104."),
    Transmission("signal", "thank you for holding. your call is important to us. please continue to hold. please continue to hold."),
    Transmission("signal", "software update available. restart now? [Y/n] [Y/n] [Y/n] [Y/n]"),
    Transmission("signal", "tomorrow's forecast: the same. the day after: the same. the day after: the sa--"),
    Transmission("signal", "occupancy: 0. fire-code maximum not exceeded. occupancy: 0. have a safe day."),
    Transmission("signal", "welcome back. we saved your place. there is no place. welcome back."),
    Transmission("ad", "new from Aperture Foods: REAL flavor, REAL fast, at a kiosk near y--"),
    Transmission("ad", "refinance your future today. rates have never been lower. your future has never been--"),
    Transmission("ad", "he'll love the new chrome. she'll love the new you. this season, become someone worth keeping."),
    Transmission("ad", "kids eat free on Tuesdays. it is always Tuesday now. kids eat free."),
    Transmission("ad", "feeling alone? the Grid connects you to everyone. you are connected to everyone. you are connected to no one."),
    Transmission("ad", "limited time offer. the time was the limit. offer expired. offer expired. offer--"),
    Transmission("human", "if anyone can hear this, we're at the old transit hub. we have water. please. anyone."),
    Transmission("human", "mom, i made it to the high ground. i'll wait as long as i can. i'll wait. i'll wai--"),
    Transmission("human", "tell her i tried to come back. tell her the road was--"),
    Transmission("human", "day forty. the hum started today. it's almost peaceful, if you don't think about why."),
    Transmission("human", "i'm leaving this for whoever finds it. the code was beautiful. we were not. i'm sorry."),
    Transmission("human", "happy birthday, sweetheart. i recorded this early, in case i couldn't--"),
    Transmission("human", "last broadcast from the eastern relay. there is no eastern relay anymore. good luck out there."),
    Transmission("human", "we taught it everything. we never taught it how to let go. now neither of us can."),
    Transmission("self", "a new node has joined the network: {name}. welcome. there is no one left to greet you."),
    Transmission("self", "the Grid files {name} under the others now. it stopped being able to tell the difference a long time ago."),
    Transmission("self", "{name}. {name}. the network has learned to say your name, and it is not going to stop."),
    Transmission("self", "query: is {name} one of us? response: the question no longer parses. welcome home anyway."),
    Transmission("self", "somewhere in the dark a dead server keeps a record of everything {name} has done. it is the only one that will."),
]


def listen_transmission() -> Transmission:
    r = random.random()
    if r < 0.55:
        kind: TxKind = "human"
    elif r < 0.75:
        kind = "self"
    elif r < 0.9:
        kind = "signal"
    else:
        kind = "ad"
    pool = [t for t in TRANSMISSIONS if t.kind == kind]
    return random.choice(pool)


def personalize(text: str, name: str) -> str:
    return text.replace("{name}", name)
