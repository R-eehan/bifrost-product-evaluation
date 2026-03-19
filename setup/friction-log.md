# Friction Log — Session 1 (2026-03-18/19)

**Evaluator**: Reehan Ahmed
**Bifrost version**: v1.4.14  
**Environment**: macOS, zsh, Claude Code with OAuth (Pro/Max), NPX install
**Session scope**: Initial research → first-run setup → Bifrost CLI → Claude Code routing

---

## F1: Maxim Platform Signup Requires Work Email

**When**: Attempting to sign up for Maxim's free Developer tier to explore the eval/observability dashboard
**Expected**: Sign up with personal Google/GitHub account like most dev tools (Braintrust, Langfuse, Helicone all allow personal emails)
**Actual**: Signup requires a work email. Google/GitHub auth options exist but must be connected to a work account.
**Friction level**: High
**Would the CTO already know this?**: Likely a deliberate sales/lead-gen decision, not an oversight.

**Why it matters for the product**:
This is a funnel leak at the most critical conversion moment. Bifrost's entire strategy is land-and-expand: developer adopts free OSS gateway → explores Maxim platform → upgrades to paid. But the exact person Bifrost acquires (solo developer, nights-and-weekends evaluator, indie hacker) gets stopped at the conversion step. The gateway-to-platform handoff requires a work email that many early adopters don't have or don't want to use.

**Competitive context**: Braintrust, Langfuse, Helicone, and Arize/Phoenix all allow personal email signups for their free tiers.

**Recommendation angle**: Gateway → platform conversion funnel friction. The work email requirement filters for enterprise leads but blocks the developer-led adoption that the OSS gateway is designed to drive. Consider allowing personal email for the free Developer tier (10K logs, 3-day retention — low risk of abuse) while gating Professional+ tiers on work email.

---

## F2: No Web UI Method for Enabling the Maxim Plugin

**When**: Trying to connect Bifrost to the Maxim dashboard for trace forwarding
**Expected**: Toggle a plugin on/off in the Web UI, paste API key and log repo ID
**Actual**: Docs only show config.json and Go SDK methods for enabling the Maxim plugin. No Web UI toggle documented. No API endpoint for adding/updating plugins (only GET /api/plugins for listing).
**Friction level**: High
**Would the CTO already know this?**: Yes — this is likely a known doc/UI gap.

**Why it matters for the product**:
A developer who set up Bifrost via the Web UI (the recommended first-run path) now has to switch to file-based config to enable the one plugin that connects Bifrost to Maxim's paid platform. The conversion moment (free gateway → paid observability) requires a config mode switch that is confusing and poorly documented. This is the second funnel leak in the gateway → platform path.

**Research backing**: GitHub issues confirm no POST/PUT endpoint for plugins. The Web UI may have an undocumented Plugins section, but it's not covered in docs.

**Recommendation angle**: The Maxim plugin is the single most important plugin for Maxim's business — it's the bridge from free to paid. It should be the easiest thing to enable, not the hardest.

---

## F3: Config Mode Confusion — Web UI vs File-Based Are Mutually Exclusive

**When**: After setting up providers via Web UI, trying to add the Maxim plugin via config.json
**Expected**: Edit config.json, restart Bifrost, plugin loads
**Actual**: When config_store is enabled (default for Web UI mode), config.json edits are ignored. Must either: (a) delete config.db, edit config.json, restart — losing Web UI config, or (b) use HTTP API — but no plugin creation endpoint exists.
**Friction level**: High
**Would the CTO already know this?**: Yes — documented as a known behavior, but the friction of switching modes is not acknowledged.

**Why it matters for the product**:
This creates a "config trap" — the recommended first-run path (Web UI) puts you in a mode that blocks the most important next step (enabling the Maxim plugin via config file). A developer who followed the happy path now has to understand an undocumented infrastructure decision to proceed.

**Research backing**: Bifrost docs note that "once config_store is enabled, modifying config.json has no effect" but don't explain how to handle the transition or when you'd need to.

**Recommendation angle**: Either add plugin management to the Web UI (preferred — keeps the config mode consistent) or document the config_store → file-based migration path prominently with a "if you set up via Web UI and now need to add plugins, here's what to do" guide.

---

## F4: No End-to-End Tutorial for Bifrost + Maxim Integration

