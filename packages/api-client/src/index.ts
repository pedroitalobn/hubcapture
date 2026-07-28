import createOpenApiClient from "openapi-fetch";
import type { paths } from "./schema";

export type { paths } from "./schema";

export interface HubClientOptions {
  /** Base URL da API v1, ex.: http://localhost:8000/api/v1 */
  baseUrl: string;
  /**
   * Retorna o access token atual (JWT) ou null. Injeta como Bearer.
   * Pode ser assíncrono — permite renovar (refresh) um token expirado
   * antes de cada request, em vez de deixar a chamada morrer em 401.
   */
  getToken?: () =>
    | string
    | null
    | undefined
    | Promise<string | null | undefined>;
}

/**
 * Cria um client tipado da API v1 do Hub Capture.
 * Os tipos vêm do OpenAPI da própria API (packages/api-client/openapi.json).
 */
export function createHubClient({ baseUrl, getToken }: HubClientOptions) {
  const client = createOpenApiClient<paths>({ baseUrl });

  if (getToken) {
    client.use({
      async onRequest({ request }) {
        const token = await getToken();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
        return request;
      },
    });
  }

  return client;
}

export default createHubClient;
