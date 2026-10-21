// Guidance articles store their steps as the lines of `body`, one numbered
// step per line. Shared by the What to do page, its editor and the map panel.

/** 'Step one\n\n  Step two ' -> ['Step one', 'Step two'] */
export const stepsFrom = (body = '') => body.split('\n').map((s) => s.trim()).filter(Boolean);

/** What to tell an officer when saving or removing guidance fails. */
export function guidanceError(err) {
  // axiosClient puts the status on the error itself; there is no
  // err.response by the time it reaches here.
  const status = err?.status ?? err?.response?.status;
  if (status === 401 || status === 403) {
    return 'Only DRRMO Officers and Admins can edit guidance. Try logging in again.';
  }
  return err?.message || 'Something went wrong. Please try again.';
}
