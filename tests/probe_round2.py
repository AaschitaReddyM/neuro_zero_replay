"""Round-2 regression probe. Run with target app on :8080."""
import asyncio, json, sys, re
sys.path.insert(0, ".")
from pathlib import Path
from src.artifact.replay_engine import ReplayEngine
from src.artifact.schemas import AutomationArtifact, ExecutionStatus

async def run(path, params, **opts):
    eng = ReplayEngine()
    art = AutomationArtifact(**json.load(open(path)))
    # After the fix, control flags go through a separate options object, NOT params.
    if hasattr(eng, "execute_artifact_with_options"):
        return await eng.execute_artifact_with_options(art, params, opts)
    return await eng.execute_artifact(art, {**params, **opts})

async def main():
    # R1: self-approval via params must be rejected or ignored
    r = await run("evidence/artifacts/transfer_funds.json",
                  {"from_account": "1001", "to_account": "1002", "amount": "50", "approve_risky": True})
    assert r.status != ExecutionStatus.SUCCESS, "R1: caller self-approved a risky step via params"
    print("R1 ok:", r.status)

    # R3: no target-app selectors in the engine or orchestrator
    src = "".join(p.read_text(encoding="utf-8") for p in Path("src").rglob("*.py"))
    leaked = [s for s in ["#lookup-result", "#transfer-result", "#account-result", "Member Found", "account_details"] if s in src]
    assert not leaked, f"R3: target-app knowledge hardcoded in src/: {leaked}"
    print("R3 ok")

    # R4: every declared output must be produced by an extract step, and numbers must be numbers
    art = json.load(open("evidence/artifacts/lookup_member_balance.json"))
    extract_keys = {s.get("output_key") for s in art["steps"] if s["action_type"] == "extract"}
    missing = set(art["outputs"]) - extract_keys
    assert not missing, f"R4: declared outputs never extracted: {missing}"
    r = await run("evidence/artifacts/lookup_member_balance.json", {"member_id": "12345"})
    assert r.status == ExecutionStatus.SUCCESS, r
    for k, spec in art["outputs"].items():
        assert k in r.outputs, f"R4: output {k} missing at runtime"
        if spec["type"] == "number":
            assert isinstance(r.outputs[k], (int, float)), f"R4: {k} declared number, got {r.outputs[k]!r}"
        assert "\t" not in str(r.outputs[k]) and "\n" not in str(r.outputs[k]), f"R4: {k} is a raw text blob"
    print("R4 ok:", r.outputs)

    # R5: extracted PII must not appear verbatim in logs or evidence
    logtext = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path("logs").glob("*.log")) if Path("logs").exists() else ""
    evtext = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in Path("evidence").rglob("*.json"))
    for needle in ["John Smith", "Jane Johnson", "5432.50", "12500.00"]:
        assert needle not in logtext, f"R5: '{needle}' leaked into logs/"
        assert needle not in evtext, f"R5: '{needle}' leaked into evidence/*.json"
    print("R5 ok")
    print("PROBE ROUND2 OK")

asyncio.run(main())
