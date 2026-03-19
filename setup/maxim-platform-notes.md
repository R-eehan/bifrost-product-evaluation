# Maxim Platform → Bifrost Gateway Connection Notes
**Date**: 2026-03-19
**Purpose**: Phase 0 deliverable — understanding the gateway → platform upgrade path

---

## Gateway → Platform Upgrade Path

1. **Free entry point**: Bifrost OSS gateway (npx install, localhost:8080) captures all LLM traffic automatically. Developer sees traces, token usage, cost, and latency in the built-in Web UI dashboard — no Maxim account needed. This is the hook.

2. **Conversion trigger**: When a developer needs evals, agent simulation, production monitoring, or team-level observability, the path is: enable the Maxim plugin in Bifrost → traces forward to Maxim's cloud dashboard. But this conversion moment has 3 friction points (see friction log F1-F4): work email signup, no Web UI for plugin enablement, config mode confusion, and no end-to-end tutorial.

3. **Feature boundary (OSS vs Paid)**:
   - **Free (Bifrost OSS)**: LLM routing, failover, load balancing, basic budgets, semantic caching, MCP catalog, Code Mode, local observability (SQLite + Web UI), OTEL export, Prometheus metrics
   - **Paid (Maxim platform)**: Prompt IDE, agent simulation, LLM-as-judge evaluation, production monitoring dashboards, quality/safety alerts, dataset curation, CI/CD integration
   - **Paid (Bifrost Enterprise)**: Hierarchical budgets, fine-grained RBAC, SSO (SAML/OAuth/LDAP), secret management (Vault/AWS SM), HA clustering, content safety (Bedrock Guardrails), federated MCP, user governance

4. **The upsell logic**: Bifrost captures everything → developer sees basic metrics locally → "I need historical trends / team dashboards / evals" → Maxim platform. The gateway is the acquisition channel; the platform is the revenue engine. This is the Cloudflare playbook applied to AI infrastructure.

5. **Current gap**: The bridge from "Bifrost user" to "Maxim customer" is underbuilt. Three sequential friction points (work email, config mode switch, missing tutorial) create a leaky funnel at the exact moment a developer is most likely to convert. Competitors (Helicone, Braintrust) have smoother free→paid paths.
