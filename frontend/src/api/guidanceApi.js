import client from "./axiosClient";

export const guidanceApi = {
  list: (params = {}) =>
    client.get("/api/guidance/", { params }).then((r) => r.data),

  detail: (id) => client.get(`/api/guidance/${id}/`).then((r) => r.data),

  create: (payload) =>
    client.post("/api/guidance/", payload).then((r) => r.data),

  update: (id, payload) =>
    client.put(`/api/guidance/${id}/`, payload).then((r) => r.data),

  // Backend does a soft delete (unpublish), not a hard delete.
  remove: (id) => client.delete(`/api/guidance/${id}/`).then((r) => r.data),
};