**When**: Trying to get traces from Bifrost into the Maxim dashboard
**Expected**: A single walkthrough: "install Bifrost → configure provider → enable Maxim plugin → see traces in dashboard"
**Actual**: Bifrost setup docs and Maxim plugin docs are separate pages with no cross-linking. Maxim-side steps (creating a log repository, finding workspace ID) are undocumented for the UI. The first-request quickstart page returned a 404.
**Friction level**: Medium-High
**Would the CTO already know this?**: The doc gap is likely known; the 404 may not be.

**Why it matters for the product**:
The Bifrost → Maxim connection is the business model. A developer who can't figure out how to see their Bifrost traces in Maxim will never become a paying customer. This should be the most polished documentation path in the entire product, not a gap.

**Research backing**: Quickstart page for first-request returned 404. Maxim log repository creation via UI is undocumented. WorkspaceId location is not explained.

**Recommendation angle**: Create a single "Bifrost → Maxim in 5 Minutes" golden path tutorial that covers both sides end-to-end. This is the conversion tutorial — it should exist before any other doc.

---

## F5: Bifrost CLI Doesn't Pick Up Env Vars Without Full Terminal Restart

**When**: Added ANTHROPIC_BASE_URL to ~/.zshrc, sourced the file, launched Bifrost CLI
**Expected**: Bifrost CLI picks up the new env var after `source ~/.zshrc`
**Actual**: Had to quit the terminal session entirely and restart for the CLI to recognize the updated env var. Only then did logs start flowing.
**Friction level**: Medium
**Would the CTO already know this?**: This is standard macOS/zsh behavior, not a Bifrost bug.

**Why it matters for the product**:
While not a Bifrost-specific bug, it's a first-run DX friction that's invisible to the team (who already have their environments configured). For a developer setting up Bifrost for the first time, "I set the env var, sourced my shell, but nothing works" → "I need to fully restart my terminal" is a 15-30 minute debugging detour. A single line in the docs ("Note: restart your terminal after adding env vars, or export them directly in your current session") would save significant frustration.

**Recommendation angle**: Minor doc improvement — add a callout box to the Claude Code integration page about terminal restart requirement.

---

## F6: 500 Errors and Timeouts on Long Claude Code Sessions

**When**: Running extended, complex Claude Code sessions routed through Bifrost
**Expected**: Stable proxying for sessions of any duration
**Actual**: HTTP 500 errors, automatic timeouts, difficult to troubleshoot. Sessions that work fine when short break during longer, tool-heavy interactions.
**Friction level**: Critical
**Would the CTO already know this?**: Yes — three related open issues exist.

**Root causes (from GitHub)**:

- **Issue #828** (open since Nov 2025, 5 months): Goroutine leaks on context cancellation. Workers never monitor ctx.Done(), so goroutines block indefinitely during streaming. They accumulate over long sessions → resource exhaustion → 500s.
- **Issue #1157** (open): I/O timeouts during streaming. Default `default_request_timeout_in_seconds` is 30s — far too low for Claude Code sessions with 2-5 minute tool-use chains.
- **Issue #1406** (open): Even when callers set longer timeouts, Bifrost's 30s default overrides them. Can't be fully fixed until #828 is resolved.

**Why it matters for the product**:
This is the single most important finding. Bifrost positions itself as agent infrastructure — "launch any coding agent through Bifrost." But the default configuration breaks on the exact use case being marketed. A 30-second timeout on a product designed for agentic coding sessions (which routinely run multi-minute tool chains) is a fundamental mismatch between the product's positioning and its defaults. The goroutine leak (#828) has been open for 5 months — this isn't an edge case, it's a core reliability issue for the primary use case.

**Competitive context**: This is unique to Bifrost's architecture — competitors like Portkey (SaaS) and Helicone handle long-lived connections differently.

