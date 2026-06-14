---
name: html-reporting
description: Generate a polished companion HTML report for detailed answers, checks, and verification outputs. Use this for complex multiple-command investigations or when asked for a report. Always produce the normal chat response first, then generate the HTML report as a companion artifact. Include a clickable path to the report in the chat response.
context: fork
---

# HTML Reporting Skill

Use this skill whenever the user requests a detailed answer, research, verification, or any "check" or "report" about code, tests, or project state. The skill produces two artifacts:

1. A normal chat response (always required).
2. A companion, self-contained HTML5 report saved under ./tmp/ with a clickable path included in the chat response.
3. Make the HTML visually appealing, with a dark blue background, white text, and a clean layout. Use inline CSS for styling.
4. Use UTF-8 emojis for visual flair where possible (e.g., ✅ for success, ❌ for failure).
5. Update the report file frequently during long-running investigations to reflect progress and findings.
6. Add a progress bar for the task. 

Guidelines and steps

1. When to use
   - The user explicitly asks for a report, detailed answer, verification, or research.
   - The user asks for anything to be "checked", "reported", "verified", "audited", or needs a long-form explanation that benefits from a browsable artifact.

2. Produce the normal chat response first
   - Keep the chat response concise and to the point.
   - Do not replace or delay the chat response in favor of the HTML. The HTML is a companion artifact only.

3. Generate the HTML report
   - Save it under ./tmp/. Use a descriptive filename: <task>-report-YYYYMMDD-HHMMSS.html (example: tmp/report-verify-tests-20260514-102530.html).
   - The report must be a complete HTML5 document with a descriptive <title>.
   - Include a short executive summary near the top (1-3 sentences).
   - Organize sections with clear headings: Summary, Findings, Commands Run, Evidence (logs, test output), Recommendations, References.
   - Use simple inline CSS for readable typography, constrained width, and spacing.
   - Style code blocks with monospace font and preserve whitespace.
   - When sources are used, include a References section with clickable links.
   - Keep the file self-contained (inline CSS). Avoid external assets unless unavoidable.

4. What to include in the report
   - A brief context paragraph describing why the report was generated.
   - Exact commands that were run and their outputs (truncate very large outputs but note truncation and where full output can be found if applicable).
   - If tests were run, show failing tests and short excerpts of failure traces.
   - A clear Recommendations section with next steps.

5. Safety and repo hygiene
   - Save reports only under ./tmp/.
   - Do not commit files from ./tmp/.
   - Never include secrets, credentials, or large binary dumps in the report.

6. User-facing link
   - In the chat response, include a clickable filesystem path to the generated HTML (markdown link to file path: ./tmp/...).
   - If the environment doesn't support clickable file URIs, include the path and a short instruction to open it (example: `open ./tmp/filename.html`).

7. When to prefer the report
   - Use the HTML companion for long-running investigations, multi-command verification runs, or when results are easier to digest in a formatted artifact.

8. Minimal examples
   - Filename convention and example command to open the file.

Do not replace the chat response with the HTML. The HTML is a companion artifact only and should not hold the only copy of crucial information.
