# ADR-004: Explainable Rule-Based Planner vs Black-Box Machine Learning

**Status:** Accepted  
**Date:** October 24, 2026  
**Deciders:** ZCF Core Engineering Team  

## Context
Compatibility selection must be trustworthy, deterministic, and auditable. When an application fails to run, developers and users need to know exactly *why* a specific runner or configuration was chosen, what requirements were satisfied, and what dependencies were missing.

Using an opaque machine learning model or generic LLM heuristic for core runtime selection introduces hallucinations, nondeterminism, and unverifiable decisions.

## Decision
ZCF implements a **Transparent, Explainable Rule-Based Constraint Satisfaction Engine** for its Compatibility Planner:
1. Hard constraints (ISA matching, OS API matching, mandatory binary architectures) are evaluated first as filter predicates.
2. Soft constraints (performance preferences, driver capabilities, graphics acceleration) are scored with explicit weights.
3. Every recommendation returns an explainable trace:
   - `selected_runtime`: The recommended adapter.
   - `candidate_evaluations`: List of all evaluated runtimes with pass/fail reasons.
   - `satisfied_requirements`: Explicit list of validated prerequisites.
   - `missing_requirements`: Explicit list of unsatisfied prerequisites.
   - `confidence_score`: Normalized metric between 0.0 and 1.0 reflecting empirical certainty.

## Consequences
- Total determinism and zero hallucination risk.
- High speed and instant evaluation with zero network or GPU compute overhead.
- Clear, actionable remediation advice surfaced directly to the user or agent.
