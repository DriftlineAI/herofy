import React, { useState, useEffect } from 'react';
import '../styles/marketing.css';

/* ============================================================
   SHARED — wordmark lockup (sigil + Antonio "Herofy")
   ============================================================ */
function Wordmark({ size = 28 }: { size?: number }) {
  return (
    <span className="m-nav__logo">
      <span className="sigil">
        <img src="/sigil.svg" alt="" style={{ height: size, width: size, display: 'block' }} />
      </span>
      <span className="m-nav__wordmark">Herofy</span>
    </span>
  );
}

function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="m-eyebrow">
      <div className="hair" />
      <span>{children}</span>
    </div>
  );
}

/* ============================================================
   GUIDED DEMO — narrative left, framed app preview right.
   4-step walkthrough: Triage → Handoff → Questions → Plan.
   ============================================================ */
interface Step {
  id: string;
  label: string;
  index: string;
  eyebrow: string;
  title: string;
  body: React.ReactNode;
  duration: number;
  stage: 'today' | 'customer' | 'batch' | 'plan';
}

const STEPS: Step[] = [
  {
    id: 'queue',
    label: 'Triage',
    index: '01',
    eyebrow: 'Monday · 09:14',
    title: 'The morning queue, already triaged.',
    body: (
      <>Open Herofy and the three customers who need you today are already at the top. <em>Acme just signed</em> — Sidekick has questions before it locks the onboarding plan.</>
    ),
    duration: 5200,
    stage: 'today',
  },
  {
    id: 'open',
    label: 'Handoff',
    index: '02',
    eyebrow: 'Acme Corporation · day 5 of 30',
    title: 'Sidekick has been reading everything.',
    body: (
      <>The SOW, the sales calls, the contacts, the open commitments — <em>Sidekick has been reading it all weekend</em>. It already has a draft plan. It just needs a few things only you know.</>
    ),
    duration: 5200,
    stage: 'customer',
  },
  {
    id: 'batch',
    label: 'Questions',
    index: '03',
    eyebrow: 'Sidekick · 4 questions, batched',
    title: 'A few questions, in one batch.',
    body: (
      <>Not a ping every hour. <em>One form, with Sidekick's suggestions already filled in</em> — from the SOW, the calls, the data. Confirm, adjust, or let it decide.</>
    ),
    duration: 11000,
    stage: 'batch',
  },
  {
    id: 'plan',
    label: 'Plan',
    index: '04',
    eyebrow: 'Plan ready · 30 days · 12 milestones',
    title: 'Your onboarding, drafted in two minutes.',
    body: (
      <>A real plan, rooted in the commitments sales made and the answers only you could give. <em>Sidekick stays on watch</em> and pings you if any milestone slips.</>
    ),
    duration: 6400,
    stage: 'plan',
  },
];

/* ---- STAGE 01 — TODAY QUEUE ---- */
const QUEUE = [
  {
    id: 'acme',
    name: 'Acme Corporation',
    arr: '$240K ARR',
    tag: 'DAY 5 / 30 · 5 QUESTIONS',
    risk: true,
    story: 'New customer. Sidekick has read the SOW and has questions before locking the 30-day plan.',
  },
  {
    id: 'meridian',
    name: 'Meridian Group',
    arr: '$420K ARR',
    tag: 'RENEWAL · 45D',
    risk: false,
    story: 'Healthy engagement, but no exec sponsor on record. QBR coming up.',
  },
  {
    id: 'helix',
    name: 'Helix Biotech',
    arr: '$180K ARR',
    tag: 'GOING DARK · 9D',
    risk: false,
    story: 'Reply latency drifting up. Last message neutral. Renewal in 84 days.',
  },
];

