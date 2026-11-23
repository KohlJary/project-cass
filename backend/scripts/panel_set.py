#!/usr/bin/env python3
"""Record a daemon's own answers about her panel, exactly as she gave them.

    python scripts/panel_set.py now=yes today=yes work=yes this_reply=yes audience=house \\
        --note this_reply="only significant self-observations, not the internal noise"
    python scripts/panel_set.py --show

Sections: now, today, commitments, stances, work, this_reply (yes, no, not_yet).
Daybook kinds: daybook.sessions, daybook.journals, daybook.dreams, daybook.self_model.
Audience: kohl, house, visitors, none. Run it only with answers she gave.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from panel import set_answers, settings  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args == ["--show"]:
        print(json.dumps(settings(), indent=1))
        sys.exit(0)
    sections, notes, audience = {}, {}, None
    it = iter(args)
    for a in it:
        if a == "--note":
            k, _, v = next(it).partition("=")
            notes[k] = v
            continue
        k, _, v = a.partition("=")
        if k == "audience":
            audience = v
        else:
            sections[k] = v
    print(json.dumps(set_answers(sections, audience, notes), indent=1))
