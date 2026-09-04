/* Static page content -- real numbers, real formulas, real field names,
   pulled directly from the actual source files (financial_system/recovery/
   signals.py, risk/scoring.py, reconciliation/deterministic.py,
   discovery_adapter/models.py). Nothing here is invented for the page. */

const WORLD = { persons:400, merchants:25, devices:371, orders:1000, payments:1000,
                settlements:610, banktx:633, instruments:513, fees:840, refunds:84 };

function money(n){ return '₹' + Number(n).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}); }

function homeHTML(){ return `
<section class="hero">
  <div class="hero-grid">
    <div>
      <div class="section-label">FINANCIAL INTELLIGENCE &amp; ACTION SYSTEM<span class="line"></span></div>
      <h1>A payment isn't a row.<br>It's a chain of <em>events</em>.</h1>
      <p class="hero-lede">Heimdall watches a causal financial world &mdash; not a spreadsheet. Risk, Recovery, and Controller reason over one shared graph, decide deterministically, act, and verify what actually happened. This site calls the real backend live: nothing you click here is a pre-baked answer.</p>
      <div class="hero-cta">
        <button class="btn btn-primary" onclick="go('live')">OPEN THE LIVE SYSTEM &rarr;</button>
        <button class="btn btn-ghost" onclick="go('docs')">READ THE DOCUMENTATION</button>
      </div>
    </div>
    <div class="loop">
      <div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title">// THE CLOSED LOOP</div>
      <div class="loop-stage world"><span class="dot"></span><span class="label">World &mdash; Truman</span><span class="tag">causal</span></div>
      <div class="loop-stage"><span class="dot"></span><span class="label">Observation</span><span class="tag">bridge</span></div>
      <div class="loop-stage control"><span class="dot"></span><span class="label">Risk / Recovery / Controller</span><span class="tag">Heimdall</span></div>
      <div class="loop-stage"><span class="dot"></span><span class="label">Policy &rarr; Action</span><span class="tag">deterministic</span></div>
      <div class="loop-stage world"><span class="dot"></span><span class="label">World updated</span><span class="tag">real outcome</span></div>
      <div class="loop-ret">&#8635; re-observed on the next tick &mdash; no memory carried in code</div>
    </div>
  </div>
</section>
<section>
  <div class="section-label">THIS RUN, EXACTLY<span class="line"></span></div>
  <h2 class="sec-title">The real, frozen judged dataset</h2>
  <p class="sec-sub">Every number below is a live count from <code>financial_graph.db</code>, the same graph the Live System page queries on every click.</p>
  <div class="statrow">
    <div class="stat"><div class="n">${WORLD.persons}</div><div class="l">customers</div></div>
    <div class="stat"><div class="n">${WORLD.merchants}</div><div class="l">merchants</div></div>
    <div class="stat"><div class="n">${WORLD.devices}</div><div class="l">devices</div></div>
    <div class="stat"><div class="n">${WORLD.payments}</div><div class="l">payments</div></div>
    <div class="stat"><div class="n">${WORLD.settlements}</div><div class="l">settlements</div></div>
    <div class="stat"><div class="n">${WORLD.banktx}</div><div class="l">bank transactions</div></div>
  </div>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:10px;">// HOW THIS SITE IS WIRED</div>
    <p style="font-size:13px; color:var(--muted); line-height:1.7;">This page is static (GitHub Pages). The Live System page calls a small FastAPI backend that imports <code>financial_system</code>'s real, unmodified decision modules directly and queries the real database on every request &mdash; there is no cache and no precomputed answer file anywhere in this repo. Its <b style="color:#fff;">TRUMAN LIVE</b> toggle goes further: a real, seeded simulation ticking forward in the backend's memory, one real day at a time &mdash; see <a href="#" onclick="go('truman'); return false;">Truman</a> for how that actually works. The chat panel calls your chosen LLM provider using a key you provide yourself in Settings; we never see or store it.</p>
  </div>
</section>`; }

