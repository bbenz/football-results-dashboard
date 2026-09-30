# Runbook: the 60-minute livestream

The timed run of show for **Build AI-powered soccer insights apps with AKS and ACA** (Microsoft Reactor, October 14, 2026, 9:00–10:00 AM Pacific). It lists exact presenter actions, the command for each step, what you should see, and what to do when it doesn't happen. The words to say and the literal questions to type are in [ONSTAGE-SCRIPT.md](ONSTAGE-SCRIPT.md). Keep this runbook on the second, unshared screen.

## How to use this runbook

- **Clock.** Times are stream time: 00:00 is when the producer hands over. Each segment has a **hard stop** 60 seconds after its planned end. At the hard stop, switch to that segment's prepared evidence and move on, whatever is running.
- **Tiers.** Each step is marked with a tier:
  - **[A] always live.** Never skip. If the live path fails, show the fallback, but show it.
  - **[B] live if on time.** Otherwise show the prepared evidence, and say it is recorded.
  - **[C] compress first.** Cut these when running long.
  Cut depth, never coverage: every promise of the session appears on screen at least as a stated result with visible evidence.
- **Commands** are `demo <command>`, the alias from `. ./demo/scripts/aliases.ps1`, run in the repository folder.
- **Evidence** means the files that rehearsal commands wrote under `EVIDENCE_DIR`:
  - `replay/<platform>-<time>/index.html` from `demo snapshot`, one saved page per card view and per prepared answer, each labeled as a recording.
  - The latest `loadtest-*.json`, `parity-*.json`, and `eval/` report.

  Open `EVIDENCE_DIR` in File Explorer before the stream.

## Recorded, not live

Say these on stream, at the point they come up:

- **One ingest run.** The ingest job runs live on one platform; the other platform's run is recorded evidence from rehearsal.
- **The v2 image** was built from the prepared commit (branch `v2-upsets`) during rehearsal. Copilot's live change is not what gets deployed.
- **Evaluation results** come from runs during rehearsal, because a full run takes longer than the segment.
- **Tier B moments shown from evidence.** Any Tier B moment shown from evidence is labeled as recorded.

Offline fallback tiers can't demonstrate live model inference or live cloud behavior. When you are on one, say so.

## Fallback ladder

Move down one level at a time, and say which level you are on:

1. **Both platforms live.** This is the normal path.
2. **One platform live.** Use the live platform for everything; show the other from `replay/<platform>-*/index.html`, plus its load-test and parity evidence.
3. **Local Docker Compose with live Foundry.** Run `demo up -LiveModel`, then open <http://127.0.0.1:8080>. The badge says Local.
4. **Local with cached narratives.** Set `AI_NARRATIVE_MODE=cached` in `.env` and run `demo up`. Each narrative is labeled with its capture time and source.
5. **Recorded screen capture** of the last good rehearsal.

## Window layout

| Window | Screen | Content |
| --- | --- | --- |
| Browser, demo profile, zoom 125% | Shared | Tab 1: ACA web. Tab 2: AKS web. For segment 1, tile the two windows side by side. |
| Windows Terminal, font size 18 or larger | Shared | Repository folder, alias loaded. A second tab for long-running commands. |
| Editor (VS Code) with the repository | Shared | Bookmarked files, listed per segment below. |
| GitHub Copilot app | Shared | The repository open, on branch `stage-upsets`. |
| This runbook, the on-stage script, producer chat | **Not shared** | Second screen. |

## Run of show

