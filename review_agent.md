Below is a tight, review-oriented RAG corpus and a retrieval strategy that works well for “what should I say in this PR review?” style agents.

1. Core sources (small, high-leverage)

If you ingest only one “stack”, make it this:

A. Architecture & patterns (for structural review comments)

Architecture Patterns with Python (Cosmic Python)
Use it as your north star for:

service layers

domain vs infrastructure separation

repositories

unit of work

dependency inversion in Python

Why it’s excellent for reviews

It answers “is this code shaped correctly?”

It gives language your agent can reuse:

“This logic belongs in the domain, not the adapter…”
“This dependency direction makes testing harder…”

How to ingest

Chunk by chapter section (e.g. “Service Layer”, “Repository Pattern”)

Add tags like:

topic=architecture
concern=dependency-direction
concern=testability

B. Testing fundamentals (for correctness + maintainability)

pytest docs (especially “How-to” + “Explanation”)
Focus on:

fixtures (scope, autouse, composition)

parametrization

monkeypatch vs mocks

tmp_path / tmp_path_factory

marks

Why
Most review comments fall into:

“this test is brittle”

“this fixture is doing too much”

“this should be parametrized”

“this should not hit the network/fs”

pytest docs give canonical phrasing and examples.

Chunking advice

One chunk per concept, not per page

Keep examples with explanation

Tag aggressively:

topic=testing
technique=fixtures
smell=overspecified-test
smell=slow-test

C. Mocking & boundaries (for “don’t test internals” feedback)

unittest.mock docs
Even if you write pytest, mocking vocabulary comes from here:

patch vs patch.object

autospec

call assertions

where to patch (import location!)

Why
Agents need to explain why a mock is wrong, not just that it is.

Add tags like:

topic=testing
technique=mocking
smell=testing-implementation-details

D. Property-based testing (for “missing cases” reviews)

Hypothesis docs
You don’t need everything — ingest:

the introduction

common strategies

stateful testing overview

Why
This lets your agent say:

“This logic has a large input space; consider a property-based test instead of examples.”

That’s a high-seniority review comment.

E. Typing & API boundaries (for design-level reviews)

typing docs + mypy docs
Focus on:

Protocol

TypedDict

structural subtyping

gradual typing philosophy

Why
Typing guidance dramatically improves review quality:

“This argument should be a Protocol”

“This return type leaks implementation details”

“This union hides an invariant”

2. What I would NOT ingest (or only lightly)

For a review agent, these add little signal:

Large pattern catalogs with Java-style implementations

Generic “clean code” blogs (too opinionated, too vague)

Full CI tooling docs (tox/nox) unless the agent reviews CI configs

If you include them, mark them low priority in metadata.

3. Review-focused retrieval strategy (important)

Instead of a single vector search, use intent routing.

Step 1: classify the review concern

Have the agent internally label the issue as one of:

architecture

test-design

test-speed

mocking

typing

readability

coupling

Step 2: restrict retrieval by metadata

Example:

{
  "topic": "testing",
  "smell": "testing-implementation-details"
}


This prevents the agent from pulling irrelevant pattern docs when reviewing a flaky test.

4. Canonical “review heuristics” to seed manually (high ROI)

I strongly recommend adding a small, hand-written document (2–4 pages) with rules like:

“Tests should assert behavior, not calls”

“If you need to patch more than one thing, reconsider the design”

“Domain code should not import infrastructure”

“If a fixture returns multiple responsibilities, split it”

“Prefer Protocols at boundaries, concrete types internally”

Tag this as:

source=internal
authority=high
purpose=review-guidelines


Your agent will naturally quote or paraphrase these during reviews.

5. Example review comment your agent should be able to generate

With this corpus, your agent should confidently produce comments like:

“This test mocks three internal methods of the same class, which tightly couples it to the implementation. Consider extracting the side-effecting behavior behind a boundary and testing the observable behavior instead (pytest + unittest.mock guidance).”

If it can’t say that yet, the RAG needs tightening — not expansion.
