; Real, minimal STRIPS domain modeling the cross-repo engineering work
; needed to close the four gaps named in the 2026-08-10 review of
; ~/ggen-marketplace and ~/wasm4pm (see docs/planning/fortune5-k8s-state-space/ROADMAP.md
; for the full citation trail). This is a CANDIDATE PLAN input, per CLAUDE.md's
; "It computes candidate plans. It does not actuate." -- nothing in this file
; performs any of the named engineering work; it only lets a real, registered
; solver (Astar, per tests/domains/python/test_pddl_domain.py's own pattern)
; compute a real, dependency-respecting task order.
;
; Modeled directly on src/autofde_lab/planning/tests/fixtures/blocks-domain.pddl's
; shape: zero-arity predicates (no ?x parameters needed -- each artifact is its
; own named fact), one :action per real task with a typed precondition/effect.
(define (domain fortune5-k8s-state-space)
  (:requirements :strips)
  (:predicates
    (has-typed-k8s-ontology)
    (has-schema-to-ontology-generator)
    (has-nested-pydantic-support)
    (has-k8s-pack-ggen)
    (has-indexed-blackboard)
    (has-scalable-blackboard)
    (has-k8s-state-encoder)
    (has-fortune5-state-space-model))

  ; Target: a typed, hierarchical k8s object schema (CRD-aware). Review
  ; finding: neither repo has this today.
  (:action build-typed-k8s-object-schema
    :parameters ()
    :precondition ()
    :effect (has-typed-k8s-ontology))

  ; Target: ~/ggen-marketplace -- a schema-to-ontology generator. Review
  ; finding 2: no such generator exists in the 94-pack marketplace; the one
  ; placeholder (autofde-semantic-registry-pack's k8s-openapi catalog entry)
  ; has every status field marked NotRetrieved/NotGenerated.
  (:action build-schema-to-ontology-generator
    :parameters ()
    :precondition ()
    :effect (has-schema-to-ontology-generator))

  ; Target: ~/ggen-marketplace, packs/dspy-pack/gates/010_admission.rq:28-31 --
  ; the gate that explicitly caps PydanticModel fields to one flat level
  ; ("nested PydanticModel-in-PydanticModel fields are out of scope for this
  ; round"). This action represents loosening that specific, named gate.
  (:action loosen-dspy-pack-nesting-gate
    :parameters ()
    :precondition ()
    :effect (has-nested-pydantic-support))

  ; Target: ~/ggen-marketplace -- author a real k8s-pack, which needs both the
  ; generator (to avoid hand-authoring hundreds of signatures) and the loosened
  ; nesting gate (to represent a Node's labels/taints/conditions faithfully).
  (:action author-k8s-pack
    :parameters ()
    :precondition (and (has-schema-to-ontology-generator) (has-nested-pydantic-support))
    :effect (has-k8s-pack-ggen))

  ; Target: ~/wasm4pm, crates/wasm4pm-cognition/src/breeds/hearsay.rs -- replace
  ; the current O(rules) linear KS-trigger scan with a real index, keyed by the
  ; typed k8s ontology so trigger-matching stops being an unindexed string scan.
  (:action index-hearsay-blackboard
    :parameters ()
    :precondition (has-typed-k8s-ontology)
    :effect (has-indexed-blackboard))

  ; Target: ~/wasm4pm, hearsay.rs's `firing_cap = rules.len() * 8` -- a formula
  ; sized for the 13-rule 1980 speech-recognition fixture, not a
  ; thousands-of-resources cluster. Requires the indexed blackboard first (no
  ; point rescaling a firing budget over an unindexed structure).
  (:action rescale-firing-budget
    :parameters ()
    :precondition (has-indexed-blackboard)
    :effect (has-scalable-blackboard))

  ; Target: ~/wasm4pm-dspy, orchestrator.py -- the generic k8s-state-to-facts
  ; encoder its own docstring explicitly declined to build ("there is no
  ; lossless shared representation"). Needs both the typed ontology (to know
  ; what a fact IS) and the scaled blackboard (to know where facts go).
  (:action build-k8s-state-encoder
    :parameters ()
    :precondition (and (has-typed-k8s-ontology) (has-scalable-blackboard))
    :effect (has-k8s-state-encoder))

  ; Target: autofde-lab itself -- wire SreTroubleshootingPipeline's
  ; system_context/observed_resource_state inputs
  ; (src/autofde_lab/reasoning/sre_troubleshooting_pipeline.py, this session's
  ; own new pipeline) to the real encoder, and the reasoning vocabulary to the
  ; real k8s-pack. This is the one action this repo could plausibly execute
  ; itself, once its two prerequisites exist elsewhere.
  (:action integrate-with-autofde-cognition
    :parameters ()
    :precondition (and (has-k8s-state-encoder) (has-k8s-pack-ggen))
    :effect (has-fortune5-state-space-model)))