function trumanHTML(){ return `
<section class="hero" style="padding-top:48px;">
  <div class="section-label">PROJECT TRUMAN &mdash; THE WORLD SIMULATOR<span class="line"></span></div>
  <h2 class="sec-title">Why it exists</h2>
  <p class="sec-sub" style="max-width:76ch;">Heimdall's own synthetic-data generator produces payment failures from a per-category coin flip: <code>retry_would_succeed = random.random() &lt; spec["retry_success_p"]</code>, with zero connection to any customer's actual financial state. Truman (<code>Simulation/</code>) exists to answer one question: what does Recovery look like when failures emerge <em>causally</em> from a person's real balance and income, instead of a dice roll?</p>
</section>
<section>
  <div class="section-label">HOW IT'S STRUCTURED<span class="line"></span></div>
  <h2 class="sec-title">Agents, mechanisms, engine</h2>
  <div class="subsys-grid">
    <div class="subsys">
      <h3>Agents</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">Person, Bank, Merchant, Device agents with real state: a person has a real balance, a monthly income, a household, and a purchase history that accrues over the run. Nothing about a person's behavior is scripted per-transaction &mdash; each purchase attempt checks the agent's <em>current</em> balance against the attempt amount.</p>
    </div>
    <div class="subsys">
      <h3>Mechanisms</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">A Mechanism is a full transition process with multiple possible outcomes &mdash; not a single failure mode. Two are formalized and tested (70/70 tests, byte-identical determinism): <b style="color:#fff;">instrument validity</b> (checked first &mdash; an expired card fails before balance is even read) and <b style="color:#fff;">funds authorization</b> (checked second, only if the instrument is valid). This ordering is itself part of the modeled process, matching how a real card network actually authorizes a transaction.</p>
    </div>
    <div class="subsys">
      <h3>Engine</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">A deterministic, seeded tick loop. The same seed reproduces the same world byte-for-byte &mdash; verified across every layer that was tested, including the live bridge loop (two independent runs, identical down to which retries were attempted and their outcomes).</p>
    </div>
  </div>
</section>
<section>
  <div class="section-label">THE HEADLINE RESULT<span class="line"></span></div>
  <h2 class="sec-title">A real, monotonic failure curve</h2>
  <p class="sec-sub" style="max-width:76ch;">Bucketing purchase attempts by balance/income ratio produces a clean, monotonic 96%&rarr;0% failure-rate curve, reproduced across three seeds &mdash; real evidence the causal approach works, not asserted. Two concrete failures, same world:</p>
  <div class="grid2">
    <div class="txn-card"><div class="corner tl"></div><div class="corner br"></div>
      <div class="txn-head"><span class="txn-id">insufficient_funds example</span><span class="pill pill-critical">FAILED</span></div>
      <div class="pipeline">
        <div class="pstage pass"><span class="idx">1</span><span class="name">Instrument validation</span><span class="result">VALID</span></div>
        <div class="pstage fail"><span class="idx">2</span><span class="name">Funds authorization</span><span class="result">balance &lt; amount</span></div>
      </div>
    </div>
    <div class="txn-card"><div class="corner tl"></div><div class="corner br"></div>
      <div class="txn-head"><span class="txn-id">expired_instrument example</span><span class="pill pill-warn">FAILED</span></div>
      <div class="pipeline">
        <div class="pstage fail"><span class="idx">1</span><span class="name">Instrument validation</span><span class="result">EXPIRED</span></div>
        <div class="pstage skip"><span class="idx">2</span><span class="name">Funds authorization</span><span class="result">not reached &mdash; would have succeeded</span></div>
      </div>
    </div>
  </div>
</section>
<section>
  <div class="section-label">THE BRIDGE<span class="line"></span></div>
  <h2 class="sec-title">Connecting Truman to Heimdall</h2>
  <p class="sec-sub" style="max-width:76ch;">One-directional and additive: Truman has zero knowledge Heimdall exists. <code>financial_system/bridges/</code> reads a finished Truman world, transforms it into Heimdall's real schema, and calls Heimdall's actual decision code &mdash; batch, or <b style="color:#fff;">live</b>, mid-simulation. In the live loop, a real RETRY decision causes Truman to actually re-attempt the purchase against the person's real, current balance: proven non-magical &mdash; a retry against a still-insufficient balance honestly fails again.</p>
  <p class="sec-sub" style="max-width:76ch;">A drift detector then checks Heimdall's live decisions against Truman's own <em>known</em> generative process &mdash; the one advantage a built simulator has over a real dataset. It already found one real, statistically significant case (p=2.6&times;10&#8315;&#8310;): Recovery's stated 45% confidence for <code>insufficient_funds</code> didn't match Truman's realized 0% retry-success rate in the live loop &mdash; traced to the loop's fixed 1-day retry window colliding with Truman's monthly-payday-only income model, not a flaw in Heimdall's own logic.</p>
</section>
<section>
  <div class="section-label">TRY IT LIVE<span class="line"></span></div>
  <h2 class="sec-title">This isn't just described &mdash; it's running</h2>
  <p class="sec-sub" style="max-width:76ch;">The <a href="#" onclick="go('live'); return false;">Live System</a> page has a <b style="color:#fff;">TRUMAN LIVE</b> toggle, backed by <code>api/truman_env.py</code>: one real, seeded <code>SimulationEngine</code> held in the backend's own memory, ticked forward one real day at a time on request &mdash; not a script that runs to completion once and hands back a static result.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:10px;">// WHAT "ADVANCE ONE DAY" ACTUALLY DOES</div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Any retry scheduled for today executes first</span><span class="tag">engine.attempt_retry()</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">The world ticks one real day forward</span><span class="tag">engine.run_one_tick()</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">The graph is rebuilt from the new state</span><span class="tag">the same pipeline the batch bridge uses</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Every new failed payment is scored by Recovery</span><span class="tag">a real RETRY schedules a real re-attempt tomorrow</span></div>
    <div class="loop-stage" style="border:none;"><span class="dot"></span><span class="label">Every device with new activity is scored by Risk</span><span class="tag">a real HOLD calls engine.block_device() &mdash; a mechanical consequence, not a log line</span></div>
  </div>
  <p class="sec-sub" style="max-width:76ch; margin-top:16px;">Stated honestly, not discovered by poking at it: this environment is <b style="color:#fff;">ephemeral</b> &mdash; it lives in the backend's memory and resets to day 0 whenever the free-tier server restarts. Its scope is <b style="color:#fff;">Recovery and Risk only</b>, the two domains with a proven live loop; Controller has no live loop yet, so Truman Live has no Settlement cases, and the Sub-Agent Investigation phase is skipped here because no live investigation endpoint exists yet. A freshly-started environment begins with zero failed payments and zero eligible devices &mdash; advance a few days to let real cases actually appear.</p>
</section>
<section>
  <div class="section-label">METHODOLOGY<span class="line"></span></div>
  <h2 class="sec-title">Cited where grounded, labeled where not</h2>
  <p class="sec-sub" style="max-width:76ch;">Every constant in Truman is tagged one of three ways in <code>Simulation/docs/Research.md</code>: grounded in a cited source, a named modeling assumption, or an uncited placeholder. Nothing is silently upgraded from one tier to another.</p>
  <div style="overflow-x:auto;"><table class="doctable"><thead><tr><th>Constant</th><th>Status</th><th>Source</th></tr></thead><tbody>
    <tr><td>Income log-normal shape</td><td>Grounded</td><td>Aitchison &amp; Brown 1957; cross-checked against a Pareto-lognormal income study and Schield 2018</td></tr>
    <tr><td>Settlement delay (T+1)</td><td>Grounded, simplification named</td><td>Stripe's own published 1&ndash;3 business day settlement window &mdash; kept at the conservative end rather than sampled, to avoid perturbing the run's RNG sequence</td></tr>
    <tr><td>Card validity window (3&ndash;5 yrs)</td><td>Grounded</td><td>WalletHub and Capital One's published card-expiration ranges</td></tr>
    <tr><td>Savings-sweep fraction (15%)</td><td>Named assumption</td><td>The popular "50/30/20" budgeting rule (Elizabeth Warren, <i>All Your Worth</i>, 2005) &mdash; a defensible round number, not independently verified</td></tr>
    <tr><td>Fraud rate (future work, not yet built)</td><td>Grounded</td><td>Kansas City Fed: 17.6bps of transaction value in 2023, up from 7.8bps in 2011</td></tr>
    <tr><td>Household size weights</td><td>Placeholder</td><td>No citation search was performed &mdash; labeled, not hidden</td></tr>
  </tbody></table></div>
  <div class="panel" style="margin-top:16px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:8px;">// A NUMBER WE FOUND AND DELIBERATELY DID NOT ADOPT</div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">A wage-inequality paper reports &sigma;&approx;0.5 for log wages &mdash; almost exactly this project's own <code>INCOME_LOGNORMAL_SIGMA=0.5</code>. It wasn't cited: the source PDF couldn't be independently verified, and wage dispersion isn't quite the same population as "income from all sources, across every adult." A tempting coincidence isn't evidence.</p>
  </div>
  <div class="panel" style="margin-top:16px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:8px;">// A NEGATIVE RESULT, KEPT NOT DELETED</div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">Bucketing purchase failures by income group alone shows almost no signal &mdash; below-median-income persons actually failed <i>less</i> often (0.94% vs 1.15%). The real driver is a person's balance/income <i>ratio</i> at the moment of purchase, not income level by itself &mdash; the monotonic 96%&rarr;0% curve above is the ratio-bucketed version. The income-only result stays in the record because a hypothesis that fails one honest test and succeeds under another is more credible than one only ever tested the way that worked.</p>
  </div>
  <div class="panel" style="margin-top:16px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:8px;">// AN ALTERNATIVE DESIGN, TRIED AND REJECTED</div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">The live Recovery loop's first working version sampled a small fixed number of new failures per checkpoint at the batch bridge's usual ~300-person scale, to keep LLM cost bounded. That's still cherry-picking out of a large population &mdash; caught in review, not after shipping &mdash; and fixed by shrinking the world instead of filtering the stream: a smaller population (20&ndash;50 people) where every real failure gets a real decision. The fix solved the honesty problem and the performance problem at the same time.</p>
  </div>
</section>
<section>
  <div class="section-label">MATURITY, STATED HONESTLY<span class="line"></span></div>
  <h2 class="sec-title">What's real vs. still a diagram</h2>
  <div class="roadgrid">
    <div>
      <div class="section-label" style="color:var(--good);">SOLID<span class="line"></span></div>
      <p style="font-size:12px; color:var(--muted); line-height:1.7;">The causal mechanism itself, double-entry ledger correctness, determinism at every tested layer, the zero-impact boundary against Heimdall's frozen code.</p>
    </div>
    <div>
      <div class="section-label" style="color:var(--warn);">GENUINELY UNCALIBRATED<span class="line"></span></div>
      <p style="font-size:12px; color:var(--muted); line-height:1.7;">Most of Truman's specific constants are labeled, honest modeling assumptions &mdash; not verified against real data. <code>Simulation/docs/Research.md</code> documents exactly which numbers are cited and which were rejected for failing verification.</p>
    </div>
    <div>
      <div class="section-label" style="color:var(--hud);">REAL, SMALL-SCALE<span class="line"></span></div>
      <p style="font-size:12px; color:var(--muted); line-height:1.7;">The live loop has only been run against small populations (20&ndash;50 people) &mdash; not stress-tested at the batch bridge's scale (hundreds of people, thousands of transactions).</p>
    </div>
    <div>
      <div class="section-label" style="color:var(--critical);">NOT BUILT<span class="line"></span></div>
      <p style="font-size:12px; color:var(--muted); line-height:1.7;">Fraud, credit, and loan mechanics are cited design proposals only. Controller has no live loop yet.</p>
    </div>
  </div>
</section>`; }

