import Foundation
import SwiftData

/// A single day's check-in for a habit.
///
/// Invariant: ``date`` is normalized to the start of the user's calendar day
/// (`Calendar.current.startOfDay(for:)`) so equality + uniqueness comparisons
/// work without time-of-day jitter. The Today view enforces this on insert.
///
/// ``value`` is stored as a Double rather than a Bool so the schema can later
/// admit numeric habits (e.g. cups of water, pages read) without migration.
/// In v0 it's always 1.0 (done) or 0.0 (skipped).
@Model
final class CheckIn {
    var date: Date
    var value: Double
    var habit: Habit?

    init(date: Date, value: Double, habit: Habit? = nil) {
        self.date = Calendar.current.startOfDay(for: date)
        self.value = value
        self.habit = habit
    }
}
