"""Track B: one idea at a time, written down BEFORE it is tested.

A hypothesis = "I think change X will fix problem Y, and it will count as a success only if Z".
Pass marks (thresholds) are fixed when the hypothesis is created and cannot be edited afterwards.

States:  DRAFT -> (backtest on train + validation) -> QUALIFIED_CANDIDATE or REJECTED
         QUALIFIED_CANDIDATE -> (final test, once) -> stays QUALIFIED_CANDIDATE if it passes, else REJECTED
REJECTED means "tested properly, the idea failed". It is different from a TECHNICALLY INVALID test (bug, bad data,
crashed run): see invalidate_batch(), which withdraws the verdict and lets the idea be re-tested after the fix.
Only ONE hypothesis may be open (DRAFT or QUALIFIED_CANDIDATE awaiting its final test) at a time.
Stored in the database 'state' table under the key 'hypotheses'.
"""
from .candidates import BASELINE_VERSION, candidate_versions
from .models import now_ms

OPEN_STATES = ("DRAFT", "QUALIFIED_CANDIDATE")


class HypothesisError(Exception):
    pass


def _all(db):
    return db.get_state("hypotheses", [])


def _save(db, items):
    db.set_state("hypotheses", items)


def list_hypotheses(db):
    return _all(db)


def get_hypothesis(db, hid):
    for h in _all(db):
        if h["id"] == hid:
            return h
    raise HypothesisError(f"No hypothesis {hid}")


def open_hypothesis(db):
    """The one hypothesis currently being worked on (or None)."""
    for h in _all(db):
        if h["state"] == "DRAFT" or (h["state"] == "QUALIFIED_CANDIDATE" and not h.get("final")):
            return h
    return None


def _log(h, state, reason, evidence=None):
    h["state"] = state
    h["history"].append({"ts_ms": now_ms(), "state": state, "actor": "agent", "reason": reason,
                         "evidence": evidence or {}})


def add_hypothesis(db, *, title, statement, prediction, candidate, min_profit_factor=1.2,
                   min_trades=20, min_return=0.0, max_drawdown=0.15) -> dict:
    for name, val in (("title", title), ("statement", statement), ("prediction", prediction)):
        if not (val or "").strip():
            raise HypothesisError(f"A hypothesis needs a {name}")
    if candidate == BASELINE_VERSION:
        raise HypothesisError("v1.0 is the permanent failed baseline and cannot be a candidate. "
                              "Give the new idea a new version id.")
    if candidate not in candidate_versions():
        raise HypothesisError(f"Candidate '{candidate}' is not registered in candidates.py "
                              f"(known: {', '.join(candidate_versions()) or 'none'})")
    cur = open_hypothesis(db)
    if cur:
        raise HypothesisError(f"{cur['id']} ('{cur['title']}') is still open ({cur['state']}). "
                              f"Finish or close it first: one idea at a time.")
    items = _all(db)
    h = {"id": f"H{len(items) + 1}", "title": title, "statement": statement, "prediction": prediction,
         "candidate": candidate, "created_ms": now_ms(), "state": "DRAFT", "history": [],
         "thresholds": {"min_profit_factor": min_profit_factor, "min_trades": min_trades,
                        "min_return": min_return, "max_drawdown": max_drawdown},
         "results": {}, "final": None}
    _log(h, "DRAFT", "hypothesis written before testing")
    items.append(h)
    _save(db, items)
    return h


def judge(thresholds: dict, metrics: dict) -> list:
    """Compare one period's metrics with the pass marks. Returns the list of failures (empty = passed)."""
    t, fails = thresholds, []
    if metrics["trades"] < t["min_trades"]:
        fails.append(f"only {metrics['trades']} trades (need {t['min_trades']}), too few to judge")
    if metrics["net_return"] <= t["min_return"]:
        fails.append(f"return {metrics['net_return']:+.2%} (need above {t['min_return']:+.2%})")
    pf = metrics["profit_factor"]            # None means no losing trades at all
    if pf is not None and pf < t["min_profit_factor"]:
        fails.append(f"profit factor {pf:.2f} (need {t['min_profit_factor']:.2f}+)")
    if metrics["max_drawdown"] > t["max_drawdown"]:
        fails.append(f"worst drop {metrics['max_drawdown']:.1%} (limit {t['max_drawdown']:.0%})")
    return fails


def record_dev_results(db, hid, results: dict, batch=None) -> dict:
    """results = {'train': metrics, 'validation': metrics}. Moves DRAFT to QUALIFIED_CANDIDATE or REJECTED.
    batch = the experiment batch these numbers came from (so a broken test can be invalidated later)."""
    items = _all(db)
    h = next((x for x in items if x["id"] == hid), None)
    if h is None:
        raise HypothesisError(f"No hypothesis {hid}")
    if h["state"] != "DRAFT":
        raise HypothesisError(f"{hid} is {h['state']}: it was already judged. Re-testing the same idea until it "
                              f"passes would be cheating; write a new hypothesis with a new version id.")
    fails = {p: judge(h["thresholds"], m) for p, m in results.items()}
    h["results"] = {p: {k: m[k] for k in ("trades", "net_return", "profit_factor", "max_drawdown", "buy_hold_return")}
                    for p, m in results.items()}
    h["dev_batch"] = batch
    bad = [f"{p}: {f}" for p, fs in fails.items() for f in fs]
    if bad:
        _log(h, "REJECTED", "failed pass marks: " + "; ".join(bad), h["results"])
    else:
        _log(h, "QUALIFIED_CANDIDATE", "passed all pass marks on train and validation", h["results"])
    _save(db, items)
    return h


