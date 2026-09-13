# Computer-Use Automation System - Design Report

## Architecture

The system is designed as a modular, single-process application with clear separation of concerns. The architecture follows a layered approach that enables both LLM-driven discovery and deterministic replay while maintaining clean abstraction boundaries for future scaling.

### Core Components

**Agent Orchestrator** (`src/agent/orchestrator.py`): Serves as the central coordinator for the discovery phase. It manages the observe-decide-act loop, interacts with the LLM for decision-making, and records actions for artifact generation. The orchestrator handles stopping conditions (max steps, timeout, goal completion) and coordinates with the safety and escalation layers.

**Browser Automation Layer** (`src/automation/browser.py`): Provides a unified interface for UI interaction using Playwright. This layer implements multiple element location strategies with intelligent fallbacks, prioritizing accessibility tree selectors for stability in legacy environments. The abstraction is designed to be extendable to desktop applications in the future.

**Artifact System** (`src/artifact/`): Defines the structured schema for automation capabilities and implements the deterministic replay engine. The artifact schema captures not just the sequence of actions, but the semantic intent (parameters, outputs, checkpoints) and error handling strategies. The replay engine executes artifacts without LLM involvement, using stable element targeting and comprehensive error classification.

**Safety Layer** (`src/safety/guardrails.py`): Enforces policy through allowlists for domains and action types, assesses risk levels, and handles data redaction. Safety checks are performed before each action execution, with risky actions requiring confirmation.

**Escalation Manager** (`src/safety/escalation.py`): Implements human-in-the-loop intervention with a real control transfer mechanism. It detects stuck states, requests intervention with full context, manages control state transitions, and records human actions for transparency.

### Key Architectural Decisions

**Single-process with modular design**: Chose a single-process architecture for simplicity and clarity in demonstration, but designed interfaces to support future multi-process scaling. The modular design with clear boundaries (automation, artifact, safety, escalation) ensures components can be extracted into services as needed.

**Accessibility-first element location**: Prioritized accessibility tree selectors over DOM selectors because they are more stable in legacy applications and work across desktop environments. This choice required more complex implementation but provides significantly better replay reliability.

**Surface abstraction**: The `BrowserAutomation` class abstracts the specifics of web interaction, making the system's core logic (agent loop, artifact schema, replay engine) surface-agnostic. This enables future desktop support without architectural changes.

**Error classification model**: Explicitly separated business outcomes from system failures in the result contract. This prevents conflating legitimate results (e.g., "member not found") with automation failures, a critical distinction in production banking environments.

### Trade-offs

**Complexity vs reliability**: The multiple fallback strategies for element location add implementation complexity but significantly improve replay reliability across UI changes and legacy applications.

**Mock operator console**: Implemented a minimal but real handoff mechanism with a mocked operator interface. This keeps the scope manageable while demonstrating the control transfer logic that would be needed in production.

**Heuristic parameter extraction**: Used simple heuristics for parameter and output extraction during discovery rather than sophisticated semantic analysis. This works for the demo but would need enhancement for complex real-world scenarios.

## Artifact Schema

The artifact schema is the central data model that enables deterministic replay and agent invocability. It captures both the procedural steps and the semantic contract of the automation capability.

### Schema Structure

