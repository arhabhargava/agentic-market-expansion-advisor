import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

const ANALYSIS_STAGES = [
  { icon: 'hub',            text: 'Connecting to MCP tools' },
  { icon: 'travel_explore', text: 'Fetching country data' },
  { icon: 'analytics',      text: 'Scoring market potential' },
  { icon: 'leaderboard',    text: 'Comparing markets' },
  { icon: 'psychology',     text: 'Generating recommendations' },
  { icon: 'auto_awesome',   text: 'Synthesizing insights' },
]

const PRODUCT_SUGGESTIONS = [
  'Luxury watches', 'SaaS platform', 'FMCG snacks',
  'Healthcare app', 'EdTech courses', 'Fintech wallet', 'E-commerce fashion',
]

const RANK_LABELS = ['1st', '2nd', '3rd', '4th', '5th']

function Icon({ name, className = '' }) {
  return <span className={`material-symbols-outlined ${className}`}>{name}</span>
}

function ScoreBar({ pct }) {
  return (
    <div className="w-full bg-surface-container h-2 rounded-full mb-lg overflow-hidden">
      <div
        className="bg-primary h-full rounded-full score-bar-fill"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function StatBox({ label, value }) {
  return (
    <div className="bg-surface p-sm rounded-lg border border-outline-variant">
      <p className="text-label-bold text-on-surface-variant">{label}</p>
      <p className="text-h3">{value}</p>
    </div>
  )
}

function MarketCard({ item, rank, isTop }) {
  const score100 = Math.round(item.score * 10)
  const pct = score100

  const gdp = item.gdp_bn != null
    ? item.gdp_bn >= 1000
      ? `$${(item.gdp_bn / 1000).toFixed(1)}T`
      : `$${item.gdp_bn.toFixed(0)}B`
    : 'N/A'

  const pop = item.population >= 1_000_000
    ? `${(item.population / 1_000_000).toFixed(1)}M`
    : item.population.toLocaleString()

  const region = item.region || '—'

  return (
    <article className={`bg-surface-container-lowest border rounded-xl p-lg shadow-sm hover:shadow-md transition-shadow ${
      isTop ? 'border-primary/20' : 'border-outline-variant'
    }`}>
      <div className="flex flex-col md:flex-row gap-lg">
        {/* Rank number */}
        <div className="flex-none">
          <div className={`w-16 h-16 rounded-xl flex items-center justify-center text-h1 font-bold ${
            isTop ? 'bg-primary text-white' : 'bg-primary/20 text-primary'
          }`}>
            {rank + 1}
          </div>
        </div>

        <div className="flex-grow">
          {/* Name + score */}
          <div className="flex justify-between items-start mb-md">
            <div>
              <h3 className="text-h2">{item.country}</h3>
              <p className="text-body-md text-on-surface-variant">
                {region}
                {item.product_fit?.product_type ? ` • ${item.product_fit.product_type}` : ''}
              </p>
            </div>
            <div className="text-right">
              <div className="text-label-bold text-on-surface-variant mb-xs">MARKET SCORE</div>
              <div className="text-h2 text-primary">{score100}/100</div>
            </div>
          </div>

          <ScoreBar pct={pct} />

          {/* Stats */}
          <div className="grid grid-cols-3 gap-md mb-lg">
            <StatBox label="POPULATION" value={pop} />
            <StatBox label="GDP" value={gdp} />
            <StatBox label="REGION" value={region.split(' ')[0]} />
          </div>

          {/* Reasoning */}
          <div className={`p-md rounded-lg border ${
            isTop
              ? 'bg-primary-container/10 border-primary/20'
              : 'bg-surface-container border-outline-variant'
          }`}>
            <div className={`flex items-center gap-xs font-semibold text-label-bold mb-xs ${
              isTop ? 'text-primary' : 'text-on-surface-variant'
            }`}>
              <Icon name={isTop ? 'verified' : 'analytics'} />
              {isTop ? 'HIGH CONFIDENCE REASONING' : `${RANK_LABELS[rank]?.toUpperCase()} — REASONING`}
            </div>
            <p className="text-body-md text-on-surface">{item.reasoning}</p>

            {/* Fit bonuses */}
            {item.product_fit?.bonuses_applied?.length > 0 && (
              <div className="flex flex-wrap gap-xs mt-sm">
                {item.product_fit.bonuses_applied.map((b, i) => (
                  <span key={i} className="text-label-bold bg-primary/10 text-primary px-sm py-xs rounded">
                    {b}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}

function AnalysisProcess({ steps, summary, confidence }) {
  const toolSteps = (steps || []).filter(s => !s.startsWith('Assistant:'))
  return (
    <details open className="group bg-surface-container-low border border-outline-variant rounded-xl overflow-hidden">
      <summary className="flex items-center justify-between p-lg cursor-pointer list-none hover:bg-surface-container transition-colors">
        <div className="flex items-center gap-md">
          <Icon name="account_tree" className="text-primary" />
          <h2 className="text-h3">Full Analysis Process</h2>
        </div>
        <Icon name="expand_more" className="chevron-icon" />
      </summary>
      <div className="p-lg border-t border-outline-variant bg-surface-container-lowest">
        {summary && (
          <div className="mb-lg p-md bg-primary/5 border border-primary/20 rounded-xl">
            <div className="flex items-center gap-xs text-primary text-label-bold mb-xs">
              <Icon name="summarize" />
              AI SUMMARY
              {confidence != null && (
                <span className="ml-auto bg-primary text-white px-sm py-xs rounded text-label-md">
                  {Math.round(confidence * 100)}% confidence
                </span>
              )}
            </div>
            <div className="prose-summary text-body-md text-on-surface">
              <ReactMarkdown>{summary}</ReactMarkdown>
            </div>
          </div>
        )}

        {toolSteps.length > 0 && (
          <>
            <p className="text-label-bold text-on-surface-variant mb-md">TOOL CALLS ({toolSteps.length})</p>
            <div className="space-y-sm">
              {toolSteps.map((step, i) => (
                <div key={i} className="flex items-start gap-sm">
                  <span className="text-label-bold text-primary bg-primary/10 rounded px-xs py-xs min-w-[24px] text-center">{i + 1}</span>
                  <code className="text-body-md text-on-surface-variant font-mono bg-surface-container px-sm py-xs rounded flex-1 break-all">
                    {step}
                  </code>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </details>
  )
}

function TypingDots() {
  return (
    <span className="typing-dots" aria-label="thinking">
      <span /><span /><span />
    </span>
  )
}

function AgentLoader({ product }) {
  const [stageIndex, setStageIndex] = useState(0)
  const intervalRef = useRef(null)

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setStageIndex(i => Math.min(i + 1, ANALYSIS_STAGES.length - 1))
    }, 2800)
    return () => clearInterval(intervalRef.current)
  }, [])

  const stage = ANALYSIS_STAGES[stageIndex]

  return (
    <div className="bg-surface-container-lowest border border-primary/20 rounded-xl p-xl space-y-lg shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-md">
        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center agent-pulse">
          <Icon name="psychology" className="text-primary" />
        </div>
        <div>
          <p className="text-label-bold text-primary">AGENT ANALYZING MARKETS</p>
          <p className="text-body-md text-on-surface-variant">
            {product ? `Product: ${product}` : 'Running full market analysis'}
          </p>
        </div>
      </div>

      {/* Current stage with typing dots */}
      <div className="flex items-center gap-sm bg-primary/5 border border-primary/15 rounded-lg px-md py-sm">
        <Icon name={stage.icon} className="text-primary text-body-lg" />
        <span className="text-body-md text-on-surface font-medium">{stage.text}</span>
        <TypingDots />
      </div>

      {/* Progressive step list */}
      <div className="space-y-xs">
        {ANALYSIS_STAGES.map((s, i) => {
          const done = i < stageIndex
          const active = i === stageIndex
          return (
            <div key={i} className={`flex items-center gap-sm text-body-md transition-all duration-500 ${
              active ? 'text-on-surface' : done ? 'text-on-surface-variant' : 'text-outline opacity-40'
            }`}>
              <Icon
                name={done ? 'check_circle' : active ? 'radio_button_checked' : 'radio_button_unchecked'}
                className={`text-body-lg ${done ? 'text-primary' : active ? 'text-primary' : 'text-outline'}`}
              />
              <span className={done ? 'line-through opacity-60' : ''}>{s.text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function App() {
  const [countries, setCountries] = useState('')
  const [product, setProduct] = useState('')
  const [budget, setBudget] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!countries.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const body = { countries: countries.trim(), product: product.trim() }
      if (budget) body.budget = budget
      const res = await fetch('http://localhost:8000/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`)
      setResult(data)
    } catch (err) {
      setError(err.message || 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  const recs = result?.recommendations || []

  return (
    <div className="bg-background text-on-surface min-h-screen">
      {/* Top App Bar */}
      <header className="fixed top-0 left-0 w-full z-50 flex items-center justify-between px-lg py-sm bg-surface border-b border-outline-variant">
        <div className="flex items-center gap-sm">
          <Icon name="language" className="text-primary text-h2" />
          <h1 className="text-h2 font-bold text-primary">Market Advisor</h1>
        </div>
        <nav className="hidden md:flex items-center gap-lg">
          <a className="text-label-md text-primary" href="#">Analyze</a>
          <a className="text-label-md text-on-surface-variant hover:bg-surface-container-low transition-colors px-sm py-xs rounded" href="#">Markets</a>
          <a className="text-label-md text-on-surface-variant hover:bg-surface-container-low transition-colors px-sm py-xs rounded" href="#">Insights</a>
          <a className="text-label-md text-on-surface-variant hover:bg-surface-container-low transition-colors px-sm py-xs rounded" href="#">Settings</a>
        </nav>
        <button className="material-symbols-outlined text-on-surface-variant hover:bg-surface-container-low p-xs rounded-full transition-colors">
          account_circle
        </button>
      </header>

      <main className="mt-[72px] min-h-screen px-margin py-xl max-w-[1440px] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">

          {/* ── Left Column: Input ── */}
          <section className="md:col-span-4 space-y-lg">
            <form
              onSubmit={handleSubmit}
              className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg shadow-sm"
            >
              <h2 className="text-h3 mb-md">Market Criteria</h2>
              <div className="space-y-md">

                <div>
                  <label className="text-label-bold text-on-surface-variant block mb-xs">
                    WHICH COUNTRIES ARE YOU CONSIDERING?
                  </label>
                  <textarea
                    value={countries}
                    onChange={e => setCountries(e.target.value)}
                    className="w-full bg-surface border border-outline rounded-lg p-md text-body-md focus:border-primary focus:ring-1 focus:ring-primary outline-none min-h-[100px] transition-all resize-none"
                    placeholder="Germany, Japan, France, Brazil..."
                    disabled={loading}
                    required
                  />
                </div>

                <div>
                  <label className="text-label-bold text-on-surface-variant block mb-xs">
                    PRODUCT TYPE
                  </label>
                  <input
                    type="text"
                    value={product}
                    onChange={e => setProduct(e.target.value)}
                    className="w-full bg-surface border border-outline rounded-lg px-md py-sm text-body-md focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                    placeholder="e.g. luxury watches, SaaS platform..."
                    disabled={loading}
                  />
                  <div className="flex flex-wrap gap-xs mt-sm">
                    {PRODUCT_SUGGESTIONS.map(s => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setProduct(s)}
                        disabled={loading}
                        className={`text-label-md px-sm py-xs rounded border transition-colors ${
                          product === s
                            ? 'border-primary text-primary bg-primary/10'
                            : 'border-outline-variant text-on-surface-variant hover:border-primary hover:text-primary'
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-label-bold text-on-surface-variant block mb-xs">
                    EXPANSION BUDGET TIER
                  </label>
                  <select
                    value={budget}
                    onChange={e => setBudget(e.target.value)}
                    disabled={loading}
                    className="w-full bg-surface border border-outline rounded-lg px-md py-sm text-body-md focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                  >
                    <option value="">Any</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={loading || !countries.trim()}
                  className="w-full bg-primary-container text-on-primary-container py-md rounded-lg text-label-bold uppercase tracking-widest active:scale-95 transition-transform flex items-center justify-center gap-xs disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Icon name={loading ? 'hourglass_empty' : 'search_insights'} />
                  {loading ? 'Analyzing...' : 'Analyze Markets'}
                </button>
              </div>
            </form>

            <div className="bg-secondary-container/30 border border-outline-variant rounded-xl p-lg">
              <div className="flex items-center gap-sm mb-sm text-on-secondary-container">
                <Icon name="info" />
                <h3 className="text-label-bold">ANALYSIS NOTES</h3>
              </div>
              <p className="text-body-md text-on-surface-variant leading-relaxed">
                Our intelligence engine evaluates market feasibility using real GDP data (World Bank),
                population, regional stability, and product-specific fit scoring across 7 product categories.
              </p>
            </div>
          </section>

          {/* ── Right Column: Results ── */}
          <section className="md:col-span-8 space-y-lg">
            <div className="flex items-center justify-between">
              <h2 className="text-h2 text-on-surface">
                {recs.length > 0 ? 'Top Recommended Markets' : 'Market Analysis Results'}
              </h2>
              {recs.length > 0 && (
                <span className="bg-primary/10 text-primary px-sm py-xs rounded text-label-md">
                  {recs.length} Market{recs.length !== 1 ? 's' : ''} Found
                </span>
              )}
              {result?.product_category && (
                <span className="bg-primary text-white px-sm py-xs rounded text-label-md">
                  {result.product_category}
                </span>
              )}
            </div>

            {/* Error */}
            {error && (
              <div className="bg-error-container border border-error/30 rounded-xl p-lg text-on-error-container">
                <div className="flex items-center gap-sm font-semibold mb-xs">
                  <Icon name="error" />
                  Analysis Error
                </div>
                <p className="text-body-md">{error}</p>
              </div>
            )}

            {/* Loading */}
            {loading && <AgentLoader product={product} />}

            {/* Empty state */}
            {!loading && !error && recs.length === 0 && (
              <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-xl flex flex-col items-center gap-md text-center">
                <Icon name="public" className="text-h1 text-outline" />
                <p className="text-body-lg text-on-surface-variant">
                  {result
                    ? 'Analysis complete — no market data was returned. Check the Full Analysis Process below for details.'
                    : 'Enter countries and click Analyze to see market recommendations.'}
                </p>
              </div>
            )}

            {/* Market cards */}
            {recs.map((item, i) => (
              <MarketCard key={item.country} item={item} rank={i} isTop={i === 0} />
            ))}
          </section>
        </div>

        {/* Full Analysis Process */}
        {result && (
          <div className="mt-xl">
            <AnalysisProcess
              steps={result.reasoning_chain}
              summary={result.summary}
              confidence={result.confidence_score}
            />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="w-full flex flex-col items-center gap-xs py-lg px-margin mb-[64px] bg-surface-container-low border-t border-outline-variant">
        <div className="flex items-center gap-lg">
          <a className="text-body-md text-secondary hover:text-primary transition-colors" href="#">GitHub</a>
          <a className="text-body-md text-secondary hover:text-primary transition-colors" href="#">Documentation</a>
        </div>
        <p className="text-label-bold text-outline">Powered by AI Intelligence Agent</p>
        <p className="text-body-md text-secondary opacity-80">© 2025 Market Advisor. All rights reserved.</p>
      </footer>

      {/* Mobile Bottom Nav */}
      <nav className="md:hidden fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-sm py-xs bg-surface border-t border-outline-variant shadow-sm">
        <div className="flex flex-col items-center bg-primary-container text-on-primary-container rounded-full px-md py-xs">
          <Icon name="search_insights" />
          <span className="text-label-md">Analyze</span>
        </div>
        <div className="flex flex-col items-center text-on-surface-variant">
          <Icon name="analytics" />
          <span className="text-label-md">Markets</span>
        </div>
        <div className="flex flex-col items-center text-on-surface-variant">
          <Icon name="psychology" />
          <span className="text-label-md">Insights</span>
        </div>
        <div className="flex flex-col items-center text-on-surface-variant">
          <Icon name="settings" />
          <span className="text-label-md">Settings</span>
        </div>
      </nav>
    </div>
  )
}
