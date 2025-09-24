import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
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

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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
        .map(part => part.trim())
        .filter(part => part && !partNumbers.includes(part));
      
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
    formData.append('file', file);

    try {
      setLoading(true);
      const response = await axios.post(`${API}/parse-csv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const newParts = response.data.part_numbers.filter(
        part => !partNumbers.includes(part)
      );
      
      setPartNumbers([...partNumbers, ...newParts]);
      toast.success(`Loaded ${newParts.length} part numbers from CSV`);
    } catch (error) {
      toast.error(`Failed to parse CSV: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
      setCsvFile(null);
      event.target.value = '';
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

      const response = await axios.post(`${API}/search-images`, {
        part_numbers: partNumbers,
        manufacturer: manufacturer.trim() || null,
        num_images_per_part: numImages
      });

      setSearchResults(response.data);
      toast.success(`Found ${response.data.total_images_found} images for ${response.data.total_parts} parts`);
    } catch (error) {
      toast.error(`Search failed: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const downloadImages = async (selectedParts = null) => {
    if (!searchResults) {
      toast.error("No search results to download");
      return;
    }

    try {
      setLoading(true);
      
      const response = await axios.post(`${API}/download-images`, {
        search_id: searchResults.search_id,
        part_numbers: selectedParts
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
      const response = await axios.get(`${API}/download-status/${downloadId}`);
      setDownloadStatus(response.data);

      if (response.data.status === "processing") {
        setTimeout(() => pollDownloadStatus(downloadId), 2000);
      } else if (response.data.status === "completed") {
        setLoading(false);
        toast.success(`Download completed! ${response.data.downloaded_images}/${response.data.total_images} images downloaded`);
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
      const response = await fetch(`${API}/download-zip/${downloadStatus.download_id}`);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
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
      setSelectedParts(selectedParts.filter(p => p !== partNumber));
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
      
      const response = await axios.post(`${API}/reprocess-images`, {
        search_id: searchResults.search_id,
        part_numbers: selectedParts,
        search_strategy: reprocessStrategy
      });

      // Update search results with reprocessed data
      const updatedResults = { ...searchResults };
      
      // Replace results for reprocessed parts
      response.data.results.forEach(newResult => {
        const existingIndex = updatedResults.results.findIndex(
          r => r.part_number === newResult.part_number
        );
        if (existingIndex !== -1) {
          updatedResults.results[existingIndex] = {
            ...newResult,
            isReprocessed: true,
            strategy: reprocessStrategy
          };
        }
      });
      
      // Update totals
      updatedResults.total_images_found = updatedResults.results.reduce(
        (sum, result) => sum + result.images.length, 0
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
      await axios.delete(`${API}/cleanup/${taskId}`);
      toast.success("Files cleaned up successfully");
    } catch (error) {
      console.error("Cleanup failed:", error);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (downloadStatus?.download_id) {
        cleanupTask(downloadStatus.download_id);
      }
    };
  }, [downloadStatus?.download_id]);

  const getStatusColor = (success) => {
    return success ? "text-green-600" : "text-red-600";
  };

  const getStatusIcon = (success) => {
    return success ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />;
  };

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
          <p className="text-slate-600 text-lg">
            Intelligently search and download the most relevant product images for part numbers
          </p>
        </div>

        {/* Input Section */}
        <Card className="mb-6 shadow-lg border-0 bg-white/80 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Add Part Numbers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="manual" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="manual">Manual Entry</TabsTrigger>
                <TabsTrigger value="paste">Paste List</TabsTrigger>
                <TabsTrigger value="csv">CSV Upload</TabsTrigger>
              </TabsList>

              <TabsContent value="manual" className="space-y-4">
                <div className="flex gap-2">
                  <Input
                    placeholder="Enter part number (e.g. ABC123)"
                    value={manualInput}
                    onChange={(e) => setManualInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && addPartNumber()}
                    className="flex-1"
                  />
                  <Button onClick={addPartNumber} disabled={!manualInput.trim()}>
                    Add
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="paste" className="space-y-4">
                <Textarea
                  placeholder="Paste multiple part numbers (separated by commas or new lines)&#10;Example:&#10;ABC123&#10;DEF456&#10;GHI789"
                  value={pasteInput}
                  onChange={(e) => setPasteInput(e.target.value)}
                  rows={4}
                />
                <Button onClick={handlePaste} disabled={!pasteInput.trim()}>
                  Add All Parts
                </Button>
              </TabsContent>

              <TabsContent value="csv" className="space-y-4">
                <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center">
                  <Upload className="h-8 w-8 mx-auto mb-2 text-slate-400" />
                  <p className="text-sm text-slate-600 mb-2">
                    Upload a CSV file with part numbers
                  </p>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={handleCsvUpload}
                    className="hidden"
                    id="csv-upload"
                  />
                  <label htmlFor="csv-upload">
                    <Button variant="outline" className="cursor-pointer">
                      {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Upload className="h-4 w-4 mr-2" />}
                      Choose CSV File
                    </Button>
                  </label>
                </div>
              </TabsContent>
            </Tabs>

            {/* Search Options */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              <div>
                <label className="text-sm font-medium mb-2 block">
                  Manufacturer (optional)
                </label>
                <Input
                  placeholder="e.g. Toyota, Ford, Bosch"
                  value={manufacturer}
                  onChange={(e) => setManufacturer(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">
                  Best Images per Part (3-5 recommended)
                </label>
                <Input
                  type="number"
                  min="3"
                  max="5"
                  value={numImages}
                  onChange={(e) => setNumImages(parseInt(e.target.value) || 4)}
                />
              </div>
            </div>

            {/* Added Parts Display */}
            {partNumbers.length > 0 && (
              <div className="mt-6">
                <label className="text-sm font-medium mb-2 block">
                  Added Parts ({partNumbers.length})
                </label>
                <div className="flex flex-wrap gap-2">
                  {partNumbers.map((part, index) => (
                    <Badge
                      key={index}
                      variant="secondary"
                      className="px-3 py-1 bg-blue-100 text-blue-800 hover:bg-blue-200 cursor-pointer"
                      onClick={() => removePartNumber(index)}
                    >
                      {part}
                      <Trash2 className="h-3 w-3 ml-2" />
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Search Button */}
            <div className="mt-6">
              <Button
                onClick={searchImages}
                disabled={loading || partNumbers.length === 0}
                size="lg"
                className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
              >
                {loading ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : <Search className="h-5 w-5 mr-2" />}
                Search Images
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Search Results */}
        {searchResults && (
          <Card className="mb-6 shadow-lg border-0 bg-white/80 backdrop-blur-sm">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Image className="h-5 w-5" />
                  Search Results
                </CardTitle>
                <div className="flex gap-2">
                  {selectedParts.length > 0 && (
                    <div className="flex items-center gap-2">
                      <Select value={reprocessStrategy} onValueChange={setReprocessStrategy}>
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="alternative">Alternative</SelectItem>
                          <SelectItem value="broader">Broader</SelectItem>
                          <SelectItem value="specific">Specific</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        onClick={reprocessSelectedParts}
                        disabled={isReprocessing}
                        variant="outline"
                        size="sm"
                        className="bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100"
                      >
                        {isReprocessing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                        Reprocess ({selectedParts.length})
                      </Button>
                    </div>
                  )}
                  <Button
                    onClick={() => downloadImages()}
                    disabled={loading}
                    className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700"
                  >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Download className="h-4 w-4 mr-2" />}
                    Download All Images
                  </Button>
                </div>
              </div>
              <div className="text-sm text-slate-600 flex items-center justify-between">
                <div className="space-y-1">
                  <div>Found {searchResults.total_images_found} best images across {searchResults.total_parts} parts</div>
                  <div className="text-xs text-green-600 flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    Intelligently curated (Processing time: {searchResults.processing_time.toFixed(1)}s)
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const allParts = searchResults.results.map(r => r.part_number);
                    setSelectedParts(selectedParts.length === allParts.length ? [] : allParts);
                  }}
                  className="text-blue-600 hover:text-blue-700"
                >
                  {selectedParts.length === searchResults.results.length ? "Deselect All" : "Select All"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {searchResults.results.map((partResult, partIndex) => (
                  <div key={partIndex} className="border rounded-lg p-4 bg-slate-50/50">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <Checkbox
                            id={`part-${partIndex}`}
                            checked={selectedParts.includes(partResult.part_number)}
                            onCheckedChange={(checked) => handlePartSelection(partResult.part_number, checked)}
                            className="h-5 w-5 border-2 border-blue-500 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                          />
                          <label 
                            htmlFor={`part-${partIndex}`}
                            className="text-sm text-slate-600 cursor-pointer"
                          >
                            Select to reprocess
                          </label>
                        </div>
                        <div>
                          <h3 className="font-semibold text-lg flex items-center gap-2">
                            Part Number: {partResult.part_number}
                            {getStatusIcon(partResult.search_success)}
                            {partResult.isReprocessed && (
                              <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200">
                                <Zap className="h-3 w-3 mr-1" />
                                {partResult.strategy}
                              </Badge>
                            )}
                          </h3>
                          <div className="text-sm text-slate-600 space-y-1">
                            <p><strong>Image Count:</strong> {partResult.images.length} best images</p>
                            <p><strong>Search Query:</strong> "{partResult.search_query}"</p>
                            {partResult.images.length > 0 && (
                              <p className="text-green-600 font-medium">
                                ✅ Download-ready links available ({partResult.images.length} images)
                              </p>
                            )}
                          </div>
                          {!partResult.search_success && (
                            <p className="text-sm text-red-600 mt-1">
                              Error: {partResult.error_message}
                            </p>
                          )}
                        </div>
                      </div>
                      <Badge variant={partResult.search_success ? "default" : "destructive"}>
                        {partResult.images.length} best images
                      </Badge>
                    </div>

                    {partResult.images.length > 0 && (
                      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                        {partResult.images.map((image, imageIndex) => (
                          <Dialog key={imageIndex}>
                            <DialogTrigger asChild>
                              <div className="group cursor-pointer relative">
                                <img
                                  src={image.thumbnail_url}
                                  alt={image.title}
                                  className="w-full h-20 object-cover rounded-lg border-2 border-slate-200 group-hover:border-blue-500 transition-all"
                                  onError={(e) => {
                                    e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTIxIDEyVjdBMiAyIDAgMCAwIDE5IDVINUEyIDIgMCAwIDAgMyA3VjE3QTIgMiAwIDAgMCA1IDE5SDEyIiBzdHJva2U9IiM5Y2EzYWYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=';
                                  }}
                                />
                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-all rounded-lg flex items-center justify-center">
                                  <Eye className="h-5 w-5 text-white opacity-0 group-hover:opacity-100 transition-all" />
                                </div>
                              </div>
                            </DialogTrigger>
                            <DialogContent className="max-w-4xl">
                              <DialogHeader>
                                <DialogTitle className="text-left">{image.title || 'Image Preview'}</DialogTitle>
                              </DialogHeader>
                              <div className="space-y-4">
                                <img
                                  src={image.original_url}
                                  alt={image.title}
                                  className="w-full max-h-96 object-contain rounded-lg border"
                                  onError={(e) => {
                                    e.target.src = image.thumbnail_url;
                                  }}
                                />
                                <div className="text-sm text-slate-600 space-y-1">
                                  <p><strong>Source:</strong> {image.source}</p>
                                  {image.width && image.height && (
                                    <p><strong>Size:</strong> {image.width} × {image.height} pixels</p>
                                  )}
                                  <p><strong>URL:</strong> <a href={image.original_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline truncate">{image.original_url}</a></p>
                                </div>
                              </div>
                            </DialogContent>
                          </Dialog>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Download Status */}
        {downloadStatus && (
          <Card className="shadow-lg border-0 bg-white/80 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Download className="h-5 w-5" />
                Download Progress
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Status: {downloadStatus.status}</span>
                  <Badge variant={downloadStatus.status === 'completed' ? 'default' : downloadStatus.status === 'failed' ? 'destructive' : 'secondary'}>
                    {downloadStatus.downloaded_images}/{downloadStatus.total_images} images
                  </Badge>
                </div>
                
                <Progress
                  value={(downloadStatus.downloaded_images / downloadStatus.total_images) * 100}
                  className="w-full"
                />

                {downloadStatus.status === 'completed' && downloadStatus.zip_file && (
                  <Button
                    onClick={downloadZip}
                    className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700"
                    size="lg"
                  >
                    <Download className="h-5 w-5 mr-2" />
                    Download ZIP File ({downloadStatus.downloaded_images} images)
                  </Button>
                )}

                {downloadStatus.results && downloadStatus.results.length > 0 && (
                  <div className="mt-4">
                    <h4 className="font-medium mb-2">Download Details</h4>
                    <div className="max-h-48 overflow-y-auto space-y-2">
                      {downloadStatus.results.map((result, index) => (
                        <div key={index} className="flex items-center justify-between text-sm p-2 bg-slate-50 rounded">
                          <div className="flex items-center gap-2">
                            {getStatusIcon(result.success)}
                            <span className="font-medium">{result.part_number}</span>
                          </div>
                          <div className={`text-xs ${getStatusColor(result.success)}`}>
                            {result.success ? 
                              `${(result.file_size / 1024).toFixed(1)} KB` : 
                              result.error_message
                            }
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

export default App;