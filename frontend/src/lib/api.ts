// frontend/src/lib/api.ts
import axios from "axios";

// Take Netlify env and remove trailing slash
const BACKEND = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

// Your FastAPI router is prefixed with /api
export const API_BASE = `${BACKEND}/api`;

export const http = axios.create({
  baseURL: `${API_BASE}/`, // one trailing slash here only
  withCredentials: false,
});

// Convenience helpers (use any you need)
export const health = () => http.get("health").then(r => r.data);
export const searchImages = (payload: { part_numbers: string[]; limit?: number; sources?: string[] }) =>
  http.post("search-images", payload).then(r => r.data);
export const downloadImages = (payload: any) =>
  http.post("download-images", payload).then(r => r.data);
export const parseCsv = (formData: FormData) =>
  http.post("parse-csv", formData, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data);
export const getDownloadStatus = (id: string) =>
  http.get(`download-status/${id}`).then(r => r.data);
export const getDownloadZip = (id: string) =>
  http.get(`download-zip/${id}`, { responseType: "blob" });
