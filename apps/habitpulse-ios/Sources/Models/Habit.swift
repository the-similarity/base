import Foundation
import SwiftData

/// One habit the user is tracking.
///
/// MVP scope is a single habit per app install. The schema admits multiple
/// rows so a future "add another habit" flow won't require a migration; the
/// UI layer is what restricts the user to one for now.
@Model
final class Habit {
    /// Display name shown on the Today screen.
    var name: String

    /// When the user first started tracking this habit. Used as the lower
    /// bound of the History heatmap.
    var createdAt: Date

    /// Inverse relationship — every ``CheckIn`` belongs to exactly one
    /// ``Habit``. Cascade-delete so removing a habit also wipes its history.
    @Relationship(deleteRule: .cascade, inverse: \CheckIn.habit)
    var checkIns: [CheckIn] = []

    init(name: String, createdAt: Date = .now) {
        self.name = name
        self.createdAt = createdAt
    }
}
