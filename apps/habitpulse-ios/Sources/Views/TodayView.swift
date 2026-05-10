import SwiftData
import SwiftUI

/// One-tap check-in for today.
///
/// Two large buttons (Done / Skipped) write a ``CheckIn`` for today. If the
/// user has already checked in, the buttons flip to "Update" affordances so
/// they can correct a mistap. Streak is computed in-memory from the most
/// recent contiguous run of done-days; for typical habit histories (<10k
/// entries) this is fine without an index.
struct TodayView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \Habit.createdAt) private var habits: [Habit]

    private var habit: Habit? { habits.first }

    private var todayCheckIn: CheckIn? {
        guard let habit else { return nil }
        let today = Calendar.current.startOfDay(for: .now)
        return habit.checkIns.first { $0.date == today }
    }

    private var streak: Int {
        guard let habit else { return 0 }
        // Sort descending by date and walk forward; stop at the first gap or
        // skipped day. ``today`` is included only if it's a done check-in so
        // the streak doesn't tick to 1 on a fresh install.
        let sorted = habit.checkIns.sorted { $0.date > $1.date }
        var count = 0
        var cursor = Calendar.current.startOfDay(for: .now)
        for entry in sorted {
            if entry.date == cursor && entry.value > 0 {
                count += 1
                cursor = Calendar.current.date(byAdding: .day, value: -1, to: cursor)!
            } else if entry.date < cursor {
                break
            }
        }
        return count
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                Spacer()

                VStack(spacing: 8) {
                    Text(habit?.name ?? "Habit")
                        .font(.largeTitle).bold()
                    Text("\(streak) day streak")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                HStack(spacing: 16) {
                    checkInButton(
                        title: todayCheckIn?.value == 1 ? "Done ✓" : "Done",
                        color: .green,
                        isActive: todayCheckIn?.value == 1
                    ) { record(value: 1.0) }

                    checkInButton(
                        title: todayCheckIn?.value == 0 ? "Skipped ✓" : "Skipped",
                        color: .orange,
                        isActive: todayCheckIn?.value == 0
                    ) { record(value: 0.0) }
                }
                .padding(.horizontal)

                Spacer()
            }
            .navigationTitle("Today")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func checkInButton(
        title: String,
        color: Color,
        isActive: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(.title2.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 100)
                .background(isActive ? color : color.opacity(0.2))
                .foregroundStyle(isActive ? .white : color)
                .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain)
    }

    private func record(value: Double) {
        guard let habit else { return }
        if let existing = todayCheckIn {
            existing.value = value
        } else {
            context.insert(CheckIn(date: .now, value: value, habit: habit))
        }
        try? context.save()
    }
}
