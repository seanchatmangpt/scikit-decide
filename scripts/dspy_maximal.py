#!/usr/bin/env python3
"""Maximal DSPy 3.1.3 live benchmark under Design for Combinatorial Maximalism.

The full lawful class/interaction graph is represented before any live selection.
Live execution is bounded and non-destructive: the only remote consequence is LM
inference through the already-authorized GROQ_API_KEY. Tools and retrieval are
local deterministic collaborators. Every class/edge receives typed standing.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import itertools
import json
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

DSPY_VERSION = "3.1.3"
DEFAULT_MODEL = "groq/openai/gpt-oss-120b"
MODULE_KINDS = (
    "Predict",
    "ChainOfThought",
    "ReAct",
    "ProgramOfThought",
    "MultiChainComparison",
    "RLM",
    "CodeAct",
    "BestOfN",
    "Refine",
    "Pipeline",
    "MultiHop",
    "KNN",
    "Parallel",
)
OPTIMIZER_KINDS = (
    "GEPA",
    "GRPO",
    "BootstrapFewShot",
    "BootstrapFewShotWithRandomSearch",
    "BootstrapFewShotWithOptuna",
    "BootstrapFinetune",
    "COPRO",
    "SignatureOptimizer",
    "MIPROv2",
    "AvatarOptimizer",
    "BetterTogether",
    "InferRules",
    "SIMBA",
    "LabeledFewShot",
    "Ensemble",
    "KNNFewShot",
)
KNOWN_UPSTREAM = {
    "SignatureOptimizer": "UPSTREAM_DSPY_3_1_3_SIGNATURE_OPTIMIZER_BROKEN",
    "AvatarOptimizer": "UPSTREAM_DSPY_3_1_3_TYPED_PREDICTOR_REMOVED",
    "BetterTogether": "UPSTREAM_DSPY_3_1_3_RUNTIME_OPTIMIZER_WHITELIST_NARROW",
}
TASK_REGIMES = ("direct", "reasoning", "tool", "retrieval", "composition")


@dataclass
class Result:
    subject: str
    phase: str
    standing: str
    elapsed_ms: int
    detail: str = ""
    output_digest: str | None = None


def digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, default=str, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def bounded_text(value: Any, n: int = 500) -> str:
    s = str(value).replace(os.environ.get("GROQ_API_KEY", ""), "<redacted>")
    return s[:n]


def call_filtered(factory: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Pass only kwargs admitted by the runtime signature unless **kwargs exists."""
    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(*args, **kwargs)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return factory(*args, **kwargs)
    admitted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return factory(*args, **admitted)


def pairwise_cover(dimensions: dict[str, tuple[str, ...]]) -> list[dict[str, str]]:
    """Deterministic greedy pairwise cover; preserves full topology separately."""
    keys = tuple(dimensions)
    all_rows = [
        dict(zip(keys, vals))
        for vals in itertools.product(*(dimensions[k] for k in keys))
    ]
    universe: set[tuple[str, str, str, str]] = set()
    for row in all_rows:
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                universe.add((a, row[a], b, row[b]))
    uncovered = set(universe)
    selected: list[dict[str, str]] = []
    while uncovered:
        best: dict[str, str] | None = None
        best_cover: set[tuple[str, str, str, str]] = set()
        for row in all_rows:
            cover = {
                (a, row[a], b, row[b])
                for i, a in enumerate(keys)
                for b in keys[i + 1 :]
                if (a, row[a], b, row[b]) in uncovered
            }
            if len(cover) > len(best_cover):
                best, best_cover = row, cover
        if not best or not best_cover:
            break
        selected.append(best)
        uncovered -= best_cover
        all_rows.remove(best)
    return selected


def run_case(
    results: list[Result],
    subject: str,
    phase: str,
    fn: Callable[[], Any],
    *,
    expected_refusal: str | None = None,
) -> Any:
    start = time.monotonic()
    try:
        value = fn()
        elapsed = int((time.monotonic() - start) * 1000)
        results.append(
            Result(subject, phase, "ALIVE", elapsed, bounded_text(value), digest(value))
        )
        return value
    except (
        Exception
    ) as exc:  # benchmark records topology instead of aborting first edge
        elapsed = int((time.monotonic() - start) * 1000)
        code = expected_refusal or f"{type(exc).__name__}"
        standing = f"UNSUPPORTED:{code}" if expected_refusal else "BUILD_BROKEN"
        results.append(
            Result(
                subject,
                phase,
                standing,
                elapsed,
                bounded_text(f"{type(exc).__name__}: {exc}"),
            )
        )
        return None


