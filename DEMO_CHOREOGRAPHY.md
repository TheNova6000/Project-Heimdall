# Screen Choreography

Built mechanically from what's actually in the repository — no step below
is aspirational. `financial_system/demo.py` is the one command that
produces every screen in this document, in order, from a single process,
against the real pipeline. It was run twice while writing this document;
both runs picked the same payment (IDs are stable across repeated runs of
`demo.py` because it doesn't regenerate the dataset — see the note at the
bottom on what *would* change the ID) and reproduced identically.

## The one live command

```bash
python -m financial_system.demo
```

Runtime: a few seconds. No LLM calls (`investigate=False` throughout, so
no network dependency, no quota risk, no latency variance during
recording — the single biggest source of live-demo risk is eliminated by
construction).

## Screen-by-screen

### Screen 1 — The financial world [0:00 of the demo segment]

```
COMMAND:    (already running — this is the first block of output)
EXPECTED:
  Payment pay_XXXXXXXXXX  amount=<real amount>  status=failed
    Customer     -> cust_XXXX
    Order        -> ord_XXXXXXXXXX
    Device       -> dev_XXXX
    Instrument   -> instr_XXXXXXXXXX
    Settlement   -> (none -- payment failed or never settled)
    reaches_bank = False
PROVES:     A real payment, real graph traversal (financial_graph/queries.py
            ::payment_journey), not a mocked object.
FALLBACK:   None needed -- this is the first line of a single script;
            if it doesn't print, nothing downstream would have run
            either, so the fallback IS the prevalidated full-run
            transcript captured below.
```

### Screen 2 — Intelligence: Recovery's finding [~1:10 in PITCH_SCRIPT.md]

```
EXPECTED:
  Decision:          RETRY
  Decision score:    0.85  (category base rate, not a per-instance guess)
  Reason:            failure_reason=technical_failure is recoverable;
                      category's own historical retry-success rate is
                      85% (a base rate, not a per-instance guess)
  Evidence:          ['pay_XXXXXXXXXX', 'ord_XXXXXXXXXX']
PROVES:     decision_score is a fixed, hardcoded category constant
            (recovery/signals.py::FAILURE_TAXONOMY), not fit to this
            payment or this dataset -- say this out loud here, it's the
            AI Judgment moment landing exactly where the script says it should.
FALLBACK:   If the score or category differs from 0.85/technical_failure
            (e.g. a dataset regeneration picked a different payment as
            "first match"), read whatever prints -- the SCRIPT's own
            claim ("a category base rate, never a per-instance guess")
            is true regardless of which category shows up. Do not
            improvise an explanation; the reason string already gives one.
```

### Screen 3 — Policy & Action [~1:10-1:30]

```
EXPECTED:
  Policy outcome:    ALLOW  (rule: R3_RECOVERY_RETRY_ALLOW)
  Authorized action: RETRY_PAYMENT

  Executing...
PROVES:     A deterministic rule authorized this, not the LLM, not a
            hardcoded "yes." rule_id is the literal rule that fired
            (policy/rules.py) -- point at it on screen.
FALLBACK:   If policy outcome is anything other than ALLOW (only possible
            if a dataset regeneration happened to pick a payment in a
            different category with decision_score < 0.5), the script
            still completes -- run_action_loop_v2 exits early with no
            action taken, and Screen 4/5 would show "no outcome event."
            If this happens live: stop, say "this category didn't clear
            the policy threshold this run — that's the same honesty the
            pitch claims," and switch to the prevalidated transcript
            (below) for the rest. Do not re-run hoping for a different
            payment; that would be improvising a demo path, which is
            exactly what this document exists to avoid.
```

### Screen 4 — Outcome becomes a financial event [~2:00]

```
EXPECTED:
  Gateway outcome:   SUCCESS
  Event recorded:    ActionOutcomeObserved  at <ISO timestamp>

  Payment status (projected from the event, not hand-edited): success
  Failure reason:    None
PROVES:     The world changed because of a durable event, not a variable
            assignment -- "projected from the event, not hand-edited" is
            printed literally so the judge doesn't have to take it on faith.
FALLBACK:   If gateway outcome is FAILURE (only if the picked payment's
            retry_would_succeed is False -- shouldn't happen, since
            _pick_payment_id() filters for retry_would_succeed=="True",
            but ground truth could theoretically change): stop here,
            switch to the prevalidated transcript. A FAILURE outcome
            here would still be a true, honest result (this is exactly
            what the false-retry-rate number describes) but it breaks
            the specific narrative arc the script is timed around, so
            don't ad lib around it live.
```