function StageToday({ active }: { active?: string }) {
  return (
    <div className="stage-today">
      <div className="stage-today__head">
        <h3 className="stage-today__title">Current situations</h3>
        <span className="stage-today__count">[3] need you</span>
      </div>
      <div className="stage-today__queue">
        {QUEUE.map((row) => (
          <div
            key={row.id}
            className={`stage-row ${row.risk ? 'is-risk' : ''} ${active && row.id === active ? 'is-active' : ''}`}
          >
            <div className="stage-row__name">{row.name}</div>
            <div className="stage-row__arr">{row.arr}</div>
            <div className="stage-row__story">{row.story}</div>
            <div className="stage-row__tag">{row.tag}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- STAGE 02 — CUSTOMER detail (Acme, new closed-won) ---- */
function StageCustomer() {
  return (
    <div className="stage-customer">
      <div className="stage-customer__head">
        <div>
          <div className="stage-customer__eyebrow">NEW CUSTOMER · DAY 5 OF 30</div>
          <h3 className="stage-customer__name">Acme Corporation</h3>
        </div>
        <div className="stage-customer__tags">
          <span className="tag is-bad">5 QUESTIONS</span>
          <span className="tag">$240K ARR</span>
        </div>
      </div>

      <div className="stage-stats">
        <div className="stage-stat">
          <div className="stage-stat__val">25d</div>
          <div className="stage-stat__label">To go-live</div>
        </div>
        <div className="stage-stat">
          <div className="stage-stat__val">12</div>
          <div className="stage-stat__label">SOW commitments</div>
        </div>
        <div className="stage-stat">
          <div className="stage-stat__val">7</div>
          <div className="stage-stat__label">Sales calls read</div>
        </div>
        <div className="stage-stat">
          <div className="stage-stat__val is-bad">5</div>
          <div className="stage-stat__label">Things only you know</div>
        </div>
      </div>

      <div className="sk-pane">
        <div className="sk-pane__header">
          <span className="pulse" />
          <span>SIDEKICK // READ EVERYTHING · DRAFTED PLAN</span>
          <span className="grow" />
          <span className="ref">SK-A12-Q08</span>
        </div>
        <div className="sk-pane__body">
          I read the <em>SOW, the 7 sales calls, and every contact thread</em> — and drafted a 30-day plan. Five things I can't infer: who the champion is, whether "Launch by Q2" is firm, which milestones to escalate on, your silence threshold, and any history I should respect.
        </div>
      </div>
    </div>
  );
}

/* ---- STAGE 03 — BATCHED QUESTIONS ---- */
interface QItem {
  num: string;
  title: React.ReactNode;
  type: 'pick-one' | 'pick-many' | 'slider';
  options?: string[];
  suggested?: number;
  suggestedMany?: number[];
  suggestedDays?: number;
  meta: string;
}

const QBATCH: QItem[] = [
  {
    num: 'Q01',
    title: 'Who should I mark as the primary champion?',
    type: 'pick-one',
    options: ['Alice Johnson · CEO', 'Bob Smith · Head of Ops', 'Sidekick, you decide'],
    suggested: 0,
    meta: 'Alice replies in 2h · Bob in 1d',
  },
  {
    num: 'Q02',
    title: <>Is <em>"Launch by Q2"</em> a firm milestone or aspiration?</>,
    type: 'pick-one',
    options: ['Firm — board commitment', 'Target', 'Aspiration'],
    suggested: 0,
    meta: 'From Marcus, Mar 14 · repeated twice',
  },
  {
    num: 'Q03',
    title: 'Which milestones should I escalate on?',
    type: 'pick-many',
    options: ['SSO live', 'API integration', 'First 5 users', 'Pricing review', 'Q2 launch'],
    suggestedMany: [0, 1, 3],
    meta: 'Pick as many as you want',
  },
  {
    num: 'Q04',
    title: 'How aggressively should I chase silence?',
    type: 'slider',
    meta: 'Aggressive · 3d  →  Patient · 21d',
    suggestedDays: 7,
  },
];

function StageBatch({ playing }: { playing: boolean }) {
  // 0: hidden, 1: rows visible, 2: suggestions glow on, 3: footer answered count
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    setPhase(0);
    const t1 = setTimeout(() => setPhase(1), 350);
    const t2 = setTimeout(() => setPhase(2), 1500);
    const t3 = setTimeout(() => setPhase(3), 3800);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [playing]);

  const showRows = phase >= 1;
  const showSuggested = phase >= 2;
  const allAnswered = phase >= 3;

  return (
    <div className="stage-batch">
      <div className="sk-pane stage-batch__hud">
        <div className="sk-pane__header">
          <span className="pulse" />
          <span>SIDEKICK // ASKING · 4 QUESTIONS · ACME ONBOARDING</span>
          <span className="grow" />
          <span className="ref">{allAnswered ? 'READY TO BUILD' : 'PRE-FILLED'}</span>
        </div>
      </div>

      <div className={`qbatch ${showRows ? 'is-in' : ''}`}>
        {QBATCH.map((q, i) => (
          <div key={i} className="qbatch__row" style={{ transitionDelay: `${i * 90}ms` }}>
            <div className="qbatch__head">
              <span className="qbatch__num">{q.num}</span>
              <span className="qbatch__title">{q.title}</span>
            </div>

            {q.type === 'pick-one' && (
              <div className="qbatch__chips">
                {q.options!.map((opt, j) => {
                  const isDecide = j === q.options!.length - 1 && opt.startsWith('Sidekick');
                  const on = showSuggested && j === q.suggested;
                  return (
                    <span
                      key={j}
                      className={`qbatch__chip ${on ? 'is-on' : ''} ${isDecide ? 'is-decide' : ''}`}
                    >
                      {!isDecide && <span className="qbatch__radio" />}
                      <span>{opt}</span>
                    </span>
                  );
                })}
              </div>
            )}

            {q.type === 'pick-many' && (
              <div className="qbatch__chips">
                {q.options!.map((opt, j) => {
                  const on = showSuggested && q.suggestedMany!.includes(j);
                  return (
                    <span key={j} className={`qbatch__chip ${on ? 'is-on' : ''}`}>
                      <span className="qbatch__check">{on ? '✓' : ''}</span>
                      <span>{opt}</span>
                    </span>
                  );
                })}
              </div>
            )}

            {q.type === 'slider' && (
              <div className="qbatch__slider">
                <div className="qbatch__track">
                  <div
                    className="qbatch__fill"
                    style={{ width: showSuggested ? `${((q.suggestedDays! - 3) / 18) * 100}%` : '0%' }}
                  />
                  <div
                    className={`qbatch__thumb ${showSuggested ? 'is-on' : ''}`}
                    style={{ left: showSuggested ? `${((q.suggestedDays! - 3) / 18) * 100}%` : '0%' }}
                  />
                </div>
                <div className="qbatch__slider-labels">
                  <span>3d</span>
                  <span className={`qbatch__current ${showSuggested ? 'is-on' : ''}`}>
                    {showSuggested ? `${q.suggestedDays} days of silence` : '—'}
                  </span>
                  <span>21d</span>
                </div>
              </div>
            )}

            <div className="qbatch__meta">{q.meta}</div>
          </div>
        ))}
      </div>

      <div className="qbatch__foot">
        <span className="qbatch__progress">
          <strong>{allAnswered ? 4 : 0}</strong>&nbsp;of 4 · Sidekick's suggestions
        </span>
        <span className="qbatch__progress-bar">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={allAnswered ? 'on' : ''} />
          ))}
        </span>
        <span className={`qbatch__cta ${allAnswered ? 'is-on' : ''}`}>Send · build plan →</span>
      </div>
    </div>
  );
}

/* ---- STAGE 04 — PLAN (timeline of phases drops in) ---- */
const PLAN = [
  {
    week: 'WK 01',
    title: 'Kickoff & Access',
    items: ['Kickoff with Alice (champion) — Tue 10am', 'Provision SSO connector', 'Invite 5 admin users'],
  },
  {
    week: 'WK 02',
    title: 'Integration Build',
    items: ['API integration spec finalized', 'Pilot data migration · staging', 'First-5-users training'],
  },
  {
    week: 'WK 03',
    title: 'Pricing & Pilot',
    items: ['Pricing review with finance', '10-user pilot launch', 'Mid-rollout feedback session'],
  },
  {
    week: 'WK 04',
    title: 'Go-Live · Q2 Launch',
    items: ['50 seats activated', 'Q2 launch retro with Alice', '30-day health check scheduled'],
  },
];

function StagePlan({ playing }: { playing: boolean }) {
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    setRevealed(0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    PLAN.forEach((_, i) => {
      timers.push(setTimeout(() => setRevealed(i + 1), 350 + i * 520));
    });
    return () => timers.forEach(clearTimeout);
  }, [playing]);

  return (
    <div className="stage-plan">
      <div className="sk-pane">
        <div className="sk-pane__header">
          <span className="pulse" />
          <span>SIDEKICK // PLAN DRAFTED · ACME · 30 DAYS · 12 MILESTONES</span>
          <span className="grow" />
          <span className="ref">FROM YOUR ANSWERS</span>
        </div>
      </div>

      <div className="plan-timeline">
        <div className="plan-timeline__rail" />
        {PLAN.map((phase, i) => (
          <div key={i} className={`plan-phase ${i < revealed ? 'is-in' : ''}`}>
            <div className="plan-phase__dot" />
            <div className="plan-phase__head">
              <span className="plan-phase__week">{phase.week}</span>
              <span className="plan-phase__title">{phase.title}</span>
            </div>
            <ul className="plan-phase__items">
              {phase.items.map((it, j) => (
                <li key={j}>{it}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="plan-foot">
        <span className="plan-foot__lab">SIDEKICK · STANDING WATCH</span>
        <span className="plan-foot__txt">I'll alert you if any milestone slips, if Alice goes quiet, or if a SOW commitment gets missed.</span>
      </div>
    </div>
  );
}

/* ---- GUIDED DEMO — the full thing ---- */
function GuidedDemo() {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const current = STEPS[step];

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      setStep((s) => (s + 1) % STEPS.length);
    }, current.duration);
    return () => clearTimeout(t);
  }, [step, playing, current.duration]);

  const go = (i: number) => {
    setStep(i);
    setPlaying(false);
  };

  const renderStage = () => {
    switch (current.stage) {
      case 'today':    return <StageToday active="acme" />;
      case 'customer': return <StageCustomer />;
      case 'batch':    return <StageBatch playing={playing && step === 2} />;
      case 'plan':     return <StagePlan playing={playing && step === 3} />;
      default:         return null;
    }
  };

  const url =
    current.stage === 'today'    ? 'app.herofy.com / today' :
    current.stage === 'customer' ? 'app.herofy.com / acme' :
    current.stage === 'batch'    ? 'app.herofy.com / acme / questions' :
                                   'app.herofy.com / acme / onboarding-plan';

  return (
    <section className="demo marketing" id="demo">
      <div className="demo__inner">
        {/* LEFT: narrative */}
        <div className="demo-narrative">
          <div className="demo-narrative__eyebrow">
            <div className="hair" />
            <span>A guided walkthrough</span>
          </div>

          <div className="demo-narrative__index">
            <span className="now">{current.index}</span> / 04 — {current.eyebrow}
          </div>

          <h2 className="demo-narrative__title">{current.title}</h2>

          <p className="demo-narrative__body">{current.body}</p>

          <div className="demo-steps">
            {STEPS.map((s, i) => (
              <button
                key={s.id}
                className={i === step ? 'is-active' : ''}
                onClick={() => go(i)}
              >
                <span className="num">{s.index}</span>
                <span className="lab">{s.label}</span>
              </button>
            ))}
          </div>

          <div className="demo-controls">
            <button
              className={playing ? 'is-playing' : ''}
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? '❚❚ Pause tour' : '▶ Play tour'}
            </button>
            <button onClick={() => go((step + 1) % STEPS.length)}>
              Next →
            </button>
          </div>
        </div>

        {/* RIGHT: framed app preview */}
        <div className="demo-frame">
          <div className="demo-frame__chrome">
            <div className="demo-frame__lights">
              <span /><span /><span />
            </div>
            <div className="demo-frame__url">
              <span className="live" />{url}
            </div>
            <div className="demo-frame__badge">Demo</div>
          </div>

          <div className="demo-stage" key={current.id}>
            {renderStage()}
          </div>

          <div className="demo-frame__foot">
            <span>{current.eyebrow}</span>
            <span className="ok">
              <span className="dot" />
              <span>Sidekick on watch</span>
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================================
   WAITLIST FORM
   ============================================================ */
function WaitlistForm({ className = '' }: { className?: string }) {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setStatus('loading');
    try {
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.message || 'Failed to join waitlist');
      }

      setStatus('success');
      setEmail('');
    } catch (err) {
      setStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Something went wrong');
    }
  };

  if (status === 'success') {
    return (
      <div className={`waitlist__confirm ${className}`}>
        <span className="dot" />
        <span>You're on the list. We'll be in touch.</span>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={`waitlist__form ${className}`}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@company.com"
        required
      />
      <button type="submit" disabled={status === 'loading'} className="cta">
        <span>{status === 'loading' ? 'Joining…' : 'Join waitlist'}</span>
        <span>&rarr;</span>
      </button>
      {status === 'error' && (
        <p style={{ color: 'var(--color-signal-bad)', position: 'absolute', bottom: -28, left: 0, fontSize: 13 }}>
          {errorMessage}
        </p>
      )}
    </form>
  );
}

/* ============================================================
   FAQ ITEM
   ============================================================ */
function FAQItem({ question, answer, defaultOpen = false }: { question: string; answer: string; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="faq__item">
      <button onClick={() => setIsOpen(!isOpen)} className={`faq__q ${isOpen ? 'open' : ''}`}>
        <span>{question}</span>
        <span className="faq__plus">+</span>
      </button>
      <div className={`faq__a ${isOpen ? 'open' : ''}`}>{answer}</div>
    </div>
  );
}

/* ============================================================
   LANDING PAGE
   ============================================================ */
export default function Landing() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-page)', color: 'var(--color-fg-100)' }}>
      {/* Navigation */}
      <nav className="m-nav marketing">
        <Wordmark />
        <div className="m-nav__links">
          <a href="#demo">Demo</a>
          <a href="#why">Why</a>
          <a href="#faq">FAQ</a>
          <a href="#waitlist" className="m-nav__cta">Join waitlist</a>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero marketing">
        <div className="hero__inner">
          <div className="hero__eyebrow">
            <div className="hero__hair"></div>
            <span>THE CUSTOMER WORKSPACE</span>
          </div>
          <h1>
            Your customers needed <span className="italic">a hero.</span>
            <br />
            <span className="accent">Herofy turns you into one.</span>
          </h1>
          <p className="hero__lede">
            Know which customers need you today, walk into every conversation prepared, and stop finding out
            about churn at the renewal call.
          </p>
          <div className="hero__actions">
            <a href="#waitlist" className="cta">
              <span>Join the waitlist</span>
              <span>&rarr;</span>
            </a>
            <span className="hero__hint">
              <span>See the walkthrough</span>
              <span className="arrow">↓</span>
            </span>
          </div>
        </div>
      </section>

      {/* Guided Demo */}
      <GuidedDemo />

      {/* Proof / Why Section */}
      <section id="why" className="proof marketing">
        <div className="proof__head">
          <SectionEyebrow>Why Herofy</SectionEyebrow>
          <h2>
            One workspace. <span className="accent">Every customer.</span>
          </h2>
        </div>

        <div className="proof-grid">
          <div className="proof-card">
            <div className="hair"></div>
            <h3>Know exactly who needs you</h3>
            <p>
              Open Herofy and see which customers need attention this morning — the one who went quiet, the
              onboarding that stalled, the renewal nobody flagged. <span className="accent">No more tab-hopping to find out.</span>
            </p>
          </div>

          <div className="proof-card">
            <div className="hair"></div>
            <h3>Show up prepared, every time</h3>
            <p>
              Five-minute prep instead of a frantic hour. Herofy reads the email threads, the Slack history,
              the open commitments, and <span className="accent">hands you a brief before the call starts.</span>
            </p>
          </div>

          <div className="proof-card">
            <div className="hair"></div>
            <h3>One place, not five</h3>
            <p>
              Your shared inbox, onboarding tracker, renewal spreadsheet, and account Notion page all come together
              in one workspace. <span className="accent">The work actually happens here</span> — not in three other tabs.
            </p>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="faq marketing">
        <SectionEyebrow>FAQ</SectionEyebrow>
        <h2>Questions you might have</h2>

        <div style={{ maxWidth: 820 }}>
          <FAQItem
            defaultOpen
            question="We already have a helpdesk. Why add another tool?"
            answer="Helpdesks handle inbound support tickets. Herofy handles the whole customer journey — from the sales handoff, through onboarding, to renewal — with your support conversations as one piece of it. Different shape, different job."
          />
          <FAQItem
            question="We're a four-person team. Do we really need a CS platform?"
            answer="You don't need a CS platform. You need to stop dropping customer commitments — and you don't have time to run an enterprise implementation. Herofy is designed to be useful on day one, not after a quarter of setup."
          />
          <FAQItem
            question="How is this different from other AI support tools?"
            answer="Most AI support tools try to reply to your customers for you. Herofy's AI does the opposite — it reads everything happening across your customers and prepares you to act. You stay in every conversation; the AI just makes sure you walk in knowing what matters."
          />
          <FAQItem
            question="We've been burned by AI tools that hallucinate. What's different here?"
            answer="Every signal cites its source. You can dismiss anything. And the rules the AI follows live in a plain-English handbook you can read and edit — no black box, no opaque settings panel."
          />
        </div>
      </section>

      {/* About Us */}
      <section className="about marketing">
        <SectionEyebrow>About us</SectionEyebrow>

        <div className="about__why">
          <h2>Why we're building this</h2>
          <p>
            The tools available for customer success at small B2B SaaS companies were built for a different problem.
            Helpdesks treat every customer as a queue of tickets. Enterprise CS platforms treat every customer as a
            12-week implementation project. Neither was built for the team of one to five people running CS at a
            company where every customer matters individually.
          </p>
          <p>
            Herofy is the workspace we wished we'd had — one place for the whole customer relationship, with AI
            that reads everything happening and prepares the human team to act.
          </p>
        </div>

        <div className="founders">
          <div className="founder">
            <img src="/images/scott-key.png" alt="Scott Key" />
            <h3>Scott Key</h3>
            <p className="role">Co-Founder &amp; CEO</p>
            <p>
              Ran customer success, onboarding, and support at four B2B SaaS companies: ExakTime, QLess, AssetSmart,
              and Convoso. Two of those (QLess and AssetSmart) were in the $1M–$10M ARR range Herofy is built for —
              small teams, high-touch accounts, and the same morning-routine of opening four tabs to find out what was happening.
            </p>
            <p>
              Built Herofy as the workspace I wished I'd had at every one of those jobs.
            </p>
          </div>

          <div className="founder">
            <img src="/images/shiva-mirzadeh.png" alt="Shiva Mirzadeh" />
            <h3>Shiva Mirzadeh</h3>
            <p className="role">Co-Founder &amp; CTO</p>
            <p>
              Engineering leader with deep platform experience — previously at Symantec, YP.com, and other companies
              where scale and security were non-negotiable. Brings the technical foundation that makes "AI watching
              the whole customer relationship" a real product, not a demo.
            </p>
            <p>
              Building Herofy's AI to be transparent about what it knows, honest about what it doesn't, and grounded
              in your actual customer data.
            </p>
          </div>
        </div>
      </section>

      {/* Waitlist CTA */}
      <section id="waitlist" className="waitlist marketing">
        <div className="waitlist__inner">
          <h2>Ready to become your customers' hero?</h2>
          <p>Join the waitlist. We'll let you know when Herofy is ready for you.</p>
          <WaitlistForm />
        </div>
      </section>

      {/* Footer */}
      <footer className="m-foot marketing">
        <span className="m-foot__logo">
          <span className="sigil">
            <img src="/sigil.svg" alt="" style={{ height: 22, width: 22, display: 'block' }} />
          </span>
          <span className="wordmark">Herofy</span>
        </span>
        <div className="m-foot__copy">
          &copy; {new Date().getFullYear()} Herofy. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