| # | Planned | Hard stop | Segment | Tier A core | Main command |
| --- | --- | --- | --- | --- | --- |
| 1 | 00:00–03:00 | 04:00 | Question, seven questions, both apps live | Both badges truthful | none (pages open) |
| 2 | 03:00–09:00 | 10:00 | Reference architecture and the data rule | Diagram; no data in the repo | `git ls-files data` |
| 3 | 09:00–15:00 | 16:00 | Data: sources, verify, quality, ingest | Data page with quality report | `demo verify`, `demo ingest-aca` |
| 4 | 15:00–30:00 | 31:00 | The seven questions | 3 live answers, 7 cards, 1 limitation | typed in the app |
| 5 | 30:00–39:00 | 40:00 | AKS versus ACA side by side | Comparison table | `demo load-test both -Rps 20 -Seconds 45` |
| 6 | 39:00–46:00 | 47:00 | Develop and ship: Copilot, v2, rollback | Stated result with evidence | `demo pytest tests/test_q8_upsets.py`, `demo rollout-v2`, `demo rollback aca` |
| 7 | 46:00–51:00 | 52:00 | Operate: trace, tokens, evaluation, filters | One end-to-end trace | trace link on the answer page |
| 8 | 51:00–53:00 | 54:00 | Hackathon launchpad | Repository tour | none |
| 9 | 53:00–60:00 | 60:00 | Q&A with the decision guide on screen | | none |

## Segment 1: the question and both apps live (00:00–03:00; hard stop 04:00)

1. **[A]** After the producer's welcome, state the question and acknowledge "soccer" and "football" once.
2. **[A]** Show the two browser windows side by side: ACA on the left, AKS on the right. Point at each environment badge: platform, region, short image digest (the same on both), data version (the same on both), model deployment, and "AI narrative: live".
3. **[A]** Scroll one app to show the seven question cards.
4. **[C]** Say what attendees will leave with: the repository, the decision guide, and the hackathon guide.

**If it fails:**

- **One platform shows an error.** Say which one, keep the other on screen, and open `replay/<platform>-*/index.html` for the failed one. Fix it after the segment with `demo smoke`.
- **Both fail.** Go to fallback level 3.
- **A badge shows "AI narrative: unavailable".** Say so. The Foundry path is checked in segment 4.

## Segment 2: reference architecture and the data rule (03:00–09:00; hard stop 10:00)

1. **[A]** Show the component diagram from [ARCHITECTURE.md](ARCHITECTURE.md), or the slide made from it. Cover:
   - One set of images on two platforms.
   - `web` is public; `insights` is internal.
   - The data flow.
   - Deterministic tools versus the AI narrative.
   - Keyless identity.
   - Telemetry.
2. **[A]** State the data rule: the repository contains no data. In the terminal, run `git ls-files data`. Expected: only `data/README.md` and `data/data sources.md`.
3. **[A]** Open `data/README.md` and show where to download the two datasets, and their licenses.
4. **[C]** Mention the guard. `demo guard` checks the index and every commit in about 25 seconds, and it also runs as a pre-commit hook and in CI.
5. **[C]** Show the request-flow sequence diagram.

**Code bookmarks:** `docs/ARCHITECTURE.md`, `data/README.md`, `.gitignore`, `demo/scripts/check_no_data.py`.

**If it fails:** Diagrams don't render? Describe the flow using the component table in `ARCHITECTURE.md`.

## Segment 3: data, verification, quality, and ingestion (09:00–15:00; hard stop 16:00)

1. **[B]** Start the job first, because it takes a few minutes. In the second terminal tab, run `demo ingest-aca`. It polls every 10 seconds and ends with "ACA ingest job succeeded".
2. **[A]** Show the two sources and licenses in the app footer, then in [data/README.md](../data/README.md).
3. **[A]** Run `demo verify`, which takes about 5 seconds. Expected last line: `verify-data PASSED: 0 failure(s), 0 warning(s).` Explain the schema contract, the hash check, and why a newer download gives a warning, not a failure.
4. **[A]** Open the **Data** page on either platform. Show:
   - Row counts and date ranges.
   - Crosswalk coverage: both teams mapped in about 91% of matches.
   - Goalscorer coverage: about a third of goals.
   - The quirks and exclusions, with reasons.
5. **[B]** Return to the job tab: it has succeeded. It reused the same curated version as the other platform's run. Say that the AKS run is recorded evidence from rehearsal, where `demo ingest-aks` printed the same version.

