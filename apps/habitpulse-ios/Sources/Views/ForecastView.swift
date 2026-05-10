import Charts
import SwiftData
import SwiftUI

/// Forecast screen — calls the API, renders a P10/P50/P75 cone and three
/// analogue cards.
///
/// Triggers a fetch every time the view appears so the user always sees a
/// fresh forecast tied to the latest check-in. The series we send is the
/// dense day-by-day value list from ``createdAt`` through today, with
/// missing days filled as 0.0 (the engine needs an evenly-spaced series).
struct ForecastView: View {
    @EnvironmentObject private var appState: AppState
    @Query(sort: \Habit.createdAt) private var habits: [Habit]

    @State private var forecast: HabitForecast?
    @State private var error: String?
    @State private var loading = false

    private var habit: Habit? { habits.first }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if let forecast {
                        riskCard(forecast: forecast)
                        coneChart(forecast: forecast)
                        analogueList(forecast: forecast)
                    } else if loading {
                        ProgressView("Searching for analogues…")
                            .frame(maxWidth: .infinity, minHeight: 200)
                    } else if let error {
                        errorCard(message: error)
                    } else {
                        Text("Tap refresh to compute a forecast.")
                            .foregroundStyle(.secondary)
                            .padding()
                    }
                }
                .padding()
            }
            .navigationTitle("Forecast")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(loading)
                }
            }
            .task { await refresh() }
        }
    }

    // MARK: - Cards

    private func riskCard(forecast: HabitForecast) -> some View {
        let pct = Int(forecast.relapseRisk * 100)
        let color: Color = forecast.relapseRisk > 0.5 ? .red : (forecast.relapseRisk > 0.25 ? .orange : .green)
        return VStack(alignment: .leading, spacing: 6) {
            Text("Relapse risk")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("\(pct)%")
                .font(.system(size: 56, weight: .bold, design: .rounded))
                .foregroundStyle(color)
            Text("Based on the next 7 days projected from \(forecast.analogues.count) past analogues.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func coneChart(forecast: HabitForecast) -> some View {
        let days = forecast.cone.p50.indices.map { $0 + 1 }
        return VStack(alignment: .leading, spacing: 8) {
            Text("Forecast cone")
                .font(.headline)
            Chart {
                ForEach(days, id: \.self) { i in
                    let idx = i - 1
                    AreaMark(
                        x: .value("Day", i),
                        yStart: .value("p10", forecast.cone.p10[idx]),
                        yEnd: .value("p75", forecast.cone.p75[idx])
                    )
                    .foregroundStyle(Color.blue.opacity(0.2))

                    LineMark(
                        x: .value("Day", i),
                        y: .value("p50", forecast.cone.p50[idx])
                    )
                    .foregroundStyle(Color.blue)
                    .interpolationMethod(.monotone)
                }
            }
            .chartYScale(domain: 0...1)
            .frame(height: 220)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func analogueList(forecast: HabitForecast) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Closest past analogues")
                .font(.headline)
            ForEach(forecast.analogues) { analogue in
                analogueRow(analogue)
            }
        }
    }

    private func analogueRow(_ a: HabitForecast.Analogue) -> some View {
        let daysAgo = (habit.flatMap { habitDayCount(for: $0) } ?? 0) - a.endIdx
        return HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("≈\(daysAgo) days ago")
                    .font(.subheadline.weight(.semibold))
                Text("Score \(Int(a.score))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            sparkline(values: a.forward)
                .frame(width: 80, height: 30)
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func sparkline(values: [Double]) -> some View {
        Chart {
            ForEach(Array(values.enumerated()), id: \.offset) { idx, v in
                LineMark(
                    x: .value("i", idx),
                    y: .value("v", v)
                )
                .foregroundStyle(Color.blue)
            }
        }
        .chartYScale(domain: 0...1)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
    }

    private func errorCard(message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Couldn't load forecast")
                .font(.headline)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color.red.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Data

    /// Build a dense day-by-day series of habit values, filling unrecorded
    /// days with 0.0. The engine requires uniform spacing, so we cannot just
    /// hand it the sparse list of CheckIn rows.
    private func denseSeries(for habit: Habit) -> [Double] {
        let cal = Calendar.current
        let start = cal.startOfDay(for: habit.createdAt)
        let today = cal.startOfDay(for: .now)
        let days = max(0, cal.dateComponents([.day], from: start, to: today).day ?? 0) + 1
        let map = Dictionary(uniqueKeysWithValues: habit.checkIns.map { ($0.date, $0.value) })
        return (0..<days).map { offset in
            let d = cal.date(byAdding: .day, value: offset, to: start)!
            return map[d] ?? 0.0
        }
    }

    private func habitDayCount(for habit: Habit) -> Int { denseSeries(for: habit).count }

    private func refresh() async {
        guard let habit else { return }
        let series = denseSeries(for: habit)
        guard series.count >= 21 else {
            await MainActor.run {
                error = "Need at least 21 days of history. You have \(series.count)."
            }
            return
        }
        await MainActor.run {
            loading = true
            error = nil
        }
        do {
            let result = try await appState.api.forecast(series: series)
            await MainActor.run {
                forecast = result
                loading = false
            }
        } catch {
            await MainActor.run {
                self.error = error.localizedDescription
                loading = false
            }
        }
    }
}
