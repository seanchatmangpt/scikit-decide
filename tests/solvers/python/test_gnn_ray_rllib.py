import logging
import os

# Disable ray's "uv run" runtime-env auto-detection *before* ray is imported/used.
# When the test suite is launched via `uv run pytest ...`, newer ray versions
# (see ray._private.worker._maybe_modify_runtime_env and
# ray._private.runtime_env.uv_runtime_env_hook.hook) auto-detect that the
# driver process was started by `uv run` and try to replicate that uv context
# on remote workers. Part of that replication validates that the project's
# pyproject.toml lives inside the runtime env's `working_dir`. We intentionally
# set `working_dir` to this test file's own directory below (so that ray
# workers can unpickle/import the GraphMaze domain classes defined in this
# module) which is a *subdirectory* of the repo root containing pyproject.toml,
# so that validation always fails with:
#   RuntimeError: Your <repo>/pyproject.toml is not in the working_dir
#   <repo>/tests/solvers/python, so the workers will not have access to the file.
# This is not a real problem here: these tests spawn local worker processes on
# the same machine, using the same already-active venv/interpreter as the
# driver -- there is no separate `uv run`-launched cluster environment that
# actually needs to be replicated. `RAY_ENABLE_UV_RUN_RUNTIME_ENV` is ray's own
# documented flag (see ray._private.ray_constants.RAY_ENABLE_UV_RUN_RUNTIME_ENV)
# for turning this uv auto-detection off; disabling it here restores the
# regular runtime_env behavior (our explicit `working_dir` below is honored
# as-is, with no pyproject.toml/uv-specific validation).
os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")

import ray
from pytest_cases import fixture

from autofde_lab.hub.solver.ray_rllib import RayRLlib
from autofde_lab.hub.solver.ray_rllib.gnn.algorithms import GraphPPO
from autofde_lab.utils import rollout


@fixture
def ray_init():
    # add module test_gnn_ray_rllib and thus GraphMaze to ray runtimeenv
    ray.init(
        ignore_reinit_error=True,
        runtime_env={"working_dir": os.path.dirname(__file__)},
        # local_mode=True,  # uncomment this line and comment the one above to debug more easily
    )


@fixture
def graphppo_config():
    return (
        GraphPPO.get_default_config()
        # This solver's GNN rollout/action-masking code (GraphRolloutWorker,
        # Graph2NodeRolloutWorker, Policy-based custom models) is written
        # against RLlib's old API stack. Ray made the new API stack the
        # default from 2.40 onward. RayRLlib.__init__ only forces the old
        # stack when it builds its *own* default config (see comment there);
        # since this fixture builds and passes an explicit `config=...`, it
        # must opt into the old stack itself, or actor creation crashes with
        # `TypeError: cannot unpack non-iterable NoneType object` deep in
        # Policy.exploration.get_exploration_action (an old-stack API that
        # doesn't get populated under the new stack).
        .api_stack(
            enable_rl_module_and_learner=False,
            enable_env_runner_and_connector_v2=False,
        )
        # set num of CPU<1 to avoid hanging for ever in github actions on macos 11
        .resources(
            num_cpus_per_worker=0.5,
        )
        # small number to increase speed of the unit test
        .training(train_batch_size=256)
    )


def test_ppo(unmasked_graph_domain_factory, graphppo_config, ray_init):
    domain_factory = unmasked_graph_domain_factory
    solver_kwargs = dict(algo_class=GraphPPO, train_iterations=1)
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert not solver._action_masking and solver._is_graph_obs
        solver.solve()
        rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )


def test_ppo_user_gnn(
    unmasked_jsp_domain_factory,
    my_gnn_class,
    my_gnn_kwargs,
    graphppo_config,
    ray_init,
    caplog,
):
    domain_factory = unmasked_jsp_domain_factory
    gnn_out_dim = 64
    gnn_class = my_gnn_class
    gnn_kwargs = my_gnn_kwargs(gnn_out_dim=gnn_out_dim)

    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_feature_extractors_kwargs=dict(
            gnn_class=gnn_class,
            gnn_kwargs=gnn_kwargs,
            gnn_out_dim=gnn_out_dim,
            features_dim=64,
        ),
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        with caplog.at_level(logging.WARNING):
            solver.solve()
        rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )

    assert gnn_class(in_channels=1, **gnn_kwargs).warning() in caplog.text


