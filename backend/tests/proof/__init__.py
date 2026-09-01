"""`SOLUTION_DESIGN.md` section 10's six-part proof suite (GitHub issue #44, milestone M6).

Run it through its own orchestrator, never bare pytest -- the suite refuses to start without a
throwaway cluster it can prove was created for it:

    uv run --frozen python docs/scripts/run_proof_suite.py
"""
