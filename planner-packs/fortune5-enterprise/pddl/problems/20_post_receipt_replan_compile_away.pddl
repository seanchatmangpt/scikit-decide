(define (problem reobserve-and-switch-planner)
  (:domain autofde-meta-planning)
  (:objects
    p01 p02 p03 p04 p05 - planner
    recover - role
    enterprise-world - world
    transition-subject - subject)
  (:init
    ;; External evidence from the preceding DO episode:
    (observation-admitted transition-subject)
    (transition-receipted transition-subject enterprise-world)
    (world-allowed enterprise-world)
    (previous-planner p01)
    (planner-available p01)
    (planner-available p02)
    (planner-available p03)
    (planner-available p04)
    (planner-available p05)
    (compatible p02 recover)
    (different-planner p01 p02))
  (:goal (and
    (planner-switched p01 p02)
    (semantic-delta-captured transition-subject)
    (ggen-projection-ready transition-subject)
    (closed-class transition-subject)))
)
