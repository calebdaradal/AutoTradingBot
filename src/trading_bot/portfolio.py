"""Account math shared by the backtester and the paper simulator, so both behave the same.

Rules: buy at ask + slippage, sell at bid - slippage, fee on every fill, never sell more than
owned, respect exchange minimum size / minimum order value, quantities rounded DOWN to the step.
"""
import math
from dataclasses import dataclass


class OrderRejected(Exception):
    pass


@dataclass
class Fill:
    side: str
    qty: float
    price: float
    fee: float
    realized_gross: float = 0.0   # profit before fees
    realized_net: float = 0.0     # profit after ALL fees (buy fee + sell fee)


def round_down(qty: float, step: float) -> float:
    return round(math.floor(qty / step + 1e-9) * step, 10)


def fill_price(side: str, mid: float, costs, quote=None) -> float:
    """Price we actually get. Uses the real bid/ask if we have a quote, else mid +/- half spread."""
    if side == "BUY":
        ask = quote.ask if quote else mid * (1 + costs.half_spread)
        return ask * (1 + costs.slippage)
    bid = quote.bid if quote else mid * (1 - costs.half_spread)
    return bid * (1 - costs.slippage)


class Portfolio:
    def __init__(self, cash: float, costs, rules):
        self.cash = cash
        self.base = 0.0           # BTC owned
        self.avg_cost = 0.0       # average buy price incl. nothing else (fees tracked separately)
        self.entry_fee = 0.0      # buy fee paid for the open position
        self.costs, self.rules = costs, rules
        self.peak_equity = cash

    def equity(self, mark: float) -> float:
        return self.cash + self.base * mark

    def update_peak(self, mark: float):
        self.peak_equity = max(self.peak_equity, self.equity(mark))

    def buy(self, qty: float, price: float) -> Fill:
        r = self.rules
        qty = round_down(qty, r.qty_step)
        if qty < r.min_qty:
            raise OrderRejected("size below exchange minimum quantity")
        notional = qty * price
        if notional < r.min_notional_usdt:
            raise OrderRejected(f"order value {notional:.2f} USDT below exchange minimum {r.min_notional_usdt}")
        fee = notional * self.costs.taker_fee
        if notional + fee > self.cash + 1e-9:
            raise OrderRejected("not enough cash")
        self.cash -= notional + fee
        total = self.base + qty
        self.avg_cost = (self.avg_cost * self.base + price * qty) / total
        self.base = round(total, 10)
        self.entry_fee += fee
        return Fill("BUY", qty, price, fee)

    def sell(self, qty: float, price: float) -> Fill:
        qty = round_down(qty, self.rules.qty_step)
        if qty > self.base + 1e-12:
            raise OrderRejected("cannot sell more than owned")  # spot: no short selling
        if qty < self.rules.min_qty:
            raise OrderRejected("size below exchange minimum quantity")
        notional = qty * price
        fee = notional * self.costs.taker_fee
        frac = qty / self.base if self.base else 1.0
        entry_fee_share = self.entry_fee * frac
        gross = (price - self.avg_cost) * qty
        net = gross - fee - entry_fee_share
        self.cash += notional - fee
        self.base = round(self.base - qty, 10)
        self.entry_fee -= entry_fee_share
        if self.base <= 1e-12:
            self.base, self.avg_cost, self.entry_fee = 0.0, 0.0, 0.0
        return Fill("SELL", qty, price, fee, gross, net)
