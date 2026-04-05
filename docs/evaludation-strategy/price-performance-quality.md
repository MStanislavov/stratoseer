# Web Scraper LLM/API: Price-Performance-Quality Analysis

> Based on first production run data: 205k input + 14k output tokens, 32 calls across 6 categories on gpt-5.4.

## Options

### Option 1: gpt-5.4 (baseline)

- **Cost per run**: ~$0.65 (at ~$2.50/1M input, $10/1M output)
- **Quality**: Best reasoning, but massively overkill for "search + extract structured data"
- **Architecture**: DuckDuckGo search -> fetch URLs -> LLM extracts (5 tool rounds/category)
- **Verdict**: Overpaying for intelligence you don't use

### Option 2: gpt-5.4-mini

- **Cost per run**: ~$0.04 (at ~$0.15/1M input, $0.60/1M output)
- **Quality**: Good enough for structured extraction. The web scraper doesn't need complex reasoning, it needs to parse search results and extract titles/URLs/descriptions
- **Architecture**: Same as current, no code changes beyond `config.py`
- **Savings**: ~94% cost reduction, zero integration effort
- **Verdict**: Best bang-for-buck, lowest risk

### Option 3: Perplexity API (sonar/sonar-pro)

- **Cost per run**: ~$0.22 for sonar ($1/1M tokens + ~$5/1000 searches, ~6 searches/run), more for sonar-pro
- **Quality**: Excellent search quality with built-in citations
- **Architecture change**: Significant. Not OpenAI tool-calling compatible. Needs a custom wrapper to replace both the search tool AND the LLM. Eliminates tool-calling rounds (1 call per category vs 5+), so input tokens drop dramatically
- **Downsides**: Vendor lock-in, new dependency, structured output extraction needs a separate LLM call or custom parsing, latency from built-in search
- **Verdict**: Better search quality, but more expensive than mini and requires significant refactoring

### Option 4: Tavily API (search tool replacement)

- **Cost per run**: ~$0.06-0.10 (Tavily search ~$0.01/search + gpt-5.4-mini for extraction)
- **Quality**: Returns clean, structured, AI-optimized results. Reduces noise vs DuckDuckGo
- **Architecture change**: Moderate. Drop-in replacement for `SafeDuckDuckGoSearchTool`. Same LangChain `BaseTool` interface. Fewer tool rounds needed because results are pre-cleaned
- **Downsides**: Paid service (free tier: 1000 searches/month), another API key to manage
- **Verdict**: Good middle ground -- cleaner results, fewer rounds, but adds cost DuckDuckGo doesn't have

## Comparison

| | Cost/Run | Code Change | Quality | Risk |
|---|---:|:---:|:---:|:---:|
| gpt-5.4 (current) | ~$0.65 | none | overkill | baseline |
| **gpt-5.4-mini** | **~$0.04** | **1 line** | **sufficient** | **near-zero** |
| Perplexity | ~$0.22 | large | excellent | medium |
| Tavily + mini | ~$0.08 | moderate | good | low |

## Decision

**gpt-5.4-mini** (Option 2) selected. 94% cost reduction with minimal risk. If search quality degrades, Tavily is the next upgrade path.
