# Remove Admin Intro

## Goal

Remove the introductory banner shown between the authenticated admin masthead and the document workspace.

## Scope

- Delete the `.page-intro` markup containing the eyebrow, page title, and explanatory sentence.
- Delete CSS used only by that banner while preserving shared heading and eyebrow styles used by the login page and workspace sections.
- Keep authentication, the masthead, company picker, document workspace, public-site link, and footer unchanged.
- Adjust page-level alert spacing so errors remain correctly positioned without the banner.
- Update the admin app tests to assert that the removed banner and its copy are absent after authentication and login.

## Result

The company and document workspace follows the authenticated masthead directly, using the existing `main` padding for consistent desktop and mobile spacing.

## Verification

Run the focused admin app tests, then the complete admin lint, typecheck, test, and production build checks.
