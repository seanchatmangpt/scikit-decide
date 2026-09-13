from ray.rllib.algorithms.ppo import PPOTorchPolicy

from autofde_lab.hub.solver.ray_rllib.gnn.policy.torch_graph_policy import (
    TorchGraphPolicy,
)


class PPOTorchGraphPolicy(TorchGraphPolicy, PPOTorchPolicy): ...
