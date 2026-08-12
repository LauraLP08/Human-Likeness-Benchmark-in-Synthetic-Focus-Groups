# Checklist for the first real run

One session. Not two, not a study. Read this before spending anything.

Nothing in Phase 3E has called a provider. Every launch so far went through a fake
worker; the real path has been exercised only up to the point where a process would
be created.

## Before

1. **Authorise it explicitly.** A real run costs money and cannot be undone. Say so
   in writing to whoever is running it.
2. **`psutil` installed.** `py -c "import psutil"` must succeed. Without it the
   launcher refuses to identify processes rather than degrading to pid-only.
3. **One session only.** Study with a single condition, a single focus group,
   `replicates = 1`. `concurrency_limit = 1`.
4. **A low `max_turns`.** 12–20. Enough to reach the second guide section; not enough
   to run a full study by accident. The cap will probably be hit — that is expected
   and produces `MAX_TURNS_REACHED`, which is a valid outcome to inspect.
5. **A short guide.** Two or three sections.
6. **Four participants at most.**
7. **Dry-run green.** All eleven checks. In particular `credentials` must name the
   provider and report `PRESENT`, and `architecture_manifest` must show the pin.
8. **Bundle confirmed and immutable.** `Hashes: Verified` on the Launch tab.
9. **A rate table, or accept `Undefined`.** Without one the run still works; the cost
   column will read Undefined and the token counts will be real.
10. **Know where the output goes.** `output/session_logs/<session_id>/` in the
    repository. Confirm the directory does not already exist.

## During

11. Start the queue, then tick the scheduler. Exactly one job should move to RUNNING.
12. Watch the job table: last turn, phase, call count, tokens. If the call count
    stays at zero for more than a minute, the CLI is failing before its first call —
    cancel and read `launcher_stdout.log`.
13. Cancellation is available and keeps every partial artefact. Cost already spent is
    not refunded.

## After

14. **The job must be COMPLETED, not REQUIRES_RECOVERY.** If it is
    REQUIRES_RECOVERY, the worker did not write a terminal record and that is the
    first thing to investigate — it is the mechanism this phase exists to provide.
15. **Read the terminal record.** `runs/jobs/job__<session_id>.terminal_record.json`:
    exit code, termination kind, completion quality, transcript hash.
16. **Check `completion_quality`.** `GUIDE_COMPLETED` or `MAX_TURNS_REACHED`. A
    capped session imports with a warning and needs reinforced confirmation before it
    joins a comparative study.
17. **Compare observed usage against the provider's own console.** If the token
    counts disagree, `api_calls.jsonl` is not capturing everything and the cost
    figures cannot be trusted.
18. **Import.** It should arrive as synthetic, not comparable, with no window.
19. **Then, separately**, create and lock a comparable window if the session is to be
    used at all.

## Stop conditions

Stop and do not launch a second session if any of these is true:

- the job reported COMPLETED without a terminal record present;
- the transcript hash in the record does not match the file;
- the config hash in the record does not match the job;
- the observed token usage is wildly different from what the provider reports;
- cancellation did not stop the process tree;
- anything in `output/session_logs/` was written under a session id the plan did not
  create.
