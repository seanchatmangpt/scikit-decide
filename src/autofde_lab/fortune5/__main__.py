"""CLI for bounded Fortune-5 state-space inspection."""

from __future__ import annotations

import argparse
import json

from . import FORTUNE5_SPACE, pairwise_token_count


def _summary() -> dict[str, object]:
    candidates = FORTUNE5_SPACE.pairwise_candidates(candidate_limit=5_000)
    return {
        "standing": "CANDIDATE",
        "authority": "NONE",
        "space_digest": FORTUNE5_SPACE.digest,
        "axes": len(FORTUNE5_SPACE.axes),
        "raw_upper_bound": FORTUNE5_SPACE.raw_upper_bound,
        "pairwise_candidates": len(candidates),
        "pairwise_tokens": pairwise_token_count(candidates),
        "compression_ratio": FORTUNE5_SPACE.raw_upper_bound / len(candidates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary")
    scenario_parser = sub.add_parser("scenario")
    scenario_parser.add_argument("--index", type=int, required=True)
    cover_parser = sub.add_parser("cover")
    cover_parser.add_argument("--max-scenarios", type=int)
    args = parser.parse_args(argv)

    if args.command == "summary":
        payload = _summary()
    elif args.command == "scenario":
        scenario = FORTUNE5_SPACE.raw_coordinate_at(args.index)
        payload = {
            "scenario_id": scenario.scenario_id,
            "space_digest": scenario.space_digest,
            "raw_index": FORTUNE5_SPACE.raw_index_of(scenario),
            "lawful": FORTUNE5_SPACE.is_lawful(scenario),
            "standing": scenario.standing,
            "authority": scenario.authority,
            "choices": scenario.names(),
        }
    else:
        candidates = FORTUNE5_SPACE.pairwise_candidates(candidate_limit=5_000)
        cover = FORTUNE5_SPACE.pairwise_covering(
            candidate_limit=5_000,
            max_scenarios=args.max_scenarios,
        )
        payload = {
            "standing": "CANDIDATE",
            "authority": "NONE",
            "space_digest": FORTUNE5_SPACE.digest,
            "candidate_count": len(candidates),
            "candidate_pair_tokens": pairwise_token_count(candidates),
            "cover_count": len(cover),
            "cover_pair_tokens": pairwise_token_count(cover),
            "scenario_ids": [scenario.scenario_id for scenario in cover],
        }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
