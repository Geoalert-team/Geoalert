import client from './axiosClient';

// Tutorial videos (backend apps/tutorials): public to read; DRRMO officers and
// admins add, edit and delete videos and categories, on the What To Do page.

// A video to save: { category, title, description, sourceType, youtubeUrl, file }.
// Only the fields given are sent, so an edit can change just the title.
function form({ category, title, description, sourceType, youtubeUrl, file }) {
  const data = new FormData();
  if (category !== undefined) data.append('category', category);
  if (title !== undefined) data.append('title', title);
  if (description !== undefined) data.append('description', description);
  if (sourceType !== undefined) data.append('source_type', sourceType);
  if (youtubeUrl !== undefined) data.append('youtube_url', youtubeUrl);
  if (file) data.append('file', file, file.name);
  return data;
}

// multipart, not the client's JSON default, or the file is lost (see reportApi.create).
// onProgress(percent) follows the upload, 0 to 100.
const upload = (onProgress) => ({
  headers: { 'Content-Type': 'multipart/form-data' },
  onUploadProgress: (e) => {
    if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
  },
});

export const tutorialsApi = {
  list: () => client.get('/api/tutorials/').then((r) => r.data),
  create: (video, onProgress) => client.post('/api/tutorials/', form(video), upload(onProgress)).then((r) => r.data),
  update: (id, video, onProgress) =>
    client.patch(`/api/tutorials/${id}/`, form(video), upload(onProgress)).then((r) => r.data),
  remove: (id) => client.delete(`/api/tutorials/${id}/`).then((r) => r.data),

  categories: () => client.get('/api/tutorials/categories/').then((r) => r.data),
  // { name, description }; a description is optional
  createCategory: (fields) => client.post('/api/tutorials/categories/', fields).then((r) => r.data),
  updateCategory: (id, fields) => client.patch(`/api/tutorials/categories/${id}/`, fields).then((r) => r.data),
  // Deletes the category's videos too
  removeCategory: (id) => client.delete(`/api/tutorials/categories/${id}/`).then((r) => r.data),

  // { youtube_id, status: 'ok' | 'not_found' | 'unchecked', title, duplicate }
  checkYouTube: (url) => client.get('/api/tutorials/youtube-check/', { params: { url } }).then((r) => r.data),
};
