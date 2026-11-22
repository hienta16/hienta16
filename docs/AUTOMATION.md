# How the automation works

This repository is the hub of Hien's GitHub identity. Python fetches the numbers, checks them, draws the pictures
and runs the cat's toy box; GitHub Actions run that Python on a schedule and when a visitor opens an issue. The
website (`hienta16/hienta16.github.io`) reads the same data files, so both surfaces show one set of numbers.

```
GitHub GraphQL + REST API ─┐
public contribution page ──┼─► catwalk.stats ──► data/github.json ──┐
                           │                                        ├─► catwalk.render ──► assets/generated/*.svg
issue "[cat-toy] yarn" ────┴─► catwalk.toys ───► data/toys.json ────┘                     README.md (marked parts)
                                                                     └─► website: src/data/hub/ (copied by
                                                                         scripts/sync_hub.py in the site repo)
```

Only the Python standard library is used. Nothing is installed in the Actions; the tests run with `unittest`.

## Run it yourself

```bash
python -m catwalk refresh          # fetch GitHub stats into data/github.json (uses `gh auth token` locally)
python -m catwalk render           # draw every SVG and update the README's generated parts
python -m catwalk toys demo        # watch sample visitors go through the real toy rules (no GitHub calls)
python -m catwalk toys status      # what is in the toy box right now
python -m catwalk check            # validate config and data files
python -m unittest discover -s tests -v
```

The cat and toy drawings come from the website, where they are React components. After changing them there,
run `npm run export:art` in the website repository; it writes static copies into `assets/art/` here.
`tools/build_font.py` (needs `pip install fonttools brotli`) rebuilds the font subset; you rarely need it.

## The Python, module by module

| File | What it does |
|---|---|
| `catwalk/cli.py` | Every command above. Each workflow step is one of these commands. Start reading here. |
| `catwalk/config.py` | Paths, and `config/catwalk.json` (login, links, the two go-live switches). |
| `catwalk/jsonio.py` | Atomic writes (temp file + rename) and "write only if changed", so quiet runs commit nothing. |
| `catwalk/timeutil.py` | UTC everywhere; refuses timestamps without a time zone. |
| `catwalk/github/client.py` | A small API client on `urllib`: retries on 5xx, stops at once on rate limits, never logs or sends the token anywhere but api.github.com. |
| `catwalk/github/public_calendar.py` | Reads the anonymous contribution page, the privacy guard below. |
| `catwalk/stats/calendar.py` | The calendar model and every metric: active days, streaks (an empty *today* does not break the current one), months, weekdays, the five levels. |
| `catwalk/stats/languages.py` | Language shares by code size and by repository. No repository names leave this module. |
| `catwalk/stats/snapshot.py` | Builds `data/github.json` from independent sections, each with its own `asOf`. |
| `catwalk/toys/rules.py` | Loads `config/toys.json`: lifetimes, cooldown, display cap, copy. |
| `catwalk/toys/events.py` | Turns a GitHub `issues` event into a gift request, trusting only fields GitHub sets. |
| `catwalk/toys/engine.py` | The rules as pure functions: duplicates, cooldown, lifetimes, display cap, expiry, pruning. |
| `catwalk/toys/models.py` | `data/toys.json` as typed objects; strict loading, deterministic saving. |
| `catwalk/toys/replies.py` | Fixed reply templates; the visitor's text is never quoted back. |
| `catwalk/toys/demo.py` | The local demonstration. |
| `catwalk/render/*.py` | Pure functions from data to SVG: `iso` (3D year), `cards` (stats, languages, rhythm), `beat`, `banner`, `toybox`, `buttons`, `readme`. |

## Numbers you can trust

* **Contributions are not commits.** The calendar counts what GitHub's profile calendar counts: commits to default
  branches, pull requests, issues and reviews. "Commits I authored" is a separate search-API count and is labelled
  separately everywhere.
