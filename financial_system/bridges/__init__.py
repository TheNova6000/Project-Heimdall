"""
financial_system/bridges/ -- additive-only integrations between Heimdall's
existing, frozen decision code and other systems in this repo.

Nothing in this package is imported by, or required by, any of
financial_system/'s scored/graded phases. It is a pure consumer: it reads
another system's finished output and calls Heimdall's existing functions on
a transformed copy of it, in a directory this package owns.
"""
