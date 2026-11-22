"""Catwalk: the Python automation behind Hien Ta's GitHub profile and website.

The data flows one way:

    GitHub APIs  ->  catwalk.stats (fetch, verify, measure)  ->  data/github.json
    issue event  ->  catwalk.toys  (validate, rate-limit, expire) ->  data/toys.json
    data/*.json  ->  catwalk.render (pure functions -> SVG)      ->  assets/generated/*.svg, README.md

The website (hienta16.github.io) reads the same JSON files and the site version of the
isometric calendar, so both surfaces are drawn from one set of numbers.

Only the Python standard library is used, so the GitHub Actions need no `pip install`.
Start reading at catwalk/cli.py; docs/AUTOMATION.md explains every moving part.
"""

__version__ = "1.0.0"
