"""Work through an order one item at a time: run the skill, check the grasp,
retry a miss once, and ask a person about anything else.

    python -m kitcheck.runner "Sort all"          a kit from config.json
    python -m kitcheck.runner red teal            items in this order
    python -m kitcheck.runner red --label 020000  a downloaded checkpoint instead of the final model
    python -m kitcheck.runner teal --label replay camera-guided replay of the nearest take (kitcheck/replay.py)

Before starting: each ring on its spot, the arm in the rest pose.
Every attempt is added to data/runs.jsonl. docs/history/05-runner.md has the design.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from kitcheck import grasp
from kitcheck.skill import ROOT, load_config, run_skill, uses_replay

RUN_LOG = ROOT / "data" / "runs.jsonl"


def say(key, item=None):
    """Optional spoken status (docs/history/10-voice.md); silent unless voice is on and its clips exist."""
    try:
        from kitcheck.voice import Voice

        Voice.from_config(ROOT / "config.json").say(key, item=item)
    except Exception:
        pass


def log_attempt(entry: dict):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def reference_for(item: str, config: dict):
    path = ROOT / config["items"][item].get("grasp_reference", f"data/grasp_{item}.json")
    return grasp.Reference.load(path) if path.exists() else None


def ask(question: str, choices: dict[str, str]) -> str:
    """Ask the person in the terminal. With no terminal, stop the order."""
    if not sys.stdin.isatty():
        return "cancel"
    keys = "  ".join(f"[{key}] {label}" for key, label in choices.items())
    while True:
        answer = input(f"{question}  {keys}: ").strip().lower()[:1]
        if answer in choices:
            return choices[answer]


def _quiet(event: str, **data):
    pass


def pack_item(item: str, config: dict, order_id: str, label: str | None, ask=ask, notify=_quiet, locate=None) -> str:
    """Returns verified, manual, skipped or cancel.

    ask(question, choices) gets the operator's answer (the terminal by default;
    the dashboard passes its own). notify(event, **data) reports progress.
    locate(item) says where the stand camera sees the part, for camera-guided
    replay; without it the replay looks with the camera itself.
    """
    retries = config.get("limits", {}).get("auto_retries", 1)
    reference = reference_for(item, config)
    attempt = 0
    while True:
        attempt += 1
        print(f"\n[{item}] attempt {attempt}: picking ...", flush=True)
        say("picking", item)
        target = locate(item) if locate and uses_replay(item, label, config) else None
        notify("picking", item=item, attempt=attempt)
        result = run_skill(item, label, config=config, target=target)

        if result.ok:
            verdict = grasp.judge_folder(result.folder, reference)
        else:
            verdict = grasp.Verdict("error", reason=result.error or "the run failed")
        log_attempt({
            "time": datetime.now().isoformat(timespec="seconds"),
            "order": order_id, "item": item, "attempt": attempt, "model": result.model,
            "run": str(result.folder.relative_to(ROOT)), "run_s": round(result.seconds, 1),
            "reference": reference is not None, **asdict(verdict),
        })
        print(f"[{item}] {verdict.outcome.upper()}: {verdict.reason} ({result.seconds:.0f} s)")
        notify("checked", item=item, attempt=attempt, outcome=verdict.outcome, reason=verdict.reason,
               run=str(result.folder), seconds=round(result.seconds, 1), model=result.model)

        if verdict.outcome in (grasp.PLACED, grasp.HELD):
            say("verified", item)
            return "verified"
        if verdict.outcome == grasp.MISSED and attempt <= retries:
            say("missed_retry", item)
            notify("retrying", item=item, attempt=attempt)
            print(f"[{item}] the ring should still be on its spot: retrying")
            continue

        # Anything else needs a person: a second miss, a drop, or a failed run.
        from kitcheck.voice import key_for_verdict

        say(key_for_verdict(verdict.outcome, verdict.reason, attempt) if verdict.outcome != "error" else "error", item)
        if verdict.outcome == "error":
            print(result.error, file=sys.stderr)
        notify("needs_operator", item=item, outcome=verdict.outcome, reason=verdict.reason)
        choice = ask(f"[{item}] needs a hand.", {"r": "retry", "p": "placed by hand", "s": "skip", "c": "cancel"})
        if choice == "retry":
            attempt = 0
            continue
        if choice == "placed by hand":
            return "manual"
        if choice == "skip":
            return "skipped"
        return "cancel"


def run_order(items: list[str], config: dict, label: str | dict | None = None, ask=ask, notify=_quiet) -> dict[str, str]:
    """label is one model label for every item, or a {item: label} dict."""
    order_id = uuid.uuid4().hex[:8]
    print(f"order {order_id}: {', '.join(items)}")
    say("order_started")
    results: dict[str, str] = {}
    for item in items:
        item_label = label.get(item) if isinstance(label, dict) else label
        outcome = pack_item(item, config, order_id, item_label, ask=ask, notify=notify)
        notify("done", item=item, result=outcome)
        if outcome == "cancel":
            results[item] = "cancelled"
            break
        results[item] = outcome
    if all(outcome in ("verified", "manual") for outcome in results.values()) and len(results) == len(items):
        say("kit_ready")
    return results


def summary(path=RUN_LOG) -> str:
    """First-try and after-retry success over the whole run log."""
    if not path.exists():
        return "no runs logged yet"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    good = lambda row: row["outcome"] in (grasp.PLACED, grasp.HELD)  # noqa: E731
    first = [row for row in rows if row["attempt"] == 1]
    picks = {(row["order"], row["item"]) for row in rows}
    done = {(row["order"], row["item"]) for row in rows if good(row)}
    return (f"first try: {sum(map(good, first))} of {len(first)} picks; "
            f"with retry: {len(done)} of {len(picks)} items")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("order", nargs="*", help='a kit name from config.json ("Sort all") or item names')
    parser.add_argument("--label", help="model label under models/<item>/, e.g. 020000 (default: the model in config.json)")
    parser.add_argument("--summary", action="store_true", help="print the success counts from the run log and stop")
    args = parser.parse_args(argv)

    if args.summary:
        print(summary())
        return 0
    config = load_config()
    if len(args.order) == 1 and args.order[0] in config["kits"]:
        items = list(config["kits"][args.order[0]])
    else:
        items = args.order
    if not items:
        parser.error(f"say what to pack: a kit ({', '.join(config['kits'])}) or items ({', '.join(config['items'])})")
    unknown = [item for item in items if item not in config["items"]]
    if unknown:
        parser.error(f"unknown item(s) {', '.join(unknown)}; config.json has {', '.join(config['items'])}")

    started = time.monotonic()
    results = run_order(items, config, args.label)
    print("\n" + "\n".join(f"  {item}: {outcome}" for item, outcome in results.items()))
    print(f"took {time.monotonic() - started:.0f} s. {summary()}")
    return 0 if all(outcome == "verified" for outcome in results.values()) and len(results) == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
