# On-stage script

The words for the livestream: what to say, the literal questions to type into the app, and the GitHub Copilot prompt. The timing, commands, and fallbacks are in [RUNBOOK.md](RUNBOOK.md). The live questions are the evaluation cases marked `capture` in `demo/src/football_insights/evaluation/cases.yaml`, so what you rehearse, snapshot, and cache is exactly what you type.

Narration is a guide, not a teleprompter: say it in your own words, keep it short, and let the screen do the work.

## 1. Opening (00:00–03:00)

> Thanks for the welcome. Here's today's question: what can more than 150 years of international football tell us, and what does it take to ship those insights as an AI app on Azure Kubernetes Service and on Azure Container Apps? The title says soccer; the data says football, so that's the word you'll hear from me.
>
> On the left, the app runs on Container Apps; on the right, on AKS. Look at the badges: same image digest, same data version, same model, different platform. These values come from each deployment, not from the page.
>
> The app answers the seven questions that come with the dataset: who's the best team ever, who dominated each era, how the game has changed, what fixtures say about geopolitics, who hosts other teams' matches, whether hosting helps, and whether friendlies help. You'll leave with the whole repository, a guide for choosing between AKS and Container Apps, and a hackathon guide.

## 2. Architecture and the data rule (03:00–09:00)

> One set of images, three services. `web` is the only public service. `insights` is internal: it holds the analytics tools and the AI agent. `ingest` is a job that turns the raw downloads into a curated, versioned store.
>
> The most important line in the diagram is this one: deterministic code computes every number. The model, from Microsoft Foundry, reads your question, picks tools, and explains their results. It never computes a statistic, and a grounding check rejects any number it writes that no tool returned.
>
> Nothing uses a key: workload identity on AKS, managed identity on Container Apps, and my own sign-in locally. Both platforms send OpenTelemetry to one Application Insights resource.
>
> And the data rule. The repository contains no data (`git ls-files data` shows only two README files). You download the two Kaggle datasets yourself; `data/README.md` shows how.

## 3. Data (09:00–15:00)

> Two datasets: international results since 1872, public domain, and World Bank development indicators, CC BY 4.0, which we credit and reshape.
>
> `demo verify` checks every file against a schema contract and the checksums this demo was verified against. A newer download only warns; a changed schema fails.
>
> The Data page is the ingest job's report: row counts, date ranges, how many teams map to World Bank economies, how many goals have scorer records, and every exclusion with its reason. Teams keep today's names while venues keep historical names, so reconciling them is half the work.
>
> The same job image runs as a Container Apps job, live now, and as a Kubernetes Job. The AKS run you'll see is from rehearsal. Both produce the same content-addressed version, because the version is a hash of the inputs.

## 4. The seven questions (15:00–30:00)

Type each question exactly as written.

**L1, question 6, the timely example:**

```text
Did hosting help Canada, Mexico, and the United States at the 2026 World Cup?
```

> Watch the tool calls: the model asked the hosting tool for the 2026 edition. Every number here has an evidence ID. The chart comes from the tool, not the model. All three co-hosts did better against their ratings than in their own non-host World Cups. And the caveat is right there: small samples, and no stage column, so no claims about rounds.

**L2, question 1, where the definition changes the answer:**

```text
Who is the best team of all time, and does the answer change with the definition?
```

> "Best" is a definition, not a fact. By peak rating it's one team; by career average and win rate, another. The rating parameters are shown, so you can argue with them.

**L3, question 3:**

```text
How has home advantage changed since the early 1900s?
```

> Home advantage in non-neutral matches, by decade, with a 95% interval. And the caveat matters: far more teams and far more friendlies in later decades change what an average means.

**The other cards.** Scroll through questions 2, 4, 5, and 7:

> The rest of the questions are right here as cards: deterministic results that don't need the model at all. Each card explains what's asked, the method, and the caveats.

**The development lens.** On question 4, choose the view **Matches within and across regions (development lens)**:

> Here's the World Bank data as context. The share of matches between teams from the same region has fallen since the 1960s: the international calendar became more global. That's a description, not a claim about any country.

**L4, a question the data can't answer:**

```text
Which Premier League team is best at counterattacks?
```

> This is the honest limitation. The data holds men's international results only, with no clubs and no match events. The app says so and says what data would be needed, instead of inventing an answer.

**Backup questions (Tier B), if you're ahead:**

```text
Which teams dominated different eras of football?
Does playing lots of friendlies help or hurt a team?
```

