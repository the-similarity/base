import SwiftData
import SwiftUI

/// Habitpulse — single-habit tracker with self-similarity forecasting.
///
/// Lifecycle:
/// - On launch we open (or create) a SwiftData container holding ``Habit`` and
///   ``CheckIn``. The container lives in the default app-support directory; no
///   explicit migration is wired yet because the schema is v0.
/// - The shared ``AppState`` is injected as an `@Environment` object so any
///   view can read or mutate the API base URL without prop-drilling.
/// - All forecasting calls hit the network; on-device inference is out of
///   scope for v0 (we'd have to port the Python engine to Swift).
@main
struct HabitpulseApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
        }
        .modelContainer(for: [Habit.self, CheckIn.self])
    }
}
