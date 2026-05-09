import Foundation

/// Decoded response shape for ``POST /habit/forecast``.
///
/// Fields mirror the Pydantic models in
/// ``the-similarity-api/app/habit_routes.py``. Keep them in lockstep — if you
/// add a field there, add it here (or extraction will silently fail when
/// JSONDecoder requires it).
struct HabitForecast: Decodable {
    struct Analogue: Decodable, Identifiable {
        let startIdx: Int
        let endIdx: Int
        let score: Double
        let forward: [Double]

        /// Stable identity for SwiftUI lists. Using ``startIdx`` is safe
        /// because matches are non-overlapping windows.
        var id: Int { startIdx }

        enum CodingKeys: String, CodingKey {
            case startIdx = "start_idx"
            case endIdx = "end_idx"
            case score
            case forward
        }
    }

    struct Cone: Decodable {
        let p10: [Double]
        let p50: [Double]
        let p75: [Double]
    }

    let analogues: [Analogue]
    let cone: Cone
    let relapseRisk: Double

    enum CodingKeys: String, CodingKey {
        case analogues
        case cone
        case relapseRisk = "relapse_risk"
    }
}
