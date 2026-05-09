import Foundation

/// Thin async URLSession client for the Habitpulse forecast endpoint.
///
/// Single responsibility — POST a habit series, decode the response. No
/// caching, no retry, no auth (the endpoint is public for v0). Errors bubble
/// up as ``HabitAPIError`` so the UI can show a meaningful message instead of
/// the raw URLError code.
struct HabitAPI {
    let baseURL: URL
    var session: URLSession = .shared

    func forecast(
        series: [Double],
        window: Int = 7,
        forwardBars: Int = 7,
        topK: Int = 3
    ) async throws -> HabitForecast {
        var request = URLRequest(url: baseURL.appendingPathComponent("habit/forecast"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // 30s is plenty — the engine resolves a 60-90 day series in well under
        // a second, and a long timeout would just mask real connectivity bugs.
        request.timeoutInterval = 30

        let body: [String: Any] = [
            "series": series,
            "window": window,
            "forward_bars": forwardBars,
            "top_k": topK,
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw HabitAPIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let detail = String(data: data, encoding: .utf8) ?? ""
            throw HabitAPIError.server(status: http.statusCode, body: detail)
        }
        return try JSONDecoder().decode(HabitForecast.self, from: data)
    }
}

enum HabitAPIError: LocalizedError {
    case invalidResponse
    case server(status: Int, body: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The server returned a malformed response."
        case let .server(status, body):
            return "Server returned \(status): \(body)"
        }
    }
}
