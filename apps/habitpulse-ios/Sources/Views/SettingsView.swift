import SwiftData
import SwiftUI

/// Settings — habit name + API base URL.
///
/// Two fields, both saved on submit. The API URL change takes effect on the
/// next forecast call (no app relaunch required) because ``AppState.api``
/// reads the AppStorage value lazily.
struct SettingsView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.modelContext) private var context
    @Query(sort: \Habit.createdAt) private var habits: [Habit]

    @State private var habitName: String = ""
    @State private var apiBaseURL: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Habit") {
                    TextField("Name", text: $habitName)
                        .onSubmit(saveHabit)
                }
                Section("Backend") {
                    TextField("API base URL", text: $apiBaseURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .onSubmit(saveURL)
                }
                Section {
                    Button("Save", action: saveAll)
                }
            }
            .navigationTitle("Settings")
            .onAppear(perform: load)
        }
    }

    private func load() {
        habitName = habits.first?.name ?? ""
        apiBaseURL = appState.apiBaseURL
    }

    private func saveHabit() {
        guard let habit = habits.first else { return }
        habit.name = habitName.trimmingCharacters(in: .whitespaces).isEmpty
            ? "My Habit" : habitName
        try? context.save()
    }

    private func saveURL() {
        appState.apiBaseURL = apiBaseURL
    }

    private func saveAll() {
        saveHabit()
        saveURL()
    }
}