```json
{
  "metadata": {
    "version": "1.0",
    "created_at": "ISO timestamp",
    "target_app": "application identifier",
    "capability_name": "semantic name",
    "description": "human-readable description",
    "tenant_id": "optional tenant identifier",
    "app_version": "optional app version"
  },
  "parameters": {
    "param_name": {
      "type": "string|number|boolean|array|object",
      "description": "parameter purpose",
      "required": true,
      "default": "optional default value"
    }
  },
  "outputs": {
    "output_name": {
      "type": "parameter type",
      "description": "output meaning"
    }
  },
  "steps": [
    {
      "step_id": 1,
      "action_type": "navigate|click|type|extract|wait|select",
      "target": {
        "strategy": "accessibility_role|semantic_selector|text_content|test_id|xpath|css_selector",
        "value": "selector value",
        "role": "accessibility role",
        "name": "accessibility name",
        "fallback_strategies": ["alternative strategies"]
      },
      "value": "action value (for type/navigate)",
      "output_key": "where to store extracted data",
      "description": "human-readable step description",
      "wait_after": "milliseconds to wait",
      "risk_level": "safe|reversible|risky|irreversible"
    }
  ],
  "checkpoint": {
    "step_id": "verification step",
    "condition": {
      "type": "element_visible",
      "target": "element location",
      "text_contains": "optional text validation"
    },
    "description": "what this checkpoint verifies"
  },
  "error_handlers": [
    {
      "error_type": "element_not_found|timeout|validation_error|permission_denied|unexpected_dialog|session_expired|business_outcome",
      "fallback_strategy": "alternative approach",
      "outcome": "business outcome identifier",
      "condition": {"text_contains": "match condition"},
      "description": "handler purpose"
    }
  ]
}
```

### Design Rationale

**Semantic contract over procedure**: The schema includes parameters, outputs, and descriptions alongside the procedural steps. This makes artifacts reviewable by humans and discoverable by AI agents as callable capabilities, not just opaque scripts.

**Versioning and metadata**: Artifacts include version, timestamp, and target app information. This enables evolution tracking and compatibility management across different app versions or tenant configurations.

**Multiple location strategies**: Each step includes a primary strategy and fallback alternatives. This acknowledges that legacy applications often lack stable selectors and provides resilience against UI changes.

**Explicit error handling**: Error handlers are first-class citizens in the schema, not afterthoughts. This allows the system to distinguish between recoverable conditions, business outcomes, and hard failures.

**Tenant and version support**: Optional fields for tenant_id and app_version provide hooks for multi-tenant reuse without requiring per-tenant artifact rebuilds.

### Parameter Substitution

The system supports parameter substitution in step values using `{{parameter_name}}` syntax. During replay, parameters are validated against the schema (type checking, required field validation) and substituted into action values. This enables a single artifact to handle multiple concrete cases.

## Determinism & Error Handling

Deterministic replay is achieved through stable element targeting, comprehensive error detection, and explicit outcome classification.

### Element Location Strategy

The replay engine uses a hierarchical fallback strategy for element location:

1. **Primary**: Accessibility tree selectors (role, name) - most stable for legacy apps
2. **Fallback 1**: Semantic HTML selectors - modern web apps
3. **Fallback 2**: Text content matching - when semantic structure is unreliable
4. **Fallback 3**: Test IDs - when available (rare in legacy apps)

Each step in the artifact specifies its primary strategy and fallback alternatives. The engine tries each in sequence until one succeeds, logging the successful strategy for debugging.

### Waiting and Timing

The system uses Playwright's built-in waiting mechanisms for element visibility and network stability. Additionally, steps can specify explicit wait times after execution to handle dynamic content loading. This balances responsiveness with reliability.

### Error Classification

Errors are classified into three distinct categories:

**Business outcomes**: Legitimate results that the caller needs to know about, such as "member not found" or "insufficient funds." These are not failures but expected outcomes that should be returned to the caller.

**Recoverable conditions**: Transient issues that can be handled automatically, such as unexpected dialogs, slow loads, or session timeouts. The system attempts fallback strategies or retries for these.

**Hard failures**: System errors that cannot be recovered from, such as permission denials, app crashes, or corrupted state. These stop execution and return a clear error for debugging.

### Error Handling Process

When an error occurs during replay:

1. **Error type detection**: The system analyzes the error message and context to classify it
2. **Handler matching**: Searches artifact error handlers for matching error types
3. **Fallback execution**: If a fallback strategy is defined, attempts the alternative approach
4. **Business outcome check**: If the error matches a business outcome condition, returns it as a legitimate result
5. **Failure reporting**: If unrecoverable, returns detailed error information including step number and expected vs observed state

### Checkpoint Verification

