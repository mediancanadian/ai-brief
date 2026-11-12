# AI Brief

Daily AI intelligence briefing by Shashank Vadrevu.

Published at: https://sjvadrevu.github.io/ai-brief/

## Repository structure

```
index.html        — Archive page listing all issues
index.json        — Machine-readable issue index (date, headline, tags, URL)
config.html       — Microsoft Teams tab configuration page
config.json       — Site configuration (base URL, repo)
robots.txt        — AI training crawler rules
issues/
  daily/          — Daily briefing HTML files (YYYY/MM/YYYY-MM-DD.html)
  weekly/         — Weekly digest HTML files (YYYY/MM/YYYY-MM-DD.html)
```

## Microsoft Teams integration

`config.html` is the Teams tab configuration page. It uses the Teams JS SDK to register the tab and point it at the published site URL. To add AI Brief as a Teams tab, use the configuration URL:

```
https://sjvadrevu.github.io/ai-brief/config.html
```

## Adding a new issue

1. Create the issue HTML file under `issues/daily/` or `issues/weekly/` following the existing date-based path convention.
2. Add a corresponding entry to the top of `index.json` with `type`, `date`, `url`, `headline`, and `tags`.
