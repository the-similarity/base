# Habitpulse

Single-habit tracker with self-similarity forecasting. Powered by the
`the-similarity` engine: every forecast is built from analogues found in the
user's *own* past behavior, not population averages.

## Stack

- **iOS 17+ SwiftUI** with SwiftData for on-device storage.
- **Swift Charts** for the forecast cone and analogue sparklines.
- **the-similarity-api** (`POST /habit/forecast`) for analogue search +
  cone projection. The mobile client owns all data; the server is stateless
  pure compute.

## Run it

```bash
# 1. Start the API
cd ../../the-similarity-api
uvicorn app.main:app --reload

# 2. Generate the Xcode project
cd ../apps/habitpulse-ios
xcodegen generate

# 3. Open + run
open Habitpulse.xcodeproj
# select an iPhone simulator and press ⌘R
```

In the simulator: **Settings → API base URL** → `http://localhost:8000`
(default). Check in for ~3 weeks (or seed manually via the simulator's data
container) and the **Forecast** tab will produce real analogues.

## Architecture

```
Sources/
├── App/
│   ├── HabitpulseApp.swift   # @main, SwiftData container
│   └── AppState.swift         # API URL via @AppStorage
├── Models/
│   ├── Habit.swift            # @Model — name + checkIns
│   └── CheckIn.swift          # @Model — date + value
├── Networking/
│   ├── HabitAPI.swift         # async URLSession client
│   └── HabitForecast.swift    # Decodable response shapes
└── Views/
    ├── RootView.swift         # 4-tab shell, seeds default habit
    ├── TodayView.swift        # one-tap Done/Skipped + streak
    ├── HistoryView.swift      # 13×7 dot heatmap
    ├── ForecastView.swift     # cone chart + analogue cards
    └── SettingsView.swift     # habit name + API URL
```

## Endpoint contract

`POST /habit/forecast` — see `the-similarity-api/app/habit_routes.py`.

Request:
```json
{ "series": [1.0, 0.0, 1.0, ...], "window": 7, "forward_bars": 7, "top_k": 3 }
```

Response:
```json
{
  "analogues": [{"start_idx": 12, "end_idx": 19, "score": 87.4, "forward": [...]}],
  "cone": {"p10": [...], "p50": [...], "p75": [...]},
  "relapse_risk": 0.23
}
```

The series is dense (one value per day, missing days = 0.0). A 21-day
minimum is enforced before the Forecast tab will fetch.

## Scope (v0)

Single habit, boolean check-ins, no notifications, no HealthKit, no sync.
Schema is forward-compatible with multi-habit + numeric values.
