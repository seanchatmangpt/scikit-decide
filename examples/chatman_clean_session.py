"""Plan and execute a Clean-Session task with scikit-decide semantics."""

from autofde_lab.hub.domain.chatman_clean_session import (
    ActuationIntent,
    BrokerReceipt,
    ChatmanCleanSessionDomain,
    RouteOutcome,
    RouteSpec,
    TaskEnvelope,
    execute_actions,
)


class ExampleBRCEBroker:
    def actuate(self, intent: ActuationIntent) -> BrokerReceipt:
        # Replace this body with the ecosystem BRCE client. The adapter requires
        # the returned receipt to bind the exact intent identity.
        return BrokerReceipt.issue(
            intent,
            standing="ALIVE",
            consequence={"executed": True, "route": intent.route},
        )


task = TaskEnvelope(
    repo="seanchatmangpt/scikit-decide",
    base="<exact-sha>",
    task="execute the admitted repository task",
    acceptance="repository-native behavioral proof",
    constraints=("zero unreceipted actuation",),
    authority="authorized repository installation",
)

domain = ChatmanCleanSessionDomain(
    task,
    routes=(
        RouteSpec(
            "local_checkout",
            cost=1.0,
            outcome=RouteOutcome.BLOCKED,
            reason="checkout absent",
        ),
        RouteSpec("github_object_graph", cost=2.0, outcome=RouteOutcome.SUCCESS),
    ),
)

plan = domain.canonical_completion_plan()
receipt = execute_actions(domain, plan, ExampleBRCEBroker())
print(receipt.receipt_id, receipt.standing)