def record_final_result(db, hid, metrics: dict, experiment_id=None) -> dict:
    items = _all(db)
    h = next((x for x in items if x["id"] == hid), None)
    if h is None or h["state"] != "QUALIFIED_CANDIDATE" or h.get("final"):
        raise HypothesisError(f"{hid} is not waiting for its final test")
    fails = judge(h["thresholds"], metrics)
    h["final"] = {"experiment_id": experiment_id, "passed": not fails, "failures": fails,
                  "net_return": metrics["net_return"], "trades": metrics["trades"]}
    if fails:
        _log(h, "REJECTED", "failed the final test: " + "; ".join(fails), h["final"])
    else:
        _log(h, "QUALIFIED_CANDIDATE", "passed the final test (next step is a deliberate paper trial)", h["final"])
    _save(db, items)
    return h


def close_hypothesis(db, hid, reason) -> dict:
    if not (reason or "").strip():
        raise HypothesisError("Closing a hypothesis needs a reason")
    items = _all(db)
    h = next((x for x in items if x["id"] == hid), None)
    if h is None:
        raise HypothesisError(f"No hypothesis {hid}")
    if h["state"] in ("REJECTED", "RETIRED"):
        raise HypothesisError(f"{hid} is already {h['state']}")
    _log(h, "RETIRED", reason)
    _save(db, items)
    return h


def invalidate_batch(db, batch, category, reason) -> dict:
    """The TEST was broken (bug, bad data, crashed run), not the idea. Flag every experiment in the batch as invalid.
    If a hypothesis was judged on that batch, withdraw its verdict and reopen it (DRAFT) so it can be re-tested
    after the problem is fixed. Its pass marks stay exactly as written. Refused once a final test was taken."""
    import re
    from .research import InvalidExperimentError, invalidate_experiments
    rows = db.conn.execute("SELECT id, note FROM experiments WHERE batch=?", (batch,)).fetchall()
    if not rows:
        raise InvalidExperimentError(f"No experiments in batch {batch} (see 'experiments' for batch numbers)")
    hids = {m.group(1) for r in rows for m in [re.search(r"hypothesis=(H\d+)", r["note"] or "")] if m}
    items = _all(db)
    touched = [h for h in items if h["id"] in hids]
    for h in touched:
        if h.get("final"):
            raise HypothesisError(f"{h['id']} already took its final test, so its history is locked. "
                                  f"Write a new hypothesis with a new version id instead.")
        other = open_hypothesis(db)
        if h.get("dev_batch") == batch and h["state"] in ("REJECTED", "QUALIFIED_CANDIDATE") \
                and other and other["id"] != h["id"]:
            raise HypothesisError(f"{other['id']} is open. Finish or close it before reopening {h['id']}.")
    ids = invalidate_experiments(db, [r["id"] for r in rows], category, reason)     # may refuse (final tests etc.)
    reopened = []
    for h in touched:
        prior = {"state": h["state"], "results": h["results"]}
        h.setdefault("invalidations", []).append({"ts_ms": now_ms(), "batch": batch, "experiment_ids": ids,
                                                  "category": category, "reason": reason, "withdrawn": prior})
        if h.get("dev_batch") == batch and h["state"] in ("REJECTED", "QUALIFIED_CANDIDATE"):
            h["results"], h["dev_batch"] = {}, None
            _log(h, "DRAFT", f"TEST INVALID ({category}): {reason}. The {prior['state']} verdict is withdrawn "
                             f"(not evidence about the idea). Re-test after the fix.", prior)
            reopened.append(h["id"])
    _save(db, items)
    return {"experiment_ids": ids, "reopened": reopened}


def require_final_ready(db, candidate) -> dict:
    """Guard for the final test. Returns the hypothesis, or raises HypothesisError."""
    if candidate == BASELINE_VERSION:
        raise HypothesisError("v1.0 failed on train and validation and is a permanent baseline. "
                              "It does not get a final test.")
    for h in reversed(_all(db)):
        if h["candidate"] == candidate:
            if h["state"] != "QUALIFIED_CANDIDATE":
                raise HypothesisError(f"{h['id']} is {h['state']}: only a QUALIFIED_CANDIDATE may take the final test")
            if h.get("final"):
                raise HypothesisError(f"{h['id']} already took its final test")
            return h
    raise HypothesisError(f"No hypothesis exists for {candidate}. Write one first ('hypothesis add').")