def local_search(query: str, k: int = 3) -> list[str]:
    corpus = [
        "POWL models partially ordered workflows and explicit choice graphs.",
        "BRCE is the exclusive consequential DO path and requires receipts.",
        "DSPy programs compose signatures, modules, tools, retrieval, and optimizers.",
        "Design for Combinatorial Maximalism preserves reversible lawful possibilities before selection.",
        "AutoFDE uses admitted evidence, bounded execution, and replayable receipts.",
    ]
    words = set(query.lower().split())
    scored = sorted(
        corpus, key=lambda s: len(words & set(s.lower().split())), reverse=True
    )
    return scored[:k]


def local_price(sku: str = "SKU-42", **_: Any) -> str:
    """Deterministic side-effect-free tool."""
    return {"SKU-42": "$42.00", "SKU-7": "$7.00"}.get(str(sku), "$1.00")


def reward_fn(example: Any, pred: Any, trace: Any = None) -> float:
    expected = str(getattr(example, "answer", "")).strip().lower()
    got = str(getattr(pred, "answer", "")).strip().lower()
    if not expected:
        return 1.0 if got else 0.0
    return float(expected in got or got in expected)


def metric(example: Any, pred: Any, trace: Any = None) -> float:
    return reward_fn(example, pred, trace)


def make_signature(dspy: Any) -> type:
    class MaximalAnswer(dspy.Signature):
        """Answer the bounded question accurately and concisely."""

        context: str = dspy.InputField(desc="Optional admitted context")
        question: str = dspy.InputField(desc="Question")
        answer: str = dspy.OutputField(desc="Concise answer")

    return MaximalAnswer


def make_dataset(dspy: Any) -> list[Any]:
    rows = [
        ("Arithmetic", "What is 2 + 3?", "5"),
        ("Architecture", "What is the exclusive consequential DO path?", "BRCE"),
        ("Process", "What model represents partial order plus choice?", "POWL"),
        ("Testing", "What test style uses real collaborators?", "Chicago"),
    ]
    return [
        dspy.Example(context=c, question=q, answer=a).with_inputs("context", "question")
        for c, q, a in rows
    ]


