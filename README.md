# Bifrost Product Evaluation

A hands-on evaluation of [Bifrost](https://getbifrost.ai), Maxim AI's open-source LLM and MCP gateway.

I evaluated Bifrost through two lenses. First, as an AI gateway: routing, observability, developer experience. Second, through an enterprise business case: can a design leader use Bifrost's MCP gateway to evaluate the cost of rolling out Paper.design to their team?

The gateway works. The cost question is unanswerable.

**[Read the full evaluation →](https://r-eehan.github.io/bifrost-product-evaluation/)**

**[See the MCP Cost Attribution prototype →](https://r-eehan.github.io/bifrost-product-evaluation/prototype-mcp-cost-attribution-v2.html)**

## Key findings

1. **MCP cost attribution is unsolved.** No MCP gateway (Bifrost, Portkey, or LiteLLM) connects tool calls to the LLM cost they trigger. LiteLLM offers manual per-tool cost assignment. Automated attribution based on actual token spend doesn't exist yet. Bifrost's schema has a foreign key designed for this correlation, but it was never populated.

2. **Agent reliability has gaps on agentic workloads.** Default 30s timeout and goroutine leaks break extended coding sessions. The CLI can't pass agent flags. These aren't edge cases. They're the primary use case.

3. **Conversion funnel works but has discoverability friction.** Work email signup blocks developer-led adoption. Plugins vs Connectors page split confuses first-time users.

## Repository structure

```
docs/           Evaluation write-up (GitHub Pages) + MCP cost attribution prototype
tests/          Test scripts (routing, observability, MCP) + results
config/         Bifrost configuration used during testing
```

## Running the tests

Requires Bifrost running at `localhost:8080` with OpenAI and Anthropic API keys configured. Python 3.11+ via conda.

```bash
conda create -n bifrost-eval python=3.11 -y
conda run -n bifrost-eval pip install -r requirements.txt
cp .env.example .env

conda run -n bifrost-eval python tests/test_routing.py
conda run -n bifrost-eval python tests/test_observability.py
conda run -n bifrost-eval python tests/test_mcp.py
```

## How this was built

Test scripts, research, GitHub issue analysis, and computational work were done in collaboration with [Claude Code](https://claude.ai/claude-code). Evaluation design, business case framing, product analysis, and prioritization were done by me. The evaluation itself was run through Bifrost, making this a case of using AI tools to evaluate AI infrastructure.

## Version tested

Bifrost v1.4.14 via `npx -y @maximhq/bifrost` · Python 3.11 · OpenAI SDK · Paper.design v0.1.10 (19 tools)

## Author

**Reehan Ahmed** · [LinkedIn](https://linkedin.com/in/r-eehan) · [GitHub](https://github.com/R-eehan)
