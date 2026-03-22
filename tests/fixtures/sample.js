/** Analytics service — tracks task events and user actions. */

export class AnalyticsService {
  constructor(config) {
    this.config = config;
  }
}

export function trackEvent(name, data) {
  return null;
}

export const formatPayload = (event) => {
  return JSON.stringify(event);
};

const BASE_URL = 'https://api.example.com';

export const MAX_BATCH_SIZE = 100;
