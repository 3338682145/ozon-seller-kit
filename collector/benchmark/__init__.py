"""V2 buyer benchmark package.

Contains the cookie supply gate (T0), data contracts (T1), outcome/event
classification (T2), source policy (T3) and isolated adapters (T4). Everything
here is offline-testable; the only network-touching code is the CDP mint and an
injected Transport, never imported implicitly.
"""