After executing all steps (or when the goal appears complete), the system verifies the checkpoint condition. This ensures the automation actually reached the expected state, not just that the actions completed without throwing errors. Checkpoints can verify element visibility, text content, or other state conditions.

### Runtime State Accommodation

The system is designed to handle the real runtime errors mentioned in the assignment:

- **Validation errors**: Detected through error message patterns and returned as business outcomes
- **Record not found**: Explicitly handled as a business outcome, not a failure
- **Permission denials**: Classified as hard failures with clear error reporting
- **Unexpected dialogs**: Handled through fallback strategies or timeout mechanisms
- **Session expiry**: Detected and classified as recoverable (would trigger re-authentication in production)
- **Transient slowness**: Handled through Playwright's automatic waiting and explicit timeouts

This approach ensures that capabilities work in production environments where the happy path is the exception rather than the rule.

## Heterogeneity & Multi-tenant

The design addresses the heterogeneous, multi-tenant environment described in the assignment through surface abstraction and artifact generalization.

### Surface Abstraction

The core system (agent loop, artifact schema, replay engine) is designed to be surface-agnostic. The current implementation uses `BrowserAutomation` for web interaction, but the interfaces are abstracted:

```python
# The interface that any surface implementation must provide
class SurfaceAutomation:
    async def start(self) -> None
    async def stop(self) -> None
    async def navigate(self, target: str) -> None
    async def find_element(self, target: TargetLocation) -> Optional[Any]
    async def execute_action(self, action_type: ActionType, target: TargetLocation, value: Optional[str]) -> Tuple[bool, Optional[str]]
    async def get_state(self) -> Dict[str, Any]
```

This design enables future `DesktopAutomation` implementations using OS-level automation frameworks or accessibility APIs, without changes to the core orchestration or artifact schema.

**Legacy web support**: The accessibility-first element location strategy works well with legacy web applications that lack clean DOMs, use framesets, or have deeply nested tables. The fallback strategies provide additional resilience for these challenging surfaces.

### Multi-tenant Reuse

The artifact schema includes optional fields for tenant identification and app versioning. This enables several multi-tenant strategies:

**Parameterized artifacts**: Artifacts use parameter substitution rather than hardcoded values, making them reusable across tenants with different concrete data.

**Tenant-specific overrides**: The schema supports tenant_id and app_version fields, enabling a base artifact to be extended with tenant-specific overrides for selectors, timeouts, or error conditions.

**Canonicalization**: While not implemented in this demo, the schema design supports normalization of concrete values into parameterized patterns (e.g., `/item/12345` → `/item/:id`). This would enable artifacts recorded on one tenant to be applied to others running the same vendor product.

**Drift detection**: The version fields and checkpoint verification provide hooks for detecting when an artifact may need updating due to UI changes across different tenant configurations.

### Cross-tenant Strategy

For the real environment where hundreds of tenants run ~20 apps each, many sharing the same underlying vendor product, the design supports:

1. **Base artifacts**: Record capabilities on a "canonical" tenant configuration
2. **Tenant overrides**: Specify per-tenant selector differences or parameter mappings
3. **Version management**: Track which app versions each artifact supports
4. **Drift monitoring**: Use checkpoint failures to detect when tenant-specific customization is needed

This approach avoids rebuilding artifacts for each tenant while still accommodating legitimate configuration differences.

## Escalation & Handoff

The human-in-the-loop escalation mechanism provides a real, albeit minimal, control transfer system for handling situations where automation cannot safely proceed.

### Stuck Detection

The system detects stuck states through multiple indicators:

- **Max steps reached**: Agent has taken the maximum number of allowed steps without goal completion
- **Consecutive failures**: Three or more consecutive action failures suggest the agent is in a loop or dead-end
- **Timeout**: Overall execution time exceeds configured maximum

When a stuck state is detected, the system automatically requests intervention rather than continuing indefinitely.

### Intervention Request

When intervention is needed, the system creates an `InterventionRequest` containing:

- **Capability context**: Which capability was being executed and the original goal
- **Current state**: Step number, current URL, page content
- **Reason for intervention**: Why the system thinks it's stuck
- **Screenshot**: Visual context of where the automation stopped
- **Action history**: What actions were taken leading to the intervention

