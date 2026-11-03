/**
 * One readable sentence for a failed API call.
 *
 * Before this, anything the server didn't phrase as {error} or {detail}
 * reached the screen as axios's own text, "Request failed with status code
 * 500", which tells an officer nothing about whether to retry, wait, or
 * call someone.
 */

const BY_STATUS = {
  400: 'Some of the details were not accepted. Check the form and try again.',
  401: 'Your session has ended. Sign in again to continue.',
  403: "Your account isn't allowed to do this.",
  404: "That item doesn't exist any more. Refresh the page.",
  409: 'Someone else changed this at the same time. Refresh the page and try again.',
  413: 'That file is too large to upload.',
  429: 'Too many attempts. Wait a minute and try again.',
  502: "The GeoAlert Talisay server isn't responding. Try again in a moment.",
  503: "The GeoAlert Talisay server is busy or can't reach its database. Try again in a moment.",
  504: 'The GeoAlert Talisay server took too long to answer. Try again in a moment.',
};

const OFFLINE =
  "Can't reach the GeoAlert Talisay server. Check your internet connection, or that the backend is running.";

/** The first message out of a DRF validation body like {"geometry": ["..."]}. */
function firstFieldError(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  for (const value of Object.values(data)) {
    if (typeof value === 'string' && value.trim()) return value;
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  }
  return null;
}

/**
 * @param {import('axios').AxiosError} err
 * @returns {string}
 */
export function errorMessage(err) {
  const response = err?.response;
  if (!response) return OFFLINE; // network down, server stopped, CORS

  const data = response.data;
  // An HTML error page is not a message
  if (data && typeof data === 'object') {
    if (typeof data.error === 'string' && data.error) return data.error;
    if (typeof data.detail === 'string' && data.detail) return data.detail;
    const field = firstFieldError(data);
    if (field) return field;
  }

  const status = response.status;
  if (BY_STATUS[status]) return BY_STATUS[status];
  if (status >= 500) {
    return 'Something went wrong on the server. Try again, and tell the system admin if it keeps happening.';
  }
  return 'The request was not accepted. Try again.';
}

export default errorMessage;
