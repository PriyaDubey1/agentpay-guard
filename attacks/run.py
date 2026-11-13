"""Run the adversarial suite and write attacks/RESULTS.md.

    python -m attacks.run
"""
from pathlib import Path

from attacks.harness import Harness
from attacks.scenarios import SCENARIOS


def run_all() -> list[dict]:
    results = []
    for s in SCENARIOS:
        h = Harness()
        try:
            passed, detail = s["fn"](h)
        except Exception as e:  # a crashing scenario counts as a failure
            passed, detail = False, f"crashed: {type(e).__name__}: {e}"
        finally:
            h.close()
        results.append({**s, "passed": passed, "detail": detail})
    return results


def main() -> None:
    results = run_all()
    attacks = [r for r in results if r["kind"] == "attack"]
    controls = [r for r in results if r["kind"] == "control"]
    blocked = sum(r["passed"] for r in attacks)
    ok = sum(r["passed"] for r in controls)

    lines = ["# Adversarial test results", "",
             f"**Attacks blocked: {blocked}/{len(attacks)}**  |  "
             f"**Legitimate flows working: {ok}/{len(controls)}**", "",
             "| Result | Type | Scenario | What happened |", "|---|---|---|---|"]
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {mark} | {r['kind']} | {r['description']} | {r['detail']} |")
    lines += ["", "Run with an in-memory database and a fake PayPal that mimics idempotency and "
              "refuses capture before buyer approval. Re-generate with `python -m attacks.run`.",
              "", "Not covered here: LLM goal-mismatch review (needs an API key), webhook forgery "
              "(webhooks are not implemented yet; the Guard polls PayPal instead)."]
    Path(__file__).with_name("RESULTS.md").write_text("\n".join(lines) + "\n")

    for r in results:
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['kind']:8} {r['name']:36} {r['detail']}")
    print(f"\nAttacks blocked: {blocked}/{len(attacks)} | Legitimate flows OK: {ok}/{len(controls)}")


if __name__ == "__main__":
    main()