* **Privacy guard.** The API calendar is published only if it matches the anonymous public page day by day (today
  may lag a few minutes; the smaller number wins). If anything differs, the last good calendar is kept.
* **Private repositories count as numbers only.** With a personal token the counts include private repositories;
  no repository name, title or message is stored.
* **Automation is not me.** Commits made by `github-actions[bot]` (including this repository's own refresh commits)
  have a different author, so they appear in neither the calendar nor the commit count.
* **No guessing.** A section that cannot be fetched keeps its last value with the date it was true (`asOf`). A
  section that was never fetched is `null` and drawn as "n/a". `refresh.problems` lists what went wrong.
* **A public-only run never overwrites complete numbers.** Without `CATWALK_STATS_TOKEN`, the workflow's own token
  sees only public data; the last complete counts are kept and the problem is recorded.
* **Not real-time.** The README and data refresh every 6 hours (and right after each toy gift). Every image shows
  the time of its last refresh.

## The toy box rules (config/toys.json)

| Rule | Value | Where |
|---|---|---|
| Yarn ball | stays 168 hours (7 days); pink or blue, alternating by issue number | `toys.yarn.lifetime_hours` |
| Feather toy | stays 48 hours | `toys.feather.lifetime_hours` |
| Cardboard box | stays 336 hours (14 days) | `toys.box.lifetime_hours` |
| Gifts per account | 1 per rolling 24 hours, by numeric account id (renaming does not reset it), measured on the issues' creation times: two gifts from one account are never both accepted within 24 hours of each other, whichever run comes first | `cooldown_hours` |
| Toys in the scene | at most 9 (configurable up to 12); the oldest by creation time goes back on the shelf early, never a newer one, and the total still counts it | `max_visible` |
| Memory | accepted gifts are remembered for 30 days (duplicates, cooldowns); issues older than 29 days (30 days minus the cooldown) are skipped as stale | `history_days` |

`created_at` is GitHub's issue creation time; `expires_at = created_at + lifetime`, both UTC. A toy leaves the
scene at exactly `expires_at`: the refresh workflow removes it from `data/toys.json` and the website also hides it
on its own clock, so an expired toy never shows even between refreshes. `totals` keeps every accepted gift forever.

Outcomes: `accepted` (reply, close as completed), `cooldown`, `unknown_toy`, `not_a_person` (bots and
organisations), `stale` (too old, or would already have expired; reply, close as not planned), `duplicate` (the gift
was already saved: the answer is rebuilt in case it was never sent, and skipped if the issue is already closed) and
`ignored` (not a toy request, or the toy box is not live: no reply, the issue stays open for Hien).

Only accepted gifts change `data/toys.json`. Refusals are answered on the issue but never saved, so a flood of bad
requests produces no commits and cannot crowd real gifts out of the retry loop. The retry time in a cooldown reply is
rounded up to the next minute.

## Security choices

* Workflows declare `permissions: {}` at the top and grant each job only what it needs. The toy box runs as two
  jobs: `record` can write the repository but not issues; `reply` can write issues but only read the repository.
  Actions are pinned to full commit SHAs.
* Writes to the GitHub API (a comment, closing an issue) are never retried after a server error, so nothing is
  posted twice; the reply step also skips an issue that is already closed.
* The issue title and body never reach a shell or an expression: Python reads `$GITHUB_EVENT_PATH`.
* The title is matched against a fixed list; the body is ignored; the login is re-validated (letters, digits,
  single hyphens) before it is stored, drawn or mentioned.
* State files are validated on load. A corrupt file stops the run rather than being overwritten.
* Writers retry from the newest `main` (fetch, reset, re-apply) up to 8 times with a random pause, so two events
  at once never lose a gift, and the dedupe ledger makes re-applying safe.
* The live switch is enforced twice: the workflow needs `CATWALK_TOYS=on`, and Python ignores every issue while
  `toys_live` is false in `config/catwalk.json`.