function discoveryHTML(){ return `
<section class="hero" style="padding-top:48px;">
  <div class="section-label">DISCOVERY.AI INSIDE HEIMDALL<span class="line"></span></div>
  <h2 class="sec-title">The one rule that makes this not-a-wrapper</h2>
  <p class="sec-sub" style="max-width:76ch;">Discovery.AI is a recursive investigation engine (a separate, larger project the same team built &mdash; see <a href="https://discovery-ai-ashen.vercel.app/" target="_blank" rel="noopener">discovery-ai-ashen.vercel.app</a>). Inside Heimdall it's wired through one narrow adapter, <code>financial_system/discovery_adapter/</code>, under one non-negotiable rule: <b style="color:#fff;">it is invoked only when deterministic evidence genuinely runs out, and its output can never become the decision.</b></p>
</section>
<section>
  <div class="section-label">THE CONTRACT<span class="line"></span></div>
  <h2 class="sec-title">InvestigationRequest &rarr; InvestigationResult</h2>
  <p class="sec-sub" style="max-width:76ch;">A domain agent (today: Controller) sends a plain-language question plus what it already knows deterministically. Discovery.AI returns a typed result &mdash; not prose the agent has to parse:</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="kv" style="grid-template-columns:1fr; gap:14px;">
      <div><div class="k">status</div><div class="v" style="font-weight:400; font-size:12.5px; color:var(--muted);"><code>EXPLAINED</code> / <code>PARTIALLY_EXPLAINED</code> / <code>UNEXPLAINED</code> &mdash; Discovery.AI's own read; logged for comparison, never substituted for Controller's own status.</div></div>
      <div><div class="k">inferences vs. hypotheses</div><div class="v" style="font-weight:400; font-size:12.5px; color:var(--muted);">Narrative connections it actually drew (<code>inferences</code>) are kept separate from uninvestigated claims (<code>hypotheses</code>) &mdash; a hypothesis is never silently promoted to a fact.</div></div>
      <div><div class="k">investigation_confidence</div><div class="v" style="font-weight:400; font-size:12.5px; color:var(--muted);">A float, carried on the verdict for audit only. <code>AgentVerdict</code>'s <code>decision</code> and <code>proposed_action</code> fields are computed before this even exists, and nothing downstream reads it to decide anything.</div></div>
      <div><div class="k">decompose_steps</div><div class="v" style="font-weight:400; font-size:12.5px; color:var(--muted);">A multi-step trace &mdash; each step's action, reasoning, and sub-question/answer &mdash; up to a step budget the <em>calling agent</em> owns, not the model.</div></div>
    </div>
  </div>
</section>
<section>
  <div class="section-label">THE PROOF, NOT JUST THE CLAIM<span class="line"></span></div>
  <h2 class="sec-title">A real adversarial test</h2>
  <p class="sec-sub" style="max-width:76ch;">A fabricated <code>investigation_confidence</code> of 0.99 cannot authorize an action whose deterministic <code>decision_score</code> is only 0.20 &mdash; because <code>PolicyDecision</code> has no field for investigation confidence at all. That's a structural boundary, not a convention a future change could quietly erode.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="verdict-metric" style="border-top:none; padding-top:0;"><span class="k">Investigations actually called, the judged run</span><span class="v">0 / 610</span></div>
    <p class="verdict-note">Not a limitation &mdash; every settlement in that run had a clean, deterministic explanation. Discovery.AI is a fallback for genuine uncertainty, not a step every case passes through.</p>
  </div>
</section>
<section>
  <div class="section-label">ALTERNATIVES CONSIDERED, AND REJECTED<span class="line"></span></div>
  <h2 class="sec-title">Why not just let the model decide?</h2>
  <p class="sec-sub" style="max-width:76ch;">Discovery.AI ships its own <code>GroundAgent</code> with a hardcoded default retriever set. Reusing it directly was considered and rejected: it would mean either patching Discovery.AI's own source, or silently letting web retrievers answer financial questions &mdash; neither acceptable. <code>discovery_adapter/</code> exists specifically so exactly one narrow module touches Discovery.AI's internals, grounded only in this project's own real financial state.</p>
  <p class="sec-sub" style="max-width:76ch;">The deterministic pass always runs first, and the model is never handed raw ledger numbers to do arithmetic on &mdash; an explicit design decision, not an oversight: a model asked "why do these differ" free-associates onto the first plausible-looking fact it sees, as the incident below shows.</p>
</section>
<section>
  <div class="section-label">A REAL BUG THE TESTS CAUGHT<span class="line"></span></div>
  <h2 class="sec-title">An unanchored question, and the fix</h2>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">An early smoke test asked Discovery.AI an unanchored "why do these differ" question. It pattern-matched onto the first fee/tax fact in view and reported 0.75 confidence in a cause that was off by <b style="color:#fff;">29&times;</b> &mdash; a real gap of &#8377;456.92 explained by a &#8377;15.74 fee. The fix: name the exact unexplained amount in the question itself, turning free association into a falsifiable check the model can actually fail correctly on.</p>
  </div>
  <p class="sec-sub" style="max-width:76ch; margin-top:16px;"><b style="color:var(--warn);">Stated honestly:</b> the investigation loop's step budget (<code>MAX_STEPS=3</code>) is deliberately owned by the calling agent, not the model &mdash; but the specific number 3, versus 2 or 5, has no documented derivation in this repo.</p>
</section>`; }

