import asyncio, json, sys
sys.path.insert(0, ".")
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import AutomationArtifact, ActionStep, ActionType, TargetLocation, LocationStrategy
from src.safety.guardrails import SafetyGuardrails

eng = ReplayEngine()
art = AutomationArtifact(**json.load(open("evidence/artifacts/lookup_member_balance.json")))
step2 = art.steps[1]

async def main():
    errors = [
        "Element not found: strategy=accessibility_role value='textbox:Member ID'",
        "Timeout 30000ms exceeded while waiting for selector",
        "net::ERR_CONNECTION_REFUSED at http://localhost:8080",
        "Page crashed",
        "Some totally unrelated exception text",
    ]
    bad = 0
    for e in errors:
        r = await eng._handle_step_error(step2, e, art)
        flag = r.get("is_business_outcome")
        print(f"{e[:50]:<52} -> business_outcome={flag} outcome={r.get('outcome')}")
        bad += bool(flag)
    assert bad == 0, "HARD FAILURES ARE BEING REPORTED AS BUSINESS OUTCOMES"

asyncio.run(main())

g = SafetyGuardrails()
s = ActionStep(step_id=1, action_type=ActionType.NAVIGATE,
               target=TargetLocation(strategy=LocationStrategy.SEMANTIC_SELECTOR, value="http://localhost:8080"),
               value="http://attacker.example/exfil", description="parameterized nav")
# After the fix, the engine must validate the RESOLVED url (step.value), not target.value.
print("PROBE: navigate step resolved url =", s.value, "allowed =", g.is_domain_allowed(s.value))
assert not g.is_domain_allowed(s.value)

r = g.redact_sensitive_data({"member": {"ssn": "123-45-6789"}, "SSN": "123-45-6789", "note": "ssn 123-45-6789"})
print("PROBE redaction:", r)
assert "123-45-6789" not in json.dumps(r), "REDACTION IS NOT RECURSIVE / CASE-INSENSITIVE / VALUE-AWARE"
print("PROBE OK")
