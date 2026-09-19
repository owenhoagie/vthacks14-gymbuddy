# Synthetic historical forecasting demo

Open [Historical demo](https://gymbuddy.work/?mode=demo), or select
**Historical demo** beside **Live VT data**. The default hosted view remains live.
Calendar connections, imports, manual busy blocks, and workout preferences survive the switch.
The banner, occupancy cards, forecast note, and recommendation provenance label demo results.

## Data

`fixtures/demo-history.csv` contains **12,096 explicitly synthetic observations**:
two gyms, every 15 minutes, for 63 days (July 13–September 13, 2026, Eastern Time).
The generator uses seed `140926`, different gym peak times, weekday/weekend patterns,
daily variation, and correlated noise. Counts fit the configured capacities of 600 and 1,200.
These patterns are invented for demonstration, not measurements or claims about VT behavior.

Run `make demo-history` to reproduce the CSV, evaluation report (`fixtures/demo.json`),
and matching API examples. Generated files are versioned and deterministic.

## Forecast

`api/demo.py` fits mean occupancy by **gym × Eastern weekday × quarter-hour**.
Neighboring slots are smoothed and interpolated for five-minute predictions. The most recent
matching historical bucket supplies the simulated current occupancy. Its difference from the
profile decays with a 90-minute time constant, producing an anchored four-hour forecast.
The extra point at minute 245 covers requests rounded up to the next five-minute start.
Predictions are bounded to 0–100%; all demo confidence remains **low**.

The forecast is calculated from the history on each request using a fitted profile cached in
the API process. It is not Gemini output. Replacing the historical observations changes the
fitted forecast. Serving uses all nine weeks; evaluation fits only the first eight weeks and
holds out the ninth week, without reading held-out values during fitting.

| Synthetic held-out week | Seasonal MAE (percentage points) | Constant-average MAE |
| --- | ---: | ---: |
| McComas | 2.909 | 16.414 |
| War Memorial | 4.131 | 15.701 |

These scores measure agreement with fabricated data generated from similar patterns.
They **do not establish real-world forecast quality**, and are not shown as live accuracy.
Demo hours explicitly allow the whole search horizon so the scenario works at any hour;
they are fictional, not VT opening hours. Calendar conflicts are still enforced.

## Isolation and operation

- `?demo=true` on any of the four API endpoints opts that request into the historical demo.
  Requests without it continue using the configured default mode; no global environment or
  user session is mutated. Invalid values return the normal validation envelope.
- Demo requests bypass warehouse refresh. The bundled model works during a Databricks outage.
- No synthetic rows are inserted into Databricks Bronze, Silver, Gold, or the real collector
  CSV/outbox. Live forecasts retain their existing Databricks rolling-mean/trend model.
- The demo runs in the existing FastAPI deployment and uses no additional services or billing.
- Returning to Live VT data uses real observations and verified operating hours. Demo values
  are never used as a fallback for failed live requests.

Tests cover reproducibility, unique history keys, fitting from changed data, held-out isolation,
baseline comparison, DST and midnight horizons, UTC output, bounded forecasts, and request-level
isolation from an unavailable live warehouse.