### Screen 5 — Fresh re-evaluation [~2:20-2:40, the killer moment]

```
EXPECTED:
  Building a brand-new graph from the changed state -- no Python object
  carries anything over from Screen 2's call.

  Fresh Recovery decision: DO_NOT_RETRY
  Reason:                  payment pay_XXXXXXXXXX is not currently failed
                            (status='success') -- nothing to recover
PROVES:     The entire pitch's thesis in one line. Say the killer line
            from PITCH_SCRIPT.md right after this prints: "Nobody told
            this second call the first attempt succeeded."
FALLBACK:   This step cannot meaningfully fail if Screen 4 succeeded --
            it's a pure function of the state Screen 4 just wrote. If it
            somehow doesn't say DO_NOT_RETRY, that's a real bug, not a
            demo-luck problem -- stop the recording, don't narrate around it.
```

### Supporting view — one shared world [~4:05-4:35 in PITCH_SCRIPT.md]

```
EXPECTED:
  Payment pay_XXXXXXXXXX -- multiple agents, same real payment, real
  disagreement:

    RISK:       HOLD  (score=0.NN)  (device-sharing evidence)
    RECOVERY:   RETRY (score=0.NN)  (category base rate)
    -- or, depending on which real conflict is found first this run,
       CONTROLLER: INVESTIGATE + RISK: HOLD instead

  CONFLICT DETECTED (not silently averaged away):
    - <the specific cross-domain conflict rule that fired>
PROVES:     Not three disconnected verdicts on three unrelated entities --
            two independent, correct agents reasoning about the SAME real
            payment and disagreeing, found live via the identical
            detect_conflicts() logic Phase 8's 1000-payment batch run
            uses (financial_system/orchestrator/compound_case.py), not a
            hardcoded example. This is the live version of the "25 real
            cross-domain conflicts" figure spoken earlier in the pitch --
            the strongest available evidence for "one shared world," not
            three separate demos glued together.
FALLBACK:   The conflict search re-scans this same fixed dataset every
            run and is deterministic (confirmed identical across two
            consecutive runs) -- it should not vary. If it ever prints
            "no cross-domain conflict found in this scan" instead (only
            possible after an unrelated dataset regeneration), that's the
            code's own graceful fallback to three independent verdicts --
            narrate generically rather than improvising, same as before.
```

## What to type, in order, during the recording

```bash
python -m financial_system.demo
```

That's the only command. Do not type anything else during the 1:10-2:40
block — no `cd`, no editor, no second terminal. One command, one
continuous scroll of real output, narrated live against
`PITCH_SCRIPT.md`.

## The prevalidated fallback

If the live command fails for any reason (network hiccup unrelated to
this script since it makes none, a terminal resize, anything) — do not
improvise a replacement demo. Have a full transcript of a successful run
saved as `financial_system/data/demo_transcripts/reference_run.txt`
*before* recording, generated by running `python -m financial_system.demo
> financial_system/data/demo_transcripts/reference_run.txt` once ahead of
time, and be ready to say: "here's the same run, captured a moment ago,"
and scroll through the saved file instead. It's the same real output,
same code, same claim — a saved successful run of a script that makes
zero network calls is a legitimate fallback; a live improvisation is not.

## What changes the specific payment ID between runs

Only regenerating the dataset (`python -m financial_system.data_generator.generate_dataset`)
changes which specific `pay_...`/`sett_...`/`dev_...` IDs appear — IDs are
`uuid4()`-based, not seeded, so a regeneration produces new IDs even at
the same seed, though the aggregate statistics (840/160 split, 610
settlements, etc.) stay the same. **Do not regenerate the dataset between
capturing the reference transcript and recording the pitch** — that would
make the fallback transcript's IDs disagree with a live re-run, which is
avoidable and easy to get wrong under time pressure. Generate once, then
leave `financial_system/data/raw/` untouched through choreography,
recording, and submission.