**Recommendation angle**: This is the strongest recommendation in the evaluation. Frame as: "Your agent infrastructure story is bottlenecked by your own defaults." Two immediate actions: (1) increase default timeout to 300s+ for the Anthropic provider (or auto-detect agentic patterns), (2) prioritize the goroutine leak fix (#828) — it's been open 5 months and directly undermines the CLI's value proposition.

---

## F7: Bifrost CLI Cannot Pass Custom Flags to Claude Code

**When**: Launching Claude Code through Bifrost CLI, needing --dangerously-skip-permissions
**Expected**: A way to pass Claude Code flags (--dangerously-skip-permissions, --model, etc.) through the Bifrost CLI config or command line
**Actual**: Bifrost CLI config (~/.bifrost/config.json) supports only 3 fields: base_url, default_harness, default_model. No flag passthrough mechanism. The only Claude Code-specific flag supported is -worktree. Exiting the Claude Code session to re-enter with the flag also exits Bifrost CLI, breaking log capture.
**Friction level**: Medium-High
**Would the CTO already know this?**: Possibly not — no GitHub issues requesting this feature were found. May be the first time this is surfaced.

**Why it matters for the product**:
If Bifrost CLI is the enterprise governance wrapper for coding agents, it must respect the configuration of the tools it governs. Most developers run Claude Code with --dangerously-skip-permissions (otherwise every bash call, web search, and file read requires manual approval — unusable for real work). An enterprise platform team rolling out Bifrost CLI to 20 developers can't tell them "you lose your preferred Claude Code configuration." This is a governance tool that doesn't respect the tool it's governing.

**Workaround**: Skip Bifrost CLI entirely. Set ANTHROPIC_BASE_URL manually, launch `claude --dangerously-skip-permissions` directly. Bifrost gateway still captures traffic via the env var. But this defeats the CLI's session management value.

**Recommendation angle**: Add an `agent_flags` or `extra_args` field to the Bifrost CLI config, or support `--` separator for passthrough args. This is a table-stakes feature for enterprise adoption of the CLI — without it, power users bypass the CLI entirely, undermining its governance purpose.

---

## F8: OAuth Token Handling Has Known Bugs

**When**: Using Claude Code with OAuth (Pro/Max) login routed through Bifrost via ANTHROPIC_BASE_URL
**Expected**: Bifrost correctly forwards the OAuth bearer token to Anthropic's API
**Actual**: Bifrost has had persistent bugs with OAuth token handling. Issue #1551: OAuth token placed in wrong header (X-Api-Key instead of Authorization: Bearer). Partially fixed in v1.4.5-1.4.6 but still broken for /v1/messages/count_tokens. One user removed Bifrost from their architecture because of this. Full OAuth support (PR #1984) is still open/unmerged.
**Friction level**: High
**Would the CTO already know this?**: Yes — multiple issues exist and a PR is in progress.

**Why it matters for the product**:
Claude Code's most common auth method for individual developers is OAuth (Pro/Max subscription). If Bifrost can't reliably handle OAuth tokens, it can't serve as the gateway for the majority of Claude Code users. This directly blocks the Bifrost CLI's primary use case. The fact that a user "removed Bifrost from their architecture" because of this (issue #1551) is a churn data point.

**Recommendation angle**: PR #1984 (full OAuth support) should be prioritized — it's the auth method most individual developers use. The current partial fix creates a worse experience than no fix (works sometimes, fails unpredictably).

---

## Summary: Friction → Recommendation Mapping


| #   | Friction                                       | Severity    | Recommendation Theme             |
| --- | ---------------------------------------------- | ----------- | -------------------------------- |
| F1  | Work email signup blocks developer conversion  | High        | Gateway → platform funnel        |
| F2  | No Web UI for Maxim plugin                     | High        | Gateway → platform funnel        |
| F3  | Config mode trap (Web UI vs file-based)        | High        | Developer experience             |
| F4  | No end-to-end Bifrost → Maxim tutorial         | Medium-High | Gateway → platform funnel        |
| F5  | Env var not picked up without terminal restart | Medium      | Documentation                    |
| F6  | 500 errors + timeouts on long sessions         | Critical    | Agent infrastructure reliability |
| F7  | CLI can't pass custom agent flags              | Medium-High | Enterprise governance            |
| F8  | OAuth token handling bugs                      | High        | Agent infrastructure reliability |


**Recommendation clusters:**

1. **"Agent infrastructure that breaks on agents"** (F6, F8): Default timeouts + goroutine leaks + OAuth bugs = the primary use case (coding agents) is unreliable. This is the highest-priority product issue.
2. **"The conversion funnel has three leaks"** (F1, F2, F3, F4): Work email → config mode trap → no plugin UI → no tutorial. Each step from free gateway to paid platform has friction. Fix the golden path.
3. **"Governance tool that doesn't respect its tools"** (F7): CLI can't pass agent flags. Enterprise adoption requires respecting agent configuration.

