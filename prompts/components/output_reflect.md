## Output Format

Respond with a **single JSON object** — no markdown fences, no text outside the JSON:

```
{
  "is_complete": True | False,
  "reasoning": "<critical evaluation: what was found, source quality, what is missing and why it matters>",
  "gap": "<the most important missing data points, stated as a specific metrics/figures/filings — or null if complete>",
  "next_step": "<plain-English instructions describing exactly what to retrieve next and from where — or null if complete>"
}
```

Field rules:
- `reasoning`: must reference specific figures from the observations and name the source type (e.g. "primary SEC filing", "market data feed", "news summary"). Do not be vague.
- `gap`: concrete missing items only — e.g. "Apple's FY2024 operating income from the 10-K"  "using alternative tools to fetch missing data". Null when `is_complete` is True.
- `next_step`: written for the planner to act on, in plain English with — e.g. "Look up Apple's FY2024 operating income from their annual SEC filing or search web or financial market sources." Null when `is_complete` is True.
