"""Disclaimer text and the one-time acknowledgement. Full text: DISCLAIMER.md."""

from __future__ import annotations

import datetime as dt
import json
import logging

from .config import ROOT

log = logging.getLogger(__name__)

# Bump this when the disclaimer changes in a meaningful way; everyone is asked again.
VERSION = 1
RECORD = ROOT / "disclaimer_accepted.json"

# Rotates through the bottom bar with the current conditions.
SHORT = "Entertainment only. For warnings, use NOAA Weather Radio & local media"

# Follows every alert in the red warning crawl.
CRAWL = ("This display is not an official warning source and may miss or delay warnings. "
         "Get warnings from NOAA Weather Radio, Wireless Emergency Alerts, local media and weather.gov.")

# Logged every time the program starts.
CONSOLE = ("This display is for entertainment only. It is not a weather alerting system, has no "
           "redundancy, and must not be relied on in an emergency or used to alert the public. "
           "See DISCLAIMER.md.")

# Shown on the first-run screen (and printed by --accept-disclaimer).
TITLE = "Please read before using this weather display"
PARAGRAPHS = [
    "This program is for entertainment and hobby use only. It is not a weather alerting system "
    "and must not be relied on in a weather emergency.",
    "It has no redundancy. It depends on one internet connection, one computer and the National "
    "Weather Service's servers. If any of them has a problem, a warning such as a Tornado Warning "
    "can show up late, incomplete or not at all, with no sign that anything was missed. Nobody "
    "monitors it.",
    "Do not use it to alert the public (for example as a cable or broadcast channel) or as anyone's "
    "main source of warnings. Get alerts from NOAA Weather Radio, Wireless Emergency Alerts on your "
    "phone, local TV and radio, and weather.gov.",
    "It is provided \"as is\", without warranty of any kind. The author accepts no liability for "
    "any damage, injury or loss of life resulting from its use or failure. If you change the "
    "program or remove these notices, you are responsible for the result.",
]
CHECKBOX = "I have read and understand this disclaimer, and I accept all risk of using this software."


def accepted() -> bool:
    try:
        data = json.loads(RECORD.read_text(encoding="utf-8"))
        return int(data.get("version", 0)) >= VERSION
    except (OSError, ValueError):
        return False


def record_acceptance(how: str) -> None:
    data = {"version": VERSION, "accepted": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "how": how}
    try:
        RECORD.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        log.info("Disclaimer accepted (%s); saved to %s", how, RECORD.name)
    except OSError as e:
        log.warning("Couldn't save the disclaimer acknowledgement (%s); you'll be asked again next time", e)


def console_text() -> str:
    width = 78
    out = [TITLE, "=" * len(TITLE), ""]
    for para in PARAGRAPHS:
        line = ""
        for word in para.split():
            if len(line) + len(word) + 1 > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        out += [line, ""]
    out.append("Full text: DISCLAIMER.md")
    return "\n".join(out)
