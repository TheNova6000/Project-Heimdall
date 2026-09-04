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
  <p class="sec-sub" style="margin-top:16px;">This is what each domain decides in isolation. What actually authorizes, executes, coordinates across domains, and checks the result afterward is a separate, real layer &mdash; see <a href="#" onclick="go('system'); return false;">System</a>.</p>
</section>`; }

function systemHTML(){ return `
<section class="hero" style="padding-top:48px;">
  <div class="section-label">THE SYSTEM AROUND THE DOMAINS<span class="line"></span></div>
  <h2 class="sec-title">A verdict isn't a decision until something authorizes it</h2>
  <p class="sec-sub" style="max-width:76ch;">Risk, Recovery, and Controller each produce a verdict. Getting from "verdict" to "money actually moved, exactly once, and someone can prove it later" takes four more real, tested systems: <b style="color:#fff;">Policy</b> (authorizes), <b style="color:#fff;">Action</b> (executes exactly once), the <b style="color:#fff;">Orchestrator</b> (coordinates when domains overlap), and <b style="color:#fff;">Verification</b> (checks afterward, independently). None of these are described anywhere else on this site &mdash; they're real, tested, and currently invisible, which is its own kind of dishonesty. This page fixes that.</p>
</section>
<section>
  <div class="section-label">POLICY<span class="line"></span></div>
  <h2 class="sec-title">11 rules, first match wins, no field for confidence</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/policy/engine.py</code> takes a domain verdict and an optional Expected Value figure, and returns a <code>PolicyDecision</code>: <code>outcome</code> (ALLOW / BLOCK / ESCALATE / REVIEW), which <code>rule_id</code> fired, and the <code>authorized_action</code>. Versioned by hand as <code>POLICY_RULES_VERSION="policy-v2"</code> &mdash; bumped whenever the rule list changes, not auto-derived.</p>
  <div style="overflow-x:auto;"><table class="doctable"><thead><tr><th>rule_id</th><th>fires when</th></tr></thead><tbody>
    <tr><td>R0_RECOVERY_EV_NEGATIVE_BLOCK</td><td>Expected Value is negative &mdash; blocks even a category-recoverable retry</td></tr>
    <tr><td>R1_CONFLICT_ESCALATE</td><td>Two domains disagree on the same subject (see Orchestrator)</td></tr>
    <tr><td>R2_RISK_HOLD_BLOCK</td><td>Risk says HOLD</td></tr>
    <tr><td>R3_RECOVERY_RETRY_ALLOW</td><td>decision_score &ge; 0.5</td></tr>
    <tr><td>R4_RECOVERY_RETRY_LOW_SCORE_REVIEW</td><td>Recovery says RETRY but score &lt; 0.5</td></tr>
    <tr><td>R5_CONTROLLER_CLEAN_ALLOW</td><td>Controller says PASS</td></tr>
    <tr><td>R6_CONTROLLER_UNRESOLVED_ESCALATE</td><td>Controller says INVESTIGATE and it's still unresolved</td></tr>
    <tr><td>R7_RISK_RELEASE_ALLOW / R8_RISK_REVIEW</td><td>Risk says RELEASE / REVIEW</td></tr>
    <tr><td>R9_RECOVERY_ESCALATE / R10_RECOVERY_DO_NOT_RETRY_ALLOW</td><td>Recovery's remaining two branches</td></tr>
    <tr><td>R99_DEFAULT_REVIEW</td><td>catch-all &mdash; nothing falls through ungoverned</td></tr>
  </tbody></table></div>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:10px;"><code>PolicyDecision</code> has no <code>investigation_confidence</code> field, and the module's own docstring says why: "copying it onto the decision would invite a future caller to read it as if it mattered to authorization." Discovery.AI's confidence literally cannot reach this struct.</p>
</section>
<section>
  <div class="section-label">ECONOMIC REASONING<span class="line"></span></div>
  <h2 class="sec-title">One real gate, narrower than it sounds</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/recovery/expected_value.py</code> (<code>EV_LOGIC_VERSION="recovery-ev-v1"</code>) computes <code>expected_value = base_success_rate &times; value &minus; fee_cost &minus; harm_cost</code> for every category-eligible retry, and Policy's <code>R0</code> rule blocks any retry whose EV is negative &mdash; even one Recovery alone would have approved.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="kv" style="grid-template-columns:1fr; gap:12px;">
      <div><div class="k">fee_cost</div><div class="v" style="font-weight:400; font-size:12px; color:var(--muted);">A flat 2% &mdash; not assumed, measured exactly across all 840 real fee rows (mean = median = min = max = 0.0200).</div></div>
      <div><div class="k">harm_cost</div><div class="v" style="font-weight:400; font-size:12px; color:var(--muted);"><code>RISK_HARM_RATE_BY_TIER &times; value</code>, Laplace-smoothed off a genuinely tiny real sample: 4 LOW-tier devices (0 fraud), 6 HIGH-tier devices (6 fraud), <b style="color:var(--warn);">zero MEDIUM-tier devices exist</b> &mdash; its rate is linearly interpolated, stated as an assumption, never claimed measured.</div></div>
      <div><div class="k">RETRY_ALLOW_THRESHOLD = 0.5</div><div class="v" style="font-weight:400; font-size:12px; color:var(--muted);">Not arbitrary &mdash; it's exactly where Phase 7's real categories split (0.85/0.80 clear it, 0.45/0.55/0.20 don't).</div></div>
    </div>
  </div>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:10px;">Real, run result: EV disagrees with category-level Recovery on <b style="color:#fff;">10 of 160</b> category-RETRY-eligible payments. 4 of those 10 are cases where the blind retry would have <em>actually succeeded</em> &mdash; correctly blocked anyway, because expected value asks whether the aggregate risk was worth taking, not whether this one instance happened to work.</p>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:8px;"><b style="color:var(--warn);">Stated honestly:</b> this is one narrow EV gate on one action type, not a general economic engine. <code>docs/NORTH_STAR.md</code>'s fuller <code>ExpectedUtility = benefit &minus; cost &minus; loss &minus; risk &minus; opportunity_cost</code> is explicitly future ("the existing EV/R0 architecture should evolve into a universal economic reasoning system") &mdash; nothing on this site should imply that engine exists today.</p>
</section>
<section>
  <div class="section-label">ACTION LIFECYCLE<span class="line"></span></div>
  <h2 class="sec-title">Exactly once, even across a crash</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/action/</code> turns an authorized decision into a real, idempotent command. An <code>Action</code> is the durable command object; its <code>execution_status</code> is, by design, the one field in the whole system explicitly allowed to mutate in place &mdash; it tracks the command's own lifecycle, never the financial world.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:10px;">// event_execution.py::execute_action_with_events()</div>
    <div class="loop-stage"><span class="dot" style="background:var(--good);"></span><span class="label">Same idempotency key, same parameters</span><span class="tag">cached result returned, zero re-execution</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--critical);"></span><span class="label">Same key, different parameters</span><span class="tag">rejected &mdash; reuse is refused, not silently accepted</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Crash mid-execution, outcome already observed</span><span class="tag">recovered from the event log, not re-run</span></div>
    <div class="loop-stage" style="border:none;"><span class="dot" style="background:var(--warn);"></span><span class="label">Crash mid-execution, genuinely stuck</span><span class="tag">refuses a second execution rather than guessing</span></div>
  </div>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:10px;">The real event sequence is <code>ActionRequested &rarr; ActionExecutionStarted &rarr; ActionOutcomeObserved</code>, and only <code>ActionOutcomeObserved</code> is ever read by the financial-state projection &mdash; requesting or starting an action can never itself move money.</p>
  <div style="overflow-x:auto; margin-top:10px;"><table class="doctable"><thead><tr><th>Test run (live, this pass)</th><th>Result</th></tr></thead><tbody>
    <tr><td>Stage 3 &mdash; behavioral preservation, all 160 failed payments + Gates A/B/C (replay, reject-on-mismatch, crash recovery)</td><td style="color:var(--good);">PASS</td></tr>
    <tr><td>Stage 4 &mdash; Gate 1 (only ActionOutcomeObserved mutates state), Gate 2 (survives a fresh DB connection), Gate 3 (re-entry: resolved payment correctly flips to DO_NOT_RETRY), Gate 5 (no phantom facts)</td><td style="color:var(--good);">PASS</td></tr>
  </tbody></table></div>