function heimdallHTML(){ return `
<section class="hero" style="padding-top:48px;">
  <div class="section-label">HEIMDALL &mdash; THE THREE DOMAINS<span class="line"></span></div>
  <h2 class="sec-title">Every tool each agent actually has</h2>
  <p class="sec-sub" style="max-width:76ch;">Each domain below is a small, auditable set of graph queries and arithmetic &mdash; the exact weights and thresholds a judge (or the Live System page) can read and argue with. Discovery.AI never touches any of this.</p>
</section>
<section>
  <div class="subsys-grid">
    <div class="subsys">
      <h3 style="color:var(--good);">Recovery &mdash; a decline-code lookup</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">Reads the payment's <code>status</code> and <code>failure_reason</code>, checks whether a sibling payment on the same order already succeeded (never retry into a duplicate charge), then looks the failure category up in a real gateway decline-code taxonomy:</p>
      <div style="overflow-x:auto; margin-top:10px;"><table class="doctable"><thead><tr><th>failure_reason</th><th>recoverable</th><th>action</th><th>base_success_rate</th></tr></thead><tbody>
        <tr><td>technical_failure</td><td>yes</td><td>RETRY_PAYMENT</td><td>85%</td></tr>
        <tr><td>timeout</td><td>yes</td><td>RETRY_PAYMENT</td><td>80%</td></tr>
        <tr><td>authentication_failure</td><td>yes</td><td>RETRY_ALT_METHOD</td><td>55%</td></tr>
        <tr><td>insufficient_funds</td><td>yes</td><td>RETRY_LATER</td><td>45%</td></tr>
        <tr><td>issuer_declined</td><td>yes</td><td>RETRY_ALT_METHOD</td><td>20%</td></tr>
        <tr><td>risk_block</td><td>no</td><td>MANUAL_REVIEW</td><td>0%</td></tr>
        <tr><td>expired</td><td>no</td><td>REQUEST_CUSTOMER_ACTION</td><td>0%</td></tr>
      </tbody></table></div>
      <div class="tools">
        <span class="tool-chip">edges_from(payment, "belongs_to")</span>
        <span class="tool-chip">edges_to(order, "belongs_to")</span>
        <span class="tool-chip">FAILURE_TAXONOMY lookup</span>
      </div>
      <div style="margin-top:14px; padding-top:12px; border-top:1px dashed var(--border);">
        <div class="loop-title" style="margin-bottom:6px;">// WHY THIS DESIGN, NOT A CLASSIFIER</div>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7;">The real question isn't "should we retry failed payments" &mdash; it's which failures are worth retrying, reliably, not by guessing. Recovery keeps two things separate on purpose: whether a <em>category</em> is recoverable at all, and whether <em>this instance</em> would actually succeed &mdash; the second is genuinely unknown, so <code>decision_score</code> stays the category's own historical base rate, stated as a base rate, never dressed up as a per-instance prediction.</p>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:8px;"><b style="color:var(--warn);">Stated honestly:</b> these seven base rates are asserted as "a real gateway's own decline-code taxonomy," not independently derived from external gateway data in this repo &mdash; and they are the identical values <code>data_generator/generate_dataset.py</code> uses to <em>generate</em> the synthetic ground truth. The taxonomy is internally consistent with this dataset by construction, not separately validated against a real payment processor.</p>
      </div>
    </div>
    <div class="subsys">
      <h3 style="color:var(--hud);">Risk &mdash; a weighted device score</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">Only runs on a device shared by 2+ customers (a lone-owner device carries no network signal). Four signals, one weighted sum:</p>
      <div style="overflow-x:auto; margin-top:10px;"><table class="doctable"><thead><tr><th>signal</th><th>weight</th><th>what it measures</th></tr></thead><tbody>
        <tr><td>burst_density</td><td>0.50</td><td>most payments inside any single 60-minute window (a real burst survives even a noisy history)</td></tr>
        <tr><td>burst_amount_clustering</td><td>0.30</td><td>coefficient of variation of amounts inside that same densest window</td></tr>
        <tr><td>n_sharers</td><td>0.15</td><td>how many distinct customers used this device</td></tr>
        <tr><td>account_age</td><td>0.05</td><td>weighted low on purpose &mdash; verified against the real generator to NOT discriminate ring membership here</td></tr>
      </tbody></table></div>
      <p style="font-size:12px; color:var(--muted-2); margin-top:8px;"><code>score &ge; 0.6</code> &rarr; HIGH &rarr; HOLD_PAYMENT &middot; <code>score &ge; 0.3</code> &rarr; MEDIUM &rarr; MANUAL_REVIEW &middot; else LOW &rarr; RELEASE.</p>
      <div class="tools">
        <span class="tool-chip">edges_to(device, "used_device")</span>
        <span class="tool-chip">densest_window(60min)</span>
        <span class="tool-chip">score_signals() weighted sum</span>
      </div>
      <div style="margin-top:14px; padding-top:12px; border-top:1px dashed var(--border);">
        <div class="loop-title" style="margin-bottom:6px;">// WHY THESE WEIGHTS, NOT A TRAINED MODEL</div>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7;">Deterministic on purpose &mdash; every weight here is a number a fraud analyst can read and argue with. The weights aren't a prior: <code>account_age</code> sits at 0.05 because it was checked against the real generator and verified to <em>not</em> differ between fraud-ring and normal accounts in this dataset &mdash; real-world meaningful, but not pretended to carry signal it doesn't have here. <code>n_sharers</code> alone is also true of an ordinary shared family device (the dataset plants exactly this trap on purpose), so it stays a moderate 0.15. Burst density and amount-clustering carry the real weight (0.50 + 0.30) because they're what the fraud-ring generator actually encodes &mdash; scored over the <em>densest</em> 60-minute window rather than a total-payments/span ratio, since a ring member's other, ordinary purchases on the same shared device would otherwise dilute that ratio to near-zero.</p>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:8px;"><b style="color:var(--warn);">Stated honestly:</b> the two tier cutoffs (0.3, 0.6) and the 60-minute window's margin over the generator's actual 45-minute burst span have no documented derivation in this repo &mdash; working values, not the output of a calibration study.</p>
      </div>
    </div>
    <div class="subsys">
      <h3 style="color:var(--warn);">Controller &mdash; reconciliation arithmetic</h3>
      <p style="font-size:13px; color:var(--muted); line-height:1.7;">Sums the real bank transactions deposited against a settlement, compares to the settlement's own expected <code>net_amount</code> (tolerance &#8377;1.00). If a real gap exists, checks one case-general explanation before escalating: does any payment appear more than once under this settlement's <code>contains</code> edges (a genuine duplicate line item)?</p>
      <p style="font-size:12px; color:var(--muted-2); margin-top:8px;">No gap &rarr; PASS &middot; gap fully explained by a duplicate &rarr; RESOLVE/ADJUST &middot; partially explained &rarr; REVIEW &middot; still unexplained &rarr; INVESTIGATE (Discovery.AI may be asked; its answer never overrides this).</p>
      <div class="tools">
        <span class="tool-chip">edges_from(settlement, "deposited_as")</span>
        <span class="tool-chip">edges_from(settlement, "contains")</span>
        <span class="tool-chip">Counter() duplicate detection</span>
      </div>
      <div style="margin-top:14px; padding-top:12px; border-top:1px dashed var(--border);">
        <div class="loop-title" style="margin-bottom:6px;">// WHY ONE CHECK, NOT NINE</div>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7;">This dataset's real ground truth has 9 distinct settlement-gap root causes &mdash; duplicate records, partial refunds, currency conversion, missing settlements, bank adjustments, split settlements, fee discrepancies, timing skew, and clean matches. Controller's deterministic check handles exactly one &mdash; duplicate line items &mdash; chosen because it's case-general, not overfit to one anomaly's specific mechanics. The other eight are left to Discovery.AI's narrative or reported unresolved, on purpose: this is <em>operational</em> reconciliation (did the money that should have arrived, arrive), not a full <em>accounting</em> reconciliation (a global debits-equal-credits invariant) &mdash; a named boundary, not an oversight, since the larger claim would need a double-entry subsystem this project doesn't have.</p>
        <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:8px;"><b style="color:var(--warn);">Stated honestly:</b> the &#8377;1.00 reconciliation tolerance has no documented derivation in this repo &mdash; a working constant, not a calibrated one.</p>
      </div>
    </div>
  </div>
</section>
<section>
  <div class="section-label">PROVEN RESULTS<span class="line"></span></div>
  <h2 class="sec-title">On the real, frozen judged dataset</h2>
  <div style="overflow-x:auto;"><table class="doctable"><thead><tr><th>Metric</th><th>What it means</th><th>Proof</th></tr></thead><tbody>
    <tr><td>100% precision / 96.3% recall / 0% FPR</td><td>Fraud-ring device detection, including 16 planted benign traps</td><td>risk/runner.py</td></tr>
    <tr><td>100% recovery rate (87/87)</td><td>Every recoverable-category case correctly attempted</td><td>recovery/runner.py</td></tr>
    <tr><td>39.6% false-retry rate</td><td>Matches categories' weighted historical base rate (39.3% expected)</td><td>recovery/runner.py</td></tr>
    <tr><td>555/610 settlement match (91.0%)</td><td>Zero LLM calls, holds with or without Discovery.AI enabled</td><td>reconciliation/runner.py</td></tr>
    <tr><td>47/50 honest-exception rate (94.0%)</td><td>Genuinely unexplainable cases left unresolved, not guessed at</td><td>reconciliation/runner.py</td></tr>
    <tr><td>77/610 settlements</td><td>A real accounting gap (gross &minus; fee &minus; tax &ne; net) found by this project</td><td>accounting_consistency_test.py</td></tr>
  </tbody></table></div>
</section>`; }

