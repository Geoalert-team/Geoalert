# "Predictive models" tab and flood data readiness — short design

Date: 2026-11-24. Status: awaiting approval. Size: small change. Uncommitted (the user commits).

## Intent and why

The Reporting and Analytics page has two tabs, Reports and Analytics. Analytics mixes records-based figures with the description of the prediction models. The user wants the model description on a tab of its own, "Predictive models", beside Reports and Analytics. This keeps history (what the records show) apart from predictive analytics (what the models say), which is the user's standing rule.

The user also asked whether anything checks if the database has enough flood data to switch models. Nothing does: the flood model learns from the 2017 UP Mananga survey, and training is rerun by hand. The user chose a read-only readiness panel on the new tab. It tells a person when a retrain or rebuild is worth running.

## Goals

1. **A third tab.** It is labelled "Predictive models", key `models`, at `?tab=models`.
   - It sits after Reports and Analytics.
   - It opens lazily and stays mounted, like the other two.
   - Its header blurb: "How the prediction models were built and tested, and whether there is enough data to improve them."
2. **The "Model accuracy" card moves** from Analytics to the new tab, unchanged.
   - "Likelihood by barangay" stays in Analytics, under its hazard filter (the user's choice).
   - The Seasonal outlook stays too, as it counts past seasons.
3. **A "Flood data readiness" card** sits on the new tab, above Model accuracy, and shows:
   - Located flood days on record, against the about 20–30 that flood forecasting needs.
   - New located floods since the flood map was published, against the 10 after which the map is reviewed, with "Under review: …" when monitoring flags it.
   - What the flood map is trained on (the 2017 UP Mananga flood survey, with its number of flood spots) and when it was built.
   - One plain status sentence:
     - under 20 days: "Not enough located flood days to try flood forecasting yet."
     - at 20 or more: "There are enough located flood days to consider building a flood forecast. That needs a rebuild by a developer."
4. **The counts show even when no flood model is trained or the model is stale.** Only the "since published" part then reads "No flood map has been published yet." (or gives the model's reason).

## Non-goals and anti-goals

- **Nothing switches, retrains or changes a prediction automatically.** The panel only counts. Automatic switching is the separate project paused on 2026-11-16.
- **Out of scope:** fire readiness; any change to the Model accuracy card's content or the Likelihood table; any change to who can see the page (DRRMO and System Admin, as now).
- **History records are read, never changed.**
- **Anti-goal:** the panel must not suggest the flood map learns from the database. The training line names the survey.

## Approaches (the user picked A)

- **A. Its own small endpoint (chosen).** `GET /api/history/forecast/readiness/` returns the counts, and the card fetches it.
  - For: the Model accuracy card stays untouched, and the counts show whatever the model's state.
  - Against: one more endpoint and request.
- **B. Add the counts to the accuracy response.** One request, but the Model accuracy card must take its data from the tab instead of loading it itself.
- **C. A few lines inside the flood section of the Model accuracy card.** The least code, but buried in the card, and gone whenever flood shows "unavailable".

## Decided how

- **A "located flood" uses the same definition as the flood map's "Since publishing" check** (`flood_purok.since_publishing`). It is a Flood history record with a map point or at least one purok, or an "Affected here" mark on a flood zone. A located flood day is a distinct local date among them.
  - The record/mark query is factored out of `since_publishing` so both share it.
  - `since_publishing`'s behaviour does not change; its tests guard that.
- **The endpoint is public and cached** (`AllowAny`, Cache-Control public, max-age 600), like `forecast/accuracy/`. It returns only aggregate counts, never a location.
- **The response shape:**

  ```json
  {
    "located_flood_days": 6,
    "forecast_days_needed": {"min": 20, "max": 30},
    "enough_for_forecasting": false,
    "flood_map": {
      "available": true,
      "reason": null,
      "version": "noah_fallback@...",
      "built_at": "...",
      "trained_on": "2017 UP Mananga flood survey",
      "survey_spots": 105
    },
    "since_publishing": {"n": 0, "review_after": 10, "under_review": false}
  }
  ```

  - With no usable model, `flood_map` is `{available: false, reason}`. `since_publishing` is then `null`.
  - The thresholds come from existing constants: `MONITOR_MIN` is 10. The 20–30 forecasting figure is a new constant beside it, citing the 2026-11-24 flood assessment.
- **Frontend:**
  - `ReportingAnalytics.jsx` gains the third tab.
  - A new `PredictiveModelsPanel` renders `FloodReadiness` (new) and then `ForecastAccuracy`.
  - `Analytics.jsx` drops the Model accuracy card and its docstring line.

## Left to the builder

- Card styling, which follows the existing `db-card` and `fc-*` classes.
- Exact test names.
- Whether `FloodReadiness` shows a loading line.
- Load and error lines ("The readiness check could not be loaded right now.").

## Builder notes

- **The Analytics PDF/print** will no longer include Model accuracy. The new tab gets no export menu (my call: nothing there is an official figure).
- **Tests:**
  - backend: distinct days counted, unlocated records ignored, marks counted, works with no model, the "since publishing" block, the public cache header;
  - frontend: the tab and `?tab=models`, Analytics without Model accuracy, readiness counts / under review / no model / load error.
