---
name: html-report-builder
description: >
  Build a self-contained HTML report as a companion artifact for audits, verifications, research, or long multi-command
  investigations. Always send a concise chat answer first, then save the HTML report under ./tmp/ and include a
  clickable path in chat. Triggers: "report", "audit", "check", "verify", "findings", "summary".
context: fork
---

# Report builder (HTML companion)

Use when the user asks for a report, audit, verification/check, research write‑up,
long-form findings, or when multi-step commands would benefit from a browsable artifact.
Produces two outputs: (1) a concise chat response (always first), (2) a self-contained
HTML5 report saved under `./tmp/` with a clickable path in chat.

## Workflow

1. Answer briefly in chat with the key outcome(s).
2. Save the HTML report under `./tmp/` as `tmp/<task>-report-YYYYMMDD-HHMMSS.html`.
3. Include a markdown link to the file path in your chat reply.
4. During long investigations, update the report incrementally.

## Report structure

- Title and timestamp
- Executive summary (1–3 sentences)
- Context (why this report exists)
- Findings (bullets with supporting data)
- Commands run (exact commands)
- Evidence (selected logs/test output; truncate if huge, note truncation, link full logs in `./tmp/*.log`)
- Recommendations (clear next steps)
- References (clickable links)

## Presentation

- Self-contained: inline CSS only, no external assets, UTF‑8 encoded.
- Default theme: dark blue background, white text. Emojis (✅/❌) for quick status cues.
- Add a progress bar when useful (see template).

## Safety and repo hygiene

- Save only under `./tmp/`. Do not commit files from `./tmp/`.
- Never include secrets/credentials or large binary dumps. Write full logs to `./tmp/*.log` and link.

## Validation checklist (pre-publish)

- [ ] Sent a concise chat answer first
- [ ] Report saved under `./tmp/` as `<task>-report-YYYYMMDD-HHMMSS.html`
- [ ] Executive summary present and accurate
- [ ] Sections populated: Context, Findings, Commands run, Evidence, Recommendations, References
- [ ] Progress bar included when multi-step/long-running
- [ ] No secrets/PII; large outputs truncated in-page with full logs in `./tmp/` and linked
- [ ] Self-contained HTML (inline CSS only), UTF‑8, code blocks readable
- [ ] Clickable filesystem path included in chat
- [ ] All links/paths resolve
- [ ] If using `.claude/skills/html-report-builder/assets/report-template.html`, replaced placeholders (`[TASK]`, `[TIMESTAMP]`, `[PROGRESS%]`, etc.)

## HTML template

Start from `.claude/skills/html-report-builder/assets/report-template.html` when you need a fuller starting point.
The file lives at that exact path inside this skill folder.

Minimal inline fallback (dark-blue theme, single-file):

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>[TASK] Report — [TIMESTAMP]</title>
  <style>
    :root { --bg:#0b1d3a; --fg:#fff; --muted:#b8c3d6; --accent:#61dafb; }
    body { margin:0; background:var(--bg); color:var(--fg);
           font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Arial,"Apple Color Emoji","Segoe UI Emoji"; }
    .container { max-width:960px; margin:40px auto; padding:0 20px; }
    h1,h2 { line-height:1.2; margin:1.25em 0 .5em; } h1{font-size:1.8rem} h2{font-size:1.3rem;color:var(--accent)}
    .muted { color:var(--muted); }
    pre { white-space:pre-wrap; word-break:break-word; background:#0a1730; padding:12px; border-radius:8px; }
    a { color:var(--accent); text-decoration:none; } a:hover{ text-decoration:underline; }
    .progress { background:#0a1730; border-radius:8px; height:16px; overflow:hidden; }
    .bar { height:100%; width:40%; background:linear-gradient(90deg,#2563eb,#22c55e); }
  </style>
</head>
<body>
  <div class="container">
    <h1>🔎 [TASK] Report <span class="muted">[TIMESTAMP]</span></h1>
    <p class="muted">Context: why this report was generated.</p>
    <h2>Executive summary</h2>
    <p>1–3 sentences with key outcomes. ✅ Passed X. ❌ Found Y.</p>
    <h2>Progress</h2>
    <div class="progress"><div class="bar" style="width:40%"></div></div>
    <h2>Findings</h2>
    <ul><li>Finding — short statement with data.</li></ul>
    <h2>Commands run</h2>
    <pre><code>$ command --flag
[trimmed output]</code></pre>
    <h2>Evidence</h2>
    <pre><code>[short excerpts; full logs in ./tmp/*.log]</code></pre>
    <h2>Recommendations</h2>
    <ol><li>Specific next step</li></ol>
    <h2>References</h2>
    <ul><li><a href="https://example.com" target="_blank" rel="noopener noreferrer">Source</a></li></ul>
  </div>
</body>
</html>
```

Do not replace the chat response with the HTML. The HTML is a companion artifact only.
