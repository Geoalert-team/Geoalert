import { actionMeta } from './adminShared';

test.each([
  ['ADD_VIDEO', 'Added a video'], ['EDIT_VIDEO', 'Edited a video'], ['DELETE_VIDEO', 'Deleted a video'],
  ['ADD_VIDEO_CATEGORY', 'Added a video category'], ['RENAME_VIDEO_CATEGORY', 'Renamed a video category'],
  ['DELETE_VIDEO_CATEGORY', 'Deleted a video category'],
])('%s reads "%s"', (action, label) => expect(actionMeta(action).label).toBe(label));