## 5. AKS versus ACA (30:00–39:00)

> Same image, same region, same replica size and floors, same model, same data. So what's different?
>
> On AKS, I write Kubernetes objects: Deployments, Services, a Gateway and an HTTPRoute, autoscalers, and a network policy so only `web` can reach `insights`. On Container Apps, I describe two apps and a job; internal ingress keeps `insights` private.
>
> Identity: on AKS, a service account federated to a managed identity; on Container Apps, the identity attached to the app.
>
> The load test hits deterministic pages only, never the model, at a fixed rate for a fixed time. Watch how each platform adds replicas.
>
> And here's the comparison with the counts and the dates behind it. Estimates are labeled as estimates.

## 6. Develop and ship (39:00–46:00)

> One small feature, live: the biggest upsets of each era, using the rating model we already have. Same pattern as the seven questions: a typed tool, a card, a test.

Paste this into the GitHub Copilot app, exactly:

```text
Add question 8 to this app: "Which results were the biggest upsets in each era". Follow the pattern of demo/src/football_insights/analytics/q2_eras.py.

1. Create demo/src/football_insights/analytics/q8_upsets.py with TOOL_NAME = "biggest_upsets", a DESCRIPTION, CARD_ARGUMENTS = {"era": "all"}, a strict Params model with era: Literal["all", "early", "interwar", "postwar", "expansion", "modern", "current"], and run(ctx, params) returning a ToolResult.
2. Use ctx.ratings().matches. For each match that one side won, the winner's chance is expected_home for a home win or 1 - expected_home for an away win. Count only matches where both teams had already played at least 30 matches, and make that minimum a parameter. Rank by chance, lowest first.
3. For era="all", return the biggest upset of each era; for a single era, its five biggest. Give each upset facts with evidence IDs such as q8.all.<era>.chance (a percentage with one decimal), plus a table, an hbar chart of the chances, the method, coverage, caveats, and cannot_tell.
4. Register the module in analytics/registry.py (QUESTION_MODULES and QUESTIONS) and add its card text as entry 8 in cards.py.
5. Add demo/tests/test_q8_upsets.py using make_store and M from demo/tests/helpers.py, with fictional teams and hand-computed ratings: every team starts at 1500, K is 20 for friendlies, and the margin multiplier is 1.75 for a three-goal win and 1.5 for a two-goal win. Use a minimum of 2 earlier matches in the test.
```

> Copilot is writing the tool, registering it, adding the card, and writing a test with ratings I can check by hand. Let's run the test.

If anything deviates, switch to the prepared commit and say:

> Generated code varies from run to run, and that's fine: here's the same change as a prepared commit from rehearsal.

Then:

> The v2 image you're about to see was built from that prepared commit during rehearsal.
>
> On Container Apps, v2 arrives as a new revision at zero traffic, then half the traffic. Refresh, and the digest on the badge switches between v1 and v2; v2 shows the new upsets card. On AKS, the same image arrives as a rolling update.
>
> Rolling back Container Apps is just moving traffic: the old revision never stopped. One command, and everyone's on v1 again.

## 7. Operate (46:00–51:00)

> Every answer has a trace ID. Here's one end to end: the web request, the call to `insights`, the agent, each model call with its tokens, and each tool call with its evidence IDs. Application Insights shows the same trace, a few minutes behind; this view is immediate.
>
> Each answer shows its tokens and estimated cost, on both platforms. The evaluation suite asks the serving model the same questions, repeatedly, and a rule written in advance decides whether it may serve: grounding, tool choice, honest limits, latency, and cost. Today that's GPT-6 Sol. With GPT-6 Astra deployed too, the same rule picks between them. Switching is one setting, no rebuild.
>
> Foundry's content filters are on for every deployment. If a response is filtered, the page says so, and the evidence still renders.

## 8. Hackathon launchpad (51:00–53:00)

> Everything you saw is in the repository: the app, the infrastructure for both platforms, and the docs. Get the data from the two Kaggle links in `data/README.md`. The hackathon guide shows how to add a question like we just did, how to bring your own dataset, and ideas to build on. And this guide helps you choose between AKS and Container Apps, based on what this project needed.

## 9. Q&A (53:00–60:00)

Keep the decision guide on screen. Short answers are in [RUNBOOK.md](RUNBOOK.md), segment 9.

## Closing line

> Deterministic code for the numbers, a model for the words, one set of images on two platforms. Thanks for joining. The repository is linked in the chat.