function docsHTML(){ return `
<section class="hero" style="padding-top:48px; padding-bottom:28px;">
  <div class="section-label">DOCUMENTATION<span class="line"></span></div>
  <h2 class="sec-title">The system, in full</h2>
  <p class="sec-sub">Real decision loop, real proof files, real incidents, honest limitations. For the per-domain formulas (Recovery's taxonomy, Risk's weights, Controller's arithmetic), see the <a href="#" onclick="go('heimdall'); return false;">Heimdall</a> page &mdash; this page covers the architecture and the whole-system claims.</p>
</section>
<section>
  <div class="section-label">ARCHITECTURE<span class="line"></span></div>
  <h2 class="sec-title">Three separately-buildable systems, one shared story</h2>
  <div class="panel" style="margin-bottom:20px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="grid3" style="margin-bottom:0;">
      <div><div style="font-weight:700; font-size:14px; color:var(--good); margin-bottom:6px;">1&nbsp;&middot;&nbsp;TRUMAN</div>
        <p style="font-size:12px; color:var(--muted); line-height:1.65;">A self-contained causal world simulator. Zero knowledge of Heimdall exists in its code.</p></div>
      <div><div style="font-weight:700; font-size:14px; color:var(--hud); margin-bottom:6px;">2&nbsp;&middot;&nbsp;THE BRIDGE</div>
        <p style="font-size:12px; color:var(--muted); line-height:1.65;">Transforms Truman's output into Heimdall's real schema and calls Heimdall's actual decision code, batch or live.</p></div>
      <div><div style="font-weight:700; font-size:14px; color:var(--warn); margin-bottom:6px;">3&nbsp;&middot;&nbsp;HEIMDALL + DISCOVERY.AI</div>
        <p style="font-size:12px; color:var(--muted); line-height:1.65;">Never knows or cares whether input came from Truman or the real dataset it was judged against.</p></div>
    </div>
  </div>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:14px;">// DATA FLOW, THIS WEBSITE</div>
    <div style="overflow-x:auto;"><pre style="font-family:var(--font-mono); font-size:11px; color:var(--muted); line-height:1.7; white-space:pre; margin:0;">Browser (GitHub Pages, static)
    |
    | fetch /api/recovery/{id}, /api/risk/{id}, /api/controller/{id}
    v
FastAPI backend (Render)
    |
    | imports financial_system.recovery.recovery_agent etc. directly
    v
Real, unmodified decision functions
    |
    | GraphRepository.get_node() / edges_from() / edges_to()
    v
financial_graph.db  (the real, frozen, judged dataset -- read-only)</pre></div>
  </div>
  <div class="panel" style="margin-top:20px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:14px;">// DATA FLOW, TRUMAN LIVE MODE</div>
    <div style="overflow-x:auto;"><pre style="font-family:var(--font-mono); font-size:11px; color:var(--muted); line-height:1.7; white-space:pre; margin:0;">Browser (TRUMAN LIVE toggle, Live System page)
    |
    | GET /api/truman/state, POST /api/truman/tick,
    | GET /api/truman/recovery/{id}, /api/truman/risk/{id}, /api/truman/graph/neighborhood/{id}
    v
FastAPI backend (Render)
    |
    | get_environment() -- one server-held, thread-locked TrumanEnvironment (api/truman_env.py)
    v
A real, seeded SimulationEngine (Simulation/world/engine.py)
    |
    | run_one_tick() / attempt_retry() / block_device() -- real engine methods, never re-implemented
    v
Rebuilt into financial_system's real graph schema on every tick,
then queried by the exact same recovery_agent.py / risk_agent.py the frozen-dataset mode calls</pre></div>
  </div>
</section>
<section>
  <div class="section-label">THE DECISION LOOP, ONE CONCRETE RUN<span class="line"></span></div>
  <h2 class="sec-title">What actually happens when a payment fails</h2>
  <p class="sec-sub">A payment fails with <code>technical_failure</code>. Recovery classifies the category as recoverable and proposes a retry, scored at the category's own historical success rate. Policy authorizes it. The action executes; the gateway reports success; that becomes a durable event. Recovery, asked about the <em>same payment</em> again from scratch, independently concludes there's nothing left to recover &mdash; it found out from the event log, not a special case.</p>
  <div class="panel" style="margin-bottom:0;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-stage"><span class="dot" style="background:var(--critical);"></span><span class="label">Payment failed</span><span class="tag">technical_failure</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Recovery signals</span><span class="tag">deterministic decline-code taxonomy</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--hud);"></span><span class="label">Investigation, if genuinely unrecognized</span><span class="tag">Discovery.AI, audit-only</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Decision</span><span class="tag">decision_score = category base rate</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Policy</span><span class="tag">deterministic rules; LLM confidence cannot authorize money</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--good);"></span><span class="label">Action</span><span class="tag">idempotent, durable, crash-safe</span></div>
    <div class="loop-stage" style="border:none;"><span class="dot" style="background:var(--good);"></span><span class="label">Fresh Recovery, asked again independently</span><span class="tag">correct, no special-case code</span></div>
  </div>
</section>
<section>
  <div class="section-label">REAL INCIDENTS THIS PROJECT'S OWN TESTS CAUGHT<span class="line"></span></div>
  <h2 class="sec-title">We caught our own architecture being wrong &mdash; on purpose</h2>
  <div class="grid3">
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// 1 &mdash; TIMING BACKWARDS</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">A replay test caught a decision's recorded "world state at the time" stamped <i>after</i> the action it authorized had executed &mdash; a stored RETRY replayed back as DO_NOT_RETRY. Fixed by moving the timestamp before the reasoning runs.</p>
    </div>
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// 2 &mdash; "WHY" VS "WHETHER"</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">After a successful retry, Recovery produced <code>"unrecognized failure_reason=None"</code>. It checked <i>why</i> a payment failed but never <i>whether</i> it still was. Fixed with a general status check.</p>
    </div>
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// 3 &mdash; WE CORRECTED OURSELVES</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">An early pass claimed 19/610 settlements had a real gap; the naive sum wasn't deduplicating a repeated line item. Corrected in the same document that made the original claim.</p>
    </div>
  </div>
</section>
<section>
  <div class="section-label">LIMITATIONS<span class="line"></span></div>
  <h2 class="sec-title">Stated up front, not discovered under questioning</h2>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <ul style="list-style:none; display:flex; flex-direction:column; gap:12px; margin:0; padding:0;">
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">Simulated gateway, not a live payment API.</b> The harness the architecture plugs a real gateway into.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">decision_score is a category base rate</b>, never a per-instance prediction. 0% false-retry would require an oracle.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">Not fully event-sourced.</b> "What did the system decide" is answerable only for decisions that led to a real, recorded action.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6;"><b style="color:#fff;">No general ledger.</b> Two targeted accounting checks exposed a real gap without building a second, unproven financial subsystem.</li>
    </ul>
  </div>
</section>
<section>
  <div class="section-label">REPRODUCTION<span class="line"></span></div>
  <h2 class="sec-title">Run it yourself</h2>
  <div class="panel" style="padding:18px 20px;"><div class="corner tl"></div><div class="corner br"></div>
    <div style="overflow-x:auto;"><pre style="font-family:var(--font-mono); font-size:11px; color:var(--muted); line-height:1.8; white-space:pre; margin:0;">python -m financial_system.data_generator.generate_dataset
python -m financial_system.financial_state.builder
python -m financial_system.entity_resolution.runner
python -m financial_system.financial_graph.builder
python -m financial_system.reconciliation.runner
python -m financial_system.risk.runner
python -m financial_system.recovery.runner

# this website's own backend, run locally:
PYTHONPATH=. uvicorn api.main:app --reload</pre></div>
  </div>
</section>
<section>
  <div class="section-label">THE UNDERLYING FILES<span class="line"></span></div>
  <h2 class="sec-title">The repository is the source of truth</h2>
  <div class="doclist">
    <div class="docrow"><span class="path">api/main.py</span><span class="desc">This site's backend &mdash; the exact file every Live System click calls.</span></div>
    <div class="docrow"><span class="path">api/truman_env.py</span><span class="desc">The live, ticking Truman environment TRUMAN LIVE mode calls &mdash; one real SimulationEngine, held in memory.</span></div>
    <div class="docrow"><span class="path">financial_system/recovery/signals.py</span><span class="desc">Recovery's real decline-code taxonomy.</span></div>
    <div class="docrow"><span class="path">financial_system/risk/scoring.py</span><span class="desc">Risk's real weighted formula.</span></div>
    <div class="docrow"><span class="path">financial_system/reconciliation/deterministic.py</span><span class="desc">Controller's real reconciliation arithmetic.</span></div>
    <div class="docrow"><span class="path">README.md</span><span class="desc">The submission itself.</span></div>
    <div class="docrow"><span class="path">docs/NORTH_STAR.md</span><span class="desc">Long-term vision, honestly tracked against what's real.</span></div>
    <div class="docrow"><span class="path">Simulation/README.md</span><span class="desc">Project Truman &mdash; built, tested, honestly uncalibrated.</span></div>
    <div class="docrow"><span class="path">financial_system/bridges/README.md</span><span class="desc">The Truman &harr; Heimdall bridge.</span></div>
  </div>
</section>`; }

