# GymBuddy: a plain-English guide for the team

*Speech-writing and presentation reference • Project state as of September 19, 2026*

**GymBuddy helps Virginia Tech students decide when and where to work out by combining gym crowd estimates, their available time, and their preferences.**

The question it answers is: **“Given my schedule, where can I fit a full workout with a crowd level I’m comfortable with?”**

- [Open the live app](https://gymbuddy-vthacks14.vercel.app/)
- [Open the historical demo](https://gymbuddy-vthacks14.vercel.app/?mode=demo)
- [View the project on GitHub](https://github.com/owenhoagie/vthacks14-gymbuddy)

## 1. The problem we are solving

A student may have a gap between classes, but that gap does not automatically make it a good time to visit the gym. The gym could be crowded, closed, or about to close. A quiet moment also does not help if the student has to leave halfway through their workout.

GymBuddy brings those questions together. Instead of making students compare a crowd counter, their calendar, and opening hours themselves, it checks for a complete workout window and recommends a gym and time.

The intended benefit is less guesswork and easier planning. We have not measured actual reductions in equipment wait times or improvements in exercise habits, so those are goals rather than proven outcomes.

## 2. What a student can do

The current app supports **McComas Hall** and **War Memorial Hall** at Virginia Tech.

| Feature | What it means for the student |
| --- | --- |
| Current occupancy cards | See the reported number of people, capacity, percentage full, and when GymBuddy fetched the information. |
| Four-hour forecast chart | See an estimate of how crowded each gym may become over the next few hours. |
| Workout duration | Choose 30, 45, 60, 75, or 90 minutes in the dashboard. |
| Gym preferences | Favor McComas, War Memorial, both, or neither. A preference influences the ranking without excluding the other gym. |
| Crowd comfort | Choose “Keep it quiet,” “Some buzz,” or “Busy is fine.” |
| Manual unavailable times | Mark periods when a workout cannot happen. |
| Calendar file import | Import an `.ics` calendar export to identify busy times automatically. |
| Google Calendar connection | Read busy times from the user’s primary Google calendar with their permission. |
| Best workout window | Get a recommended gym, start time, end time, and estimated average crowd level for the entire workout. |
| Alternative | See another option when one is available. |
| Explanation | Understand why the recommendation fits, with Gemini providing the wording when available. |

Times are displayed in Eastern Time, matching Virginia Tech’s location. The dashboard refreshes occupancy and forecasts every minute. An existing recommendation keeps its original generation time until another recommendation is requested.

### An example to explain aloud

Imagine a student wants a 75-minute workout, prefers McComas, and has a class during part of the next four hours. They connect their calendar or enter that class manually, then click **Find my gym window**.

GymBuddy checks which full 75-minute windows avoid the class, fall within known gym opening hours, and have usable forecasts. It compares expected crowd levels across those windows and returns a recommendation plus an alternative when possible.

This is an illustrative scenario. The actual time and gym depend on the current data and the student’s inputs. If no full workout fits, the app says so rather than forcing a suggestion.

## 3. How a recommendation is chosen

The core decision follows explicit rules. It does not rely on a language model guessing a time.

1. **Look ahead up to four hours.** Consider possible workout starts five minutes apart.
2. **Remove conflicts.** Combine manual and imported busy periods, including overlapping events.
3. **Check the whole workout.** It must finish before another commitment, before the gym closes, and before the available forecast ends.
4. **Check the data.** Stale or missing forecasts cannot support a recommendation. Unknown or expired opening hours exclude that gym.
5. **Estimate the crowd throughout the workout.** Compare the average expected occupancy over the full session, not just the first minute.
6. **Apply crowd comfort and gym preferences.** Favor acceptable crowd levels, then rank by crowd level with a small preference bonus. Earlier starts break ties.

The crowd-comfort thresholds are 40%, 65%, and 85% full. A preferred gym receives a five-percentage-point bonus **in the ranking only**; the displayed occupancy estimate is not reduced.

If every feasible option exceeds the selected crowd threshold, GymBuddy chooses the least crowded feasible option and clearly warns the student. In that situation, gym preference does not override the least crowded choice.

The alternative usually offers a different gym. When that is not possible, the system may offer a separate time at the same gym. An alternative is not guaranteed.

## 4. Where the real information comes from

GymBuddy retrieves the occupancy information published by **Virginia Tech RecSports**. It reads the existing website’s response and extracts the counts for the two supported gyms. We did not install cameras, sensors, or new tracking hardware.

The collector calculates capacity from the reported occupied and remaining spaces, then calculates the percentage full. It also translates the source’s “WMH Service Desk” label into the clearer “War Memorial Hall.”

Opening hours come from VT’s separate public hours service. The app checks date-specific hours rather than assuming a gym is always open.

One important detail: VT does not provide a verified measurement-update timestamp in the occupancy response we use. GymBuddy therefore displays **“Fetched…”** to say when it retrieved the information. That is not a promise that VT’s underlying count changed at that moment.

These are building-level occupancy estimates. GymBuddy cannot tell whether a particular squat rack, treadmill, or machine is free.

## 5. How the project works behind the scenes

Think of the system as a small team with different jobs:

| Part | Plain-English job |
| --- | --- |
| **Cloudflare** | The alarm clock: tells the collector to start every five minutes. |
| **GitHub Actions** | The worker: runs the collection program on a hosted computer. |
| **Collector** | The researcher: fetches VT occupancy and saves successful observations. |
| **Databricks** | The shared data store and calculator: keeps real observations and computes live forecasts. |
| **FastAPI backend** | The coordinator: gives the website its data, checks availability, and ranks workout options. “Backend” means the part running on a server. |
| **Gemini** | The explainer: turns the checked workout options into a short, readable explanation. |
| **Next.js dashboard** | The screen students use: displays charts, accepts preferences, and shows the recommendation. |
| **Vercel** | The host: makes the dashboard and backend accessible online. |

The regular data journey is:

**Cloudflare timer → GitHub collector → VT occupancy → Databricks history and forecasts → backend → dashboard**

When someone requests a workout, there is another step:

**Available time + preferences + opening hours + forecasts → checked workout options → Gemini explanation → recommendation card**

The hosted system runs without a teammate’s laptop or browser staying open. Collection is scheduled every five minutes; the dashboard checks for updates every minute. These are different intervals, so refreshing the page does not necessarily mean a new VT observation has been collected.

The website and backend use Vercel Hobby, and the scheduler uses Cloudflare Workers Free. The public repository runs the collector on GitHub Actions. Databricks and Gemini use the project’s configured accounts and quotas. The setup has not required a paid hosting upgrade; credentials, trial expiration, and provider limits still need attention.

## 6. What Databricks does

Databricks is actively used in the live product. It stores real occupancy history and computes the forecasts displayed in live mode.

The data has three stages, commonly called Bronze, Silver, and Gold:

| Stage | Simple explanation |
| --- | --- |
| **Bronze: observations** | The logbook of actual fetched counts and their original timestamps. Re-uploading the same observation does not create another copy. |
| **Silver: recent patterns** | A summary of recent observations, including the average occupancy over a 30-minute window and information used to estimate a trend. |
| **Gold: forecasts** | The ready-to-use predictions that the app reads. |

### How the live forecast is calculated

The live forecast starts with the recent 30-minute average, then extends the recent upward or downward trend. The trend is limited to 0.25 percentage points per minute so a sudden change cannot create an unlimited projection. Predicted occupancy stays between 0% and 100%.

Each gym receives 49 forecast points, spaced five minutes apart, covering four hours from its latest observation. With fewer than three observations in the recent window, the forecast stays flat and is labeled low confidence. With enough observations, it uses the capped trend and is labeled medium confidence.

This is a simple statistical starting model. It is not a sophisticated model trained on years of real gym behavior. Confidence labels describe the available support for the estimate; they are not measured probabilities of being correct.

## 7. What Gemini does—and what it does not do

Gemini is used when a valid recommendation is available. The backend first calculates the approved workout options. Gemini then requests those options through a tool and submits an explanation tied to their identifiers.

A “tool” here is a controlled way for the AI to obtain information from the application. It lets Gemini explain options that the system has actually checked.

The backend validates the response and keeps control of the selected gym, workout times, crowd estimates, confidence, and warnings. Gemini does not calculate the forecast, choose an unchecked time, edit calendars, reserve gym space, or generate a workout routine.

If Gemini is slow, unavailable, over quota, or returns an invalid response, the original recommendation still works with a standard explanation. AI improves the presentation without becoming a requirement for the scheduling calculation.

**Useful speech wording:** “We use Databricks to forecast crowds, explicit scheduling rules to find a workout that fits, and Gemini to explain the recommendation.”

## 8. Calendars and privacy

Calendar support makes the recommendation personal without needing event contents on our server.

- **Calendar files:** An `.ics` file is a common calendar export. GymBuddy processes it inside the browser, including supported recurring events, cancellations, all-day events, and time zones. It does not upload the original file.
- **Google Calendar:** The user grants permission to read busy/free information from their primary calendar. GymBuddy does not request event titles or permission to change events.
- **What reaches the backend:** Busy start/end times, workout duration, gym preferences, and crowd tolerance. The application does not persist those busy periods.
- **What reaches Gemini:** Checked workout options and relevant preferences. Calendar files, busy blocks, event contents, and Google access tokens are excluded.
- **What stays in the tab:** Imported calendar data and Google access tokens remain in tab memory and clear on reload. Reloading does not itself revoke the permission previously granted through Google.

Google sign-in currently uses testing mode, so demo users must be added as approved testers. It is not yet an unrestricted public Google integration. People can still enter busy times manually or import a file.

If an attached calendar cannot be read, the app asks for reconnection, retry, or explicit removal rather than silently ignoring the calendar. Some unusual or overly complex calendar exports are rejected instead of interpreted unreliably.

The app includes a [privacy page](https://gymbuddy-vthacks14.vercel.app/privacy). It is not a claim of complete anonymity: hosting providers process ordinary request information, and Gemini processes its limited inputs under Google’s service terms.

## 9. Live mode versus historical demo mode

These are deliberately separate experiences.

| | Live VT data | Historical demo |
| --- | --- | --- |
| Occupancy source | Real observations fetched from VT | Invented observations created for demonstration |
| Forecast method | Databricks recent-average and trend calculation | Patterns fitted from synthetic history by gym, weekday, and time of day |
| Opening hours | VT’s published hours | Clearly fictional hours that cover the demo window |
| Intended use | Current gym-planning estimates | Demonstrating the product and historical forecasting behavior |
| Confidence | Low or medium depending on recent samples | Always low |

The demo contains **12,096 synthetic observations across nine weeks**. It includes invented weekday/weekend differences, different gym peak times, and variation between days. The demo model learns an average pattern from that history and adjusts its forecast around the simulated current occupancy.

That means the demo chart is calculated from a dataset rather than being a fixed decorative line. However, its history is fabricated. Testing against part of that synthetic history does not prove accuracy on real students or real gym attendance.

Synthetic data is kept separate from the real Databricks tables and collection buffer. Live mode never silently substitutes demo data during an outage. Calendar conflicts still apply in demo mode, even though demo opening hours are fictional.

**Useful speech wording:** “Our live pipeline uses real VT observations. We also have a clearly labeled synthetic-history mode to demonstrate longer-term patterns while real history accumulates.”

## 10. What happens when something fails

Reliability is part of the prototype:

- A successful fetch is saved before the upload is attempted. Failed uploads remain in a retry buffer for a later run.
- Repeating an upload does not duplicate the same observation.
- A failed forecast rebuild retains the previous published forecast and leaves refresh work pending.
- When an existing cached snapshot is available, the app can show it with its original timestamps. Cached data is labeled; it does not become “new” just because it is served again.
- Forecasts backed by observations more than 15 minutes old cannot produce recommendations.
- Missing data, unknown hours, and a schedule with no full workout window produce explicit unavailable or no-window results.
- Gemini failure leaves the ordinary scheduling result available.

The hosted backend’s temporary cache can disappear when its server instance restarts. If Databricks is unavailable and no cache exists, the app shows unavailable data. The collector’s retry buffer also has limited retention, so this is not a promise of indefinite recovery from every outage.

The original GitHub timer did not produce scheduled runs, so we replaced that trigger with Cloudflare. We verified five consecutive successful automatic cycles at **4:20, 4:25, 4:30, 4:35, and 4:40 PM Eastern on September 19**. The resulting observations and forecasts reached the live API. That verifies operation during that period, not permanent uptime.

The current scheduler token expires **September 26, 2026**. It must be replaced before expiration for automatic collection to continue. Other account credentials and trial limits also remain operational dependencies.

## 11. What is built today, and what could come later

The working prototype includes the hosted dashboard, two-gym occupancy collection, real Databricks storage and forecasts, automatic cloud scheduling, workout ranking, calendar import, Google free/busy access for approved testers, Gemini explanations, and the separate historical demo.

Automated checks cover data parsing, upload recovery, forecast calculations, scheduling constraints, calendar handling, Gemini failures, and the Cloudflare runtime. Checks also ensure that the website and backend agree on the format of the data they exchange and that the website builds successfully. Live checks have exercised collection, Databricks updates, the public app, Google consent, and 75-minute recommendations.

Potential next steps include collecting more real history, measuring forecast accuracy against later observations, improving the forecast model, expanding supported facilities, and preparing Google authorization for a broader audience.

The current product does **not** include equipment reservations, calendar write-back, social features, notifications, exercise-program generation, or personalized fitness coaching. It also does not track individual gym visitors or use a user’s past attendance to learn their habits.

## 12. A presentation walkthrough

1. **Start with the student’s problem:** “I have time to work out, but is that a good time to go?”
2. **Show the occupancy cards:** Explain the two gyms, percentages, and fetch timestamps.
3. **Show the forecast chart:** Explain that planning ahead is the goal, with estimates rather than guarantees.
4. **Set a 75-minute workout:** Choose a gym preference and crowd comfort.
5. **Add a schedule conflict:** Use a manual block or a prepared calendar file. Use Google only with an approved test account.
6. **Request a recommendation:** Point out the full start/end window, predicted crowd level, explanation, and alternative.
7. **Explain the system briefly:** “A cloud timer collects VT data, Databricks forecasts crowds, scheduling rules find a fit, and Gemini explains it.”
8. **If using historical demo mode, say so explicitly:** Explain why synthetic history exists and that it stays separate from live data.

If the real gyms are closed or no complete session fits, a no-window result is correct. The historical demo is useful for presenting a forecast and recommendation at any hour, but it cannot override a calendar that blocks the entire search window.

### Suggested three-minute speech structure

| Approximate time | Focus |
| --- | --- |
| 0:00–0:25 | The student problem and GymBuddy’s central question. |
| 0:25–1:20 | Walk through preferences, schedule conflicts, and the resulting workout window. |
| 1:20–2:10 | Explain VT data, Databricks forecasting, and Gemini’s specific role. |
| 2:10–2:40 | Highlight calendar privacy, automatic collection, and honest handling of missing data. |
| 2:40–3:00 | Describe the current prototype and the next step: improving forecasts with more real history. |

### A possible opening

> “Students already have to fit workouts around classes, meetings, and everything else in their day. But a free hour on your calendar doesn’t tell you whether the gym will be crowded—or whether you can finish before your next commitment. GymBuddy brings your availability and Virginia Tech’s gym occupancy information together to recommend a time and place for a complete workout.”

### Quick answers to likely questions

**Is the data real?** Live occupancy comes from VT, and live forecasts are calculated in Databricks. The separate historical demo uses explicitly synthetic data.

**Is this just an AI chatbot?** No. It is a scheduling and forecasting application. Gemini explains options that the scheduling system has already checked.

**How accurate is it?** Real-world forecast accuracy has not yet been established. The live model is a recent-average and capped-trend baseline, with visible confidence and freshness information.

**Does it know what is on my calendar?** The scheduling server receives busy time ranges, not event titles or the original calendar file. Gemini does not receive those busy ranges.

**Does it run if your laptop is off?** Yes. Cloudflare triggers a hosted GitHub collector, and the app is hosted on Vercel.

**Can it guarantee an empty gym?** No. It estimates building occupancy; it cannot guarantee equipment availability or future attendance.

**What makes it useful beyond an occupancy counter?** It combines expected crowd levels with the user’s whole workout duration, schedule, gym preferences, and opening hours to produce an actionable time window.

## 13. Where to find things in the repository

This section is optional for the speech, but useful when handing the project to another teammate.

| Folder | What is inside |
| --- | --- |
| `web/` | The website, charts, calendar controls, and browser-side calendar processing. |
| `api/` | Data access, availability checks, workout ranking, demo forecasts, and Gemini integration. |
| `collector/` | Fetching VT occupancy and safely synchronizing observations. |
| `databricks/` | Instructions for the three data stages and the live forecast calculation. |
| `scheduler/` | Cloudflare’s five-minute trigger, tests, and operating instructions. |
| `.github/workflows/` | Hosted collection and automated project checks. |
| `scripts/` | Helper commands for setup, data checks, demo generation, and verification. |
| `fixtures/` | Synthetic demonstration history and example data formats. |
| `tests/` | Automated backend checks. |
| `docs/` | This guide and deeper explanations of hosting, calendars, Gemini, and demo history. |

For technical follow-up, see the [main README](../README.md), [hosting guide](HOSTING.md), [calendar guide](CALENDARS.md), [Gemini guide](GEMINI.md), [historical demo guide](DEMO_HISTORY.md), and [scheduler guide](../scheduler/README.md).