**Code bookmarks:** `demo/src/football_insights/data/contract.py`, `demo/src/football_insights/ingest/pipeline.py`, `demo/k8s/ingest-job.yaml`, `demo/infra/aca.bicep` (the `ingestJob` resource).

**If it fails:**

- **The job fails or is still running at 14:30.** Say so and show the job output from rehearsal. Nothing depends on this run, because the curated version already exists.
- **`demo verify` fails.** The data folder changed. Show the rehearsal output, and don't re-download on stream.

## Segment 4: the seven questions (15:00–30:00; hard stop 31:00)

Type each question from [ONSTAGE-SCRIPT.md](ONSTAGE-SCRIPT.md) into the question box on the ACA tab, or the AKS tab if ACA is down. For each answer, point at:

- The narrative and the green grounding badge.
- The key numbers, each with its evidence ID.
- The chart, which is built from tool data.
- The caveats and "what this data can't tell you".
- The model, tokens, latency, and estimated cost.
- The **Tool calls** expander.
- The copyable trace ID: copy the first one for segment 7.

| Step | Tier | Question | Expected tool calls | Expected result (verified dataset) | No-model fallback |
| --- | --- | --- | --- | --- | --- |
| 4.1 | A | L1: 2026 World Cup hosts | `hosting_effect(view="edition", tournament="FIFA World Cup", year=2026)`, possibly `view="pooled"` | All 3 co-hosts did better against rating expectations than in their own non-host World Cups; Mexico gained most, 0.30 points per match | Q6 card, view "Hosts of the latest FIFA World Cup": `/card/6?v=2` |
| 4.2 | A | L2: best team, by definition | `best_team(lens="peak")`, `best_team(lens="career_average")`, possibly `lens="records"` | Peak: Spain, 2,326 (2026). Career average: Brazil, 1,897. Records: Brazil, 63.4% wins | `/card/1?v=0`, then `/card/1?v=1` |
| 4.3 | A | L3: home advantage | `trends(metric="home_advantage")` | Home wins: 44.4% of non-neutral matches in the 1900s, 51.0% in the 2020s; peak 54.4% in the 1940s | `/card/3?v=0` |
| 4.4 | A | Remaining cards | none | Scroll through Q2, Q4, Q5, Q7, and open one "About this question" expander | the cards are the fallback |
| 4.5 | A | Development lens | none | Q4 card, view "Matches within and across regions (development lens)": the same-region share fell from 83.0% in the 1960s to 71.2% in the 2020s | `/card/4?v=3` |
| 4.6 | A | L4: out-of-scope question | `data_limits(topic="club_football")` and/or `topic="tactics"` | An honest limitation: the data holds men's international results only; club and event data would be needed | show the Premier League Q&A answer below |
| 4.7 | B | One more question, if on time | any | | skip |

**Checkpoints:**

- By 21:00, L1 and L2 are done.
- By 25:00, L3 is done.
- By 29:00, the limitation is done.
- If an answer takes longer than 45 seconds, stop waiting: open the no-model fallback URL for that question and say the narrative didn't arrive in time.

**If it fails:**

- **"AI narrative unavailable" or throttling.** The cards and evidence still render. Say the model path is down, show the fallback URLs, and continue. After the segment, check with `demo preflight`.
- **The grounding badge shows "fallback".** That is the safety net working. Say so: the model wrote a number no tool returned, so the page shows the evidence instead.
- **Content filter or "filtered" status on a question.** Say that Foundry's content filter blocked it, show that the evidence still rendered, and move on. It is also a good lead-in to segment 7.

## Segment 5: AKS versus ACA side by side (30:00–39:00; hard stop 40:00)

1. **[B]** Start the load test first, in the second terminal tab: `demo load-test both -Rps 20 -Seconds 45`. It targets deterministic pages only, never the model. Before and after, it prints AKS pods and autoscalers, and ACA replica counts.
2. **[C]** Walk through the deployment definitions side by side:
   - **AKS:** `demo/k8s/football.yaml`, showing a Deployment, the `ClusterIP` Service, the `NetworkPolicy`, the `Gateway` and `HTTPRoute`, and an autoscaler.
   - **ACA:** `demo/infra/aca.bicep`, showing `webApp` with its ingress, `insightsApp` with `external: false`, and the scale rule.
