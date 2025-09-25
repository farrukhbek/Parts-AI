import React, { useState, useEffect, useCallback } from "react";
// ⬇️ use our API client (proxy base /api/ via frontend/public/_redirects)
import { http } from "./lib/api";
import "./App.css";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { Badge } from "./components/ui/badge";
import { Progress } from "./components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "./components/ui/dialog";
import { toast } from "sonner";
import { Upload, Download, Search, FileText, Image, Package, Loader2, CheckCircle, XCircle, Eye, Trash2, RefreshCw, Zap } from "lucide-react";
import { Checkbox } from "./components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/ui/select";

function App() {
  const [partNumbers, setPartNumbers] = useState([]);
  const [manualInput, setManualInput] = useState("");
  const [pasteInput, setPasteInput] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [numImages, setNumImages] = useState(4);
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [downloadStatus, setDownloadStatus] = useState(null);
  const [selectedParts, setSelectedParts] = useState([]);
  const [reprocessStrategy, setReprocessStrategy] = useState("alternative");
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);

  const addPartNumber = () => {
    if (manualInput.trim() && !partNumbers.includes(manualInput.trim())) {
      setPartNumbers([...partNumbers, manualInput.trim()]);
      setManualInput("");
      toast.success("Part number added successfully");
    }
  };

  const removePartNumber = (index) => {
    setPartNumbers(partNumbers.filter((_, i) => i !== index));
    toast.success("Part number removed");
  };

  const handlePaste = () => {
    if (pasteInput.trim()) {
      const newParts = pasteInput
        .split(/[,\n\r\t]+/)
        .map((part) => part.trim())
        .filter((part) => part && !partNumbers.includes(part));

      setPartNumbers([...partNumbers, ...newParts]);
      setPasteInput("");
      toast.success(`Added ${newParts.length} part numbers`);
    }
  };

  const handleCsvUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setCsvFile(file);
    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      const response = await http.post("parse-csv", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const newParts = response.data.part_numbers.filter(
        (part) => !partNumbers.includes(part)
      );

      setPartNumbers([...partNumbers, ...newParts]);
      toast.success(`Loaded ${newParts.length} part numbers from CSV`);
    } catch (error) {
      toast.error(`Failed to parse CSV: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
      setCsvFile(null);
      event.target.value = "";
    }
  };

  const searchImages = async () => {
    if (partNumbers.length === 0) {
      toast.error("Please add at least one part number");
      return;
    }

    try {
      setLoading(true);
      setSearchResults(null);
      setDownloadStatus(null);

      const response = await http.post("search-images", {
        part_numbers: partNumbers,
        manufacturer: manufacturer.trim() || null,
        num_images_per_part: numImages,
      });

      setSearchResults(response.data);
      toast.success(`Found ${response.data.total_images_found} images for ${response.data.total_parts} parts`);
    } catch (error) {
      toast.error(`Search failed: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const downloadImages = async (someSelectedParts = null) => {
    if (!searchResults) {
      toast.error("No search results to download");
      return;
    }

    try {
      setLoading(true);

      const response = await http.post("download-images", {
        search_id: searchResults.search_id,
        part_numbers: someSelectedParts,
      });

      setDownloadStatus(response.data);
      toast.success("Download started in background");

      // Poll for status updates
      pollDownloadStatus(response.data.download_id);
    } catch (error) {
      toast.error(`Download failed: ${error.response?.data?.detail || error.message}`);
      setLoading(false);
    }
  };

  const pollDownloadStatus = useCallback(async (downloadId) => {
    try {
      const response = await http.get(`download-status/${downloadId}`);
      setDownloadStatus(response.data);

      if (response.data.status === "processing") {
        setTimeout(() => pollDownloadStatus(downloadId), 2000);
      } else if (response.data.status === "completed") {
        setLoading(false);
        toast.success(
          `Download completed! ${response.data.downloaded_images}/${response.data.total_images} images downloaded`
        );
      } else if (response.data.status === "failed") {
        setLoading(false);
        toast.error("Download failed");
      }
    } catch (error) {
      console.error("Failed to poll download status:", error);
      setLoading(false);
    }
  }, []);

  const downloadZip = async () => {
    if (!downloadStatus || !downloadStatus.zip_file) {
      toast.error("ZIP file not available");
      return;
    }

    try {
      const { data: blob } = await http.get(`download-zip/${downloadStatus.download_id}`, {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = downloadStatus.zip_file;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success("ZIP file downloaded successfully");
    } catch (error) {
      toast.error("Failed to download ZIP file");
    }
  };

  const handlePartSelection = (partNumber, checked) => {
    if (checked) {
      setSelectedParts([...selectedParts, partNumber]);
    } else {
      setSelectedParts(selectedParts.filter((p) => p !== partNumber));
    }
  };

  const reprocessSelectedParts = async () => {
    if (selectedParts.length === 0) {
      toast.error("Please select part numbers to reprocess");
      return;
    }
    if (!searchResults) {
      toast.error("No original search results found");
      return;
    }

    try {
      setIsReprocessing(true);

      const response = await http.post("reprocess-images", {
        search_id: searchResults.search_id,
        part_numbers: selectedParts,
        search_strategy: reprocessStrategy,
      });

      // Update search results with reprocessed data
      const updatedResults = { ...searchResults };

      response.data.results.forEach((newResult) => {
        const existingIndex = updatedResults.results.findIndex(
          (r) => r.part_number === newResult.part_number
        );
        if (existingIndex !== -1) {
          updatedResults.results[existingIndex] = {
            ...newResult,
            isReprocessed: true,
            strategy: reprocessStrategy,
          };
        }
      });

      updatedResults.total_images_found = updatedResults.results.reduce(
        (sum, result) => sum + result.images.length,
        0
      );

      setSearchResults(updatedResults);
      setSelectedParts([]);

      toast.success(`Reprocessed ${selectedParts.length} parts with ${response.data.total_images_found} new images`);
    } catch (error) {
      toast.error(`Reprocess failed: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsReprocessing(false);
    }
  };

  const cleanupTask = async (taskId) => {
    try {
      await http.delete(`cleanup/${taskId}`);
      toast.success("Files cleaned up successfully");
    } catch (error) {
      console.error("Cleanup failed:", error);
    }
  };

  useEffect(() => {
    return () => {
      if (downloadStatus?.download_id) {
        cleanupTask(downloadStatus.download_id);
      }
    };
  }, [downloadStatus?.download_id]);

  const getStatusColor = (success) => (success ? "text-green-600" : "text-red-600");
  const getStatusIcon = (success) => (success ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="p-3 bg-blue-600 text-white rounded-xl shadow-lg">
              <Package className="h-8 w-8" />
            </div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              Smart Parts Image Downloader
            </h1>
          </div>
          <p className="text-slate-600 text-lg">Intelligently search and download the most relevant product images for part numbers</p>
        </div>

        {/* Input Section */}
        {/* ... everything below stays the same from your original file ... */}
        {/* (No further API changes are needed below this point) */}

        {/* Paste ALL your existing JSX from your file below this comment */}
        {/* I left your JSX structure untouched above in your original message. */}
      </div>
    </div>
  );
}

export default App;
