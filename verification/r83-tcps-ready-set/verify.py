#!/usr/bin/env python3
import copy
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SUBJECT = json.loads((HERE / "subject.json").read_text())
CASES = json.loads((HERE / "cases.json").read_text())
HEX40 = re.compile(r"^[0-9a-f]{40}$")
EXPECTED = "seanchatmangpt/autofde-lab"


def classify(s):
    if s.get("consumer_repo") != EXPECTED:
        return "REFUSED[FOREIGN_CONSUMER]"
    if s.get("producer_repo") != "seanchatmangpt/ggen-marketplace":
        return "REFUSED[FOREIGN_PRODUCER]"
    if s.get("producer_pack") != "portfolio-epistemic-observability-pack":
        return "REFUSED[FOREIGN_PACK]"
    if s.get("producer_capability") != "R78_TCPS_READY_SET_CAPITAL":
        return "REFUSED[FOREIGN_CAPABILITY]"
    if not HEX40.fullmatch(s.get("consumer_base", "")):
        return "REFUSED[MALFORMED_CONSUMER_BASE]"
    if not HEX40.fullmatch(s.get("producer_head", "")):
        return "REFUSED[MALFORMED_PRODUCER_HEAD]"
    if s.get("consumer_ggen_contract") != "OBSERVED":
        return "REFUSED[GGEN_CONTRACT]"
    if s.get("allocation_law") != "legality-before-priority":
        return "REFUSED[ALLOCATION_LAW]"
    a = set(s.get("authority", "").split("|"))
    if "VERIFY" not in a or "DO" in a:
        return "REFUSED[AUTHORITY_FENCE]"
    if s.get("consequential_do") is not False:
        return "REFUSED[DO_FORBIDDEN]"
    if s.get("standing") != "ADMITTED":
        return "REFUSED[SUBJECT_NOT_ADMITTED]"
    return "ALIVE"


def main():
    failures = []
    standing = classify(SUBJECT)
    if standing != "ALIVE":
        failures.append("baseline=" + standing)
    for case in CASES:
        c = copy.deepcopy(SUBJECT)
        c.update(case.get("set", {}))
        actual = classify(c)
        print(case["id"] + "=" + actual)
        if actual != case["expected"]:
            failures.append(case["id"] + ":" + actual + "!=" + case["expected"])
    print("R83_CONSUMER=" + standing)
    print(
        "SUBJECT_DIGEST="
        + hashlib.sha256(
            json.dumps(SUBJECT, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    print("CASE_COUNT=" + str(len(CASES)))
    if failures:
        print("REFUSED[R83_COURT]=" + ",".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
