"""Paper broker: pretends to be the exchange. Real prices in, fake money out. Never touches a real account.

Safety features:
  * Idempotent: sending the same client_order_id twice only ever fills once (no double-buys).
  * Transactional: the order, the fill and the new balances are saved together or not at all.
  * Journal rows can never be edited afterwards (the database blocks it).
  * Gross profit (before costs) and net profit (after costs) are recorded separately.
"""
import json
from dataclasses import dataclass

from . import log
from .models import now_ms
from .portfolio import Fill, OrderRejected, Portfolio, fill_price


@dataclass
class OrderResult:
    status: str                 # FILLED | REJECTED | DUPLICATE
    fill: Fill | None = None
    reason: str | None = None


def portfolio_state(pf: Portfolio) -> dict:
    return {"cash": pf.cash, "base": pf.base, "avg_cost": pf.avg_cost, "entry_fee": pf.entry_fee,
            "peak_equity": pf.peak_equity}


def load_portfolio(pf: Portfolio, d: dict):
    pf.cash, pf.base, pf.avg_cost = d["cash"], d["base"], d["avg_cost"]
    pf.entry_fee, pf.peak_equity = d["entry_fee"], d["peak_equity"]


class PaperBroker:
    def __init__(self, cfg, db, pf: Portfolio):
        self.cfg, self.db, self.pf = cfg, db, pf

    def submit(self, client_order_id: str, side: str, qty: float, mid: float, quote=None,
               reason: str = "", decision_id: int | None = None, extra_state: dict | None = None) -> OrderResult:
        db, pf = self.db, self.pf
        if db.conn.execute("SELECT 1 FROM orders WHERE client_order_id=?", (client_order_id,)).fetchone():
            log.warn(f"Duplicate order {client_order_id} ignored")
            return OrderResult("DUPLICATE", reason="already processed")
        price = fill_price(side, mid, self.cfg.costs, quote)
        snapshot = portfolio_state(pf)
        ts = now_ms()
        db.begin()
        try:
            try:
                fill = pf.buy(qty, price) if side == "BUY" else pf.sell(qty, price)
            except OrderRejected as e:
                db.conn.execute(
                    "INSERT INTO orders(client_order_id,ts_ms,side,order_type,qty,ref_price,status,reject_reason,decision_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (client_order_id, ts, side, "MARKET", str(qty), str(mid), "REJECTED", str(e), decision_id))
                db.commit()
                log.warn(f"{side} rejected by simulator: {e}")
                return OrderResult("REJECTED", reason=str(e))
            cur = db.conn.execute(
                "INSERT INTO orders(client_order_id,ts_ms,side,order_type,qty,ref_price,status,decision_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (client_order_id, ts, side, "MARKET", str(fill.qty), str(mid), "FILLED", decision_id))
            db.conn.execute(
                "INSERT INTO fills(order_id,ts_ms,side,qty,price,fee,cash_after,base_after,realized_gross,realized_net,reason) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cur.lastrowid, ts, side, str(fill.qty), str(fill.price), str(fill.fee), str(pf.cash), str(pf.base),
                 str(fill.realized_gross), str(fill.realized_net), reason))
            db.set_state("portfolio", portfolio_state(pf))
            extra = extra_state(fill) if callable(extra_state) else (extra_state or {})
            for k, v in extra.items():
                db.set_state(k, v)
            db.commit()
        except Exception as e:
            db.rollback()
            load_portfolio(pf, snapshot)  # undo in-memory change: memory must match the database
            log.error(f"Order {client_order_id} failed and was rolled back: {e}")
            raise
        log.ok(f"PAPER {side} {fill.qty:.6f} BTC @ {fill.price:,.1f} (fee {fill.fee:.4f} USDT) - {reason}")
        return OrderResult("FILLED", fill)


def reconcile(db, pf: Portfolio) -> bool:
    """On restart: the last fill in the journal is the truth. Compare it with the saved balances."""
    row = db.conn.execute("SELECT cash_after, base_after FROM fills ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        log.ok("Restart check: no past trades, nothing to reconcile")
        return True
    cash, base = float(row["cash_after"]), float(row["base_after"])
    if abs(cash - pf.cash) < 1e-6 and abs(base - pf.base) < 1e-9:
        log.ok("Restart check: balances match the trade journal")
        return True
    log.error(f"Restart check FAILED: saved {pf.cash:.4f}/{pf.base} vs journal {cash:.4f}/{base}. Using journal.")
    db.log_event("ERROR", "reconcile", json.dumps({"saved": [pf.cash, pf.base], "journal": [cash, base]}))
    pf.cash, pf.base = cash, base
    return False
