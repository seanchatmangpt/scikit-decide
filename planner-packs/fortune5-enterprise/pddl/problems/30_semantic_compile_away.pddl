(define (problem semantic-compile-away)
  (:domain autofde-meta-planning)
  (:objects
    bounded-world - world
    solved-subject - subject)
  (:init
    (observation-admitted solved-subject)
    (transition-receipted solved-subject bounded-world)
    (world-allowed bounded-world))
  (:goal (and
    (semantic-delta-captured solved-subject)
    (ggen-projection-ready solved-subject)
    (closed-class solved-subject)))
)