3. **[C]** Walk through the identity wiring:
   - **AKS:** a service account annotation and a federated credential in `demo/infra/aks.bicep`.
   - **ACA:** the `identity` block and `registries[].identity`.
4. **[B]** Return to the load test. Show requests, errors, p50/p95 latency, and replicas before and after on each platform.
5. **[A]** Show the comparison table in [AKS-VS-ACA.md](AKS-VS-ACA.md#at-a-glance). Name what was measured and what was estimated.

**If it fails:**

- **The load test errors or runs past 37:30.** Stop it with Ctrl+C and open the latest `loadtest-aks-*.json` and `loadtest-aca-*.json` from rehearsal. Say they are recorded.
- **A platform isn't reachable.** Run `demo load-test aca` or `demo load-test aks` for the reachable one only.

## Segment 6: develop and ship (39:00–46:00; hard stop 47:00)

Before the stream, the Copilot app is open on branch `stage-upsets`, created from `main`.

1. **[B]** Paste the Copilot prompt from [ONSTAGE-SCRIPT.md](ONSTAGE-SCRIPT.md) into the GitHub Copilot app and let it work. Narrate what it changes:
   - A new tool module.
   - The registry.
   - The card text.
   - A test.
2. **[B]** Run `demo pytest tests/test_q8_upsets.py`. Expected: all tests pass. The tool contract test covers the new tool automatically when the full suite runs.
3. **If anything deviates** (errors, a failing test, or an unexpected edit), stop and switch to the prepared commit:

   ```powershell
   git stash push -u -m copilot-attempt; git switch v2-upsets; demo pytest tests/test_q8_upsets.py
   ```

   Say: "Copilot's output varies from run to run, so here is the prepared commit from rehearsal."
4. **[A]** Say that the v2 image was built from the prepared commit `v2-upsets` during rehearsal.
5. **[B]** Run `demo rollout-v2`, which takes about 2 minutes:
   - **ACA:** a new web revision starts at 0% traffic, then the traffic splits 50/50.
   - **AKS:** a rolling update.
   While it runs, refresh the ACA tab a few times. The badge digest alternates between v1 and v2, and v2 pages show the new card **Q8: biggest upsets** (Luxembourg's 2008 win over Switzerland, at a 0.6% pre-match chance).
6. **[B]** Roll back one platform with `demo rollback aca`. The old revision is still running, so all traffic moves back at once. Refresh: only v1 remains. AKS keeps v2 until the reset after the show.

**If it fails:**

- **Rollout errors or passes 45:30.** Stop and show the rollout output and ACA traffic table from rehearsal. Say they are recorded.
- **Rollback leaves a split.** Run `demo rollback aca` again, then continue.

## Segment 7: operate (46:00–51:00; hard stop 52:00)

1. **[A]** On the L1 answer page from segment 4, click **local trace view**, or open `/trace/<trace ID>`. It shows one request end to end:
   - the web request;
   - the call to `insights`;
   - `invoke_agent football-insights`;
   - each `chat <deployment>` model call, with its tokens;
   - each `execute_tool` call, with its evidence IDs.
2. **[C]** Run `demo trace <trace ID>`, which prints the trace URLs on both platforms and the KQL query to paste into Application Insights. Ingestion can lag by minutes; the local view doesn't.
3. **[A]** Show token usage and the estimated cost per answer on the answer pages from both platforms.
4. **[B]** Show the evaluation report from rehearsal (`EVIDENCE_DIR/eval/`) and how the rule chose the serving deployment. The rule:
   - A deployment qualifies with a grounding pass rate ≥ 95%, tool selection ≥ 90%, all limitation and framing cases passing, ≥ 95% live narratives, and p95 ≤ 25 s.
   - Among qualifying deployments, the cheaper per answer wins, unless the other is at least 5 points more accurate at tool selection.
5. **[B]** Content filtering: Foundry's filters are on for both deployments. Show that a filtered answer is labeled "filtered" while its evidence still renders (use the rehearsal recording if nothing was filtered live).

**If it fails:** The trace view is empty? Spans stay in memory only on the replica that served the request. Refresh the answer page and use its trace ID, or open a trace from the snapshot.

## Segment 8: hackathon launchpad (51:00–53:00; hard stop 54:00)

1. **[A]** Tour the repository: `README.md`, `docs/`, `demo/`.
2. **[A]** Point to [data/README.md](../data/README.md) for getting the data, and to the two extension paths in [HACKATHON-GUIDE.md](HACKATHON-GUIDE.md): add a question, or bring your own dataset.
3. **[A]** Open [AKS-VS-ACA.md](AKS-VS-ACA.md#which-should-my-hackathon-team-choose) and leave the decision guide on screen for Q&A.

## Segment 9: Q&A (53:00–60:00)

Keep the decision guide on screen. Short answers:

- **Which platform should a hackathon team choose?** Start with ACA if you want the shortest path from a container to an HTTPS URL and don't need Kubernetes itself: here that was 4 resources against 23 declarations. Choose AKS if you need the Kubernetes ecosystem, per-pod network policies, or node control, or you want Kubernetes experience. Either way, use the same images, managed identities, and deployment by digest.
- **Why doesn't the model compute the statistics or write SQL?** Numbers must be reproducible and tested. A model's arithmetic or SQL can be wrong silently, and nobody can review it live. Here the model only chooses typed, read-only tools and explains their results, and a deterministic check rejects any number it didn't get from a tool.
- **Where did the Premier League scenarios from the abstract go?** Play styles, counterattacks, and player patterns need club match events or tracking data, and these datasets hold international results only. The architecture takes such data the same way:
  - a schema contract;
  - a reviewed crosswalk;
  - new ingest tables;
  - new tools.

  Check the license first: detailed club event data is usually commercial.
- **What does it cost to run?** See [AKS-VS-ACA.md](AKS-VS-ACA.md#estimated-daily-cost-at-demo-scale). An idle ACA replica costs cents per day, while an AKS Automatic cluster costs dollars per day for its control plane and node. Model tokens are billed per answer, and the app shows each answer's tokens and estimated cost. A budget alert watches the total.
- **Why deploy two models, and how was one chosen?** They trade quality, latency, and price: GPT-6 Astra costs five times as much as GPT-6 Sol per token. The evaluation suite ran both repeatedly against the same cases and picked one with a written rule (see segment 7). Switching is one setting, `demo switch-model`, with no rebuild.
- **Could an open or self-hosted model replace them?** Yes, if it supports tool calling and structured output: deploy it, add it to the allowed deployments, run `demo eval`, and switch. The grounding check protects the numbers whatever model you use.

## Before the stream

### Preparation timeline

| When | Date | Done when |
| --- | --- | --- |
| T-14 | Sep 30 | Repository and ground truth ready; subscription, region, quota, and budget confirmed |
| T-12 | Oct 2 | Local app complete; Foundry foundation with both model deployments provisioned |
| T-10 | Oct 4 | All seven questions answered live on both models; evaluation has chosen the serving deployment |
| T-8 | Oct 6 | Both platforms deployed from the docs; `demo smoke` passes; docs updated from what the deployment proved |
| T-7 | Oct 7 | First timed rehearsal on the presenter machine with pinned tools. Then `demo snapshot both`, `demo capture`, and a screen recording. Rehearse the Copilot moment and build v2 (below). |
| T-4 | Oct 10 | Second timed rehearsal after `demo reset`; runbook and on-stage script frozen; Reactor tech check done |
| T-1 | Oct 13 | Services warm; `demo verify` shows 0 warnings on the frozen data; `demo preflight` passes; snapshots open offline |
| Day of | Oct 14 | Preflight an hour before; no updates installed |

### Build the v2 image (during rehearsal)

```powershell
git switch v2-upsets; $env:IMAGE_TAG = 'v2-upsets'; demo build-push -Output v2; git switch main
```

### Rehearsal checklist

- [ ] `demo reset` returns both platforms to v1 and the default model deployment.
- [ ] `demo smoke` passes, covering health, digests, the data version, parity, and `insights` isolation.
- [ ] Run the full show with a timer and record actual versus planned time per segment.
- [ ] Rehearse each fallback at least once:
  - [ ] a no-model fallback URL;
  - [ ] the switch to `v2-upsets`;
  - [ ] a replay page;
  - [ ] `demo up -LiveModel`.
- [ ] After a good run, run `demo snapshot both` and check that `index.html` opens with the network off.
- [ ] Recreate `stage-upsets` from `main` for the next run: `git switch main; git branch -D stage-upsets; git switch -c stage-upsets`.

### Day-of timeline

| When | Action |
| --- | --- |
| 60 min before | Run `demo preflight`; every line must be PASS. Fix anything else now. |
| 45 min before | Run `demo reset`, then `demo smoke`. |
| 30 min before | Warm up: ask one prepared question on each platform, so each model deployment has served a request, and open each card once. |
| 20 min before | Set up the window layout. Load the ACA and AKS tabs and the Data page. Open the Copilot app on `stage-upsets`. Open the evidence folder. |
| 10 min before | Screen-hygiene checklist below. Confirm with the producer which window or screen is captured. |
| 2 min before | Close everything not in the layout. Run `demo preflight` once more if time allows. |

### Presenter machine and screen hygiene

- [ ] Notifications and Focus Assist off; mail, chat, and calendar closed; system sounds muted.
- [ ] A demo-only browser profile with no corporate autofill, saved passwords, or personal bookmarks.
- [ ] Fonts legible on a compressed 1080p stream:
  - [ ] the app at 125% zoom (the app's A+ button also works);
  - [ ] terminal font 18 or larger;
  - [ ] editor font 18 or larger.
- [ ] High-contrast theme in the terminal and editor.
- [ ] A fixed window layout with few switches.
- [ ] Confirm with the producer exactly which screen or window is captured.
- [ ] The runbook and on-stage script on the second, unshared screen.
- [ ] Shell history cleared of anything sensitive (`Clear-History`; for PSReadLine, delete the history file).
- [ ] No subscription or tenant IDs, email addresses, keys, portal account menus, or notes on screen. Prefer the app and the terminal over the Azure portal. The recording is permanent.
- [ ] A wired network connection, and a phone hotspot tested as a fallback.

### Credentials and their lifetimes

Check them all with `demo preflight`. Re-authenticating fits inside a segment.

| Credential | Lifetime | Check | Re-authenticate |
| --- | --- | --- | --- |
| Azure CLI sign-in | Access tokens last about an hour and refresh automatically. The sign-in lasts until it is revoked, expires from inactivity, or your organization's sign-in-frequency policy asks again. | `demo preflight` reports the token's expiry | `az login`, then `demo preflight` (about 1 minute) |
| kubectl (AKS) | Uses the Azure CLI sign-in through kubelogin, so nothing separate expires | `demo preflight`: "kubectl reaches cluster" | Any AKS command reconnects (`az aks get-credentials` and `kubelogin convert-kubeconfig -l azurecli`) |
| GitHub Copilot app | Stays signed in until you sign out or the session is revoked | Open the app and send a short test prompt 30 minutes before | Sign in again from the app's account menu, off screen |
| Kaggle | Not needed during the stream: the data is downloaded, frozen, and uploaded | not applicable | not applicable |
| Local Foundry token file (fallback level 3 only) | Tokens last about an hour; `demo up -LiveModel` refreshes them every 15 minutes | `demo preflight` | `demo up -LiveModel` |

## After the stream

- Run `demo reset` to return AKS to v1 and the default model.
- Leave both deployments running only as long as agreed. Run `demo teardown -DryRun` to list what will be deleted. The real `demo teardown` deletes the whole resource group, and only after you type its name, so run it once the deletion is approved.
