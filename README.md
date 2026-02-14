<div align="center">
  <img src="SponsorStream%20MCP.png" alt="SponsorStream Logo">

  <p>
    <strong>Contextual Campaign Matching for the Agentic Web</strong>
  </p>

  <p>
    <a href="https://python.org">
      <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
    </a>
    <a href="./LICENSE">
      <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
    </a>
    <img src="https://img.shields.io/badge/Surface-Engine%20%2F%20Studio-blueviolet" alt="Engine/Studio">
    <img src="https://img.shields.io/badge/MCP-Compatible-orange" alt="MCP Compatible">
  </p>

  <p align="center">
    🐦 <a href="https://x.com/mr19042000">Follow Updates</a> •
    📧 <a href="mailto:ritesh19@bu.edu?subject=SponsorStream">Contact & Feedback</a>
  </p>

  <p>
    <a href="https://buymeacoffee.com/ritesh.rana" target="_blank">
      <img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="35">
    </a>
  </p>
</div>
<br/>

**SponsorStream** is a semantic sponsorship engine for LLM agents. It injects contextual campaign creatives into AI interactions using meaning-based matching, not brittle keyword rules.

## Overview

SponsorStream embeds conversational context locally (FastEmbed), queries Qdrant for candidate creatives, then applies typed targeting, policy gating, scheduling, and pacing. The MCP surface is intentionally small and safe.

Key highlights:
- **Engine/Studio split**: Engine is read-only for agent runtime; Studio handles provisioning and ingestion.
- **Campaign + Creative model**: one campaign, many creatives, shared targeting/policy/schedule.
- **Scheduling & pacing**: start/end windows plus adaptive pacing from real-time analytics.
- **SQLite analytics**: fast local reporting, campaign summaries, pacing inputs.

## Prerequisites

