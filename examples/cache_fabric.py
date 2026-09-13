"""End-to-end cache fabric example for a deterministic planning domain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autofde_lab.caching import CacheConfig, CachePolicy, cache_domain_factory


@dataclass(frozen=True)
class State:
    position: int


class LineDomain:
    def __init__(self) -> None:
        self.transition_evaluations = 0

    def get_next_state(self, state: State, action: int) -> State:
        self.transition_evaluations += 1
        return State(state.position + action)

    def is_terminal(self, state: State) -> bool:
        return state.position >= 10


def make_domain() -> LineDomain:
    return LineDomain()


def main() -> None:
    factory = cache_domain_factory(
        make_domain,
        policy=CachePolicy.custom("get_next_state", "is_terminal"),
        namespace="line-domain:model-v1",
        config=CacheConfig(
            memory_max_entries=10_000,
            persistent_path=Path(".cache/autofde_lab/line-domain.sqlite3"),
        ),
    )
    factory.cache_fabric.clear(reset_stats=True)
    first = factory()
    second = factory()
    state = State(0)

    assert first.get_next_state(state, 1) == State(1)
    assert second.get_next_state(state, 1) == State(1)
    assert first.transition_evaluations == 1
    assert second.transition_evaluations == 0

    print(factory.cache_fabric.info())
    print(factory.cache_fabric.last_receipt.to_json())
    factory.close()


if __name__ == "__main__":
    main()
