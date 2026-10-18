# BACKLOG

Design decisions and known gaps that need a maintainer call before anyone
touches the code. Each entry states the conflict, the options, and why it is
not being fixed unilaterally.

## `RetryPolicy.is_retryable`: terminal marker vs. user configuration

**Status:** open — needs a design decision.

**What is wrong.** The docstring of `is_retryable` in
`src/tool_call_retry/policy.py` lists a precedence order whose rule 5 is
"``NonRetryableError`` — always False". That branch is **not in the code**.
It was dropped in `06ea402` ("consult retryable_exceptions before HTTP
status", #20) when the precedence order was rewritten, and the now-unused
`NonRetryableError` import was left behind (ruff F401).

The observable consequence, reproduced by
`/root/.hermes/cache/scratch/probe_nonretryable.py`:

```
is_retryable(NonRetryableError) with it in retryable_exceptions = True
docstring rule 5 says it must be False -> VIOLATED
```

So `RetryPolicy(retryable_exceptions=(NonRetryableError,))` silently makes a
terminal failure retryable. The default policy still returns `False`, which is
why the existing suite never caught it — every test that asserts the terminal
behaviour uses the default policy.

**Why it is not a one-line fix.** The obvious correction — check
`isinstance(exc, NonRetryableError)` before consulting the user's spec —
breaks a behaviour that a test *does* pin:

```
tests/test_retry_policy.py::test_retryable_exceptions_can_make_4xx_retryable
```

`HTTPStatusError` subclasses `NonRetryableError` (see `errors.py`), and that
test asserts that listing `HTTPStatusError` in `retryable_exceptions` makes a
404 retryable. Putting the terminal check first returns `False` for every
`HTTPStatusError` and reddens that test.

The two requirements are in genuine conflict:

- (A) `NonRetryableError` is an unconditional terminal marker, as the docstring
  and the README table (`| ToolCallError(retryable=False), NonRetryableError | no |`)
  both claim.
- (B) `retryable_exceptions` is an explicit user override that wins over type
  defaults, as #20 established and its test pins.

Resolving it means choosing which one yields, and that is a contract change for
every downstream user of `retryable_exceptions` — not a bug fix.

**Options.**

1. **Marker wins (A over B).** Check `NonRetryableError` before the spec, and
   special-case `HTTPStatusError` ahead of it so 429/5xx stay transient.
   Cost: `retryable_exceptions` can no longer override a terminal marker, and
   the README table becomes accurate. This is what the docs already promise.
2. **Config wins (B over A).** Delete rule 5 from the docstring and the
   `NonRetryableError` import, and document that `retryable_exceptions`
   overrides the terminal marker. Cost: the README table is wrong and a user
   who lists a terminal error gets retries they did not expect.
3. **Split the hierarchy.** Give `HTTPStatusError` its own base so it is no
   longer a `NonRetryableError`, then apply option 1 cleanly. Largest diff;
   touches the public exception hierarchy.

**Recommendation:** option 1 — it matches the documented contract, keeps #20's
behaviour intact, and the only thing it removes is an override that contradicts
the docs. Option 3 is the cleaner long-term shape if the hierarchy is not yet
relied upon downstream.

**Not done in this run:** the code change is deliberately left out. The
`NonRetryableError` import is still flagged by ruff (F401) and is the one lint
finding in this repo; it is left in place so the branch can be restored by
whichever option is chosen.