def test_ppo_user_reduction_layer(
    unmasked_jsp_domain_factory,
    my_reduction_layer_class,
    my_reduction_layer_kwargs,
    graphppo_config,
    ray_init,
    caplog,
):
    domain_factory = unmasked_jsp_domain_factory
    gnn_out_dim = 128
    features_dim = 64
    reduction_layer_class = my_reduction_layer_class
    reduction_layer_kwargs = my_reduction_layer_kwargs(
        gnn_out_dim=gnn_out_dim,
        features_dim=features_dim,
    )
    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_feature_extractors_kwargs=dict(
            gnn_out_dim=gnn_out_dim,
            features_dim=features_dim,
            reduction_layer_class=reduction_layer_class,
            reduction_layer_kwargs=reduction_layer_kwargs,
        ),
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        with caplog.at_level(logging.WARNING):
            solver.solve()
        rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )

    assert reduction_layer_class(**reduction_layer_kwargs).warning() in caplog.text


def test_dict_ppo(unmasked_jsp_dict_domain_factory, graphppo_config, ray_init):
    domain_factory = unmasked_jsp_dict_domain_factory
    solver_kwargs = dict(algo_class=GraphPPO, train_iterations=1)
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert not solver._action_masking and solver._is_graph_multiinput_obs
        solver.solve()
        rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )


def test_ppo_masked(graph_domain_factory, graphppo_config, ray_init):
    domain_factory = graph_domain_factory
    solver_kwargs = dict(algo_class=GraphPPO, train_iterations=1)
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert solver._action_masking and solver._is_graph_obs
        solver.solve()
        episodes = rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
            return_episodes=True,
        )
    if "Jsp" in domain_factory().__class__.__name__:
        # with masking only 9 steps necessary since only 9 tasks to perform
        observations, actions, values = episodes[0]
        assert len(actions) == 9


def test_dict_ppo_masked(jsp_dict_domain_factory, graphppo_config, ray_init):
    domain_factory = jsp_dict_domain_factory
    solver_kwargs = dict(algo_class=GraphPPO, train_iterations=1)
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert solver._action_masking and solver._is_graph_multiinput_obs
        solver.solve()
        episodes = rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
            return_episodes=True,
        )
    # with masking only 9 steps necessary since only 9 tasks to perform
    observations, actions, values = episodes[0]
    assert len(actions) == 9


def test_ppo_masked_user_gnn(
    jsp_domain_factory,
    my_gnn_class,
    my_gnn_kwargs,
    graphppo_config,
    ray_init,
    caplog,
):
    domain_factory = jsp_domain_factory
    gnn_out_dim = 64
    gnn_class = my_gnn_class
    gnn_kwargs = my_gnn_kwargs(gnn_out_dim=gnn_out_dim)

    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_feature_extractors_kwargs=dict(
            gnn_class=gnn_class,
            gnn_kwargs=gnn_kwargs,
            gnn_out_dim=gnn_out_dim,
            features_dim=64,
        ),
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert solver._action_masking and solver._is_graph_obs
        with caplog.at_level(logging.WARNING):
            solver.solve()
    assert gnn_class(in_channels=1, **gnn_kwargs).warning() in caplog.text


def test_dict_ppo_masked_user_gnn(
    jsp_dict_domain_factory,
    my_gnn_class,
    my_gnn_kwargs,
    graphppo_config,
    ray_init,
    caplog,
):
    domain_factory = jsp_dict_domain_factory
    gnn_out_dim = 64
    gnn_class = my_gnn_class
    gnn_kwargs = my_gnn_kwargs(gnn_out_dim=gnn_out_dim)

    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_feature_extractors_kwargs=dict(
            gnn_class=gnn_class,
            gnn_kwargs=gnn_kwargs,
            gnn_out_dim=gnn_out_dim,
            features_dim=64,
        ),
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert solver._action_masking and solver._is_graph_multiinput_obs
        with caplog.at_level(logging.WARNING):
            solver.solve()
    assert gnn_class(in_channels=1, **gnn_kwargs).warning() in caplog.text


def test_graph2node_ppo(
    unmasked_jsp_domain_factory,
    graphppo_config,
    ray_init,
):
    domain_factory = unmasked_jsp_domain_factory
    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_node_action=True,
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert (
            not solver._action_masking and solver._is_graph_obs and solver._graph2node
        )
        solver.solve()
        rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
        )


def test_maskable_graph2node_ppo(
    jsp_graph2node_domain_factory,
    graphppo_config,
    ray_init,
):
    domain_factory = jsp_graph2node_domain_factory
    solver_kwargs = dict(
        algo_class=GraphPPO,
        train_iterations=1,
        graph_node_action=True,
    )
    with RayRLlib(
        domain_factory=domain_factory, config=graphppo_config, **solver_kwargs
    ) as solver:
        assert solver._action_masking and solver._is_graph_obs and solver._graph2node
        solver.solve()
        episodes = rollout(
            domain=domain_factory(),
            solver=solver,
            max_steps=30,
            num_episodes=1,
            render=False,
            return_episodes=True,
        )
    # with masking only 9 steps necessary since only 9 tasks to perform
    observations, actions, values = episodes[0]
    assert len(actions) == 9
