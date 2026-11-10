"""volbt.analytics: returns and their metrics, and paired-loss inference (milestone 4); P&L attribution, regimes,
the stress grid, PSR and DSR (ADR-0010) in milestone 6.

    returns.py     ADR-0007 §6: daily returns, the risk-free return, Sharpe, Sortino, drawdown, CAGR, Calmar
    inference.py   QLIKE, the forecast test (the EWC t and its moving-block bootstrap-t), the block sign flip,
                   the Newey-West t, the moving-block SE and CI, Holm

It reads the run ledger tables only. May import (volbt): config, pricing.
"""