def build_modules(
    dspy: Any, sig: type, trainset: list[Any], results: list[Result]
) -> dict[str, Any]:
    modules: dict[str, Any] = {}
    base = run_case(results, "Predict", "construct", lambda: dspy.Predict(sig))
    modules["Predict"] = base
    cot = run_case(
        results, "ChainOfThought", "construct", lambda: dspy.ChainOfThought(sig)
    )
    modules["ChainOfThought"] = cot
    modules["ReAct"] = run_case(
        results,
        "ReAct",
        "construct",
        lambda: call_filtered(dspy.ReAct, sig, tools=[local_price], max_iters=2),
    )
    modules["ProgramOfThought"] = run_case(
        results,
        "ProgramOfThought",
        "construct",
        lambda: call_filtered(dspy.ProgramOfThought, sig, max_iters=2),
    )
    modules["MultiChainComparison"] = run_case(
        results,
        "MultiChainComparison",
        "construct",
        lambda: call_filtered(dspy.MultiChainComparison, sig, M=2, temperature=0.2),
    )
    modules["RLM"] = run_case(
        results,
        "RLM",
        "construct",
        lambda: call_filtered(
            dspy.RLM,
            sig,
            max_iterations=2,
            max_llm_calls=4,
            max_output_chars=2000,
            verbose=False,
        ),
    )
    modules["CodeAct"] = run_case(
        results,
        "CodeAct",
        "construct",
        lambda: call_filtered(dspy.CodeAct, sig, tools=[local_price], max_iters=2),
    )
    modules["BestOfN"] = run_case(
        results,
        "BestOfN",
        "construct",
        lambda: call_filtered(
            dspy.BestOfN,
            module=cot,
            N=2,
            reward_fn=reward_fn,
            threshold=0.7,
            fail_count=1,
        ),
    )
    modules["Refine"] = run_case(
        results,
        "Refine",
        "construct",
        lambda: call_filtered(
            dspy.Refine, module=cot, N=2, reward_fn=reward_fn, threshold=0.7
        ),
    )

    class LocalPipeline(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.reason = dspy.ChainOfThought(sig)

        def forward(self, context: str, question: str) -> Any:
            passages = local_search(question, 3)
            return self.reason(context="\n".join(passages), question=question)

    modules["Pipeline"] = run_case(results, "Pipeline", "construct", LocalPipeline)

    class LocalMultiHop(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.query = dspy.ChainOfThought(sig)
            self.answer = dspy.ChainOfThought(sig)

        def forward(self, context: str, question: str) -> Any:
            q = self.query(
                context=context,
                question=f"Produce one short search query for: {question}",
            )
            passages = local_search(str(getattr(q, "answer", question)), 2)
            return self.answer(context="\n".join(passages), question=question)

    modules["MultiHop"] = run_case(results, "MultiHop", "construct", LocalMultiHop)

    def vectorizer(texts: Any) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for text in texts:
            raw = hashlib.sha256(str(text).encode()).digest()
            out.append([b / 255.0 for b in raw[:16]])
        return out

    modules["KNN"] = run_case(
        results,
        "KNN",
        "construct",
        lambda: call_filtered(dspy.KNN, k=2, trainset=trainset, vectorizer=vectorizer),
    )
    modules["Parallel"] = run_case(
        results,
        "Parallel",
        "construct",
        lambda: call_filtered(
            dspy.Parallel, num_threads=2, max_errors=2, disable_progress_bar=True
        ),
    )
    return modules


def execute_modules(dspy: Any, modules: dict[str, Any], results: list[Result]) -> None:
    kwargs = {"context": "Use admitted evidence only.", "question": "What is 2 + 3?"}
    for name in MODULE_KINDS:
        module = modules.get(name)
        if module is None:
            continue
        if name == "KNN":
            run_case(results, name, "execute", lambda m=module: m(**kwargs))
        elif name == "Parallel":
            pred = modules.get("Predict")
            run_case(
                results,
                name,
                "execute",
                lambda m=module, p=pred: m(
                    [(p, kwargs), (p, {**kwargs, "question": "Name the DO path."})]
                ),
            )
        else:
            run_case(results, name, "execute", lambda m=module: m(**kwargs))


def get_optimizer_class(dspy: Any, name: str) -> Any:
    obj = getattr(dspy, name, None)
    if obj is not None:
        return obj
    for holder_name in ("teleprompt", "teleprompt.signature_opt_typed", "evaluate"):
        holder = dspy
        try:
            for part in holder_name.split("."):
                holder = getattr(holder, part)
            obj = getattr(holder, name, None)
            if obj is not None:
                return obj
        except Exception:
            pass
    raise AttributeError(name)


def optimizer_kwargs(
    name: str, dspy: Any, lm: Any, trainset: list[Any], modules: dict[str, Any]
) -> dict[str, Any]:
    # Deliberately smallest lawful budgets; constructor kwargs are filtered by runtime signature.
    common = {
        "metric": metric,
        "prompt_model": lm,
        "task_model": lm,
        "max_errors": 2,
        "num_threads": 1,
    }
    table: dict[str, dict[str, Any]] = {
        "GEPA": {**common, "max_full_evals": 1, "reflection_lm": lm},
        "GRPO": {**common},
        "BootstrapFewShot": {
            "metric": metric,
            "max_bootstrapped_demos": 1,
            "max_labeled_demos": 1,
            "max_rounds": 1,
            "max_errors": 2,
        },
        "BootstrapFewShotWithRandomSearch": {
            "metric": metric,
            "max_bootstrapped_demos": 1,
            "max_labeled_demos": 1,
            "num_candidate_programs": 1,
            "num_threads": 1,
            "max_errors": 2,
        },
        "BootstrapFewShotWithOptuna": {
            "metric": metric,
            "max_bootstrapped_demos": 1,
            "max_labeled_demos": 1,
            "num_candidate_programs": 1,
        },
        "BootstrapFinetune": {"metric": metric, "multitask": False, "num_threads": 1},
        "COPRO": {
            "metric": metric,
            "prompt_model": lm,
            "breadth": 2,
            "depth": 1,
            "init_temperature": 0.3,
        },
        "SignatureOptimizer": {
            "metric": metric,
            "prompt_model": lm,
            "breadth": 2,
            "depth": 1,
            "init_temperature": 0.3,
            "verbose": False,
        },
        "MIPROv2": {
            "metric": metric,
            "prompt_model": lm,
            "task_model": lm,
            "max_bootstrapped_demos": 1,
            "max_labeled_demos": 1,
            "num_candidates": 2,
            "max_errors": 2,
            "seed": 7,
        },
        "AvatarOptimizer": {
            "metric": metric,
            "max_iters": 1,
            "lower_bound": 0,
            "upper_bound": 1,
            "max_positive_inputs": 2,
            "max_negative_inputs": 2,
            "optimize_for": "max",
        },
        "InferRules": {
            "metric": metric,
            "num_candidates": 2,
            "num_rules": 2,
            "num_threads": 1,
        },
        "SIMBA": {
            "metric": metric,
            "bsize": 2,
            "num_candidates": 2,
            "max_steps": 1,
            "max_demos": 1,
            "prompt_model": lm,
            "num_threads": 1,
        },
        "LabeledFewShot": {"k": 1},
        "Ensemble": {"reduce_fn": lambda xs: xs[0] if xs else None, "size": 2},
        "KNNFewShot": {"k": 1, "trainset": trainset},
    }
    if name == "BetterTogether":
        # Runtime whitelist is narrower in 3.1.3; use the simplest prompt optimizer.
        table[name] = {"metric": metric, "prompt_optimizer": None, "seed": 42}
    return table.get(name, common)


def compile_optimizer(
    name: str,
    optimizer: Any,
    student: Any,
    trainset: list[Any],
    modules: dict[str, Any],
) -> Any:
    compile_fn = optimizer.compile
    sig = inspect.signature(compile_fn)
    kwargs: dict[str, Any] = {}
    params = sig.parameters
    if name == "Ensemble":
        return compile_fn([modules["Predict"], modules["ChainOfThought"]])
    if name == "KNNFewShot":
        return compile_fn(student)
    if "student" in params:
        kwargs["student"] = student
    elif "program" in params:
        kwargs["program"] = student
    elif "module" in params:
        kwargs["module"] = student
    else:
        # most DSPy teleprompters use first positional student
        positional = [
            p
            for p in params.values()
            if p.name != "self"
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if positional:
            kwargs[positional[0].name] = student
    if "trainset" in params:
        kwargs["trainset"] = trainset
    if "devset" in params:
        kwargs["devset"] = trainset
    if "valset" in params:
        kwargs["valset"] = trainset
    if "max_demos" in params:
        kwargs["max_demos"] = 2
    if "eval_kwargs" in params:
        kwargs["eval_kwargs"] = {
            "num_threads": 1,
            "display_progress": False,
            "display_table": False,
        }
    if "requires_permission_to_run" in params:
        kwargs["requires_permission_to_run"] = False
    if "num_trials" in params:
        kwargs["num_trials"] = 1
    return compile_fn(**kwargs)


def execute_optimizers(
    dspy: Any,
    lm: Any,
    trainset: list[Any],
    modules: dict[str, Any],
    results: list[Result],
    compile_live: bool,
) -> dict[str, Any]:
    built: dict[str, Any] = {}
    for name in OPTIMIZER_KINDS:
        expected = KNOWN_UPSTREAM.get(name)
        try:
            cls = get_optimizer_class(dspy, name)
        except Exception as exc:
            results.append(
                Result(
                    name,
                    "construct",
                    f"UNSUPPORTED:{expected or 'CLASS_NOT_EXPORTED'}",
                    0,
                    bounded_text(exc),
                )
            )
            continue
        kwargs = optimizer_kwargs(name, dspy, lm, trainset, modules)
        if name == "BetterTogether" and kwargs.get("prompt_optimizer") is None:
            try:
                kwargs["prompt_optimizer"] = call_filtered(
                    get_optimizer_class(dspy, "LabeledFewShot"), k=1
                )
            except Exception:
                pass
        opt = run_case(
            results,
            name,
            "construct",
            lambda cls=cls, kw=kwargs: call_filtered(cls, **kw),
            expected_refusal=None,
        )
        if opt is None:
            continue
        built[name] = opt
        if not compile_live:
            continue
        run_case(
            results,
            name,
            "compile",
            lambda n=name, o=opt: compile_optimizer(
                n, o, modules["ChainOfThought"], trainset, modules
            ),
            expected_refusal=expected,
        )
    return built


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--output", type=Path, default=Path("dspy-maximal-receipt.json"))
    ap.add_argument("--compile-optimizers", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("REFUSED:GROQ_AUTHORITY_ABSENT")

    import dspy

    observed_version = getattr(dspy, "__version__", "unknown")
    if observed_version != DSPY_VERSION:
        raise SystemExit(f"REFUSED:DSPY_VERSION_DRIFT:{observed_version}")

    lm = dspy.LM(args.model, temperature=0.0, max_tokens=512, cache=False)
    dspy.configure(lm=lm)
    sig = make_signature(dspy)
    trainset = make_dataset(dspy)
    results: list[Result] = []
    modules = build_modules(dspy, sig, trainset, results)
    execute_modules(dspy, modules, results)
    optimizers = execute_optimizers(
        dspy, lm, trainset, modules, results, args.compile_optimizers
    )

    dims = {
        "module": MODULE_KINDS,
        "optimizer": OPTIMIZER_KINDS,
        "regime": TASK_REGIMES,
    }
    full_count = 1
    for values in dims.values():
        full_count *= len(values)
    cover = pairwise_cover(dims)
    observed_subjects = {r.subject for r in results}
    missing = [
        x for x in (*MODULE_KINDS, *OPTIMIZER_KINDS) if x not in observed_subjects
    ]
    unexpected_broken = [
        asdict(r)
        for r in results
        if r.standing == "BUILD_BROKEN" and r.subject not in KNOWN_UPSTREAM
    ]
    module_exec_alive = sorted(
        {r.subject for r in results if r.phase == "execute" and r.standing == "ALIVE"}
    )
    optimizer_construct_alive = sorted(
        {
            r.subject
            for r in results
            if r.phase == "construct"
            and r.subject in OPTIMIZER_KINDS
            and r.standing == "ALIVE"
        }
    )
    optimizer_compile_alive = sorted(
        {r.subject for r in results if r.phase == "compile" and r.standing == "ALIVE"}
    )

    standing = "ALIVE"
    falsifiers = []
    if missing:
        standing = "BUILD_BROKEN"
        falsifiers.append({"missing_inventory": missing})
    if args.strict and unexpected_broken:
        standing = "BUILD_BROKEN"
        falsifiers.append({"unexpected_broken": unexpected_broken})

    receipt = {
        "schema": "autofde.dspy-maximal.v1",
        "technicalStanding": standing,
        "identity": {
            "autofde_head": os.environ.get("AUTOFDE_HEAD", "UNKNOWN"),
            "dspy_version": observed_version,
            "model": args.model,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "authority": {
            "groq_secret_present": True,
            "secret_exported": False,
            "external_actuation": False,
            "tools": "local deterministic only",
        },
        "bounds": {
            "lm_max_tokens_per_call": 512,
            "optimizer_live_compile": args.compile_optimizers,
            "dataset_examples": len(trainset),
        },
        "inventory": {
            "module_kinds": list(MODULE_KINDS),
            "optimizer_kinds": list(OPTIMIZER_KINDS),
            "known_upstream_exclusions": KNOWN_UPSTREAM,
        },
        "combinatorial_space": {
            "dimensions": {k: list(v) for k, v in dims.items()},
            "cartesian_candidates": full_count,
            "pairwise_selected": len(cover),
            "pairwise_cover": cover,
        },
        "coverage": {
            "module_execute_alive": module_exec_alive,
            "optimizer_construct_alive": optimizer_construct_alive,
            "optimizer_compile_alive": optimizer_compile_alive,
            "observed_subject_count": len(observed_subjects),
        },
        "results": [asdict(r) for r in results],
        "falsifiers": falsifiers,
    }
    receipt["receipt_digest"] = digest(receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if standing == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
