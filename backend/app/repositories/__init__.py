"""Repository tier -- persistence and scope enforcement.

Introduced by E2.2 (issue #22). Two responsibilities live here and nowhere else:

1. `scope.py` -- the single implementation of every server-side scope rule. `NFR-020` requires
   scope to be enforced "in the repository layer, not the router or tool schema"; before this
   package existed the same rules were re-implemented six independent times across routers,
   services and the scheduling layer, so a correction had to be applied six times to be real.
2. The remaining modules -- SQL for a table family, returning plain rows. Routers must not call
   `text()`; they call a service, which calls one of these.

Nothing in this package derives scope from a client-supplied argument (`M15`/`NFR-019`): every
function takes the trusted `ExecutionContext` and treats any caller-supplied facility id as a
*request* to be validated against it, never as the answer.
"""