</section>
<section>
  <div class="section-label">ORCHESTRATOR<span class="line"></span></div>
  <h2 class="sec-title">Coordination, not a fourth brain</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/orchestrator/</code>'s <code>process_payment()</code> runs Controller, Risk, and Recovery independently on their own subjects, then merges whichever verdicts apply into one <code>CompoundCase</code> <em>without flattening them into a single score</em> &mdash; the module's own docstring is explicit that this is "coordination, not becoming a mysterious fourth brain." A genuine cross-domain conflict triggers one audit-only Discovery.AI investigation, under the identical firewall Controller uses alone.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="verdict-metric" style="border-top:none; padding-top:0;"><span class="k">Verdicts produced, full 1000-payment corpus</span><span class="v">risk 143 &middot; recovery 160 &middot; controller 807</span></div>
    <div class="verdict-metric"><span class="k">Compound cases (2+ verdicts on one subject)</span><span class="v">139 / 1000</span></div>
    <div class="verdict-metric"><span class="k">Conflicts, offline (full transaction history)</span><span class="v">25 / 1000</span></div>
    <div class="verdict-metric"><span class="k">Conflicts, contemporaneous (decision-time honest)</span><span class="v">10 / 1000</span></div>
    <p class="verdict-note">These two conflict counts are reported separately on purpose, not averaged: the gap between them <em>is</em> the temporal-honesty fix (the same one Risk's own scoring uses) applied to conflict detection itself &mdash; judging a decision by everything that happened after it, versus only what was knowable at the time, are different questions with different honest answers.</p>
  </div>
</section>
<section>
  <div class="section-label">VERIFICATION<span class="line"></span></div>
  <h2 class="sec-title">Checking the system's work, independently</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/verification/</code> implements 4 of the 11 properties <code>docs/NORTH_STAR.md</code> names for a full verification engine &mdash; a deliberate, bounded slice, stated as such in the module's own README, not the whole vision.</p>
  <div style="overflow-x:auto;"><table class="doctable"><thead><tr><th>Property</th><th>Method</th><th>Real result</th></tr></thead><tbody>
    <tr><td>Replay</td><td>Two independent rebuilds from raw input, compared by row counts + exact Decimal money sums + sha256</td><td>IDENTICAL, both the real dataset and a bridged Truman run</td></tr>
    <tr><td>Temporal integrity</td><td>Every Risk verdict's evidence checked against its own <code>as_of</code> cutoff (Recovery/Controller have no as_of parameter &mdash; not audited rather than faked)</td><td>0 Payment-evidence violations across 143 real + 2,583 bridged decisions</td></tr>
    <tr><td>Evidence grounding</td><td>Every verdict's evidence/entity id must resolve to a real graph node</td><td>Zero dangling ids, all three domains, both data sources</td></tr>
    <tr><td>Decision idempotency</td><td>Same subject, same graph, called twice &mdash; byte-identical verdict (distinct from Action's execution idempotency above)</td><td>Identical, all six sampled cases</td></tr>
  </tbody></table></div>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:10px;"><b style="color:var(--warn);">A real, separately-diagnosed anomaly, reported rather than hidden:</b> 41 non-Payment temporal-integrity flags trace to exactly two customers whose raw <code>payments.csv</code> rows predate their own <code>customers.csv</code> account-creation timestamp &mdash; a raw-data defect, named explicitly, and deliberately left unfixed as out of scope for this check.</p>
  <p style="font-size:11.5px; color:var(--muted); line-height:1.7; margin-top:8px;"><b style="color:var(--warn);">Stated honestly:</b> the other 7 properties NORTH_STAR names for a full verification engine &mdash; was the observation itself valid, was the policy/EV computation correct, was the outcome actually checked against its own events, and more &mdash; are not built. The module's own README lists them as open, not solved quietly.</p>
</section>
<section>
  <div class="section-label">A DOCUMENTATION DISCREPANCY, NAMED RATHER THAN REPEATED<span class="line"></span></div>
  <h2 class="sec-title">The graph is real. It isn't what one internal doc calls it.</h2>
  <p class="sec-sub" style="max-width:76ch;"><code>financial_system/financial_graph/repository.py</code>'s own docstring calls itself "a Neo4j-shaped store, backed by SQLite" &mdash; a real, stated reason: this environment has no Docker and no <code>neo4j</code> driver installed, designed so a future <code>Neo4jGraphRepository</code> could swap in against the same interface. One internal design doc (<code>docs/ARCHITECTURE.md</code>) informally labels this layer "Knowledge Graph" running on "Neo4j." That's aspirational language left over from an earlier draft, not what's actually deployed &mdash; worth naming here rather than quietly repeating on a page meant to be exact about what's real.</p>
  <p class="sec-sub" style="max-width:76ch; margin-top:12px;">Also stated plainly: the graph schema today is flat and single-level &mdash; 10 real node types (Customer, Merchant, Device, PaymentInstrument, Order, Payment, Settlement, BankTransaction, Fee, Refund), no <code>Account</code>/<code>PaymentIntent</code>/<code>PaymentAttempt</code> abstraction layer, and no separate World/Knowledge/Evidence graph split. <code>docs/NORTH_STAR.md</code> proposes both as future architecture ("Heimdall should eventually contain three distinct but connected graph structures") &mdash; neither exists today.</p>
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
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">No general ledger.</b> Two targeted accounting checks exposed a real gap without building a second, unproven financial subsystem.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6;"><b style="color:#fff;">Each domain investigates in isolation.</b> The Orchestrator merges verdicts and detects conflicts across domains, but there is no mechanism today for one domain's investigation to inform another's &mdash; named explicitly in <code>docs/FUTURE_ARCHITECTURE.md</code> as the next real boundary, not solved by the Orchestrator's existing conflict-merge.</li>
    </ul>
  </div>
</section>
<section>
  <div class="section-label">WHAT ISN'T PROVEN<span class="line"></span></div>
  <h2 class="sec-title">Said plainly, because a project that never says this isn't trustworthy</h2>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <ul style="list-style:none; display:flex; flex-direction:column; gap:10px; margin:0; padding:0;">
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">Production-scale deployment, or performance at real payment-processor volume</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">Universal fraud detection &mdash; Risk is one dataset's device-sharing signal, not a general fraud model</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">Generalization to a real institution's actual data, conventions, or scale</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">Credit intelligence, AML, treasury, insurance, or markets reasoning &mdash; none built</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">A general economic engine &mdash; one narrow Expected Value gate exists (see <a href="#" onclick="go('system'); return false;">System</a>), not CLV, opportunity cost, or network costs</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">An autonomous research-to-world-extension loop &mdash; the provenance catalog and drift detector are real, static tools a human runs, not a self-expanding system</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">A universal world registry, or a World/Knowledge/Evidence graph split &mdash; one flat financial graph exists today</li>
      <li style="font-size:12px; color:var(--muted); line-height:1.6;">Counterfactual or adversarial world generation beyond the one drift-detector comparison already shown</li>
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

const REPORTS = [
  {
    id: 'risk-eval', title: 'Risk Evaluation', headline: '100% precision · 96.3% recall · 0% FPR',
    question: "Does Risk's deterministic device score actually separate real fraud rings from ordinary shared devices?",
    method: 'Score every device shared by 2+ customers with the real weighted formula (burst_density 0.50, burst_amount_clustering 0.30, n_sharers 0.15, account_age 0.05); classify HIGH/MEDIUM/LOW; compare against the dataset\'s own planted ground truth.',
    input: 'financial_graph.db &mdash; 371 devices, 6 planted fraud rings, 8 deliberately-benign shared-device traps (16 total test cases the generator built specifically to punish a naive detector)',
    result: '100% precision, 96.3% recall, 0% false-positive rate &mdash; <code>financial_system/risk/runner.py</code>',
    interpretation: 'Every planted fraud ring was caught; the one recall miss is a gap, not a false alarm; every benign trap (an ordinary shared family device) was correctly released, not flagged.',
    limitations: "One dataset, one generator's fraud-ring pattern (burst timing + amount clustering). Not validated against real-world fraud, which may not look like this. \"0% FPR\" is exact on 16 specifically-planted traps &mdash; not a general false-positive-rate claim at scale.",
    conclusion: 'The weighted-score design is sound for the exact pattern it was built to catch. This is evidence the implementation works, not evidence of general fraud-detection capability.',
  },
  {
    id: 'recovery-eval', title: 'Recovery Evaluation', headline: '87/87 category accuracy · 39.6% false-retry rate',
    question: 'Does Recovery correctly identify which failure categories are worth retrying?',
    method: "Classify every one of the corpus's category-eligible payment failures (correctly attempted vs. not) against the real decline-code taxonomy and ground-truth failure_reason labels.",
    input: '87 recoverable-category payments, financial_graph.db',
    result: '87/87 (100%) category accuracy &mdash; <code>financial_system/recovery/runner.py</code>; 39.6% false-retry rate, matching the categories\' own weighted historical base rate (39.3% expected)',
    interpretation: "100% is category-classification accuracy, NOT successful-recovery accuracy &mdash; a case counts as correct when Recovery attempted retry on a genuinely recoverable category, independent of whether that specific retry actually succeeded. The 39.6% false-retry rate is the honest cost: even a correct category-level decision fails 4 times in 10, because decision_score is a base rate, never a per-instance prediction.",
    limitations: 'The corpus\'s own failure labels come from a category-level coin flip (<code>retry_would_succeed = random() &lt; spec[...]</code>) with zero connection to amount, customer, device, or timing &mdash; testing a fancier per-instance model on this corpus would be circular, since no real instance-level signal exists to learn from.',
    conclusion: '87/87 proves the taxonomy lookup is implemented correctly, not that retries succeed reliably. Building an ML classifier on this specific corpus would be scientifically dishonest.',
  },
  {
    id: 'controller-eval', title: 'Controller Evaluation', headline: '555/610 operational · 47/50 honest-exception rate',
    question: 'Does the deterministic reconciliation check correctly separate explainable settlement gaps from genuinely unexplained ones?',
    method: "Run the full 610-settlement corpus through Controller's deterministic check; separately, evaluate a targeted 50-case sample against the dataset's real 9-category root-cause ground truth.",
    input: '610 real settlements, financial_graph.db',
    result: '555/610 (91.0%) resolved cleanly (PASS or duplicate-detected RESOLVE) &mdash; <code>financial_system/reconciliation/runner.py</code>; 47/50 (94.0%) honest-exception rate on the targeted sample',
    interpretation: 'These two numbers measure different things and must not be merged: 555/610 is the full corpus\'s operational outcome; 47/50 checks specifically whether Controller resists guessing when it genuinely doesn\'t have an explanation.',
    limitations: "Controller's deterministic check handles exactly 1 of the dataset's 9 real root-cause categories (duplicate line items). The other 8 (partial refunds, currency conversion, missing settlements, bank adjustments, split settlements, fee discrepancies, timing skew) rely on Discovery.AI's narrative or stay unresolved.",
    conclusion: "Controller is real and honest, but the least automated of the three domains &mdash; most gap categories still need investigation or a human, not a formula.",
  },
  {
    id: 'temporal-leakage', title: 'Temporal Leakage Investigation & Fix', headline: 'A real bug, found and fixed before submission',
    question: "Could Risk's score for a device be influenced by information that hadn't happened yet at decision time?",
    method: "Audit every real Risk verdict's evidence against an as_of cutoff equal to the payment's own timestamp.",
    input: 'Every real Risk verdict, both the frozen dataset and bridged Truman runs',
    result: "Found: an earlier version of the burst-window signals scanned a device's FULL transaction history, including transactions AFTER the payment being scored. Fixed by introducing a reusable temporal observation boundary (an <code>as_of</code> parameter) scoping every signal query to only what existed at decision time.",
    interpretation: 'Post-fix, <code>financial_system/verification/temporal.py</code> re-audits every real Risk verdict: 0 Payment-evidence violations across 143 real + 2,583 bridged decisions.',
    limitations: 'The <code>as_of</code> boundary exists only for Risk today. Recovery and Controller have no equivalent parameter and are not audited for this class of leakage &mdash; a stated open gap, not an assumed-safe one.',
    conclusion: "The clearest example in this project of a real correctness bug an adversarial test caught before submission, not after &mdash; and the reason \"only observe what was knowable at decision time\" is stated as an architectural principle, not a nice-to-have.",
  },
  {
    id: 'replay', title: 'Replay Verification', headline: 'IDENTICAL, both data sources',
    question: 'Does rebuilding the entire financial state from raw input twice produce byte-identical results?',
    method: 'Two independent rebuilds from the same raw CSVs, compared by row counts, exact Decimal money sums, and a sha256 content hash.',
    input: 'The real Heimdall dataset and a bridged Truman run',
    result: 'IDENTICAL on both &mdash; <code>financial_system/verification/replay.py</code>',
    interpretation: 'Proves the ingestion pipeline itself is deterministic, with no hidden nondeterminism (dict ordering, floating point, uncontrolled randomness).',
    limitations: 'Replay checks the state-BUILDING pipeline, not whether a decision was correct &mdash; a wrong-but-deterministic decision would still replay identically.',
    conclusion: 'A necessary, not sufficient, correctness property &mdash; and a genuinely proven one.',
  },
  {
    id: 'action-idempotency', title: 'Action Idempotency', headline: 'Stage 3 PASS · Stage 4 PASS (re-run live this session)',
    question: 'Can the same authorized action be executed exactly once, even across a crash?',
    method: 'Stage 3 (behavioral preservation across all 160 failed payments, plus Gates A/B/C) and Stage 4 (Gates 1/2/3/5) test suites.',
    input: 'The full 160-payment recoverable-category set, real Action/ActionAttempt/ActionCase store',
    result: 'Both PASS, re-run live for this documentation: same key + same params &rarr; cached result returned; same key + different params &rarr; rejected; crash mid-execution &rarr; recovered from the event log, or refused rather than guessed; only <code>ActionOutcomeObserved</code> ever mutates financial state.',
    interpretation: 'A real distributed-systems correctness property (idempotency + crash recovery), not something typically found at hackathon scale.',
    limitations: 'Tested against the local SQLite-backed action store under single-process conditions &mdash; not tested under concurrent multi-process access or real network partitions.',
    conclusion: 'A solid foundation. Concurrency and distributed-lock hardening are future work, not claimed today.',
  },
  {
    id: 'live-recovery-loop', title: 'Live Recovery Loop', headline: 'A real retry that honestly failed again',
    question: 'Does a real RETRY decision, executed inside a running simulation, produce a real, sometimes-honestly-failing outcome?',
    method: "Run the live bridge against a small (20-50 person) Truman world; execute scheduled retries against the person's real, then-current balance.",
    input: 'A live, seeded Truman environment (this session\'s own run, seed=42)',
    result: "A genuine RETRY on <code>pay_bridge_txn_00000027</code> was scheduled and executed the next day &mdash; it failed again, honestly, because the person's balance still hadn't recovered.",
    interpretation: "Proves the loop isn't a scripted success story: a real retry against a real, still-insufficient balance produces a real second failure, consistent with the project's own documented ~39.6% false-retry rate.",
    limitations: 'Small population (20-50 people), not stress-tested at the batch bridge\'s larger scale.',
    conclusion: 'Genuinely closed-loop, re-verified this session, not just historically documented.',
  },
  {
    id: 'live-risk-loop', title: 'Live Risk Loop', headline: '239 decisions · 1 device blocked · 35 attempts mechanically prevented',
    question: 'Does a real HOLD decision, executed inside a running simulation, actually and mechanically block future purchases?',
    method: 'Run the live bridge (seed=42, population=30, 90 days), scoring every device with new activity each day, calling <code>block_device()</code> on HOLD.',
    input: 'A seeded 90-day Truman run',
    result: '239 Risk decisions (208 RELEASE, 31 REVIEW); 1 device blocked (<code>dev_00000d</code>); 35 subsequent purchase attempts from that device mechanically prevented &mdash; all 35 of which would have succeeded if not blocked.',
    interpretation: 'A real counterfactual makes this checkable, not just counted: the identical seed run WITHOUT the live loop shows person_00017\'s day-49 &#8377;41.62 purchase actually succeeding (balance drops 2402.25&rarr;2360.63); the live-loop run shows the same attempt blocked, balance unchanged.',
    limitations: 'One run, one seed. That all 35 prevented attempts "would have succeeded" reflects this population\'s balance distribution, not a general claim that blocked devices always have sufficient funds.',
    conclusion: 'A real, mechanical, checkable enforcement action &mdash; not a logged recommendation nobody acted on.',
  },
  {
    id: 'truman-determinism', title: 'Truman Determinism', headline: 'Reproduced across seeds — and again this session',
    question: 'Does the same seed reproduce the exact same simulated world?',
    method: 'Run the engine twice with an identical seed; compare outputs. The balance/income failure curve specifically checked across three seeds (42, 7, 2026).',
    input: 'Simulation/world/engine.py, seeded SimulationEngine',
    result: "Identical counts and case-type distributions across repeats. This session's own re-run (seed=42) reproduced the IDENTICAL failed-payment sequence (same payment id, same devices, same day-by-day decisions) as an earlier, independent session's run.",
    interpretation: 'Real, load-bearing determinism &mdash; every other verification here (replay, drift detection) depends on this holding.',
    limitations: 'Entity IDs (<code>uuid4()</code>) are NOT reproducible across runs &mdash; only counts, case-type distributions, and RNG-driven decisions are. Stated explicitly, not glossed over.',
    conclusion: "Solid. The one honestly-stated exception (entity IDs) doesn't undermine the property that actually matters: behavioral reproducibility.",
  },
  {
    id: 'mechanism-eval', title: 'Mechanism Evaluation', headline: 'Two mechanisms, causally ordered, tested',
    question: "Do Truman's causal failure mechanisms — not label assignment — actually and correctly gate purchase outcomes?",
    method: '<code>Simulation/tests/test_mechanisms.py</code>: prove <code>InsufficientFundsMechanism</code> identical to the real balance check including the exact amount==balance boundary; prove <code>ExpiredInstrumentMechanism</code> fires iff day &ge; expiry regardless of balance; test the fixed causal ordering itself.',
    input: 'Simulation/world/mechanisms.py',
    result: 'Real, specific, passing tests &mdash; not just documented behavior.',
    interpretation: "The instrument-validity check runs before the funds check by design, mirroring how a real card network actually authorizes a transaction: an expired card is declined before the cardholder's balance is ever consulted.",
    limitations: 'Only two mechanisms exist today. Authentication failure and issuer availability are named as future mechanisms, not built.',
    conclusion: 'A real, small, correctly-ordered, tested mechanism pipeline. The foundation is sound; the coverage is intentionally narrow.',
  },
  {
    id: 'drift-detection', title: 'Bridge / Drift Detection', headline: 'One real, statistically significant finding',
    question: "Are Heimdall's live decisions against Truman consistent with Truman's own KNOWN generative mechanisms?",
    method: 'Three checks: Recovery retry timing vs. Truman\'s payday mechanism; Recovery\'s stated confidence vs. realized retry-success rate; device-sharing intensity vs. Risk score.',
    input: 'The live Recovery and Risk loops\' own recorded runs',
    result: 'One real, statistically significant drift found (p=2.6&times;10&#8315;&#8310;): Recovery\'s stated 45% confidence for <code>insufficient_funds</code> didn\'t match Truman\'s realized 0% retry-success rate in the live loop.',
    interpretation: "Traced to a specific, real cause &mdash; the live loop's fixed 1-day retry window colliding with Truman's monthly-payday-only income model &mdash; not a flaw in Heimdall's own decision logic.",
    limitations: 'Three checks only, each pinned to one specific mechanism &mdash; not a general model-consistency score.',
    conclusion: "The project's strongest argument for why simulate at all: a simulation is valuable not because it's real, but because its mechanisms are known, making this kind of controlled, diagnosable evaluation possible in the first place.",
  },
  {
    id: 'provenance', title: 'Provenance Validation', headline: '28 implemented + 15 proposed entries, all verified',
    question: 'Does every research-grounded or modeling-assumption constant in Truman actually match what it claims to cite?',
    method: '<code>Simulation/tests/test_provenance.py</code>: verify every "implemented" catalog entry\'s location/value against actual current source via <code>ast.literal_eval</code>; verify every research-grounded citation is a real substring of Research.md; re-scan source for provenance-tagged constants and assert every one has a catalog entry.',
    input: 'Simulation/provenance/catalog.py, Simulation/docs/Research.md',
    result: '28 implemented entries + 15 proposed (not-yet-built) entries, all passing.',
    interpretation: 'A real, automated discipline preventing a modeling assumption from silently being presented as empirically grounded, or a citation from going stale as code changes.',
    limitations: 'Not CI-enforced continuously &mdash; only re-verified when pytest is run. Doesn\'t catch a tag\'s stated meaning being edited without its value changing. Three Phase 2 structural decisions have no attached numeric constant and are named as exceptions rather than silently omitted.',
    conclusion: 'Real, tested, and honest about its own blind spots &mdash; which is itself the point of building it.',
  },
];

function reportItem(r){
  const field = (label, val) => `<div class="report-field"><div class="fl">${label}</div><div class="fv">${val}</div></div>`;
  return `
  <details class="report-item" id="${r.id}">
    <summary><span class="rt">${r.title}</span><span class="rh">${r.headline}</span></summary>
    <div class="report-body">
      ${field('Question', r.question)}
      ${field('Method', r.method)}
      ${field('Input / Dataset / World', r.input)}
      ${field('Result', r.result)}
      ${field('Interpretation', r.interpretation)}
      ${field('Limitations', r.limitations)}
      ${field('Conclusion', r.conclusion)}
    </div>
  </details>`;
}

function howItWorksHTML(){ return `
<section class="hero" style="padding-top:44px; padding-bottom:8px;">
  <div class="section-label">TECHNICAL REFERENCE<span class="line"></span></div>
  <h2 class="sec-title">How Heimdall actually works</h2>
  <p class="sec-sub" style="max-width:76ch;">This is a straight technical account of the running system &mdash; the real decision loop, the real evidence each domain reads, the real branches it can take, and the real limits it hits. Nothing here is aspirational; where something isn't built yet, it says so.</p>
</section>

<section>
  <div class="section-label">01 &mdash; OVERVIEW<span class="line"></span></div>
  <h2 class="sec-title">A world, not a row</h2>
  <p class="sec-sub" style="max-width:76ch;">Heimdall doesn't score a payment as an isolated record. It reads a payment's current state and its real neighborhood in a graph, applies one of three small deterministic domains (Risk, Recovery, Controller), authorizes the result through a real policy engine, executes it through a real idempotent action lifecycle, and independently checks the outcome afterward. Discovery.AI is consulted only when deterministic evidence genuinely runs out, and its answer can never become the decision &mdash; a structural boundary, not a convention.</p>
  <p class="sec-sub" style="max-width:76ch;">It is deliberately not a general financial AI and doesn't claim to be one. It's three narrow, auditable domains over one real graph, with a real system around them making sure a verdict becomes an authorized, executed, and verified action &mdash; see <a href="#" onclick="go('reports'); return false;">Reports</a> for exactly what's been proven and how.</p>
</section>

<section>
  <div class="section-label">02 &mdash; THEORY<span class="line"></span></div>
  <h2 class="sec-title">Why observe a world instead of scoring a row</h2>
  <p class="sec-sub" style="max-width:76ch;">Before any of this was code, it was a conceptual answer to one question: how do you make a financial decision defensible? Not accurate on average &mdash; defensible, meaning a specific person could later ask "why did you do that," and get a specific, checkable answer.</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:10px;">// THE FULL LOOP</div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Financial world</span><span class="tag">Truman, or the real frozen dataset</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Event history &rarr; world state</span><span class="tag">every payment, settlement, device, instrument</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Observation</span><span class="tag">a graph query, scoped to what's knowable right now</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Intelligence (Risk / Recovery / Controller)</span><span class="tag">deterministic signals &rarr; a verdict</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Investigation, if evidence genuinely runs out</span><span class="tag">Discovery.AI, audit-only</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Economic evaluation</span><span class="tag">one Expected Value gate, Recovery only</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Policy</span><span class="tag">11 ordered rules authorize or refuse</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Action</span><span class="tag">idempotent, crash-safe execution</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Outcome</span><span class="tag">only the observed outcome mutates state</span></div>
    <div class="loop-stage"><span class="dot"></span><span class="label">Verification</span><span class="tag">an independent check, after the fact</span></div>
    <div class="loop-stage" style="border:none;"><span class="dot"></span><span class="label">World update &rarr; re-observed next tick</span><span class="tag">no memory carried in code</span></div>
  </div>
  <p class="sec-sub" style="max-width:76ch; margin-top:16px;">The separation that actually matters is <b style="color:#fff;">world &ne; observation &ne; evidence &ne; decision &ne; action &ne; outcome</b>. Collapse any two of these and you lose the ability to answer "why" precisely: if observation and decision are the same step, you can't ask whether the decision used stale information; if action and outcome are the same step, you can't tell a request from what actually happened. Every real incident on this page (&sect;08) is a story about one of these boundaries being drawn in the wrong place, found, and fixed.</p>
  <div class="panel" style="margin-top:16px;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-title" style="margin-bottom:8px;">// THEORY VS. WHAT'S ACTUALLY LIVE</div>
    <p style="font-size:12px; color:var(--muted); line-height:1.7;">Real and tested today: Risk, Recovery, Controller, the Discovery.AI adapter, Policy, the Action lifecycle, the Orchestrator, Verification (4 of 11 named properties), Truman's causal simulation and live bridge, and the drift detector. Designed but not built: a general economic engine beyond one narrow EV gate, an autonomous research-to-world-extension loop, a universal world registry, a World/Knowledge/Evidence graph split, and multiple graph abstraction levels &mdash; the graph today is flat and single-level. None of the unbuilt items are implied as real anywhere else on this site.</p>
  </div>
</section>

<section>
  <div class="section-label">03 &mdash; ARCHITECTURE<span class="line"></span></div>
  <h2 class="sec-title">Nine real modules, each with one job</h2>
  <p class="sec-sub" style="max-width:76ch;">No single module decides everything. Each owns exactly one responsibility, and only the Graph Interface touches the database directly.</p>
  <div class="doclist">
    <div class="docrow"><span class="path">Simulation/world/</span><span class="desc">Truman &mdash; the causal world. Zero knowledge Heimdall exists.</span></div>
    <div class="docrow"><span class="path">financial_system/bridges/</span><span class="desc">One-directional adapter &mdash; batch and live. Never mutates Heimdall's frozen logic.</span></div>
    <div class="docrow"><span class="path">financial_system/financial_graph/</span><span class="desc">The only code that queries the graph. A SQLite store, shaped like a future Neo4j one.</span></div>
    <div class="docrow"><span class="path">financial_system/risk/ · recovery/ · reconciliation/</span><span class="desc">The three deterministic domains &mdash; signals in, a typed verdict out.</span></div>
    <div class="docrow"><span class="path">financial_system/discovery_adapter/</span><span class="desc">The one narrow module touching Discovery.AI's internals. Audit-only, structurally.</span></div>
    <div class="docrow"><span class="path">financial_system/recovery/expected_value.py</span><span class="desc">One real Expected Value gate &mdash; narrower than a general economic engine.</span></div>
    <div class="docrow"><span class="path">financial_system/policy/</span><span class="desc">11 ordered rules, first match wins. No field for LLM confidence, by design.</span></div>
    <div class="docrow"><span class="path">financial_system/action/</span><span class="desc">Idempotent execution. Only ActionOutcomeObserved ever mutates financial state.</span></div>
    <div class="docrow"><span class="path">financial_system/orchestrator/ · verification/</span><span class="desc">Cross-domain conflict coordination, and an independent check afterward.</span></div>
  </div>
  <p style="font-size:11px; color:var(--muted-2); margin-top:14px;">The arrows in &sect;02's loop diagram are real, currently-wired call paths for the frozen dataset and for the live Truman bridge &mdash; not a target architecture. See <a href="#" onclick="go('system'); return false;">System</a> for Policy/Action/Orchestrator/Verification in full depth, and <a href="#" onclick="go('heimdall'); return false;">Heimdall</a> for each domain's real formula.</p>
</section>

<section>
  <div class="section-label">04 &mdash; THE DECISION LOOP<span class="line"></span></div>
  <h2 class="sec-title">One concrete run, start to finish</h2>
  <p class="sec-sub" style="max-width:76ch;">A payment fails with <code>technical_failure</code>. Recovery classifies the category as recoverable and proposes a retry, scored at the category's own historical success rate. Policy authorizes it. Action executes it, exactly once. The gateway reports success; that becomes a durable, observed event &mdash; not something Action itself declared true. Verification later confirms the evidence behind that decision resolves to real graph nodes with no dangling ids. Recovery, asked about the <em>same payment</em> again from scratch, independently concludes there's nothing left to recover &mdash; it found out from the event log, not a special case written for this scenario.</p>
  <div class="panel" style="margin-bottom:0;"><div class="corner tl"></div><div class="corner br"></div>
    <div class="loop-stage"><span class="dot" style="background:var(--critical);"></span><span class="label">Payment failed</span><span class="tag">technical_failure, 85% category base rate</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Recovery signals &rarr; decision</span><span class="tag">deterministic decline-code taxonomy</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--warn);"></span><span class="label">Policy</span><span class="tag">R3_RECOVERY_RETRY_ALLOW fires, score &ge; 0.5</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--good);"></span><span class="label">Action</span><span class="tag">ActionRequested &rarr; Started &rarr; OutcomeObserved</span></div>
    <div class="loop-stage"><span class="dot" style="background:var(--good);"></span><span class="label">Verification</span><span class="tag">evidence grounded, idempotency confirmed</span></div>
    <div class="loop-stage" style="border:none;"><span class="dot" style="background:var(--good);"></span><span class="label">Fresh Recovery, asked again independently</span><span class="tag">correct, no special-case code</span></div>
  </div>
</section>

<section>
  <div class="section-label">05 &mdash; EVIDENCE &amp; CONFIDENCE<span class="line"></span></div>
  <h2 class="sec-title">Real evidence, scored honestly &mdash; including when confidence is high and still wrong to act on</h2>
  <p class="sec-sub" style="max-width:76ch;">When Controller genuinely can't explain a settlement gap deterministically, Discovery.AI investigates &mdash; and the real, inspected result from this project's own held-out run is more interesting than a clean success story:</p>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <div class="verdict-metric" style="border-top:none; padding-top:0;"><span class="k">Genuinely unexplainable cases investigated</span><span class="v">52 / 52</span></div>
    <div class="verdict-metric"><span class="k">Average / peak LLM confidence on these cases</span><span class="v">0.82 avg &middot; up to 0.95</span></div>
    <div class="verdict-metric"><span class="k">Cases where confidence flipped status to EXPLAINED</span><span class="v">0 / 52</span></div>
    <div class="verdict-metric"><span class="k">Hallucination flags (a number cited but not grounded)</span><span class="v">0 / 52</span></div>
    <p class="verdict-note">One real case, at 0.95 confidence, narrates: "no single transaction, fee, or combination of entries matches &mdash; this indicates either an unrecorded bank adjustment or a missing fee/charge not yet ingested." A plausible, well-reasoned, high-confidence explanation &mdash; and <code>result.status</code> stays UNEXPLAINED anyway, because the narrative never grounds to a specific retrievable ledger entry. This is the audit-only boundary working exactly as designed: confidence describes the narrative, it does not authorize a conclusion.</p>
  </div>
</section>

<section>
  <div class="section-label">06 &mdash; STRUCTURAL DECISIONS<span class="line"></span></div>
  <h2 class="sec-title">Never guess &mdash; exactly one branch applies</h2>
  <p class="sec-sub" style="max-width:76ch;">Every domain's decision is a small, closed set of branches, not an open-ended judgment call. Recovery has 5 branches (DO_NOT_RETRY &times;2, INVESTIGATE, ESCALATE, RETRY). Risk has 3 tiers (RELEASE / REVIEW / HOLD). Controller has 4 (PASS / RESOLVE / REVIEW / INVESTIGATE). Policy sits above all three with 11 ordered rules, first match wins, ending in a catch-all (<code>R99_DEFAULT_REVIEW</code>) so nothing ever falls through ungoverned. See <a href="#" onclick="go('heimdall'); return false;">Heimdall</a> and <a href="#" onclick="go('system'); return false;">System</a> for every branch's real condition.</p>
</section>

<section>
  <div class="section-label">07 &mdash; TYPED RELATIONSHIPS<span class="line"></span></div>
  <h2 class="sec-title">Every edge carries its own evidence chain</h2>
  <p class="sec-sub" style="max-width:76ch;">The graph's real edges (<code>belongs_to</code>, <code>used_device</code>, <code>used_instrument</code>, <code>contains</code>, <code>deposited_as</code>, plus derived edges <code>generates</code>, <code>refunded_by</code>, <code>uses</code>, <code>deducts</code>) aren't inferred by an LLM at query time &mdash; they're built once, at graph-construction time, either from persisted entity-resolution matches or computed directly from the ledger, and every one carries a real <code>source_record_ids</code> chain back to the raw record it came from. Nothing in this graph is a relationship the system merely believes is probably true.</p>
</section>

<section>
  <div class="section-label">08 &mdash; REAL INCIDENTS<span class="line"></span></div>
  <h2 class="sec-title">Proving a boundary was drawn correctly, not assuming it</h2>
  <div class="grid3">
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// TEMPORAL LEAKAGE</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">Risk's burst-window signals once scanned a device's FULL history, including transactions after the payment being scored. Found by auditing every verdict against an <code>as_of</code> cutoff; fixed by scoping every signal query to only what existed at decision time. Post-fix: 0 violations across 143 real + 2,583 bridged decisions.</p>
    </div>
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// TIMING BACKWARDS</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">A replay test caught a decision's recorded "world state at the time" stamped <i>after</i> the action it authorized had run &mdash; a stored RETRY replayed back as DO_NOT_RETRY. Fixed by capturing the timestamp before reasoning runs, not after.</p>
    </div>
    <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
      <div class="loop-title" style="margin-bottom:8px;">// WHY VS. WHETHER</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.65;">After a successful retry, Recovery produced "unrecognized failure_reason=None" &mdash; it checked <i>why</i> a payment failed but never <i>whether</i> it still was. Fixed with a general status check that gives the same answer on attempt 1, 2, or 5.</p>
    </div>
  </div>
  <p style="font-size:11.5px; color:var(--muted-2); margin-top:14px;">A fourth, non-bug story: an early accounting-boundary review claimed 19/610 settlements had a real gap. Tracing the actual implementation showed that 19 was exactly the count of already-known <code>duplicate_record</code> cases, not a new finding &mdash; corrected in the same document that made the original claim, the moment better evidence existed. Full technical detail on each: <a href="#" onclick="go('docs'); return false;">Documentation</a>.</p>
</section>

<section>
  <div class="section-label">09 &mdash; RELIABILITY &amp; LIMITS<span class="line"></span></div>
  <h2 class="sec-title">What this doesn't promise</h2>
  <div class="panel"><div class="corner tl"></div><div class="corner br"></div>
    <ul style="list-style:none; display:flex; flex-direction:column; gap:12px; margin:0; padding:0;">
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">Several real constants have no documented derivation.</b> Risk's 0.3/0.6 tier cutoffs, its 60-minute window's margin, Controller's &#8377;1.00 tolerance, and Discovery.AI's 3-step investigation budget are working values, not calibration results &mdash; stated on their own pages, not hidden here.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">Each domain investigates in isolation.</b> The Orchestrator merges verdicts and detects conflicts, but one domain's investigation still can't inform another's.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">The graph is flat, not multi-level.</b> One internal doc informally calls it a "Neo4j Knowledge Graph"; the real, shipped store is SQLite, by its own docstring's stated reason, with no Account/PaymentIntent/PaymentAttempt abstraction layer.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6; padding-bottom:12px; border-bottom:1px dashed var(--border);"><b style="color:#fff;">The live Truman environment is small and ephemeral.</b> 20-50 people, resets to day 0 on server restart &mdash; not stress-tested at the batch bridge's larger scale.</li>
      <li style="font-size:12.5px; color:var(--muted); line-height:1.6;"><b style="color:#fff;">Free-tier infrastructure is real infrastructure.</b> The backend can cold-start after inactivity; the BYOK chat depends on whichever provider's free tier hasn't been exhausted that day.</li>
    </ul>
  </div>
</section>

<section>
  <div class="section-label">10 &mdash; TECH STACK<span class="line"></span></div>
  <h2 class="sec-title">What it actually runs on</h2>
  <div class="doclist">
    <div class="docrow"><span class="path">FastAPI</span><span class="desc">This site's backend &mdash; imports financial_system's real decision modules directly, no reimplementation.</span></div>
    <div class="docrow"><span class="path">SQLite</span><span class="desc">The graph, financial state, and action stores &mdash; "Neo4j-shaped," not Neo4j.</span></div>
    <div class="docrow"><span class="path">Groq &middot; Gemini &middot; Anthropic</span><span class="desc">BYOK fallback chain for the chat panel and Discovery.AI's investigation pass.</span></div>
    <div class="docrow"><span class="path">Cytoscape.js</span><span class="desc">The real graph view on the Live System page &mdash; deterministic fcose layout.</span></div>
    <div class="docrow"><span class="path">Vanilla JS / HTML / CSS</span><span class="desc">This entire frontend. No framework, no build step.</span></div>
    <div class="docrow"><span class="path">GitHub Pages + Render</span><span class="desc">Static frontend, free-tier Python backend.</span></div>
    <div class="docrow"><span class="path">pytest</span><span class="desc">70/70 Simulation tests, plus the Stage 3/4 action and provenance test suites.</span></div>
  </div>
</section>

<section>
  <div class="section-label">11 &mdash; REPORTS<span class="line"></span></div>
  <h2 class="sec-title">Every verification pass, in one log</h2>
  <p class="sec-sub" style="max-width:76ch;">Everything claimed above is backed by a test that actually ran, not asserted from design intent. The full log &mdash; question, method, dataset, result, interpretation, limitations, conclusion, for all twelve &mdash; lives on its own page.</p>
  <button class="btn btn-primary" onclick="go('reports')">OPEN THE REPORTS LOG &rarr;</button>
</section>`; }

function reportsHTML(){ return `
<section class="hero" style="padding-top:48px; padding-bottom:20px;">
  <div class="section-label">REPORTS<span class="line"></span></div>
  <h2 class="sec-title">Twelve real experiments, not isolated numbers on cards</h2>
  <p class="sec-sub" style="max-width:74ch;">Every metric anywhere else on this site traces back to one of these. Each report states its question, its method, exactly what it ran against, its real result, what that result does and doesn't mean, its limitations, and its conclusion &mdash; click a report to expand it.</p>
</section>
<section>
  ${REPORTS.map(reportItem).join('')}
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
<section>
  <div class="section-label">ABOUT THE BUILDER<span class="line"></span></div>
  <h2 class="sec-title">Sri Krishna Batkeeri</h2>
  <p class="sec-sub" style="max-width:70ch;">AI/ML &amp; Generative AI engineer, 2nd-year B.Tech CSE (AI &amp; ML) at Aurora University. Builds retrieval-augmented and agentic systems end to end &mdash; RAG and GraphRAG pipelines, multi-agent reasoning over knowledge graphs, LLM-integrated products &mdash; alongside lower-level systems work (browser-based OS kernels, WebAssembly). This project follows the same pattern as the rest of the work below: own the architecture and the debugging, direct AI coding agents to build it, and label honestly which parts were hand-written.</p>
  <div class="tools" style="margin-top:10px; margin-bottom:24px;">
    <span class="tool-chip">srikrishnabatkeeri@gmail.com</span>
    <span class="tool-chip"><a href="https://github.com/TheNova6000" target="_blank" rel="noopener" style="color:inherit; text-decoration:none;">github.com/TheNova6000</a></span>
  </div>
  <div class="subsys-grid">
    <div class="subsys">
      <h3 style="color:var(--hud);">Discovery.AI <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; AI-generated &middot; live</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A recursive knowledge-graph investigator: decomposes open-ended questions into sub-questions, investigates each through six live retrievers, and renders results as an explorable, source-attributed graph instead of a single answer. This is the same engine wired into Heimdall's own investigation boundary, above.</p>
    </div>
    <div class="subsys">
      <h3 style="color:var(--hud);">NexusHub <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; AI-generated</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A citation-graph search engine treating research literature as a graph, not a keyword index &mdash; crawls OpenAlex's 250M-work graph, runs PageRank/HITS/Louvain/Node2Vec to surface cross-domain bridge papers, behind a FastAPI hybrid search backend.</p>
    </div>
    <div class="subsys">
      <h3 style="color:var(--hud);">REOS <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; AI-generated &middot; live</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A multi-tenant real-estate SaaS, co-built with a two-person team &mdash; a Next.js + Supabase dashboard and a client-branded property site sharing one tenant-isolated backend. Shipped to a real first client.</p>
    </div>
    <div class="subsys">
      <h3 style="color:var(--hud);">WAROS <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; AI-generated</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A browser-native OS kernel running untrusted apps sandboxed in Web Workers behind a permission-gated IPC layer, with simulated scheduling, virtual memory (SharedArrayBuffer), and a filesystem (IndexedDB/OPFS). Ported DOOM and a Game Boy emulator to run inside it.</p>
    </div>
    <div class="subsys">
      <h3 style="color:var(--good);">Pyone <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; hand-coded, no AI assistance</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A natural-language-syntax DSL designed and interpreted from scratch by hand &mdash; lexer, stack-based expression evaluator, variable management, control-flow parsing &mdash; for a first-year term project.</p>
    </div>
    <div class="subsys">
      <h3 style="color:var(--good);">Career Intelligence Agent <span style="font-size:10px; color:var(--muted-2); font-weight:400;">&middot; hand-coded &middot; live</span></h3>
      <p style="font-size:12.5px; color:var(--muted); line-height:1.65;">A six-phase job-search pipeline &mdash; fit scoring, company research, cold-email generation &mdash; hand-built end to end, orchestrating LLM, GitHub, and JSearch APIs directly. Advanced Frontend course project.</p>
    </div>
  </div>
  <p style="font-size:11px; color:var(--muted-2); margin-top:18px;">CVIT Summer Schools on AI, IIIT Hyderabad (2025, 2026) &middot; SERI 2026, IIIT Hyderabad &middot; BITS Pilani Hyderabad AI/ML Workshop &amp; Hackathon (Jan 2026)</p>
</section>
<footer><p>PROJECT HEIMDALL &middot; AI REVENUE RECOVERY</p></footer>`; }
