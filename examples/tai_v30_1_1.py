"""Execute the deterministic TAI v30.1.1 planning case study."""

from autofde_lab.hub.domain.tai_v30_1_1 import (
    INITIAL_STATE,
    POSITIVE_PLAN,
    TAIForwardDeploymentDomain,
    build_receipt,
)


def main() -> None:
    domain = TAIForwardDeploymentDomain()
    state = INITIAL_STATE
    for action in POSITIVE_PLAN:
        print(f"{action.name}: {state}")
        state = domain.get_next_state(state, action)
    print(build_receipt(POSITIVE_PLAN, state).to_json())


if __name__ == "__main__":
    main()
