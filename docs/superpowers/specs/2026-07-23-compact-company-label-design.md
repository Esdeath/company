# Compact Company Label Design

## Goal

Make company entries in the public library directory shorter and keep each label on one line.

## Display Rule

- Render a company with a ticker as `公司名(股票代码)`, for example `泡泡玛特(09992)`.
- Render a company without a ticker as its company name only.
- Do not include the market in the company entry label.
- Keep the label on one line and truncate overflowing text with an ellipsis.

## Scope

Only the company entries in `LibraryDirectory` change. Document entries and the mobile directory trigger retain their current content and behavior.

## Verification

Add component coverage for the formatted label and its single-line truncation class, then run the focused web component test and web checks.
