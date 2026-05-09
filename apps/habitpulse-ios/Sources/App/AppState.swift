import Foundation
import SwiftUI

/// Mutable, observable settings the user can change at runtime.
///
/// Persisted via `@AppStorage` (UserDefaults) because these values are tiny
/// strings the user changes once and forgets — overkill to put them in
/// SwiftData. The defaults assume a developer running the API on localhost;
/// production builds should ship with the deployed API URL.
final class AppState: ObservableObject {
    @AppStorage("apiBaseURL") var apiBaseURL: String = "http://localhost:8000"

    /// Returns the API client bound to the current ``apiBaseURL``.
    /// Recreated on every access so URL edits in Settings take effect on the
    /// next request without needing to re-launch the app.
    var api: HabitAPI {
        HabitAPI(baseURL: URL(string: apiBaseURL) ?? URL(string: "http://localhost:8000")!)
    }
}
