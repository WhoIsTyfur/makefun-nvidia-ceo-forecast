"""Candidate forecasters for the benchmark. Each takes a case dict and returns {"forecasts": [...]}."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_main():
    spec = importlib.util.spec_from_file_location("entry", os.path.join(HERE, "..", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENTRY = _load_main()


def entry(case):
    return ENTRY.forecast_case(case)
