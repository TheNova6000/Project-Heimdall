"""
Bank agent -- Phase 2 scope: an Account registry plus a real
double-entry ledger (assets/liabilities, not just a running balance
number). Phases.md, Phase 2: "Real double-entry-style ledger for Bank
(assets/liabilities, not just a balance number), an Account registry,
basic settlement between Merchant and Bank."

## What changed from Phase 1

Phase 1's `Bank.credit()`/`Bank.debit()` each wrote exactly one
LedgerEntry to exactly one account -- a single-entry running balance,
explicitly scoped that way in Phase 1's own docstring ("a real
double-entry ledger... is not built here"). Phase 2 replaces both with
double-entry-aware primitives that always post a *balanced pair* of
LedgerEntry rows (one debit + one credit of equal magnitude, sharing a
`transaction_id`):

- `fund_external()` -- external money entering the closed system
  (Phase 2: salary only, same synthetic-source convention Phase 1 used
  for `employer:<id>`, see world/engine.py). Posts Debit to this bank's
  own `bank_reserve` asset account, Credit to the target liability
  account.
- `post_transfer()` (module-level function, not a method -- see its
  docstring for why) -- moves money between two liability accounts,
  possibly at two different Bank agents. Posts Debit to the source,
  Credit to the destination. THE enforcement point for Rules.md #7 (no
  negative balances): returns False and posts nothing if the source
  can't cover the amount, exactly the role Phase 1's `debit()` played.

`Account.balance` is still maintained as a live cache on every post
(kept for Phase 1 code and CSV-output compatibility -- persons.csv,
merchants.csv, accounts.csv all read it directly), but per models.py's
module docstring, the ledger is the source of truth going forward: an
account's balance is always exactly the sum of its ledger's credit
amounts minus its debit amounts (or the reverse, for the one asset
account type -- see `_post`), replayed from zero.

## Why a `bank_reserve` asset account, and why it can never go negative

Real double-entry bookkeeping distinguishes assets from liabilities.
Every customer deposit account here (`owner_type` "person", "merchant",
"merchant_pending") is a *liability* -- money the bank owes its
depositor. When new money enters the closed system from an unmodeled
external source (salary, from a synthetic `employer:<id>`, mirroring
Phase 1's existing convention), the double-entry pair for that has to
land on the bank's own books too, not just the depositor's: crediting a
liability without a matching debit somewhere would be exactly the kind
of unbalanced ledger Phase 2 exists to eliminate.

So each Bank gets exactly one `bank_reserve` account (`owner_type=
"bank_reserve"`, `owner_id=<bank_id>`) representing the asset side of
its balance sheet: cumulative external cash it has received on behalf
of its depositors. It is only ever *debited* (increased, per standard
asset-side accounting) by `fund_external()`; nothing in Phase 2's scope
ever draws it down (no cash withdrawal, no bank failure is modeled), so
it is monotonically non-decreasing and can never go negative by
construction -- Rules.md #7 ("no negative balances, ever") holds for it
trivially, not by a special-cased exemption.

## Cross-bank transfers: a stated, honest simplification

A Person's bank and a Merchant's bank are chosen independently at world-
generation time (world/engine.py), so most purchases move money between
accounts at two *different* Bank agents. Real banks settle such
transfers through interbank/correspondent-banking mechanics (nostro/
vostro accounts, net settlement batches) -- modeling that honestly would
require a per-bank interbank clearing account that could legitimately
carry a negative net position, which conflicts with this task's explicit
"no negative balances anywhere, including inside the new ledger" bar.

Phase 2 does not attempt that. `post_transfer()` posts a single balanced
debit/credit pair directly between the two named accounts regardless of
which Bank agent(s) own them -- as if every Bank shared one clearing
ledger. This keeps the double-entry invariant ("debits == credits across
the whole ledger, at all times") literally true without inventing an
interbank layer nobody asked Phase 2 to build. A real interbank
settlement model is a reasonable candidate for a later phase, not
attempted here. Named plainly, not hidden -- see Memory.md.

## Opening balances are still out of ledger scope, same as Phase 1

A Person's/Merchant's *opening* balance (set once, at world-generation
time, before day 0) is still seeded directly onto `Account.balance` with
no ledger entries at all -- exactly Phase 1's behavior, unchanged. This
is a documented, deliberate scope boundary, not an oversight: it is
world-generation *initial condition*, not a simulated transaction, so
the double-entry invariant (which is about the ledger -- i.e. about
modeled economic events) is not expected to explain it. See Memory.md
for why this was chosen over inventing a synthetic "bootstrap funding"
transaction Phase 1 never had and Phase 2 was not asked to add.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from world.models import Account, LedgerEntry

# Which owner_types sit on which side of the balance sheet -- this is
# the one place that decides whether a "debit" increases or decreases
# an account's cached balance (see `_post`). Everything that is not a
# reserve/asset account is treated as a liability account.
ASSET_OWNER_TYPES = {"bank_reserve"}


@dataclass
class Bank:
    bank_id: str
    name: str
    accounts: dict[str, Account] = field(default_factory=dict)
    reserve_account_id: str | None = None  # set by open_reserve_account()

    # ------------------------------------------------------------------
    # Account registry
    # ------------------------------------------------------------------
    def open_account(
        self, account_id: str, owner_id: str, owner_type: str, opening_balance: float = 0.0
    ) -> Account:
        """
        Register a new liability account (a Person's or Merchant's
        deposit account, or Phase 2's new Merchant "pending settlement"
        holding account -- owner_type "merchant_pending").

        `opening_balance` (Person accounts only, in practice) is seeded
        directly onto `Account.balance` with no matching ledger entry --
        see this module's docstring, "Opening balances are still out of
        ledger scope". Unchanged from Phase 1.
        """
        account = Account(
            account_id=account_id,
            bank_id=self.bank_id,
            owner_id=owner_id,
            owner_type=owner_type,
            balance=round(opening_balance, 2),
        )
        self.accounts[account_id] = account
        return account

    def open_reserve_account(self, account_id: str) -> Account:
        """
        Register this Bank's single asset-side `bank_reserve` account --
        see this module's docstring for what it represents and why it
        can never go negative. Must be called once per Bank, before any
        `fund_external()` call against that bank.
        """
        account = Account(
            account_id=account_id,
            bank_id=self.bank_id,
            owner_id=self.bank_id,
            owner_type="bank_reserve",
            balance=0.0,
        )
        self.accounts[account_id] = account
        self.reserve_account_id = account_id
        return account

    def balance_of(self, account_id: str) -> float:
        return self.accounts[account_id].balance

    # ------------------------------------------------------------------
    # Double-entry posting primitives
    # ------------------------------------------------------------------
    def _post(
        self,
        account_id: str,
        amount: float,
        entry_type: str,
        timestamp: str,
        description: str,
        entry_id: str,
        transaction_id: str,
    ) -> None:
        """
        Append exactly one LedgerEntry to one account and update its
        cached balance, applying standard double-entry sign convention
        for that account's side of the balance sheet (asset vs
        liability -- see ASSET_OWNER_TYPES above).

        Private/internal: always called in balanced pairs by
        `fund_external()` and `post_transfer()` below, never on its own,
        so the double-entry invariant is a structural property of this
        module's public API rather than something callers have to
        remember to maintain.
        """
        account = self.accounts[account_id]
        is_asset = account.owner_type in ASSET_OWNER_TYPES
        if entry_type == "debit":
            delta = amount if is_asset else -amount
        else:
            delta = -amount if is_asset else amount
        account.balance = round(account.balance + delta, 2)
        account.ledger.append(
            LedgerEntry(
                entry_id=entry_id,
                account_id=account_id,
                timestamp=timestamp,
                entry_type=entry_type,
                amount=round(amount, 2),
                balance_after=account.balance,
                description=description,
                transaction_id=transaction_id,
            )
        )

    def fund_external(
        self,
        account_id: str,
        amount: float,
        timestamp: str,
        description: str,
        entry_ids: tuple[str, str],
        transaction_id: str,
    ) -> None:
        """
        Money entering the modeled closed system from an unmodeled
        external source (Phase 2: salary only -- see world/engine.py's
        `employer:<id>` convention, which this replaces the ledger side
        of). Posts a balanced pair: Debit this bank's `bank_reserve`
        asset account (asset increases), Credit `account_id` (liability
        increases).

        Unconditional -- unlike `post_transfer`, there is no "can't
        cover it" failure mode here, since the reserve account is only
        ever increased, never checked against a balance. `amount <= 0`
        is treated as a no-op, matching Phase 1's `credit()` behavior.

        `entry_ids`: (reserve_entry_id, account_entry_id).
        """
        if amount <= 0:
            return
        if self.reserve_account_id is None:
            raise RuntimeError(
                f"Bank {self.bank_id} has no reserve account -- "
                "open_reserve_account() must be called before fund_external()"
            )
        reserve_entry_id, account_entry_id = entry_ids
        self._post(
            self.reserve_account_id, amount, "debit", timestamp, description, reserve_entry_id, transaction_id
        )
        self._post(account_id, amount, "credit", timestamp, description, account_entry_id, transaction_id)


def post_transfer(
    from_bank: Bank,
    from_account_id: str,
    to_bank: Bank,
    to_account_id: str,
    amount: float,
    timestamp: str,
    description: str,
    entry_ids: tuple[str, str],
    transaction_id: str,
) -> bool:
    """
    Move `amount` from one liability account to another as a balanced
    double-entry pair (Debit source, Credit destination) -- used for
    both purchases (Person -> Merchant's pending account) and
    settlement (a Merchant's own pending -> settled account transfer).

    A module-level function, not a `Bank` method, because a transfer's
    two accounts may live at two different `Bank` agents (see this
    module's docstring, "Cross-bank transfers"); `from_bank`/`to_bank`
    may be the same object for a same-bank transfer.

    THE enforcement point for Rules.md #7 (no negative balances) for
    every liability-to-liability movement -- returns False and posts
    NOTHING at all if `from_account_id` can't cover `amount`, exactly
    the role Phase 1's `Bank.debit()` played. `amount <= 0` is a no-op
    that returns True, matching Phase 1's `debit()` behavior.

    `entry_ids`: (from_entry_id, to_entry_id).
    """
    if amount <= 0:
        return True
    from_account = from_bank.accounts[from_account_id]
    if amount > from_account.balance:
        return False
    from_entry_id, to_entry_id = entry_ids
    from_bank._post(from_account_id, amount, "debit", timestamp, description, from_entry_id, transaction_id)
    to_bank._post(to_account_id, amount, "credit", timestamp, description, to_entry_id, transaction_id)
    return True