This comprehensive context enables the human operator to quickly understand the situation and take appropriate action.

### Control Transfer

The escalation manager implements a clear state machine for control:

- **AUTOMATION**: Normal operation, agent or replay engine in control
- **PAUSED**: Automation paused, waiting for human intervention
- **HUMAN_CONTROL**: Human operator has taken control of the session

The transfer process:
1. System detects stuck state → requests intervention → transitions to PAUSED
2. Human acknowledges request → transitions to HUMAN_CONTROL
3. Human performs manual actions → system records each action
4. Human indicates completion → transitions back to AUTOMATION
5. Automation resumes from the post-intervention state

### Operator Console

For this demo, the operator console is mocked as a simple timeout-based simulation. In a production system, this would be a real-time co-browsing interface that:

- Shows the live browser session to the operator
- Allows the operator to take manual control
- Provides communication channels for guidance
- Captures operator actions for audit trails

The control transfer logic and state management are real and would integrate with any operator console implementation.

### Resume After Intervention

After human intervention, the system records all manual actions taken. This provides:
- **Audit trail**: Complete record of what the human did
- **Learning opportunity**: Could be used to improve the artifact or train the LLM
- **Transparency**: Clear distinction between automated and manual steps

The automation can then resume either from the current state or, if the human completed the task, skip to verification.

## Safety

The safety layer implements a defense-in-depth approach to prevent unauthorized or harmful actions.

### Allowlist Enforcement

**Domain allowlist**: The system only permits navigation to configured domains. This prevents the agent from being redirected to malicious sites or accessing unauthorized applications. Domains are checked before any navigate action.

**Action type allowlist**: Only specific action types are permitted (navigate, click, type, extract, wait by default). Risky actions like delete or submit must be explicitly enabled in configuration.

### Risk Classification

Actions are assessed at three risk levels:

**Safe**: Read-only operations with no side effects (navigate, extract, wait)

**Reversible**: Actions that can be undone (type into form fields, select options)

**Risky**: Actions with potential side effects (click submit buttons, delete operations)

**Irreversible**: Actions that cannot be undone (confirm destructive operations)

The system automatically classifies actions based on type and context, with configuration overrides available.

### Confirmation Requirements

Risky and irreversible actions require human confirmation before execution. In this demo, this is implemented as a policy check. In production, this would integrate with the escalation system to route confirmation requests to appropriate operators based on risk level and action context.

### Data Redaction

The system automatically redacts sensitive data from:
- Logs and execution traces
- Artifacts (parameter values and outputs)
- Intervention requests and context

Sensitive fields are identified by common patterns (password, ssn, credit_card, etc.) and replaced with `***REDACTED***`. This prevents regulated financial data from being persisted or exposed in logs.

### Input Validation

Before execution, the system validates:
- **Parameters**: Type checking, required field validation, range validation
- **URLs**: Domain allowlist checking, protocol validation
- **Actions**: Type validation, target validation

Invalid inputs are rejected before any automation occurs, providing fail-safe behavior.

### Policy Configuration

Safety policies are configurable through environment variables:
- `ALLOWED_DOMAINS`: Comma-separated list of permitted domains
- `ALLOWED_ACTION_TYPES`: Permitted action types
- `RISKY_ACTION_TYPES`: Actions requiring confirmation

This allows policies to be tailored per environment (dev vs production) or per tenant without code changes.

## Cuts

Given the focused scope and time constraints, several features were deliberately cut or stubbed while maintaining the integrity of the core requirements.

### Intentional Cuts

**Full operator console**: Implemented a minimal but real control transfer mechanism with a mocked operator interface. A full real-time co-browsing console would require WebSocket infrastructure, authentication, and a separate frontend - significantly expanding scope. The control transfer logic and state management are genuine and would integrate with any operator console implementation.

