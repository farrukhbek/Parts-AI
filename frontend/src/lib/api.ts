// frontend/src/lib/api.ts
import axios from "axios";

// Proxy base (handled by Netlify _redirects)
export const http = axios.create({
  baseURL: "/api/",            // <-- relative; Netlify proxies to Render
  withCredentials: false,
  timeout: 60000,
});

// Helpers (use as needed)
export const health = () => http.get("health").then(r => r.data);
export const searchImages = (payload: {
  part_numbers: string[];
  manufacturer?: string;
  limit?: number;
  sources?: string[];
}) => http.post("search-images", payload).then(r => r.data);

export const reprocessImages = (payload: {
  part_numbers: string[];
  limit?: number;
  sources?: string[];
}) => http.post("reprocess-images", payload).then(r => r.data);

export const downloadImages = (payload: {
  part_numbers: string[];
  limit?: number;
  sources?: string[];
}) => http.post("download-images", payload).then(r => r.data);

export const parseCsv = (formData: FormData) =>
  http.post("parse-csv", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data);

export const getDownloadStatus = (id: string) =>
  http.get(`download-status/${id}`).then(r => r.data);

export const getDownloadZip = (id: string) =>
  http.get(`download-zip/${id}`, { responseType: "blob" });

export const cleanupTask = (taskId: string) =>
  http.delete(`cleanup/${taskId}`).then(r => r.data);