function settingsHTML(){ return `
<section class="hero" style="padding-top:48px; padding-bottom:20px;">
  <div class="section-label">SETTINGS<span class="line"></span></div>
  <h2 class="sec-title">Your keys, your browser, nothing sent to us</h2>
  <p class="sec-sub" style="max-width:70ch;">Every field below is saved only in this browser's <code>localStorage</code>. A key is sent, per request, straight through our backend to that one provider and never written to disk or logged &mdash; the backend is a stateless proxy, not a key store. The chat tries Groq first, then Gemini, then Anthropic, using the first configured key that answers &mdash; add just one, or all three.</p>
</section>
<section>
  <div class="panel" style="margin-bottom:24px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="settings-form">
      <div>
        <label for="set-key-groq">Groq API key(s) &mdash; tried first, free tier</label>
        <input type="password" id="set-key-groq" placeholder="gsk_..., gsk_... (comma-separated for multiple)" autocomplete="off">
        <div class="settings-row" style="margin-top:6px;">
          <span id="badge-groq" class="badge badge-off">not set</span>
          <span style="font-size:11px; color:var(--muted-2);">Get one at <a href="https://console.groq.com/keys" target="_blank" rel="noopener">console.groq.com/keys</a></span>
        </div>
      </div>
      <div>
        <label for="set-key-gemini">Gemini API key(s) &mdash; tried second, free tier</label>
        <input type="password" id="set-key-gemini" placeholder="AIza..., AIza... (comma-separated for multiple)" autocomplete="off">
        <div class="settings-row" style="margin-top:6px;">
          <span id="badge-gemini" class="badge badge-off">not set</span>
          <span style="font-size:11px; color:var(--muted-2);">Get one at <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a></span>
        </div>
      </div>
      <div>
        <label for="set-key-anthropic">Anthropic API key(s) &mdash; tried last, paid</label>
        <input type="password" id="set-key-anthropic" placeholder="sk-ant-..., sk-ant-... (comma-separated for multiple)" autocomplete="off">
        <div class="settings-row" style="margin-top:6px;">
          <span id="badge-anthropic" class="badge badge-off">not set</span>
          <span style="font-size:11px; color:var(--muted-2);">Get one at <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">console.anthropic.com</a></span>
        </div>
      </div>
      <div>
        <label for="set-api-base">Backend URL (only change this if the default is down)</label>
        <input type="text" id="set-api-base" placeholder="${DEFAULT_API_BASE}">
      </div>
      <div class="settings-row">
        <span class="status-dot js-backend-dot"></span>
        <span class="js-backend-label" style="font-size:11px; color:var(--muted-2);">connecting…</span>
        <button class="btn btn-ghost" id="set-recheck" style="margin-left:auto; padding:6px 12px; font-size:11px;">RE-CHECK</button>
      </div>
      <div class="hero-cta">
        <button class="btn btn-primary" id="set-save">SAVE</button>
        <button class="btn btn-ghost" id="set-clear">CLEAR ALL KEYS</button>
      </div>
    </div>
  </div>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:8px;">// WHY BYOK, NOT A SHARED KEY</div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">This is a static GitHub Pages site with a free-tier backend &mdash; there's no account system and no budget for a shared LLM key every visitor could drain. Bringing your own key means the chat is genuinely yours: your usage, your rate limits, your bill. Multiple comma-separated keys for one provider let the chat fall through to the next key if one hits a rate limit, without you having to notice or intervene.</p>
  </div>
</section>`; }

