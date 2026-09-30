# Methods

This document defines how the app answers each of the seven questions: the data used, the method, the minimum sample sizes, how uncertainty is shown, and what each answer cannot tell you. It is the contract for the analytics code under `demo/src/football_insights/`.

> Status: Phase 0 draft, verified against the data on 2026-09-29. Evaluation results are added after the evaluation suite runs.

## Deterministic numbers, AI explanations

Every number the app shows comes from deterministic, tested analytics over a curated copy of the data. A Microsoft Foundry model reads the viewer's question, chooses which analytics tools to call, and writes a short explanation of their results. The model never computes, invents, or overrides a statistic: a grounding check compares every number in its narrative with the tool results, and an answer that fails is either retried once or replaced by the evidence alone, with a visible notice.

## Data

| Dataset | Version verified | License | Used for |
| --- | --- | --- | --- |
| [International football results from 1872 to 2026](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017), by Mart Jürisoo | Kaggle version 137 (updated 2026-08-26) | CC0: Public Domain | Matches, goalscorers, shootouts, former names |
| [Global Development Data (1960–2025)](https://www.kaggle.com/datasets/yogeshm01/global-development-data-19602025), by Yogesh Mishra, from the World Bank's World Development Indicators (WDI) | Kaggle version 1 (updated 2026-07-14) | CC BY 4.0 | Region, income group, population, GDP per capita |

The repository contains no data. See [data/README.md](../data/README.md) to download it. This app reshapes and filters the WDI data (wide to long format, a short indicator list, economies only).

Facts about the data that shape every method:

- The data covers men's full internationals only. Scores include extra time but not penalty shootouts, which are recorded separately. There is no stage or round column.
- Teams appear under their current names (a 1950s Gold Coast match is listed under Ghana), while the venue country is named as it was at the time.
- Goalscorer records exist for about a third of all goals. When a match has scorer records, its timeline is complete, so goal-level analysis uses only those matches and reports the coverage.
- The data runs from 1872-11-30 to 2026-08-26 in the verified version, including all 104 matches of the 2026 FIFA World Cup.

## Shared definitions

### Results

- A win scores 1, a draw 0.5, and a loss 0 for rating purposes. A match decided by a penalty shootout counts as a draw; the shootout winner is reported separately.
- Points per match, where shown, use 3 for a win and 1 for a draw.

### Team and venue identity

- A team is identified by its name in the data, which is its current name.
- A venue is identified by reconciling the venue country with `former_names.csv` (for example Soviet Union → Russia, Zaïre → DR Congo) plus two reviewed aliases for venue names that file does not cover (Manchuria → Manchukuo, Yemen AR → Yemen).
- A match is **hosted by a third party** when the data flags it as neutral **and** the reconciled venue identity is neither team. The two signals disagree in 371 of 49,547 matches; the app reports both disagreement types and follows the rule above.

### Match categories

`demo/src/football_insights/reference/tournaments.yaml` classifies all 202 tournament names into ten categories: FIFA World Cup, continental championships, intercontinental finals, qualifiers, nations leagues, regional championships, multi-sport games, tournaments for teams outside FIFA, invitational friendly tournaments, and friendlies. Ingest fails if the data contains a tournament name the file does not classify.

- **Friendly-like matches** are `Friendly` plus 97 reviewed invitational tournaments and bilateral trophies (for example Kirin Cup, King's Cup, Merdeka Tournament, Copa Roca, FIFA Series). An invitational tournament is organized by a host association or sponsor, has no qualification route, and has no regional-championship status. The British Home Championship, for example, is a regional championship, not a friendly tournament.
- **Competitive matches** are all other categories.
- **Major tournaments** (question 6) are the FIFA World Cup, UEFA Euro, Copa América, African Cup of Nations, AFC Asian Cup, CONCACAF Championship and its successor the Gold Cup, and the Oceania Nations Cup. The Confederations Cup is excluded as a small invitational field.

### Eras

`eras.yaml` defines six contiguous eras: 1872–1914, 1915–1945, 1946–1969, 1970–1989, 1990–2009, and 2010–2026. They follow structural breaks (the world wars, the spread of continental championships, the post-1990 wave of new states, the modern calendar). Era boundaries are a choice, not a finding, and early eras contain few teams and matches.

### Rating model

A transparent Elo-style rating, method version `ratings-v1`, processes every match in date order:

- Every team starts at 1500.
- Expected score for the home team: `E = 1 / (1 + 10^(-(R_home + H - R_away) / 400))`, with home advantage `H = 100` points unless the match is neutral.
- Match importance `K`: 60 World Cup finals; 50 continental championship and intercontinental finals; 40 qualifiers and nations leagues; 30 regional championships, multi-sport games, and non-FIFA tournaments; 20 friendlies and friendly tournaments.
- Margin multiplier `G`: 1 for a margin of 0 or 1 goal, 1.5 for 2 goals, and `(11 + margin) / 8` for 3 or more.
- Update: the home team gains `K × G × (W − E)` and the away team loses the same amount.

These choices follow the widely used World Football Elo scheme. Ratings are relative within the connected pool of teams in the data; they are not official rankings.

A team is **active** in a year if it played at least one match in that year or the three before it.

### Team to development-data crosswalk

`crosswalk.yaml` maps each of the 337 team names to a WDI economy, or records why it cannot. It is hand-reviewed and contains names and codes only.

| Mapping | Teams | Examples |
| --- | ---: | --- |
| Exact name match | 179 | Brazil → BRA; Czech Republic → CZE (WDI long name) |
| Reviewed alias | 36 | South Korea → KOR; Ivory Coast → CIV; Turkey → TUR; Palestine → PSE; Tahiti → PYF |
| Shared economy | 8 | England, Scotland, Wales, Northern Ireland → GBR; Guernsey, Jersey, Alderney, Sark → CHI |
| No WDI economy | 114 | Historical states (Czechoslovakia, Yugoslavia, German DR, …), territories WDI does not report separately (Martinique, Zanzibar, …), non-FIFA regional teams, Taiwan |

- Shared mappings support region and income-group views only, never per-capita values.
- Russia maps to the Russian Federation from 1992. Its 391 matches from 1910 to 1991 are the Soviet Union era, which has no WDI entity, so they are unmapped for development joins.
- Coverage on the verified data: both teams mapped in 91.3% of matches (93.9% since 1990); 94.9% of team appearances mapped. Every view that uses WDI reports its own coverage, and unmapped teams are counted, never dropped silently.
- WDI income groups are the World Bank's **current** classification. A "high income" label describes a country today, not in 1965.

Development indicators in the curated store: population (`SP.POP.TOTL`), GDP per capita in constant 2015 US dollars (`NY.GDP.PCAP.KD`), and urban population share (`SP.URB.TOTL.IN.ZS`), 1960–2025, economies only (the 48 regional and income aggregates are excluded).

### Uncertainty and sample sizes

- Proportions (for example the home-win share in a decade) carry 95% Wilson score intervals.
- Differences between groups (host effect, friendly effect) carry 95% bootstrap percentile intervals from 2,000 resamples with a fixed seed, so the same data always produces the same interval.
- Each question states its minimum sample; results below it are not shown.

## Question 1: Who is the best team of all time?

**What the app computes.** Four lenses on the rating model, because "best" depends on the definition, plus plain records:

- **Peak**: the highest rating a team reached, counting only peaks after its 30th match, with the date.
- **Career average**: the mean year-end rating across every year the team played, for teams with at least 40 such years.
- **Time at the top**: year-ends ranked first, and in the top five, among active teams.
- **Records**: win rate and points per match for teams with at least 300 matches.
- **Novelty lens (development data)**: wins per million inhabitants, using the latest WDI population, for teams with at least 100 matches and an exact or alias mapping. It is labeled as a novelty: it divides a century of results by today's population.

**Must disclose.** The answer changes with the lens and with the rating parameters, which the app shows. Early eras have sparse schedules: before 1915, fewer than 40 teams were active.

**Cannot tell you.** Which team would beat which across eras, anything about players or tactics, or anything about club football.

## Question 2: Which teams dominated different eras?

**What the app computes.** For each era: every team's era rating (the mean of its post-match ratings within the era, with the era's minimum number of matches), the top five, the leader's dominance margin over the runner-up, and the leader's record against the other four.

**Must disclose.** Era boundaries are a choice; a team that peaked across a boundary splits its dominance. Early eras have small samples (454 matches before 1915).

**Cannot tell you.** Why a team dominated.

## Question 3: What trends have there been in international football?

**What the app computes.**

- **Home advantage**: in non-neutral matches, the home win, draw, and away win shares per decade with Wilson intervals, and the mean home goal difference.
- **Total goals**: goals per match per decade, overall and split into competitive and friendly-like matches.
- **Distribution of teams' strength**: per year-end, the number of active teams, the spread (standard deviation) of their ratings, the 10th, 50th, and 90th percentiles, and the gap between the top-ten mean and the median.
- **Goal timing and penalties** (goalscorer data, matches with timelines only): per decade, the share of goals from penalties, from own goals, and after the 75th minute, with that decade's timeline coverage.
- **Development lens**: since 1960, mean year-end rating by WDI region and by income group, per decade.

**Must disclose.** Goalscorer coverage rises from none before 1910 to about half of scoring matches in the 2020s. The composition changes: many more teams and many more friendlies over time, which moves every trend.

**Cannot tell you.** Why goals per match fell, or anything causal about development and strength.

## Question 4: What can football fixtures say about geopolitics?

**What the app computes.**

- **How the number of teams changed**: distinct teams playing each year; first appearances per decade; exits of teams whose state dissolved, merged, or split (`lineage.yaml`), with their successors, and the post-1991 appearance of post-Soviet states.
- **Which teams like to play each other**: the most frequent pairings, all time and per era.
- **The fixture network**: for 2010–2026, teams are nodes and matches are weighted links. Louvain community detection (fixed seed) finds groups of teams that mostly play each other, and the app compares those communities with WDI regions (the share of each community in its most common region).
- **Intra- versus inter-region share**: per decade, among matches where both teams are mapped, the share between teams of the same WDI region, and of the same income group.

**Must disclose.** This is observational. A football team is not always a sovereign state (the four UK associations, territories, historical states). Historical teams have no WDI entity. Scheduling reflects confederation rules and travel as well as politics.

**Cannot tell you.** Anything about relations between governments or peoples; causes of any pattern.

## Question 5: Which countries host the most matches they are not playing in?

**What the app computes.** Matches hosted by a third party (13,107 in the verified data, across 213 host identities), ranked all time and per era; the third-party share of all matches per decade; the top host cities; and, as a development lens, the WDI region and income group of the most frequent hosts.

**Must disclose.** How venues were reconciled (former names plus two aliases) and how the 371 disagreements with the neutral flag were handled: 51 matches flagged neutral in a participant's own country are not counted; 320 matches flagged non-neutral at a venue identity that is neither team are treated as home matches, as flagged (mostly regional teams at home inside their sovereign state).

**Cannot tell you.** Why a country hosts, or attendance and revenue.

## Question 6: Does hosting a major tournament help?

**What the app computes.**

- **Editions**: matches of one major tournament less than 90 days apart form an edition, labeled by the year of its first match (official names can differ: Euro 2020 was played in 2021).
- **Hosts**: participants whose reconciled venue identity hosted at least one of the edition's matches, which handles co-hosts (2002, 2026). Editions with no single host are excluded: fewer than 40% neutral matches (home-and-away formats such as Copa América 1975–1983), more than three venue countries (Euro 2020), or fewer than four teams.
- **Performance against expectation**: for each host match, the actual score minus the expected score from pre-match ratings **without** the home bonus. The host effect is the difference between a team's host editions and its non-host editions of the same tournament, pooled with a bootstrap interval.
- **Progression proxy**: matches played by the host divided by the edition's median matches per team, compared with the same team's non-host editions. More matches usually means going further.
- **2026 example**: Canada, Mexico, and the United States at the 2026 FIFA World Cup.
- **Development lens (optional)**: host effects split by the host's GDP per capita in the edition year, described, not modeled.

**Minimum sample.** The pooled estimate needs at least 20 host editions with a non-host comparison; per-tournament estimates need at least 6.

**Must disclose.** Samples are small, formats vary across editions, and there is no stage column, so the app does not claim titles or rounds.

**Cannot tell you.** Whether hosting causes better results (hosts differ from non-hosts in many ways), or how a future host will do.

## Question 7: Who plays the most friendlies, and does it help or hurt?

**What the app computes.**

- **Activity leaders**: per era, the teams with the most friendly-like matches and the highest friendly share (at least the era's minimum matches).
- **Comparison design**: team histories are cut into fixed four-year windows from 1946. For each team and window with at least five competitive matches in the **next** window, the app compares friendly-like volume in the window with performance against expectation in the next window's competitive matches. Teams are split into thirds by friendly volume within each window, so eras are compared with themselves; the app reports the top-minus-bottom difference with a bootstrap interval and the rank correlation.
- **Development lens**: friendly-like matches per team-year by WDI income group since 1960.

**Must disclose.** Observational, not causal. Selection effects run both ways: strong teams receive more invitations, and teams eliminated early from competitions fill their calendars with friendlies.

**Cannot tell you.** Whether playing more friendlies would help a particular team.

## Responsible framing

Questions 3, 4, 5, and 7 touch geopolitics and national development. The app describes patterns neutrally, makes no causal or value-laden claims about countries or peoples, and treats development indicators as context, never as explanations or rankings of worth. The model's instructions and the evaluation cases enforce this.

## Outside the data

The app answers these with an honest limitation and the data that would be needed: club football; women's internationals; tactics such as possession, pressing, or counterattacks; player statistics beyond goals; predictions or betting; and anything after the last match in the loaded data version.

## Grounding and evaluation

Every tool result carries evidence IDs, the method version, the dataset version, coverage notes, and caveats. A deterministic validator checks that every number in the narrative matches a tool value within the stated rounding. The evaluation suite and its results are documented here after Phase 3.
