"""CLI for the deterministic Fortune-5 SAFe simulation."""

import argparse
import json

from . import Fortune5Config, run_full_matrix, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix", action="store_true", help="run all policy × disruption episodes"
    )
    parser.add_argument("--seed", type=int, default=Fortune5Config.seed)
    args = parser.parse_args()
    config = Fortune5Config(seed=args.seed)
    payload = summary(config)
    if args.matrix:
        result = run_full_matrix(config)
        payload.update(
            {
                "feasible_policy_count": len(result.feasible_policy_ids),
                "pareto_policy_count": len(result.pareto_policy_ids),
                "diversity_score": result.diversity_score,
                "matrix_digest": result.matrix_digest,
                "pareto_policy_ids": result.pareto_policy_ids,
                "selection": None,
            }
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
