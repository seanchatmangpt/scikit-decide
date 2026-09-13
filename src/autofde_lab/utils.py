# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""This module contains utility functions."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import time
from collections.abc import Callable, Iterable
from enum import Enum
from typing import Any, Optional, Union

from autofde_lab import (
    D,
    Domain,
    EnvironmentOutcome,
    Solver,
    Value,
    autocast_all,
    autocastable,
)
from autofde_lab.builders.domain import (
    Goals,
    Initializable,
    Markovian,
    Renderable,
)
from autofde_lab.builders.solver import DeterministicPolicies, Policies

__all__ = [
    "get_registered_domains",
    "get_registered_solvers",
    "load_registered_domain",
    "load_registered_solver",
    "match_solvers",
    "rollout",
]

from autofde_lab.core import autocast

# Data-home identity. This names a directory on a user's disk that may hold
# gigabytes of downloaded weather data, so it is VERSIONED_MIGRATION, not a
# rename: silently switching the default would leave the old directory
# stranded and re-download everything into the new one, with the only
# symptom being a slow first run. The legacy names are kept and honoured.
AUTOFDE_LAB_DEFAULT_DATAHOME = "~/autofde_lab_data"
AUTOFDE_LAB_DATAHOME_ENVVARNAME = "AUTOFDE_LAB_DATA"
SKDECIDE_DEFAULT_DATAHOME = "~/skdecide_data"
SKDECIDE_DEFAULT_DATAHOME_ENVVARNAME = "SKDECIDE_DATA"

# One warning per process, not per call: get_data_home() is called inside
# download loops.
_legacy_datahome_warned = False

logger = logging.getLogger("autofde_lab.utils")

logger.setLevel(logging.INFO)

if not len(logger.handlers):
    ch = logging.StreamHandler()
    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    )
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(ch)
    logger.propagate = False


def _resolve_default_data_home() -> str:
    """Resolve the data directory, honouring the pre-rename location.

    Precedence, most explicit first:

    1. ``AUTOFDE_LAB_DATA`` -- the current environment variable.
    2. ``SKDECIDE_DATA`` -- the legacy variable, still honoured. A user with
       it exported has said where their data lives; a rename is not a reason
       to stop listening.
    3. ``~/skdecide_data`` **if it already exists** -- an existing directory
       is evidence of a real prior install with real downloaded data. Using
       it (with a one-time notice) is what keeps the rename from silently
       re-downloading gigabytes into a new path.
    4. ``~/autofde_lab_data`` -- the default for a fresh install.

    Nothing is moved, copied, or deleted. Migration is the user's call; this
    function only avoids making it for them.
    """
    global _legacy_datahome_warned

    explicit = os.environ.get(AUTOFDE_LAB_DATAHOME_ENVVARNAME)
    if explicit:
        return explicit

    legacy_env = os.environ.get(SKDECIDE_DEFAULT_DATAHOME_ENVVARNAME)
    if legacy_env:
        return legacy_env

    legacy_dir = os.path.expanduser(SKDECIDE_DEFAULT_DATAHOME)
    if os.path.isdir(legacy_dir):
        if not _legacy_datahome_warned:
            _legacy_datahome_warned = True
            logger.info(
                "Using the legacy data directory %s. The current default is "
                "%s. Nothing has been moved -- to migrate, move the directory "
                "yourself or set %s. This notice appears once per process.",
                legacy_dir,
                AUTOFDE_LAB_DEFAULT_DATAHOME,
                AUTOFDE_LAB_DATAHOME_ENVVARNAME,
            )
        return legacy_dir

    return AUTOFDE_LAB_DEFAULT_DATAHOME


