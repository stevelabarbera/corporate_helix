M4.3D — helix_company integration

This patch wires the validated root_entity_resolver into helix_company.py.

Behavior:
- `python3 code/helix_company.py --company "NTT"` now invokes root resolution.
- AUTO_RESOLVED roots flow directly into existing GLEIF expansion.
- REVIEW_REQUIRED / NO_MATCH stop safely with candidate diagnostics.
- `--lei` remains an explicit operator override and bypasses automatic resolution.

Apply from the repository root:

    git apply ~/Downloads/corporation_helix_m43d_helix_company_integration/m43d_helix_company_integration.patch

Then copy the test file if needed, or unzip the supplied archive over the repo.
