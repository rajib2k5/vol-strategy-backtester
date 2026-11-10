"""volbt.signals: realised variance, the HAR forecast, IV30, the VIX regimes and the VRP signal (milestone 4).

    base.py       SignalValue and the Signal interface the engine calls at step 9
    realised.py   total log returns from the unadjusted close plus the ex-date dividend; window means
    har.py        HAR-RV, the direct 21-session forecast, refitted on the first session of each month
    iv30.py       the ATM-forward implied vol at 30 calendar days, from the session's usable smiles
    regime.py     ADR-0010's VIX buckets and vol-shock regimes, lagged one session
    vrp.py        VrpSignal: s_t = ln(IV30^2 / RV^2) over the sessions of the next 30 calendar days

GARCH is not built (plan section 2: scipy.optimize would be an ADR change, and it adds trials).

Every signal is causal: computed inside the daily loop from a MarketView(as_of = t), refitted
monthly on data up to t only (ADR-0001 §2; tests/test_signals_causal.py). Signals never see the store.
May import (volbt): pricing, view. The import test also bans sys.modules, getattr/setattr with
a name, vars(), globals() and private-attribute reads here: each is a way round the allow-list.
"""
