# Browser Automation Layering

Cognix browser automation is split into three layers so product UX stays simple while the runtime remains explicit and auditable.

## 1. Browser MCP Runtime

The Browser MCP Runtime is an internal execution backend. It is not exposed as ordinary user configuration.

Supported engines:

- `playwright`: deterministic isolated browser execution.
- `cdp`: attach to an existing Chromium session for user-owned login state.
- `browser_use`: agentic multi-step navigation when deterministic selectors are insufficient.

Canonical runtime actions:

- `browser.goto`
- `browser.observe`
- `browser.click`
- `browser.fill`
- `browser.select`
- `browser.wait`
- `browser.download`
- `browser.extract_table`
- `browser.screenshot`

The runtime maps these stable Cognix action names to concrete Playwright MCP tools, CDP calls, or browser-use instructions. All browser runs must pass workspace policy checks, approval gates, and artifact persistence.

## 2. Browser Automation Skill

`browser_automation` is a generic planning skill, not an executor.

It defines:

- Compliance confirmation requirements.
- Login/session strategy.
- Collection strategy and route priority.
- Artifact output contract.
- Error recovery strategy.
- Planner hints for when to route work to the internal runtime.

The skill should tell Planner when to pause for authorization, when to reuse CDP/session state, and how to structure output. It should not click, scrape, download, or run Playwright itself.

## 3. Domain Skills

Domain skills encode reusable SOPs for specific systems or workflows. They should be promoted into the local Skill Hub when a workflow repeats.

Example: `life_partner_coupon_codes`

It defines:

- System entry path: Life Partner/LinKe coupon data page.
- Menu path: `生财有数 / 券码数据`.
- Filter strategy: default date field `支付时间`, date range semantics such as `昨天`.
- Field strategy: select all visible/custom fields, with fallback canonical fields.
- Export priority: official export, browser download, table extraction, page observation.
- Result artifact schema: records, field definitions, source attribution, limitations, and recovery notes.

## Planner Rule

For browser tasks, Planner should prefer this order:

1. Match a domain skill for business SOP.
2. Use `browser_automation` to validate approval, login, collection, artifact, and recovery contracts.
3. Route execution to Browser MCP Runtime using `browser_run`.
4. Persist results as Artifacts. Do not let the LLM respond with "switch to a browser environment" when runtime setup is missing; return a recoverable runtime error artifact instead.