**Real-time monitoring**: While metrics collection and confidence scoring are implemented, a full monitoring dashboard with Prometheus/Grafana integration is stubbed in the Docker Compose configuration. The metrics infrastructure is ready for production monitoring integration.

**Multi-process execution**: The architecture is designed for multi-process deployment with Docker Compose showing the separation of concerns, but actual queue-based execution and worker scaling are not implemented. The interfaces and artifact schema support this expansion.

**Advanced canonicalization**: The schema supports parameterized patterns, but sophisticated canonicalization algorithms for cross-tenant artifact normalization are not implemented. This would require semantic analysis and pattern recognition beyond the current scope.

## Production Readiness Enhancements

### Enterprise Features Added

**Artifact Marketplace**: Implemented a comprehensive artifact management system with:
- Directory service for multiple automation capabilities
- Search functionality by name, description, or target application
- Validation and consistency checking across artifacts
- Metadata extraction and cataloging

**Performance Metrics**: Added enterprise-grade monitoring:
- Execution tracking with detailed metrics
- Confidence scoring based on success rates and execution consistency
- Reliability factor analysis (error recovery, fallback efficiency)
- Historical performance reporting

**Multi-Artifact Support**: Expanded from single artifact to comprehensive capability suite:
- `lookup_member_balance`: Member information retrieval
- `transfer_funds`: Financial transaction processing
- `account_management`: Account operations and management

**Containerization**: Full Docker support for production deployment:
- Multi-stage Dockerfile for optimized builds
- Docker Compose orchestration for service management
- Volume mounting for persistence and development
- Network isolation and service dependencies

### Scalability Architecture

The system is designed for horizontal scaling:

**Service Separation**: Target application and automation workers are separate services
**Stateless Workers**: Automation workers can be scaled horizontally
**Artifact Storage**: Artifacts stored in shared volumes for multi-worker access
**Metrics Aggregation**: Centralized metrics collection for system-wide monitoring

**Deployment Strategies**:
- **Development**: Local Docker Compose with volume mounts
- **Staging**: Containerized deployment with minimal worker count
- **Production**: Kubernetes deployment with auto-scaling workers
- **Multi-tenant**: Separate artifact namespaces per tenant with shared execution infrastructure

**Multi-process architecture**: Designed interfaces to support queue-based, multi-process execution but implemented a single-process architecture. Scaling infrastructure (queues, clusters, multi-tenant plumbing) was explicitly called out as not rewarded in the evaluation criteria.

**Desktop surface support**: Designed the abstraction layer to support desktop applications but only implemented the web surface. Desktop automation would require additional work with OS-level frameworks but the architecture doesn't paint into a corner.

**Sophisticated goal completion detection**: Used simple heuristics (success indicators in text) for detecting goal completion. A production system would use semantic understanding or LLM-based verification of whether the goal was actually achieved.

**Advanced parameter extraction**: Used heuristic-based parameter extraction during discovery. A more sophisticated system would use semantic analysis of the goal and page content to identify parameters and outputs more accurately.

**Code generation**: Did not implement the optional stretch goal of generating runnable test scripts from artifacts. This would be valuable for developer workflows but wasn't core to the requirements.

### What Would Be Built Next

With more time, the highest priority additions would be:

1. **Agent-facing capability interface**: Expose saved artifacts as a catalog of callable capabilities via a simple API or function-calling interface. This would demonstrate the full agent-invocable vision.

2. **Enhanced goal completion detection**: Integrate LLM-based verification to confirm goals are actually achieved, not just that actions completed.

3. **Desktop surface implementation**: Add a `DesktopAutomation` implementation using accessibility APIs to demonstrate the surface abstraction design.

4. **Canonicalization**: Implement normalization of concrete values into parameterized patterns to enable cross-tenant artifact reuse.

5. **Multi-run stability testing**: Add functionality to replay artifacts N times and report stability/flakiness metrics.

6. **Production operator console**: Build a real-time web-based operator interface for the escalation system.

These additions would enhance the system's capabilities while building on the solid foundation established by the core implementation. The architectural decisions made during initial implementation were specifically chosen to not preclude these enhancements.