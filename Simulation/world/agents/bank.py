"""
Bank agent -- Phase 1 scope: an account registry plus a simple running-
balance ledger per account. Architecture.md scopes Bank to "accounts,
basic ledger"; a real double-entry ledger (assets/liabilities, not just a
balance number) is explicit Phase 2 scope (Phases.md, Phase 2) and is not
built here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from world.models import Account, LedgerEntry


@dataclass
class Bank:
    bank_id: str
    name: str
    accounts: dict[str, Account] = field(default_factory=dict)

    def open_account(
        self, account_id: str, owner_id: str, owner_type: str, opening_balance: float = 0.0
    ) -> Account:
        account = Account(
            account_id=account_id,
            bank_id=self.bank_id,
            owner_id=owner_id,
            owner_type=owner_type,
            balance=round(opening_balance, 2),
        )
        self.accounts[account_id] = account
        return account

    def balance_of(self, account_id: str) -> float:
        return self.accounts[account_id].balance

    def credit(
        self, account_id: str, amount: float, timestamp: str, description: str, entry_id: str
    ) -> None:
        """
        Add money to an account. Used for salary arrivals (money entering
        the modeled system from an external, unmodeled employer -- see
        engine.py for why that is not the "fabricated money" Rules.md #7
        warns against) and for the merchant side of a successful purchase.
        """
        if amount <= 0:
            return
        account = self.accounts[account_id]
        account.balance = round(account.balance + amount, 2)
        account.ledger.append(
            LedgerEntry(
                entry_id=entry_id,
                account_id=account_id,
                timestamp=timestamp,
                amount=round(amount, 2),
                balance_after=account.balance,
                description=description,
            )
        )

    def debit(
        self, account_id: str, amount: float, timestamp: str, description: str, entry_id: str
    ) -> bool:
        """
        Attempt to remove `amount` from an account. Returns False and makes
        NO change at all if the account cannot cover it.

        This is the single enforcement point for Rules.md #7 ("An agent
        cannot spend money it doesn't have... If a Person's balance can go
        negative silently, the whole causal-structure premise is broken").
        Every payment_failure emitted anywhere in the simulation traces
        back to this check returning False -- the failure is a direct,
        inspectable consequence of this account's balance at this moment,
        not an independently-drawn label.
        """
        account = self.accounts[account_id]
        if amount <= 0:
            return True  # a zero/negative debit is a no-op, not a failure
        if amount > account.balance:
            return False
        account.balance = round(account.balance - amount, 2)
        account.ledger.append(
            LedgerEntry(
                entry_id=entry_id,
                account_id=account_id,
                timestamp=timestamp,
                amount=round(-amount, 2),
                balance_after=account.balance,
                description=description,
            )
        )
        return True
