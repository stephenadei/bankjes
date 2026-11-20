import Foundation

/// The one seam to the network, so the checks can run every request through a fake.
public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionTransport: HTTPTransport {
    let session: URLSession
    public init(session: URLSession = .shared) { self.session = session }
    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, resp) = try await session.data(for: request)
        guard let http = resp as? HTTPURLResponse else { throw APIError.transport("no HTTP response") }
        return (data, http)
    }

    /// No cookies (the app authenticates by Bearer in I5), gzip by default, a launch-friendly timeout.
    public static func makeDefault() -> URLSessionTransport {
        let cfg = URLSessionConfiguration.default
        cfg.httpShouldSetCookies = false
        cfg.httpCookieAcceptPolicy = .never
        cfg.timeoutIntervalForRequest = 20
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSessionTransport(session: URLSession(configuration: cfg))
    }
}

public enum APIError: Error, Equatable, Sendable {
    case http(status: Int, detail: String?)
    case decoding(String)
    case transport(String)
}

public struct APIClient: Sendable {
    public let environment: AppEnvironment
    let transport: HTTPTransport

    public init(environment: AppEnvironment, transport: HTTPTransport = URLSessionTransport.makeDefault()) {
        self.environment = environment; self.transport = transport
    }

    public func itemsRequest() -> URLRequest {
        var comps = URLComponents(url: environment.apiBase.appending(path: "api/items"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "dataset", value: "bench")]
        var req = URLRequest(url: comps.url!)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        return req
    }

    /// `GET /api/items?dataset=bench`. Returns the decoded benches plus the raw body (for the disk cache).
    public func items() async throws -> (benches: [Bench], raw: Data) {
        let data = try await get(itemsRequest())
        do {
            return (try ItemsResponse.decode(data).items, data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    func get(_ req: URLRequest) async throws -> Data {
        let data: Data, resp: HTTPURLResponse
        do { (data, resp) = try await transport.send(req) } catch let e as APIError { throw e } catch {
            throw APIError.transport(error.localizedDescription)
        }
        guard (200..<300).contains(resp.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError.http(status: resp.statusCode, detail: detail)
        }
        return data
    }
}
