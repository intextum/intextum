import { apiUrl, httpClient } from "./client.ts";

export interface GeneralSettings {
  public_base_url: string | null;
  // Read-only default from server config (PUBLIC_BASE_URL / config.yaml).
  config_public_base_url: string | null;
}

export const generalSettingsApi = {
  get: async (): Promise<GeneralSettings> => {
    const { json } = await httpClient(`${apiUrl}/general-settings`);
    return json;
  },

  update: async (data: { public_base_url: string | null }): Promise<GeneralSettings> => {
    const { json } = await httpClient(`${apiUrl}/general-settings`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
    return json;
  },
};