def get_data_home(data_home: Optional[str] = None) -> str:
    """Return the path of the scikit-decide data directory.

    This folder is used by some large dataset loaders to avoid downloading the
    data several times, as for instance the weather data used by the flight planning domain.
    This folder is used by some large dataset loaders to avoid downloading
    the data several times, as for instance the weather data used by the
    flight planning domain.

    By default the data dir is a folder named 'autofde_lab_data' in the user
    home folder -- unless a pre-rename '~/skdecide_data' already exists, in
    which case that is used instead so an existing install keeps its data.
    It can also be set by the 'AUTOFDE_LAB_DATA' environment variable, by
    the legacy 'SKDECIDE_DATA' variable, or programmatically by giving an
    explicit folder path. See `_resolve_default_data_home` for the exact
    precedence. The '~' symbol is expanded to the user home folder. If the
    folder does not already exist, it is automatically created.

    Params:
        data_home : The path to the data directory. If `None`, the default
        is resolved as described above.

    """
    if data_home is None:
        data_home = _resolve_default_data_home()
    data_home = os.path.expanduser(data_home)
    os.makedirs(data_home, exist_ok=True)
    return data_home


def _get_registered_entries(entry_type: str) -> list[str]:
    return [e.name for e in importlib.metadata.entry_points(group=entry_type)]


def _load_registered_entry(entry_type: str, entry_name: str) -> Optional[Any]:
    potential_entry_points = tuple(
        importlib.metadata.entry_points(group=entry_type, name=entry_name)
    )
    if len(potential_entry_points) == 0:
        logger.warning(
            rf'/!\ {entry_name} could not be loaded because it is not registered in group "{entry_type}".'
        )
    else:
        try:
            return potential_entry_points[0].load()
        except Exception as e:
            logger.warning(rf"/!\ {entry_name} could not be loaded ({e}).")


def get_registered_domains() -> list[str]:
    return _get_registered_entries("autofde_lab.domains")


def get_registered_solvers() -> list[str]:
    return _get_registered_entries("autofde_lab.solvers")


def load_registered_domain(name: str) -> type[Domain]:
    return _load_registered_entry("autofde_lab.domains", name)


def load_registered_solver(name: str) -> type[Solver]:
    return _load_registered_entry("autofde_lab.solvers", name)


def _solver_measures(solver_type: type[Solver]) -> tuple[float, float, float, float]:
    """Derive 4 real, class-level numeric measures for a matched solver.

    Every value comes from an attribute that genuinely exists on the real
    ``Solver``/``Hyperparametrizable`` classes (see the grounding report this
    change was built from) -- nothing here is a fabricated score, confidence,
    speed, or quality metric, since no such hook exists anywhere in
    ``Solver``. These are structural/complexity proxies only, in the order
    consumed by ``cmca_rank_cli``'s 4 measure slots:

    1. ``domain_requirements`` -- ``len(solver_type.get_domain_requirements())``:
       how many domain-builder mixins the solver demands. A real structural
       specialization signal (more requirements = exploits richer domain
       structure; fewer = broader, more generic applicability).
    2. ``hyperparameter_count`` -- ``len(solver_type.get_hyperparameters_names())``:
       count of declared tunable hyperparameters, a real configurability
       proxy every ``discrete_optimization``-based solver already carries via
       ``Hyperparametrizable``.
    3. ``has_domain_check`` -- ``1.0`` if ``solver_type`` overrides
       ``Solver._check_domain_additional`` (does real, solver-specific
       compatibility reasoning beyond the generic requirements check) else
       ``0.0``.
    4. ``mro_depth`` -- ``len(solver_type.__mro__)``: a rough
       specialization-vs-genericity signal from the real class hierarchy
       depth. Weaker than the others but still a real, inspectable class
       attribute, not invented.

    These are intentionally unweighted, unnormalized raw counts -- the actual
    weighting/ranking policy lives in ``cmca_rank_cli``'s compiled
    ``case_studies`` lens registry, not here.
    """
    domain_requirements = float(len(solver_type.get_domain_requirements()))
    hyperparameter_count = float(len(solver_type.get_hyperparameters_names()))
    has_domain_check = (
        1.0
        if solver_type._check_domain_additional is not Solver._check_domain_additional
        else 0.0
    )
    mro_depth = float(len(solver_type.__mro__))
    return (domain_requirements, hyperparameter_count, has_domain_check, mro_depth)


