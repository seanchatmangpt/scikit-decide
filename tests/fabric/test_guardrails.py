from autofde_lab.fabric.guardrails import GuardrailStanding, guarded_candidate


class ProviderA:
    def propose(self, observation):
        return {"answer": observation["x"] + 1, "tool": "lookup"}


class ProviderB:
    def propose(self, observation):
        return {"answer": observation["x"] + 1, "tool": "lookup"}


def test_provider_identity_is_not_part_of_candidate_correctness():
    kwargs = dict(
        input_guards=(lambda row: isinstance(row.get("x"), int),),
        output_guards=(lambda row: row.get("answer") == 2,),
        allowed_tools=frozenset({"lookup"}),
    )
    assert (
        guarded_candidate(ProviderA(), {"x": 1}, **kwargs).candidate
        == guarded_candidate(ProviderB(), {"x": 1}, **kwargs).candidate
    )


def test_input_output_and_tool_refusals_are_distinct():
    assert (
        guarded_candidate(
            ProviderA(),
            {"x": "bad"},
            input_guards=(lambda row: isinstance(row.get("x"), int),),
        ).standing
        is GuardrailStanding.REFUSED_INPUT
    )
    assert (
        guarded_candidate(
            ProviderA(), {"x": 1}, output_guards=(lambda row: row.get("answer") == 99,)
        ).standing
        is GuardrailStanding.REFUSED_OUTPUT
    )
    assert (
        guarded_candidate(ProviderA(), {"x": 1}).standing
        is GuardrailStanding.REFUSED_TOOL
    )


def test_passing_guardrails_still_produce_candidate_not_authority():
    decision = guarded_candidate(
        ProviderA(), {"x": 1}, allowed_tools=frozenset({"lookup"})
    )
    assert decision.standing is GuardrailStanding.CANDIDATE
    assert "no execution authority" in decision.reason
