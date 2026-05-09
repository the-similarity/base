import SwiftData
import SwiftUI

/// 90-day check-in heatmap, GitHub-contributions style.
///
/// Renders a 13-column × 7-row grid (~91 days) of dots colored by check-in
/// state. We anchor the most recent column to "today" so the layout is
/// stable as days roll over. Older days simply fall off the left edge.
struct HistoryView: View {
    @Query(sort: \Habit.createdAt) private var habits: [Habit]

    private let columns = 13
    private let rows = 7

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text("Last \(columns * rows) days")
                    .font(.headline)
                    .padding(.horizontal)

                grid
                    .padding(.horizontal)

                legend
                    .padding(.horizontal)

                Spacer()
            }
            .navigationTitle("History")
        }
    }

    private var grid: some View {
        let map = checkInMap()
        let today = Calendar.current.startOfDay(for: .now)
        // Build day-by-day from oldest to newest so the column on the right
        // is always today. We iterate column-major to match a calendar's
        // visual layout (each column = one week-ish slice).
        return HStack(spacing: 4) {
            ForEach(0..<columns, id: \.self) { col in
                VStack(spacing: 4) {
                    ForEach(0..<rows, id: \.self) { row in
                        let offset = (columns - 1 - col) * rows + (rows - 1 - row)
                        let date = Calendar.current.date(byAdding: .day, value: -offset, to: today)!
                        cell(for: map[date])
                    }
                }
            }
        }
    }

    private func cell(for value: Double?) -> some View {
        let color: Color
        switch value {
        case 1.0?: color = .green
        case 0.0?: color = .orange
        default: color = Color.gray.opacity(0.15)
        }
        return RoundedRectangle(cornerRadius: 4)
            .fill(color)
            .aspectRatio(1, contentMode: .fit)
    }

    private var legend: some View {
        HStack(spacing: 12) {
            legendItem(color: .green, label: "Done")
            legendItem(color: .orange, label: "Skipped")
            legendItem(color: Color.gray.opacity(0.15), label: "No data")
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    private func legendItem(color: Color, label: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 3)
                .fill(color)
                .frame(width: 12, height: 12)
            Text(label)
        }
    }

    /// Build a date → value lookup so cell rendering is O(1) per day.
    private func checkInMap() -> [Date: Double] {
        guard let habit = habits.first else { return [:] }
        return Dictionary(uniqueKeysWithValues: habit.checkIns.map { ($0.date, $0.value) })
    }
}
