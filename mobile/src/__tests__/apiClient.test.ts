import { ApiClient, ApiError, Fetcher } from "../services/apiClient";

function response(body: unknown, init: ResponseInit = {}): Response {
  return {
    ok: init.status ? init.status >= 200 && init.status < 300 : true,
    status: init.status ?? 200,
    statusText: init.statusText ?? "OK",
    headers: new Headers(init.headers),
    json: () => Promise.resolve(body)
  } as Response;
}

describe("ApiClient", () => {
  it("attaches the bearer token and parses JSON", async () => {
    const fetcher = jest.fn(() => Promise.resolve(response({ ok: true }))) as unknown as jest.MockedFunction<Fetcher>;
    const client = new ApiClient({
      baseUrl: "http://api.test/api/v1",
      tokenProvider: () => Promise.resolve("token-123"),
      fetcher
    });

    await expect(client.request<{ ok: boolean }>("/projects")).resolves.toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledWith(
      "http://api.test/api/v1/projects",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer token-123" })
      })
    );
  });

  it("calls unauthorized handler on 401", async () => {
    const onUnauthorized = jest.fn();
    const fetcher = jest.fn(() => Promise.resolve(response({ detail: "expired" }, { status: 401, statusText: "Unauthorized" }))) as unknown as jest.MockedFunction<Fetcher>;
    const client = new ApiClient({
      baseUrl: "http://api.test/api/v1",
      tokenProvider: () => Promise.resolve("expired"),
      onUnauthorized,
      fetcher
    });

    await expect(client.request("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
