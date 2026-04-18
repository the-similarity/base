"""Natural-language narrative to time-series pipeline.

This package compiles textual narrative sequences (crash, rally,
consolidation, breakout, reversal, etc.) into deterministic NumPy
time-series arrays and registers them as platform artifacts.

Modules
-------
compiler
    Core compilation logic: ``compile_trajectory`` turns a sequence of
    narrative events into a concatenated price array, and
    ``compile_and_register`` wraps that with registry integration.
"""
