import client from './axiosClient';

// The newsfeed (backend apps/news): announcements and a post for each hazard
// alert that went out, newest first. Public to read; DRRMO, admins and BFP post.
function form({ title, body, photo, removePhoto }) {
  const data = new FormData();
  if (title !== undefined) data.append('title', title);
  if (body !== undefined) data.append('body', body);
  if (photo) data.append('photo', photo, photo.name);
  if (removePhoto) data.append('remove_photo', 'true');
  return data;
}

// multipart, not the client's JSON default, or the photo is lost (see reportApi.create)
const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } };

export const newsApi = {
  // One page, { results, next_before }; pass next_before as before for the next
  feed: ({ before, limit } = {}) =>
    client.get('/api/news/', { params: { ...(before ? { before } : {}), ...(limit ? { limit } : {}) } })
      .then((r) => r.data),
  create: (post) => client.post('/api/news/', form(post), MULTIPART).then((r) => r.data),
  update: (id, post) => client.patch(`/api/news/${id}/`, form(post), MULTIPART).then((r) => r.data),
  remove: (id) => client.delete(`/api/news/${id}/`).then((r) => r.data),
};
