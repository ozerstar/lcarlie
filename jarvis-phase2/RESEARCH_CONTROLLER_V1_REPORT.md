# RESEARCH CONTROLLER V1

## Scope

Merge-ready adaptive research control plane. It is intentionally not wired to
ExecutionRuntime and is not deployed. Data Fabric, Web Console, CodingExecutor,
Action Firewall, Context Compiler, Planner, Runtime and Adapter Factory are
unchanged.

## Existing Components Reused

- `AdapterFactory.for_capability()` for provider-neutral source discovery.
- `CapabilityAdapter` health/execute/evidence/metrics contract.
- Existing `ResearchCache` generation/TTL invalidation.
- Existing `research.SourceRecord` and `fuse()` compatibility output.
- Existing resource/concurrency policy conventions.

## Adaptive Policy

Start with two independent adapters. Stop when confidence, coverage and source
independence thresholds pass without contradiction. Otherwise add one source at
a time up to the configured cap. Syndicated copies sharing an origin/content
hash count once.

## Upstream Status

No verified SearXNG, Agent Reach, Crawl4AI or Miniflux adapter/smoke/benchmark
evidence exists in current main. They remain candidates requiring the existing
factory stages: isolated inspection, smoke, benchmark, adapter contract tests,
PROPOSED integration and human approval. No installation was attempted.

## Security

Only HTTP(S) global addresses are accepted. Credentials, localhost, private,
link-local, reserved and metadata targets are blocked after DNS resolution.
Fetched text is always untrusted data; injection markers are evidence metadata,
never instructions. No action or credential surface exists.

## Rollback

Revert the Research Controller commit. No production files, database schema,
services or runtime triggers are changed.
