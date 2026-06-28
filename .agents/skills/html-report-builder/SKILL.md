---
name: html-report-builder
description: >
  Build a self-contained HTML report as a companion artifact for audits, verifications, research, or long multi-command
  investigations. Always send a concise chat answer first, then save the HTML report under ./tmp/ and include a 
  clickable path in chat. Triggers: "report", "audit", "check", "verify", "findings", "summary".
metadata:
  context: fork
---

# Report builder (HTML companion)

Use this skill when the user asks for a report, audit, verification/check, research write‑up,
long-form findings, or when multi-step commands would benefit from a browsable artifact.
The skill produces two outputs:

1. A concise chat response (always first)
2. A companion, self-contained HTML5 report saved under ./tmp/ with a clickable path in chat

## Workflow

1. Answer briefly in chat with the key outcome(s).
2. Generate/update the HTML report under ./tmp/ using a descriptive filename pattern:
   - tmp/<task>-report-YYYYMMDD-HHMMSS.html (example: tmp/verify-tests-report-20260514-102530.html)
3. Include a markdown link to the file path in your chat reply: ./tmp/....html
4. During long investigations, update the report incrementally to reflect progress.

## Report structure (sections)

- Title and timestamp
- Executive summary (1–3 sentences)
- Context (why this report exists)
- Findings (bullet points with supporting data)
- Commands run (exact commands)
- Evidence (selected logs/test output; truncate if huge and note truncation)
- Recommendations (clear next steps)
- References (clickable links to sources, tickets, docs)

## Presentation

- Keep the file self-contained (inline CSS only; no external assets) and UTF‑8 encoded.
- Default theme: dark blue background, white text, clean layout. Emojis (✅/❌) allowed for quick status cues.
- Add a simple progress bar when useful (see template below).

## Safety and repo hygiene

- Save only under ./tmp/.
- Do not commit files from ./tmp/.
- Never include secrets/credentials or large binary dumps. For long logs, write the full log to
  a separate ./tmp/*.log file and link to it from the report; include only short excerpts inline.

## Validation checklist (pre-publish)

Use this checklist before linking the report in chat:

- [ ] Sent a concise chat answer first (key outcomes, link follows)
- [ ] Report saved under ./tmp/ using <task>-report-YYYYMMDD-HHMMSS.html
- [ ] Title includes the task and a human-readable timestamp
- [ ] Executive summary (1–3 sentences) is present and accurate
- [ ] Sections included and populated:
  - [ ] Context (why the report exists)
  - [ ] Findings (bullet points with supporting data)
  - [ ] Commands run (exact commands)
  - [ ] Evidence (short excerpts); note any truncation and link full logs in ./tmp/*.log
  - [ ] Recommendations (clear next steps with owners if known)
  - [ ] References (clickable URLs and/or local ./tmp files)
- [ ] Progress bar included when investigation was multi-step or long-running
- [ ] No secrets/PII/sensitive credentials present; redact if needed
- [ ] Large outputs/logs truncated in-page; full logs saved separately in ./tmp and linked
- [ ] Self-contained HTML (inline CSS only), UTF-8 encoded; code blocks readable
- [ ] Clickable filesystem path included in the chat message to the report (and any log files)
- [ ] All links/paths tested and resolve correctly
- [ ] If using assets/report-template.html, replaced placeholders ([TASK], [TIMESTAMP], [PROGRESS%], etc.)
- [ ] Files in ./tmp/ are not committed to git

## Minimal HTML template

You can start from assets/report-template.html when you need a fuller starting point.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>[TASK] Report — 2026-05-14 10:25</title>
  <style>
    :root { --bg:#0b1d3a; --fg:#ffffff; --muted:#b8c3d6; --accent:#61dafb; --ok:#22c55e; --err:#ef4444; }
    body { margin:0; background:var(--bg); color:var(--fg); font: 16px/1.5 system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, "Apple Color Emoji","Segoe UI Emoji"; }
    .container { max-width: 960px; margin: 40px auto; padding: 0 20px; }
    h1, h2, h3 { line-height:1.2; margin: 1.25em 0 0.5em; }
    h1 { font-size: 1.8rem; }
    h2 { font-size: 1.3rem; color: var(--accent); }
    p, li { color: var(--fg); }
    .muted { color: var(--muted); }
    .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#0e2954; color:#cde3ff; font-size:12px; }
    pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
    pre { white-space: pre-wrap; word-break: break-word; background:#0a1730; padding:12px; border-radius:8px; border:1px solid #0e2a58; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .progress { background:#0a1730; border:1px solid #0e2a58; border-radius:8px; height:16px; width:100%; overflow:hidden; }
    .bar { height:100%; width:40%; background:linear-gradient(90deg,#2563eb,#22c55e); }
    .kv { display:grid; grid-template-columns: 160px 1fr; gap:8px 16px; }
    .kv div:nth-child(odd) { color: var(--muted); }
  </style>
</head>
<body>
  <div class="container">
    <h1>🔎 [TASK] Report <span class="pill">2026-05-14 10:25</span></h1>
    <p class="muted">Context: Briefly state why this report was generated.</p>

    <h2>Executive summary</h2>
    <p>1–3 sentences with the key outcome(s). ✅ Passed X checks. ❌ Found Y issues.</p>

    <h2>Progress</h2>
    <div class="progress" title="40% complete"><div class="bar" style="width:40%"></div></div>

    <h2>Findings</h2>
    <ul>
      <li>Finding 1 — short statement with supporting data.</li>
      <li>Finding 2 — short statement with supporting data.</li>
    </ul>

    <h2>Commands run</h2>
    <pre><code>$ command one --flag
[trimmed output]

$ command two
[trimmed output]</code></pre>

    <h2>Evidence (selected excerpts)</h2>
    <pre><code>[short log/test output excerpts]
[Note: full logs saved to ./tmp/XYZ.log]</code></pre>

    <h2>Recommendations</h2>
    <ol>
      <li>Specific next step 1</li>
      <li>Specific next step 2</li>
    </ol>

    <h2>References</h2>
    <ul>
      <li><a href="https://example.com" target="_blank" rel="noopener noreferrer">Source link</a></li>
    </ul>
  </div>
</body>
</html>
```

## Minimal examples

- Filename convention: tmp/<task>-report-YYYYMMDD-HHMMSS.html
- Open locally (macOS/Linux): `open ./tmp/<file>.html` or `xdg-open ./tmp/<file>.html`

Do not replace the chat response with the HTML. The HTML is a companion artifact only and should not hold the only copy of crucial information.
