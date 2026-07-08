import createOpenApiClient from "openapi-fetch";
import type { paths } from "./schema";

export type { paths } from "./schema";

export interface HubClientOptions {
  /** Base URL da API v1, ex.: http://localhost:8000/api/v1 */
  baseUrl: string;
  /** Retorna o access token atual (JWT) ou null. Injeta como Bearer. */
  getToken?: () => string | null | undefined;
}

/**
 * Cria um client tipado da API v1 do Hub Capture.
 * Os tipos vêm do OpenAPI da própria API (packages/api-client/openapi.json).
 */
export function createHubClient({ baseUrl, getToken }: HubClientOptions) {
  const client = createOpenApiClient<paths>({ baseUrl });

  if (getToken) {
    client.use({
      onRequest({ request }) {
        const token = getToken();
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
