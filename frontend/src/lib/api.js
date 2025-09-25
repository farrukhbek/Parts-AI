// frontend/src/lib/api.js
import axios from "axios";

// Proxy base (handled by Netlify _redirects)
export const http = axios.create({
  baseURL: "/api/",           // relative; Netlify proxies to Render
  withCredentials: false,
  timeout: 60000,
});

// Helpers
export const health = () => http.get("health").then(r => r.data);

export const searchImages = (payload) =>
  http.post("search-images", payload).then(r => r.data);

export const reprocessImages = (payload) =>
  http.post("reprocess-images", payload).then(r => r.data);

export const downloadImages = (payload) =>
  http.post("download-images", payload).then(r => r.data);

export const parseCsv = (formData) =>
  http.post("parse-csv", formData, {
    headers: { "content-type": "multipart/form-data" },
  }).then(r => r.data);

export const getDownloadStatus = (id) =>
  http.get(`download-status/${id}`).then(r => r.data);

export const getDownloadZip = (id) =>
  http.get(`download-zip/${id}`, { responseType: "blob" }).then(r => r.data);

export const cleanupTask = (taskId) =>
  http.delete(`cleanup/${taskId}`).then(r => r.data);
