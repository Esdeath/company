# Remove Library Intro

## Goal

Remove the redundant introductory banner shown between the public-site masthead and the research workspace.

## Scope

- Delete the `.library-intro` markup containing the eyebrow, page title, and explanatory sentence.
- Delete CSS used only by that banner, including its responsive layout rule.
- Keep the masthead, three-column research workspace, and footer unchanged.
- Update the app test so it asserts that the removed banner and its copy are absent.

## Result

The research workspace follows the masthead directly, using the existing `.library-main` padding for consistent spacing on desktop and mobile.

## Verification

Run the web unit tests, lint, typecheck, and production build.
