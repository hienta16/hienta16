# Going live: the switches, in order

Everything is built and tested, and nothing is switched on. This page lists exactly what turns each part on, so it
happens only when Hien decides. Nothing here is done by the automation itself.

## Where things stand

| | State |
|---|---|
| `hienta16/hienta16` (this hub) | private staging repository; review branch `feature/python-catwalk-cat-toys` |
| `hienta16/hienta16.github.io` (website) | private; review branch `feature/python-catwalk-cat-toys`; GitHub Pages **not** enabled |
| Workflows | committed, inert: they live on a review branch (schedules and issue events only run from the default branch), and every job also waits for a repository variable that is not set |
| `config/catwalk.json` | `hub_public: false`, `toys_live: false` |

## 1. Stats refresh only (safe while everything is private)

1. Review and merge `feature/python-catwalk-cat-toys` into `main` in this repository.
2. Optional, for complete counts: create a fine-grained personal access token with read-only access to your
   repositories' contents and metadata (or a classic token with `repo`), and save it as the repository secret
   `CATWALK_STATS_TOKEN`. Without it the first complete snapshot (already committed) is kept and marked with its date.
3. Add the repository variable `CATWALK_AUTOMATION` = `on` (Settings → Secrets and variables → Actions → Variables).
4. Actions → Refresh stats → Run workflow, once, to see it work. After that it runs every 6 hours.

## 2. The public profile README

1. Make this repository public (Settings → General → Danger zone). Its README then appears on github.com/hienta16.
2. In `config/catwalk.json` set `"hub_public": true`, run `python -m catwalk render`, commit, push. The README's
   footer then says the refresh is automatic, and the website starts reading `data/*.json` live from here.

## 3. The cat's toy box (needs step 2: visitors can only open issues on a public repository)

1. In `config/catwalk.json` set `"toys_live": true`, run `python -m catwalk render`, commit, push. The README shows
   the Give buttons.
2. Add the repository variable `CATWALK_TOYS` = `on`. Keep `CATWALK_AUTOMATION` on as well: the 6-hourly refresh is
   what retires expired toys from the README picture when no new gifts arrive.
3. Test it yourself: open an issue titled `[cat-toy] yarn`. Within a minute the bot replies and closes it, and
   `data/toys.json` lists the yarn. (Add your login to `exempt_logins` in `config/toys.json` if you want to test
   more than once a day.)
4. To pause the toy box at any time, set `CATWALK_TOYS` to `off`. Gifts already given stay until they expire.

## 4. The website

1. In the website repository, set `hubPublic`/`toysLive` by copying the hub config (`npm run data`), build, and
   check locally (`npm run build && npm run preview`).
2. Make `hienta16.github.io` public if your plan needs it for Pages, then enable GitHub Pages (Settings → Pages →
   GitHub Actions) with the deploy workflow kept in `ops/activation/pages.yml` of that repository.

## Turning everything off again

Set `CATWALK_AUTOMATION` and `CATWALK_TOYS` to `off` (or delete them). Set the two config switches back to false
and render. Making a repository private again hides the profile README and stops visitors opening issues.
