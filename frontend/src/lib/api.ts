// frontend/src/lib/api.ts
import axios from "axios";

/**
 * BACKEND comes from Netlify/Vite env:
 *   VITE_BACKEND_URL = https://<your-render-app>.onrender.com
 * No trailing slash, we'll add paths below.
 */
const BACKEND = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

// FastAPI router is prefixed with /api
export const API_BASE = `${BACKEND}/api`;

// Axios instance used everywhere in the app
export const http = axios.create({
  baseURL: `${API_BASE}/`, // NOTE: backticks! single trailing slash here only
  withCredentials: false,
  timeout: 60000,
});

// ---- Convenience helpers mapping to your FastAPI routes ----

export const health = () =>
  http.get("health").then((r) => r.data);

export const searchImages = (payload: {
  part_numbers: string[];
  manufacturer?: string;
  limit?: number;           // best images per part
  sources?: string[];       // e.g., ["google"]
}) =>
  http.post("search-images", payload).then((r) => r.data);

export const reprocessImages = (payload: {
  part_numbers: string[];
  limit?: number;
  sources?: string[];
}) =>
  http.post("reprocess-images", payload).then((r) => r.data);

export const downloadImages = (payload: {
  part_numbers: string[];
  limit?: number;
  sources?: string[];
}) =>
  http.post("download-images", payload).then((r) => r.data);

export const parseCsv = (formData: FormData) =>
  http
    .post("parse-csv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);

export const getDownloadStatus = (downloadId: string) =>
  http.get(`download-status/${downloadId}`).then((r) => r.data);

export const getDownloadZip = (downloadId: string) =>
  http.get(`download-zip/${downloadId}`, { responseType: "blob" });

export const cleanupTask = (taskId: string) =>
  http.delete(`cleanup/${taskId}`).then((r) => r.data);

// Optional: warn in console if the env var was missing at build time
if (!BACKEND) {
  // eslint-disable-next-line no-console
  console.warn(
    "[api] VITE_BACKEND_URL is empty. " +
      "If you see requests to /undefined/api/..., clear cache & redeploy on Netlify " +
      "after setting VITE_BACKEND_URL."
  );
}