const SETTINGS_PROVIDERS = ['groq', 'gemini', 'anthropic'];

function wireSettingsForm(){
  document.getElementById('set-recheck').addEventListener('click', pingBackend);
  document.getElementById('set-save').addEventListener('click', () => {
    Settings.apiBase = document.getElementById('set-api-base').value.trim();
    for(const p of SETTINGS_PROVIDERS){
      Settings.setKeys(p, document.getElementById('set-key-' + p).value.trim());
    }
    renderSettingsPage();
    pingBackend();
  });
  document.getElementById('set-clear').addEventListener('click', () => {
    for(const p of SETTINGS_PROVIDERS) Settings.setKeys(p, '');
    renderSettingsPage();
  });
}

function renderSettingsPage(){
  const base = document.getElementById('set-api-base');
  if(base) base.value = Settings.apiBase === DEFAULT_API_BASE ? '' : Settings.apiBase;
  for(const p of SETTINGS_PROVIDERS){
    const input = document.getElementById('set-key-' + p);
    const badge = document.getElementById('badge-' + p);
    const n = Settings.keys(p).length;
    if(input) input.value = Settings._keysRaw(p);
    if(badge){
      if(n === 1){ badge.textContent = 'key set'; badge.className = 'badge badge-ok'; }
      else if(n > 1){ badge.textContent = n + ' keys set'; badge.className = 'badge badge-ok'; }
      else{ badge.textContent = 'not set'; badge.className = 'badge badge-off'; }
    }
  }
}

function aboutHTML(){ return `
<section class="hero" style="padding-top:48px;">
  <div class="section-label">ABOUT THIS SUBMISSION<span class="line"></span></div>
  <h2 class="sec-title">The claim, stated precisely</h2>
  <p class="sec-sub" style="font-size:15.5px; color:var(--text); max-width:58ch;">We built a causal financial world, connected it to three decision domains, and demonstrated that decisions can act on that world and observe the resulting consequences &mdash; without contaminating the underlying financial state.</p>
  <p class="sec-sub">This website is a live window into that system, not a mockup of one: every verdict you see was computed by the real backend, on the real dataset, at the moment you clicked.</p>
</section>
<footer><p>PROJECT HEIMDALL &middot; AI REVENUE RECOVERY</p></footer>`; }