- Python 3.10
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [Qdrant](https://qdrant.tech/) running locally

## Install

```bash
# uv (recommended)
uv sync

# pip (editable for development)
pip install -e .

# or standard install
pip install .
```

## Quickstart

```bash
# 1) Start Qdrant
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant

# 2) Create collection
uv run sponsorstream-cli create

# 3) Seed sample campaigns
uv run sponsorstream-cli seed

# 4) Start Engine (LLM-facing)
uv run sponsorstream-engine

# 5) Start Studio (admin)
uv run sponsorstream-studio

# 6) View analytics
uv run sponsorstream-cli report --since-hours 24
```

Sample campaigns are in `data/test_ads.json` (campaign/creative schema). Re-running `seed` upserts.

## Architecture

| Surface | Purpose | Who calls it | Entrypoint |
|---------|---------|-------------|------------|
| **Engine** | Matching, read-only retrieval | LLMs / agents | `uv run sponsorstream-engine` |
| **Studio** | Provisioning, ingestion, admin ops | Humans, CI/CD | `uv run sponsorstream-studio` or `uv run sponsorstream-cli` |

### Engine tools (LLM-facing)

- `campaigns_match` — semantic matching (context_text, constraints, top_k); returns candidates + match_id
- `campaigns_explain` — audit trace for a prior match
- `campaigns_health` — liveness/readiness
- `campaigns_capabilities` — placements, constraints, embedding model, schema version

### Studio tools (admin)

- `collection_ensure` — create/align collection
- `collection_info` — collection metadata
- `collection_migrate` — optional schema migrations
- `campaigns_upsert_batch` — batch campaign/creative ingestion
- `creatives_delete` — delete a creative
- `campaigns_bulk_disable` — disable creatives by filter
- `creatives_get` — fetch a creative
- `campaigns_report` — analytics summary or campaign report

## Campaign Schema (excerpt)

```json
{
  "campaign_id": "camp-001",
  "advertiser_id": "adv-tech",
  "name": "Python Mastery",
  "creatives": [
    {
      "creative_id": "cr-001-a",
      "title": "Learn Python Today",
      "body": "Master Python programming...",
      "cta_text": "Start Learning",
      "landing_url": "https://example.com/python"
    }
  ],
  "targeting": {
    "topics": ["python", "education"],
    "locale": ["en-US"],
    "audience_segments": ["developers"],
    "keywords": ["python", "ai"]
  },
  "policy": {
    "sensitive": false,
    "age_restricted": false,
    "brand_safety_tier": "high"
  },
  "schedule": {
    "start_at": "2024-01-01T00:00:00+00:00",
    "end_at": "2030-01-01T00:00:00+00:00"
  },
  "budget": {
    "daily_budget": 50.0,
    "total_budget": 1000.0,
    "pacing_mode": "adaptive",
    "cpm": 12.0,
    "target_ctr": 0.1
  }
}
```

## Configuration

Environment variables (or `.env`) validated at startup:

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `localhost` | Qdrant server host |
| `QDRANT_PORT` | `6333` | Qdrant server port |
| `QDRANT_COLLECTION_NAME` | `ads` | Collection name |
| `EMBEDDING_MODEL_ID` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `EMBEDDING_DIMENSION` | `384` | Vector dimension |
| `CREATIVE_ID_NAMESPACE` | `a1b2...` | UUID namespace for creative IDs |
| `MAX_TOP_K` | `100` | Max results per match query |
| `MAX_BATCH_SIZE` | `500` | Max creatives per upsert batch |
| `REQUEST_TIMEOUT_SECONDS` | `30.0` | Per-request timeout |
| `REQUIRE_ENGINE_KEY` | `false` | Require `MCP_ENGINE_KEY` |
| `REQUIRE_STUDIO_KEY` | `false` | Require `MCP_STUDIO_KEY` |
| `ANALYTICS_DB_PATH` | `data/analytics.db` | SQLite analytics path |

## Validation

```bash
uv run pytest tests/ -v
```

Verify tool allowlists:

```bash
uv run python -c "
from sponsorstream.interface.mcp.server import create_server
from sponsorstream.interface.mcp.tools import ENGINE_ALLOWED_TOOLS
s = create_server('engine')
tools = set(s._tool_manager._tools.keys())
assert tools == ENGINE_ALLOWED_TOOLS
print('Engine tool allowlist OK')
"
```

## Usage Example

```python
from sponsorstream.domain.sponsorship import Campaign, CreativeSpec
from sponsorstream.models.mcp_requests import MatchRequest
from sponsorstream.wiring import build_index_service, build_match_service

campaign = Campaign(
    campaign_id="camp-001",
    advertiser_id="adv-1",
    name="Python Mastery",
    creatives=[
        CreativeSpec(
            creative_id="cr-001-a",
            title="Learn Python Today",
            body="Master Python programming...",
            cta_text="Start",
            landing_url="https://example.com/python",
        )
    ],
)

index_svc = build_index_service()
index_svc.ensure_collection()
index_svc.upsert_campaigns([campaign])

match_svc = build_match_service()
resp, trace = match_svc.match(MatchRequest(context_text="python tutorial", top_k=3))
print(resp.model_dump_json(indent=2))
```
## Contact

If you are building MCP tooling or agent monetization stacks, feel free to reach out:

- 🐦 https://x.com/mr19042000
- 📧 mailto:ritesh19@bu.edu

### 5. Verify config loads and validates

```bash
# Defaults
uv run python -c "
from sponsorstream_mcp.config import get_settings
s = get_settings()
print(f'host={s.qdrant_host} port={s.qdrant_port} model={s.embedding_model_id}')
"

# Invalid port fails fast
QDRANT_PORT=99999 uv run python -c "from sponsorstream_mcp.config.runtime import RuntimeSettings; RuntimeSettings()" 2>&1 | head -3
```

### 6. Verify import isolation (Data Plane does not load admin code)

```bash
uv run python -c "
import sys
from sponsorstream_mcp.main_runtime import main
mods = [m for m in sys.modules if m.startswith('sponsorstream_mcp')]
assert 'sponsorstream_mcp.cli' not in mods, 'FAIL: cli imported'
print('PASS: main_runtime has clean import graph (no admin modules)')
"
```

### Add Dependencies

```bash
uv add <package-name>           # Add a dependency
uv add --dev <package-name>     # Add a dev dependency
```

## Ad Schema

Each ad stored in Qdrant contains:

| Field | Type | Description |
|-------|------|-------------|
| `ad_id` | string | Unique identifier for the ad |
| `advertiser_id` | string | Identifier for the advertiser |
| `title` | string | Ad headline |
| `body` | string | Ad body text |
| `cta_text` | string | Call-to-action text |
| `landing_url` | string | Redirect URL |
| `targeting.topics` | string[] | Topics to target |
| `targeting.locale` | string[] | Locale codes (e.g., "en-US") |
| `targeting.verticals` | string[] | Industry verticals |
| `targeting.blocked_keywords` | string[] | Keywords to exclude |
| `policy.sensitive` | boolean | Sensitive content flag |
| `policy.age_restricted` | boolean | Age restriction flag |
| `enabled` | boolean | Whether the ad is eligible for matching (default `true`; `ads_bulk_disable` sets `false`) |

**Embedding text**: The vector embedding is generated from `title + body + topics`.

## Usage Example

```python
from sponsorstream_mcp.models import Ad, AdTargeting, AdPolicy
from sponsorstream_mcp.wiring import build_index_service, build_match_service
from sponsorstream_mcp.models.mcp_requests import MatchRequest

# Create the collection (once) and seed ads via IndexService
index_svc = build_index_service()
index_svc.ensure_collection()
ad = Ad(
    ad_id="ad-001",
    advertiser_id="adv-123",
    title="Learn Python Today",
    body="Master Python programming with our interactive courses.",
    cta_text="Start Learning",
    landing_url="https://example.com/python",
    targeting=AdTargeting(
        topics=["programming", "python", "education"],
        locale=["en-US"],
        verticals=["education", "technology"],
    ),
    policy=AdPolicy(sensitive=False, age_restricted=False),
)
index_svc.upsert_ads([ad])

# Match ads via MatchService (Data Plane logic)
match_svc = build_match_service()
response, audit_trace = match_svc.match(
    MatchRequest(context_text="python tutorial", top_k=5)
)
for c in response.candidates:
    print(f"{c.ad_id}: {c.title} (score={c.score}, match_id={c.match_id})")
```

## `ads_match` request / response schemas

The Data Plane `ads_match` tool uses typed DTOs — no raw dict filters are accepted.

### Request parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `context_text` | string (1-10000 chars) | *required* | Conversational / page context to match against |
| `top_k` | int (1-100) | `5` | Number of candidates to return |
| `placement` | string | `"inline"` | Placement slot (e.g. `inline`, `sidebar`, `banner`) |
| `surface` | string | `"chat"` | Surface type (e.g. `chat`, `search`, `feed`) |
| `topics` | string[] \| null | `null` | Restrict to these topics |
| `locale` | string \| null | `null` | Required locale (e.g. `en-US`) |
| `verticals` | string[] \| null | `null` | Restrict to these verticals |
| `exclude_advertiser_ids` | string[] \| null | `null` | Advertiser IDs to exclude |
| `exclude_ad_ids` | string[] \| null | `null` | Ad IDs to exclude |
| `age_restricted_ok` | bool | `false` | Allow age-restricted ads |
| `sensitive_ok` | bool | `false` | Allow sensitive-content ads |

### Response shape

```json
{
  "candidates": [
    {
      "ad_id": "ad-001",
      "advertiser_id": "adv-123",
      "title": "Learn Python Today",
      "body": "Master Python programming...",
      "cta_text": "Start Learning",
      "landing_url": "https://example.com/python",
      "score": 0.95,
      "match_id": "m-abc123"
    }
  ],
  "request_id": "req-xyz-456",
  "placement": "sidebar"
}
```

- `match_id` can be passed to `ads_explain` for audit traces (why eligible/ineligible, filters, scores)
- `score` is cosine similarity (0-1)


## Talk to me

I’m always up for nerding out about MCP tooling, retrieval systems, and practical LLM monetization.  
If you’re building something similar—or want to pressure-test your architecture—reach out:

- 🐦 Twitter: https://x.com/mr19042000  
- 📧 Email: mailto:ritesh19@bu.edu?subject=SponsorStream-MCP
