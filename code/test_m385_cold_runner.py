#!/usr/bin/env python3
import importlib.util,pathlib
p=pathlib.Path(__file__).with_name("run_m385_cold.py")
spec=importlib.util.spec_from_file_location("cold",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert callable(m.load_m385)
print("PASS cold-runner import")
print("1 passed / 0 failed")
