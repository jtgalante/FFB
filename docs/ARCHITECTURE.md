# What this repo is, in one picture

Data comes in from five outside sources, gets cleaned and joined **once**, and
three different things read from that clean layer.

```mermaid
flowchart TB
    subgraph S["① SOURCES — the messy outside world"]
        direction LR
        FP["FantasyPros CSV<br/><i>exports QBs at 4-pt TDs</i>"]
        FFC["FantasyFootballCalculator<br/><i>ADP + dispersion</i>"]
        NFL["nflverse<br/><i>weekly stats, injuries</i>"]
        SLP["Sleeper / ESPN<br/><i>league history</i>"]
        CD["ClickyDraft boards<br/><i>the golden source</i>"]
    end

    subgraph G["② THE GATE — where the bugs used to get through"]
        V["validate.py<br/>min rows · team codes · season balance · draft complete"]
        VC["verify_clickydraft.py<br/>repairs draft slots"]
    end

    subgraph W["③ WAREHOUSE — joined once, correctly"]
        direction LR
        P["picks<br/>2,420"]
        TW["team_weeks<br/>2,498<br/><i>+ opponent</i>"]
        PW["player_weeks<br/>29,340"]
        R["rosters<br/>9,086"]
        CH["champions<br/>18"]
    end

    subgraph U["④ WHAT IT'S FOR"]
        direction LR
        RES["<b>Research</b><br/>trends, trash talk"]
        DR["<b>Draft</b><br/>board + live picks"]
        ST["<b>Starters</b><br/>later"]
    end

    EX["📦 data/export/ffb.sqlite<br/>+ DATA_DICTIONARY.md<br/><i>the hand-off</i>"]

    FP --> V
    FFC --> V
    NFL --> V
    SLP --> V
    CD --> VC
    V --> W
    VC --> W
    W --> U
    W --> EX

    style G fill:#5b2333,stroke:#c44,color:#fff
    style W fill:#1e3a5f,stroke:#4a9,color:#fff
    style EX fill:#2d4a22,stroke:#7c4,color:#fff
```

## The four pieces

**① Sources** — five outside feeds, each with its own quirks, all documented in
`docs/DATA.md`.

**② The gate** — `src/draft/validate.py` refuses bad data at the moment it would
be written. Every check exists because that exact bug already happened here: a
paywalled 10-of-852 API slice, a team-code mismatch that deleted two teams' bye
weeks, a schema difference that deleted four seasons of injury data.
`scripts/verify_clickydraft.py` is separate because it does something unusual —
it repairs the archive against photographs of the original draft boards.

**③ The warehouse** — five tables, one grain each, joins already resolved. The
one that matters most is `team_weeks`, because it carries **who you actually
played**, reconstructed by score-matching since the platforms never recorded
opponent names.

**④ Three uses** — research, draft, starters. Plus `data/export/`: one SQLite
file anyone can open, with a dictionary stating every caveat.

## What "clean" means here

Not that the data is perfect — that the imperfections are **known and written
down**. The dictionary tells a new reader that opponents are reconstructed, that
18 win-flags contradict their own scores, that bench players were never
exported, and that the platforms name the wrong champion in at least three
seasons. That honesty is what makes it hand-off-able.

Rebuild the whole thing:

```bash
python -m scripts.fetch_data          # sources -> data/draft/
python -m scripts.build_warehouse     # -> data/warehouse/
python -m scripts.export_datasheet    # -> data/export/
python -m pytest tests/ -q            # 201 invariants
```