# Optional adapter: an out-of-process ranking backend for match_solvers(ranked=True).
# Follows the exact BcinrSchedulerAdapter/adapters.base convention: probed via
# BCINR_HOME (plus a CMCA_RANK_CLI_BIN override), never required, never raises out
# of the probe, and any failure degrades to the existing unranked match order --
# never a crash. See autofde_lab.adapters.bcinr.BcinrSchedulerAdapter and
# autofde_lab.adapters.base for the shared primitives this mirrors.
CMCA_RANK_CLI_BIN_ENVVARNAME = "CMCA_RANK_CLI_BIN"
_CMCA_RANK_CLI_RELATIVE_PATH = "target/debug/cmca_rank_cli"

# One warning per process for ranked=True falling back, mirroring the
# _legacy_datahome_warned convention above -- ranked=True may be called in a loop
# (e.g. once per matched domain), and a fallback here is expected/optional
# behaviour, not a bug to spam about.
_cmca_rank_cli_fallback_warned = False


def _resolve_cmca_rank_cli_bin() -> Optional[str]:
    """Locate the optional ``cmca_rank_cli`` binary, or return ``None``.

    Precedence, most explicit first, mirroring
    ``autofde_lab.adapters.base.resolve_home``:

    1. ``CMCA_RANK_CLI_BIN`` -- an explicit path to the binary itself.
    2. ``$BCINR_HOME/target/debug/cmca_rank_cli`` -- the same ``BCINR_HOME``
       env var ``BcinrSchedulerAdapter`` probes, joined to the binary's
       conventional build output path.
    3. ``~/bcinr/target/debug/cmca_rank_cli`` -- the same default root
       ``BcinrSchedulerAdapter`` uses.

    Never raises. Returns ``None`` (not found / not executable) rather than
    a boolean, so the caller can log where it looked.
    """
    explicit = os.environ.get(CMCA_RANK_CLI_BIN_ENVVARNAME)
    if explicit:
        return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None

    from autofde_lab.adapters.base import resolve_home
    from autofde_lab.adapters.bcinr import BcinrSchedulerAdapter

    root = resolve_home(BcinrSchedulerAdapter.env_var, BcinrSchedulerAdapter.default_root)
    candidate = os.path.join(root, _CMCA_RANK_CLI_RELATIVE_PATH)
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def _rank_via_cmca_rank_cli(
    matches: list[type[Solver]],
) -> Optional[list[tuple[type[Solver], float]]]:
    """Try to rank ``matches`` via the optional ``cmca_rank_cli`` subprocess.

    Returns ``None`` (never raises) on any failure -- binary not found,
    subprocess error, malformed output, or a name in the response that
    doesn't match a real candidate -- so the caller can fall back to the
    existing unranked match order. This is the graceful-degradation half of
    the adapter philosophy in ``autofde_lab.adapters.base``: a missing
    sibling optional backend must never lower the standing of the core.
    """
    global _cmca_rank_cli_fallback_warned

    def _fallback(reason: str) -> None:
        global _cmca_rank_cli_fallback_warned
        if not _cmca_rank_cli_fallback_warned:
            _cmca_rank_cli_fallback_warned = True
            logger.info(
                "match_solvers(ranked=True) falling back to unranked match order: %s "
                "(this notice appears once per process; ranked=True degrades "
                "gracefully by design when cmca_rank_cli is unavailable or fails)",
                reason,
            )

    binary = _resolve_cmca_rank_cli_bin()
    if binary is None:
        _fallback(
            f"cmca_rank_cli binary not found (checked {CMCA_RANK_CLI_BIN_ENVVARNAME} and "
            f"$BCINR_HOME/{_CMCA_RANK_CLI_RELATIVE_PATH})"
        )
        return None

    import json
    import subprocess

    # Names must be unique for the response to be unambiguously mappable back
    # to a solver type; qualify by module to avoid collisions between solvers
    # sharing a class name.
    name_by_key: dict[str, type[Solver]] = {}
    candidates_payload = []
    for solver_type in matches:
        key = f"{solver_type.__module__}.{solver_type.__qualname__}"
        name_by_key[key] = solver_type
        candidates_payload.append(
            {"name": key, "measures": list(_solver_measures(solver_type))}
        )

    try:
        result = subprocess.run(
            [binary],
            input=json.dumps({"candidates": candidates_payload}),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _fallback(f"subprocess invocation failed ({exc!r})")
        return None

    if result.returncode != 0:
        _fallback(
            f"cmca_rank_cli exited {result.returncode}: {result.stderr.strip() or result.stdout.strip()}"
        )
        return None

    try:
        parsed = json.loads(result.stdout)
        ranking = parsed["ranking"]
        ranked_pairs = [(name_by_key[entry["name"]], entry["share"]) for entry in ranking]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        _fallback(f"could not parse cmca_rank_cli output ({exc!r})")
        return None

    if len(ranked_pairs) != len(matches):
        _fallback(
            f"cmca_rank_cli returned {len(ranked_pairs)} ranked candidates for "
            f"{len(matches)} matches"
        )
        return None

    return ranked_pairs


# cmca_rank_cli (CMCA-108) is compiled for at most this many candidates and
# refuses (typed error, not a crash) above it. Real autofde-lab domains can
# match up to 46 candidates, so without a pre-filter ranked=True always hit
# the refusal and silently fell back to unranked order -- the real ranking
# success path was never exercised on real data.
_CMCA_RANK_CLI_MAX_CANDIDATES = 8


def _prefilter_top_for_ranking(
    matches: list[type[Solver]], limit: int = _CMCA_RANK_CLI_MAX_CANDIDATES
) -> tuple[list[type[Solver]], list[type[Solver]]]:
    """Split ``matches`` into (top ``limit``, remainder) for ``cmca_rank_cli``.

    Criterion, chosen deliberately rather than inventing a new metric: the
    unweighted sum of ``_solver_measures``'s 4 existing real signals
    (``domain_requirements + hyperparameter_count + has_domain_check +
    mro_depth``). This reuses exactly the measures already computed for the
    CLI payload -- no fifth metric is introduced. The sum is defensible as a
    single "overall structural specificity" proxy: solvers that declare more
    domain requirements, more tunable hyperparameters, override the
    additional domain-check hook, and sit deeper in the class hierarchy are,
    on these real, inspectable signals, the more specialized/informative
    candidates to spend the CLI's 8-candidate budget on. Ties are broken by
    the qualified name (``module.qualname``) for full determinism, since
    ``_solver_measures`` alone can tie.

    Returns ``(top, rest)`` where ``top`` has at most ``limit`` entries
    (sent to ``cmca_rank_cli`` for real governed ranking) and ``rest`` holds
    every other matched candidate, in their original relative match order
    (see ``match_solvers`` for what happens to ``rest`` in the final
    result -- they are appended, not dropped).
    """
    if len(matches) <= limit:
        return matches, []

    def _sort_key(solver_type: type[Solver]) -> tuple[float, str]:
        total = sum(_solver_measures(solver_type))
        qualified_name = f"{solver_type.__module__}.{solver_type.__qualname__}"
        return (-total, qualified_name)

    ordered = sorted(matches, key=_sort_key)
    top_set = set(ordered[:limit])
    # Preserve each group's original match order rather than the
    # criterion-sorted order, so `rest` reads as "everything else, in the
    # order match_solvers found it" -- the least surprising behaviour.
    top = [s for s in matches if s in top_set]
    rest = [s for s in matches if s not in top_set]
    return top, rest


def match_solvers(
    domain: Domain,
    candidates: Optional[Iterable[type[Solver]]] = None,
    ranked: bool = False,
) -> Union[list[type[Solver]], list[tuple[type[Solver], float]]]:
    """Filter registered solver classes by domain compatibility.

    If ``ranked`` is ``False`` (the default), behaviour is unchanged: a plain
    list of matched solver classes in match order.

    If ``ranked`` is ``True``, the matched candidates are additionally scored
    via ``_solver_measures`` (4 real, inspectable class-level attributes --
    see that function's docstring) and, if the optional ``cmca_rank_cli``
    binary is available (probed via the same ``BCINR_HOME``/``default_root``
    convention as ``autofde_lab.adapters.bcinr.BcinrSchedulerAdapter``, plus a
    ``CMCA_RANK_CLI_BIN`` override), ranked by subprocess-calling it and
    reordering by the returned share, descending. This is entirely optional:
    if the binary is unavailable, or the subprocess call fails for any
    reason, ``ranked=True`` degrades gracefully to the existing match order
    (each solver paired with rank position as its score) rather than raising
    -- matching this repo's stated philosophy that sibling repos are never
    prerequisites (see ``autofde_lab/adapters/base.py``).

    ``cmca_rank_cli`` (CMCA-108) is compiled for at most 8 candidates and
    refuses above that. When more than 8 candidates match, this function
    pre-filters to the top 8 (see ``_prefilter_top_for_ranking`` for the
    exact criterion) *before* invoking the CLI, so the real ranking success
    path actually fires on real data instead of always hitting the refusal.
    The candidates outside the top 8 are **not dropped** from the returned
    list: they are appended after the ranked 8, in their original match
    order, each paired with a synthetic score strictly lower than every real
    share returned by the CLI -- so a caller that sorts or reads the list
    top-down sees "really ranked" candidates first and "matched but not
    CLI-ranked" candidates last, without silently losing any match. This is
    the least-surprising choice: ``ranked=True`` never returns fewer
    candidates than ``ranked=False`` would for the same domain.
    """
    if candidates is None:
        candidates = [load_registered_solver(s) for s in get_registered_solvers()]
        candidates = [
            c for c in candidates if c is not None
        ]  # filter out None entries (failed loadings)
    matches = []
    for solver_type in candidates:
        if solver_type.check_domain(domain):
            matches.append(solver_type)

    if not ranked:
        return matches

    top, rest = _prefilter_top_for_ranking(matches) if matches else ([], [])
    ranked_via_cli = _rank_via_cmca_rank_cli(top) if top else []
    if ranked_via_cli is not None:
        ranked_via_cli.sort(key=lambda pair: pair[1], reverse=True)
        if rest:
            # Synthetic scores strictly below every real share so `rest`
            # always sorts after the real-ranked candidates, while
            # preserving `rest`'s own original match order among itself.
            min_share = min(score for _, score in ranked_via_cli)
            floor = min_share - 1.0
            tail = [(solver_type, floor - i) for i, solver_type in enumerate(rest)]
            return ranked_via_cli + tail
        return ranked_via_cli

    # Graceful fallback: preserve existing match order, pairing each solver
    # with its (1-based) rank position as an int score (an int is trivially
    # compatible with the declared list[tuple[type[Solver], float]] slot).
    return [(solver_type, i) for i, solver_type in enumerate(matches, start=1)]


class ReplayOutOfActionMethod(Enum):
    LOOP = "loop"
    LAST = "last"
    ERROR = "error"


class ReplaySolver(DeterministicPolicies):
    """Wrapper around a list of actions mimicking a computed policy.

    The goal is to be able to replay a rollout from a previous episode.

    # Attributes
    actions: list of actions to wrap
    out_of_action_method: method to use when we run out of actions
      - LOOP: we loop on actions, beginning back with the first action,
      - LAST: we keep returning the last action,
      - ERROR: we raise a RuntimeError.

    # Example
    ```python
    # rollout with actual solver
    episodes = rollout(
        domain,
        solver,
        return_episodes=True
    )
    # take the first episode
    observations, actions, values = episodes[0]
    # wrap the corresponding actions in a replay solver
    replay_solver = ReplaySolver(actions)
    # replay the rollout
    replayed_episodes = rollout(
        domain=domain,
        solver=replay_solver,
        return_episodes=True
    )
    # same outputs (for deterministic domain)
    assert episodes == replayed_episodes
    ```

    """

    def __init__(
        self,
        actions: list[D.T_agent[D.T_concurrency[D.T_event]]],
        out_of_action_method: ReplayOutOfActionMethod = ReplayOutOfActionMethod.LAST,
    ):
        self.actions = actions
        self.out_of_action_method = out_of_action_method
        self._i_action = 0

    @autocastable
    def reset(self) -> None:
        self._i_action = 0

    def _is_policy_defined_for(self, observation: D.T_agent[D.T_observation]) -> bool:
        return True

    def _get_next_action(
        self, observation: D.T_agent[D.T_observation], domain: Optional[Domain] = None
    ) -> D.T_agent[D.T_concurrency[D.T_event]]:
        if self._i_action >= len(self.actions):
            if self.out_of_action_method == ReplayOutOfActionMethod.LOOP:
                self._i_action = 0
            elif self.out_of_action_method == ReplayOutOfActionMethod.LAST:
                self._i_action = len(self.actions) - 1
            else:
                raise RuntimeError(
                    "You require more actions than available in the registered plan!"
                )

        action = self.actions[self._i_action]
        self._i_action += 1
        return action


def rollout(
    domain: Domain,
    solver: Optional[Policies] = None,
    from_memory: Optional[D.T_memory[D.T_state]] = None,
    from_action: Optional[D.T_agent[D.T_concurrency[D.T_event]]] = None,
    num_episodes: int = 1,
    max_steps: Optional[int] = None,
    render: bool = True,
    max_framerate: Optional[float] = None,
    verbose: bool = True,
    action_formatter: Optional[Callable[[D.T_event], str]] = lambda a: str(a),
    outcome_formatter: Optional[Callable[[EnvironmentOutcome], str]] = lambda o: str(o),
    observation_formatter: Optional[Callable[[D.T_observation], str]] = lambda o: str(
        o
    ),
    return_episodes: bool = False,
    goal_logging_level: int = logging.INFO,
    rollout_callback: Optional[RolloutCallback] = None,
    use_applicable_actions: Optional[bool] = None,
) -> Optional[
    list[
        tuple[
            list[D.T_agent[D.T_observation]],
            list[D.T_agent[D.T_concurrency[D.T_event]]],
            list[D.T_agent[Value[D.T_value]]],
        ]
    ]
]:
    """This method will run one or more episodes in a domain according to the policy of a solver.

    # Parameters
    domain: The domain in which the episode(s) will be run.
    solver: The solver whose policy will select actions to take (if None, a random policy is used).
    from_memory: The memory or state to consider as rollout starting point (if None, the domain is reset first).
    from_action: The last applied action when from_memory is used (if necessary for initial observation computation).
    num_episodes: The number of episodes to run.
    max_steps: The maximum number of steps for each episode (if None, no limit is set).
    render: Whether to render the episode(s) during rollout if the domain is renderable.
    max_framerate: The maximum number of steps/renders per second (if None, steps/renders are never slowed down).
    verbose: Whether to print information to the console during rollout.
    action_formatter: The function transforming actions in the string to print (if None, no print).
    outcome_formatter: The function transforming EnvironmentOutcome objects in the string to print (if None, no print).
    observation_formatter: The function transforming Observation objects in the string to print (if None, no print).
    return_episodes: if True, return the list of episodes, each episode as a tuple of observations, actions, and values.
        else return nothing.
    goal_logging_level: logging level at which we want to display if goal has been reached or not

    """
    previous_log_level = logger.level
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug(
            "Logger is in verbose mode: all debug messages will be there for you to enjoy （〜^∇^ )〜"
        )

    if rollout_callback is None:
        rollout_callback = RolloutCallback()

    if solver is None:
        # Create solver-like random walker that works for any domain
        class RandomWalk(Policies):
            T_domain = Domain

            @autocastable
            def sample_action(
                self,
                observation: D.T_agent[D.T_observation],
                domain: Optional[Domain] = None,
            ) -> D.T_agent[D.T_concurrency[D.T_event]]:
                get_applicable_actions = autocast(
                    domain.get_applicable_actions, domain, self.T_domain
                )
                return {
                    agent: [space.sample()]
                    for agent, space in get_applicable_actions().items()
                }

            @autocastable
            def is_policy_defined_for(
                self, observation: D.T_agent[D.T_observation]
            ) -> bool:
                return True

        solver = RandomWalk()
        autocast_all(solver, solver.T_domain, domain)

    episodes: list[
        tuple[
            list[D.T_agent[D.T_observation]],
            list[D.T_agent[D.T_concurrency[D.T_event]]],
            list[D.T_agent[Value[D.T_value]]],
        ]
    ] = []

    if num_episodes > 1 and from_memory is None and not hasattr(domain, "reset"):
        raise ValueError(
            "If from_memory is not specified and domain has no reset() method, "
            "num_episodes should be equal to 1."
        )

    rollout_callback.at_rollout_start()

    has_render = isinstance(domain, Renderable)
    has_goal = isinstance(domain, Goals)
    has_memory = not isinstance(domain, Markovian)
    for i_episode in range(num_episodes):
        rollout_callback.at_episode_start()

        # Initialize episode
        if isinstance(solver, Solver):
            solver.reset()
        if from_memory is None:
            if isinstance(domain, Initializable):
                observation = domain.reset()
            else:
                raise ValueError(
                    "The domain must be initializable if from_memory is None."
                )
        else:
            if hasattr(domain, "set_memory"):
                domain.set_memory(from_memory)
                last_state = from_memory[-1] if has_memory else from_memory
                observation = domain.get_observation_distribution(
                    last_state, from_action
                ).sample()
            else:
                raise ValueError(
                    "from_memory must be None if domain has no set_memory() method."
                )
        if observation_formatter is not None:
            logger.debug(f"Episode {i_episode + 1} started with following observation:")
            logger.debug(observation_formatter(observation))
        else:
            logger.debug(f"Episode {i_episode + 1} starting")
        # Run episode
        step = 1

        observations: list[D.T_agent[D.T_observation]] = []
        actions: list[D.T_agent[D.T_concurrency[D.T_event]]] = []
        values: list[D.T_agent[Value[D.T_value]]] = []
        # save the initial observation
        observations.append(observation)

        while max_steps is None or step <= max_steps:
            old_time = time.perf_counter()
            if render and has_render:
                domain.render()
            action = solver.sample_action(observation, domain=domain)
            if action_formatter is not None:
                logger.debug("Action: {}".format(action_formatter(action)))
            outcome = domain.step(action)
            observation = outcome.observation
            if return_episodes:
                observations.append(observation)
                actions.append(action)
                values.append(outcome.value)
            if outcome_formatter is not None:
                logger.debug("Result: {}".format(outcome_formatter(outcome)))
            termination = (
                outcome.termination
                if domain.T_agent == Union
                else all(t for a, t in outcome.termination.items())
            )
            if termination:
                logger.debug(
                    f"Episode {i_episode + 1} terminated after {step + 1} steps."
                )
                break
            # user callback -> stopping?
            stopping = rollout_callback.at_episode_step(
                i_episode=i_episode,
                step=step,
                domain=domain,
                solver=solver,
                action=action,
                outcome=outcome,
            )
            if stopping:
                break
            if max_framerate is not None:
                wait = 1 / max_framerate - (time.perf_counter() - old_time)
                if wait > 0:
                    time.sleep(wait)
            step += 1

        if render and has_render:
            domain.render()
        if has_goal:
            logger.log(
                goal_logging_level,
                f"The goal was{'' if domain.is_goal(observation) else ' not'} reached "
                f"in episode {i_episode + 1}.",
            )
        if return_episodes:
            episodes.append((observations, actions, values))
        rollout_callback.at_episode_end()
    rollout_callback.at_rollout_end()
    if verbose:
        logger.setLevel(previous_log_level)
    if return_episodes:
        return episodes


class RolloutCallback:
    """Callback used during rollout to add custom behaviour.

    One should derives from this one in order to hook in different stages of the rollout.

    """

    def at_rollout_start(self):
        """Called at rollout start."""
        ...

    def at_rollout_end(self):
        """Called at rollout end."""
        ...

    def at_episode_start(self):
        """Called before each episode."""
        ...

    def at_episode_end(self):
        """Called after each episode."""
        ...

    def at_episode_step(
        self,
        i_episode: int,
        step: int,
        domain: Domain,
        solver: Union[Solver, Policies],
        action: D.T_agent[D.T_concurrency[D.T_event]],
        outcome: EnvironmentOutcome[
            D.T_agent[D.T_observation],
            D.T_agent[Value[D.T_value]],
            D.T_agent[D.T_predicate],
            D.T_agent[D.T_info],
        ],
    ) -> bool:
        """

        # Parameters
        i_episode: current episode number
        step: current step number within the episode
        domain: domain considered
        solver: solver considered (or randomwalk policy if solver was None in rollout)
        action: last action sampled
        outcome: outcome of the last action applied to the domain

        # Returns
        stopping: if True, the rollout for the current episode stops and the next episode starts.

        """
        return False
