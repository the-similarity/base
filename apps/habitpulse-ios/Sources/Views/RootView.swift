import SwiftData
import SwiftUI

/// App root — four-tab shell.
///
/// Bootstraps a default ``Habit`` on first launch so the user is never
/// staring at an empty Today screen. Subsequent launches use whatever the
/// user has named their habit in Settings.
struct RootView: View {
    @Environment(\.modelContext) private var context
    @Query private var habits: [Habit]

    var body: some View {
        TabView {
            TodayView()
                .tabItem { Label("Today", systemImage: "checkmark.circle") }

            HistoryView()
                .tabItem { Label("History", systemImage: "square.grid.3x3") }

            ForecastView()
                .tabItem { Label("Forecast", systemImage: "chart.xyaxis.line") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .task { ensureHabit() }
    }

    private func ensureHabit() {
        guard habits.isEmpty else { return }
        context.insert(Habit(name: "My Habit"))
        try? context.save()
    }
}
