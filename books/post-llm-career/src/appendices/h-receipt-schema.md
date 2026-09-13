# Appendix H. Agent-System and Career Receipt Schema

A receipt binds an action or artifact to its exact subject, admitted observations, authority, execution, result, and replay path.

This appendix provides a general schema. Adapt it to the consequence of the domain.

## Minimal receipt

```yaml
receipt_version: "1.0"
receipt_id: "unique-id"
created_at: "ISO-8601 timestamp"

subject:
  kind: "project | workflow | account | document | role-campaign"
  id: "exact identifier"
  revision: "version, commit, or state identifier"

objective:
  statement: "bounded intended outcome"
  acceptance:
    - "observable criterion"

observation:
  sources:
    - id: "source identifier"
      observed_at: "timestamp"
      hash: "optional content hash"
  admission:
    status: "ADMITTED | PARTIAL | REFUSED"
    rationale: "why these observations apply"

construction:
  actor: "human, model, agent, planner, or tool identity"
  artifact: "artifact identifier"
  method: "module, command, or workflow"

validation:
  checks:
    - name: "check name"
      command: "exact command if applicable"
      exit: 0
      result: "PASS | FAIL | PARTIAL"
  limitations:
    - "boundary of evidence"

authority:
  requester: "identity and role"
  approver: "identity and role"
  scope: "permitted subject/action"
  policy: "policy identifier"

actuation:
  broker: "authorized execution path"
  action: "external state change"
  executed_at: "timestamp"
  result: "observed result"

replay:
  prerequisites:
    - "dependency"
  fixture: "fixture identifier"
  command: "exact replay command"
  expected: "expected replay result"

standing:
  status: "UNKNOWN | PARTIAL_ALIVE | ALIVE | BLOCKED | BUILD_BROKEN | UNSUPPORTED"
  applies_to: "exact subject and environment"
  falsifiers:
    - "condition that would invalidate standing"
```

## Receipt principles

### Exact subject

“Project works” is not a subject. Name the repository, revision, configuration, environment, workflow, or customer segment.

### Admitted observation

Record why the inputs are applicable and current enough. Raw context is not automatically evidence.

### Separation of construction and actuation

A model or agent may construct a candidate without possessing permission to change external state.

### Proportionate evidence

A low-consequence draft may need a lightweight receipt. A production or regulated action needs stronger identity, policy, validation, and replay.

### Negative standing

A receipt can validly establish `BLOCKED`, `UNSUPPORTED`, or a typed refusal. Failure evidence prevents repeated false attempts.

## Career-campaign receipt

```yaml
subject:
  kind: "career-campaign"
  id: "agentic-architect-2026-q3"
  revision: "week-04"

objective:
  statement: "Create five qualified employer conversations"
  acceptance:
    - "Conversation includes a buyer, recruiter, or technical sponsor"
    - "The contact accurately understands the proposed role"

observation:
  sources:
    - id: "linkedin-analytics-export"
    - id: "conversation-ledger"
    - id: "evidence-index"

construction:
  actor: "Sean + editorial agent workflow"
  artifact: "six-post challenger arc"

validation:
  checks:
    - name: "role classification test"
      result: "PASS"
    - name: "proof links resolve"
      result: "PASS"

authority:
  requester: "Sean, career owner"
  approver: "Sean"
  scope: "public posts and individually approved outreach"

actuation:
  action: "Published posts and sent approved messages"
  result: "7 qualified conversations; 2 portfolio reviews"

standing:
  status: "ALIVE"
  applies_to: "campaign week 1–4 and stated audience"
  falsifiers:
    - "contacts did not understand role"
    - "conversations were not employer relevant"
```

## Repository proof receipt

```yaml
subject:
  kind: "repository"
  id: "owner/repo"
  revision: "exact commit SHA"

objective:
  statement: "Demonstrate bounded behavior"
  acceptance:
    - "documented command exits 0"
    - "negative fixture is refused"

observation:
  sources:
    - id: "exact checked-out tree"
  admission:
    status: "ADMITTED"
    rationale: "tree identity verified against commit"

validation:
  checks:
    - name: "narrow verifier"
      command: "make verify-feature"
      exit: 0
      result: "PASS"
    - name: "integration test"
      command: "pytest tests/integration/test_feature.py"
      exit: 0
      result: "PASS"

standing:
  status: "ALIVE"
  applies_to: "exact SHA, operating system, and configuration"
  falsifiers:
    - "dependency identity changes"
    - "test is not executed against the exact subject"
```

## Content receipt

A public post can have a receipt too.

Record:

- source and creator;
- observation date;
- quoted or summarized claim;
- your inference;
- evidence boundary;
- related proof;
- publication URL;
- correction history;
- qualified conversion.

This makes public teaching a learning system rather than an ephemeral feed.

## Receipt review

Before using a receipt as proof, ask:

1. Does the identity match the claim?
2. Was the action actually executed?
3. Does the validator test the target behavior?
4. Was authority present?
5. Are limitations visible?
6. Can another person replay or inspect it?
7. Has the environment changed?

A named file called `receipt.json` is not automatically a receipt. Correspondence creates standing.
