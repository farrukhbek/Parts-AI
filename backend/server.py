from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pathlib import Path
import os
import uuid
import asyncio
import aiohttp
import aiofiles
import zipfile
import tempfile
import logging
import time
import csv
import io
from datetime import datetime
from serpapi import GoogleSearch
from PIL import Image

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI(title="Parts Image Downloader API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create directories
DOWNLOADS_DIR = Path("/tmp/downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Models
class PartSearchRequest(BaseModel):
    part_numbers: List[str] = Field(..., description="List of part numbers to search")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name for better search")
    num_images_per_part: int = Field(4, description="Number of images to fetch per part", ge=3, le=5)

class ReprocessRequest(BaseModel):
    search_id: str = Field(..., description="Original search ID")
    part_numbers: List[str] = Field(..., description="Part numbers to re-process")
    search_strategy: Optional[str] = Field("alternative", description="Search strategy: 'alternative', 'broader', 'specific'")
    exclude_sources: Optional[List[str]] = Field(None, description="Sources to exclude from results")
    
class ImageResult(BaseModel):
    title: str
    original_url: str
    thumbnail_url: str
    source: str
    width: Optional[int] = None
    height: Optional[int] = None

class PartSearchResult(BaseModel):
    part_number: str
    search_query: str
    images: List[ImageResult]
    search_success: bool
    error_message: Optional[str] = None

class SearchResponse(BaseModel):
    search_id: str
    results: List[PartSearchResult]
    total_parts: int
    total_images_found: int
    processing_time: float

class DownloadRequest(BaseModel):
    search_id: str
    part_numbers: Optional[List[str]] = None  # If None, download all parts

class DownloadResult(BaseModel):
    part_number: str
    image_url: str
    filename: str
    success: bool
    error_message: Optional[str] = None
    file_size: Optional[int] = None

class DownloadResponse(BaseModel):
    download_id: str
    status: str  # "started", "processing", "completed", "failed"
    total_images: int
    downloaded_images: int
    results: List[DownloadResult] = []
    zip_file: Optional[str] = None

# Services
class GoogleImageSearchService:
    def __init__(self):
        self.api_key = os.getenv('SERPAPI_KEY')
        if not self.api_key:
            raise ValueError("SERPAPI_KEY not found in environment variables")
    
    def _score_image_relevance(self, image_data: dict, part_number: str, manufacturer: str = None) -> float:
        """Score image relevance based on title, source, and metadata"""
        score = 0.0
        title = image_data.get("title", "").lower()
        source = image_data.get("source", "").lower()
        
        # Part number match in title (highest priority)
        part_clean = part_number.lower().replace("-", "").replace(" ", "")
        if part_clean in title.replace("-", "").replace(" ", ""):
            score += 50
        elif part_number.lower() in title:
            score += 30
        
        # Manufacturer match
        if manufacturer and manufacturer.lower() in title:
            score += 20
        
        # Relevant keywords in title - updated for industrial parts
        part_keywords = ["transformer", "relay", "contactor", "breaker", "component", 
                        "electrical", "industrial", "genuine", "oem", "original", 
                        "schneider", "abb", "siemens", "eocr", "current"]
        for keyword in part_keywords:
            if keyword in title:
                score += 8
        
        # Prefer industrial/technical sources
        industrial_sources = ["alliance", "automation", "industrial", "electric", "schneider", 
                             "abb.com", "siemens", "rockwell", "eaton", "ge.com", "westinghouse",
                             "technical", "catalog", "datasheet", "spec"]
        for source in industrial_sources:
            if source in source:
                score += 20
                break
        
        # Prefer certain sources (more likely to have accurate part images)
        trusted_sources = ["ebay", "amazon", "digikey", "mouser", "newark", "rs-online", 
                          "farnell", "allied", "grainger"]
        for trusted in trusted_sources:
            if trusted in source:
                score += 10
                break
        
        # Penalize irrelevant content
        avoid_keywords = ["logo", "banner", "advertisement", "ad", "promo", "sale", 
                         "coupon", "catalog", "manual", "diagram", "schematic"]
        for avoid in avoid_keywords:
            if avoid in title:
                score -= 10
        
        # Image dimensions (prefer reasonable sizes, not tiny icons or huge banners)
        width = image_data.get("original_width", 0)
        height = image_data.get("original_height", 0)
        if width and height:
            if 200 <= width <= 1000 and 200 <= height <= 1000:
                score += 10
            elif width < 100 or height < 100:  # Too small
                score -= 15
            elif width > 2000 or height > 2000:  # Too large
                score -= 5
        
        return max(0, score)
    
    def _select_best_images(self, images: list, part_number: str, manufacturer: str = None, max_images: int = 4) -> list:
        """Select the most relevant images based on scoring"""
        # Score all images
        scored_images = []
        for img in images:
            score = self._score_image_relevance(img, part_number, manufacturer)
            scored_images.append((score, img))
        
        # Sort by score (highest first) and take top images
        scored_images.sort(key=lambda x: x[0], reverse=True)
        
        # Select top images, ensuring diversity by avoiding too many from same source
        selected = []
        used_sources = set()
        
        for score, img in scored_images:
            if len(selected) >= max_images:
                break
            
            source = img.get("source", "").lower()
            # Allow max 2 images from same source to ensure diversity
            source_count = sum(1 for sel_img in selected if sel_img.get("source", "").lower() == source)
            
            if score > 10 and source_count < 2:  # Only include if score is reasonable
                selected.append(img)
                used_sources.add(source)
        
        return selected
    
    def _get_alternative_search_params(self, part_number: str, manufacturer: str = None, 
                                     strategy: str = "alternative", exclude_urls: List[str] = None) -> dict:
        """Get different search parameters for re-processing"""
        base_params = {
            "api_key": self.api_key,
            "engine": "google_images",
            "safe": "off",
            "location": "United States",
        }
        
        if strategy == "broader":
            # Broader search with more general terms
            query_parts = [part_number, "automotive part", "replacement"]
            if manufacturer:
                query_parts.append(manufacturer)
            base_params.update({
                "q": " ".join(query_parts),
                "num": 25,
                "tbs": "isz:m"  # Medium size
            })
        elif strategy == "specific":
            # More specific search with exact terms
            query_parts = [f'"{part_number}"', "genuine", "original"]
            if manufacturer:
                query_parts.insert(1, f'"{manufacturer}"')
            base_params.update({
                "q": " ".join(query_parts),
                "num": 20,
                "tbs": "isz:l"  # Large size for better quality
            })
        else:  # alternative
            # Alternative search with different keywords
            query_parts = [part_number, "aftermarket", "compatible", "fits"]
            if manufacturer:
                query_parts.append(manufacturer)
            base_params.update({
                "q": " ".join(query_parts),
                "num": 20,
                "tbs": "isz:m"
            })
        
        return base_params

    def _filter_previous_images(self, images: list, exclude_urls: List[str] = None) -> list:
        """Filter out previously found images"""
        if not exclude_urls:
            return images
        
        exclude_set = set(exclude_urls)
        filtered = []
        
        for img in images:
            original_url = img.get("original", "")
            link_url = img.get("link", "")
            
            # Check if this image was already found
            if original_url not in exclude_set and link_url not in exclude_set:
                filtered.append(img)
        
        return filtered

    async def reprocess_part_images(self, part_number: str, manufacturer: Optional[str] = None,
                                  num_results: int = 4, strategy: str = "alternative",
                                  exclude_urls: List[str] = None) -> PartSearchResult:
        """Re-process part number search with different strategy and exclusions"""
        try:
            # Get alternative search parameters
            params = self._get_alternative_search_params(part_number, manufacturer, strategy, exclude_urls)
            
            # Execute search
            search = GoogleSearch(params)
            results = search.get_dict()
            
            # Check for errors
            if "error" in results:
                return PartSearchResult(
                    part_number=part_number,
                    search_query=params["q"],
                    images=[],
                    search_success=False,
                    error_message=results["error"]
                )
            
            # Parse and filter results
            raw_images = []
            if "images_results" in results:
                raw_images = results["images_results"]
            
            # Filter out previously found images
            filtered_images = self._filter_previous_images(raw_images, exclude_urls)
            
            # Select best images from filtered results (no AI needed)
            best_images = self._select_best_images(filtered_images, part_number, manufacturer, num_results)
            
            # Convert to our format
            images = []
            for img in best_images:
                images.append(ImageResult(
                    title=img.get("title", ""),
                    original_url=img.get("original", img.get("link", "")),
                    thumbnail_url=img.get("thumbnail", ""),
                    source=img.get("source", ""),
                    width=img.get("original_width"),
                    height=img.get("original_height")
                ))
            
            return PartSearchResult(
                part_number=part_number,
                search_query=params["q"],
                images=images,
                search_success=True
            )
            
        except Exception as e:
            logger.error(f"Re-process failed for part {part_number}: {str(e)}")
            return PartSearchResult(
                part_number=part_number,
                search_query="",
                images=[],
                search_success=False,
                error_message=str(e)
            )

    async def search_part_images(self, part_number: str, manufacturer: Optional[str] = None, 
                                num_results: int = 4) -> PartSearchResult:
        try:
            # Build optimized search query for different part types
            part_lower = part_number.lower()
            
            # Detect part type and optimize search accordingly
            if any(keyword in part_lower for keyword in ['ct-', 'transformer', 'relay', 'contactor', 'breaker']):
                # Industrial electrical components
                if manufacturer:
                    search_query = f'"{part_number}" {manufacturer} electrical component industrial'
                else:
                    search_query = f'"{part_number}" electrical component transformer relay'
            elif any(keyword in part_lower for keyword in ['pf', 'filter', 'bpr', 'ngk', 'spark']):
                # Automotive parts
                if manufacturer:
                    search_query = f'"{part_number}" "{manufacturer}" genuine part'
                else:
                    search_query = f'"{part_number}" genuine OEM part'
            else:
                # Generic industrial/mechanical parts
                if manufacturer:
                    search_query = f'"{part_number}" {manufacturer} part component'
                else:
                    search_query = f'"{part_number}" industrial part component'
            
            # Search parameters - get more results to have better selection
            params = {
                "api_key": self.api_key,
                "engine": "google_images",
                "q": search_query,
                "num": min(num_results * 5, 20),  # Get 5x more results for better selection
                "safe": "off",
                "location": "United States",
                "tbs": "isz:m"  # Medium size images preferred
            }
            
            # Execute search
            search = GoogleSearch(params)
            results = search.get_dict()
            
            # Debug logging
            logger.info(f"Search query for {part_number}: {search_query}")
            raw_image_count = len(results.get("images_results", []))
            logger.info(f"Raw SERP results: {raw_image_count} images")
            
            # Check for errors
            if "error" in results:
                return PartSearchResult(
                    part_number=part_number,
                    search_query=search_query,
                    images=[],
                    search_success=False,
                    error_message=results["error"]
                )
            
            # Parse and score results
            raw_images = []
            if "images_results" in results:
                raw_images = results["images_results"]
            
            # Select best images using intelligent scoring (no AI needed)
            best_images = self._select_best_images(raw_images, part_number, manufacturer, num_results)
            
            # Convert to our format
            images = []
            for img in best_images:
                images.append(ImageResult(
                    title=img.get("title", ""),
                    original_url=img.get("original", img.get("link", "")),
                    thumbnail_url=img.get("thumbnail", ""),
                    source=img.get("source", ""),
                    width=img.get("original_width"),
                    height=img.get("original_height")
                ))
            
            return PartSearchResult(
                part_number=part_number,
                search_query=search_query,
                images=images,
                search_success=True
            )
            
        except Exception as e:
            logger.error(f"Search failed for part {part_number}: {str(e)}")
            return PartSearchResult(
                part_number=part_number,
                search_query="",
                images=[],
                search_success=False,
                error_message=str(e)
            )

class AsyncImageDownloader:
    def __init__(self, max_concurrent: int = 5, timeout: int = 15):
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
    
    async def download_image(self, url: str, filename: str) -> DownloadResult:
        """Download a single image"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PartImageDownloader/1.0)'}) as response:
                    if response.status == 200:
                        filepath = DOWNLOADS_DIR / filename
                        content = await response.read()
                        
                        # Write file
                        async with aiofiles.open(filepath, 'wb') as f:
                            await f.write(content)
                        
                        # Verify the file
                        if filepath.exists() and len(content) > 1000:  # At least 1KB
                            try:
                                # Quick validation without full verification
                                with Image.open(filepath) as img:
                                    # Just check if it opens, don't verify fully
                                    img.format  
                                return DownloadResult(
                                    part_number="",
                                    image_url=url,
                                    filename=filename,
                                    success=True,
                                    file_size=len(content)
                                )
                            except Exception:
                                # Remove invalid image
                                filepath.unlink(missing_ok=True)
                                return DownloadResult(
                                    part_number="",
                                    image_url=url,
                                    filename=filename,
                                    success=False,
                                    error_message="Invalid image format"
                                )
                        else:
                            filepath.unlink(missing_ok=True)
                            return DownloadResult(
                                part_number="",
                                image_url=url,
                                filename=filename,
                                success=False,
                                error_message="File too small or empty"
                            )
                    else:
                        return DownloadResult(
                            part_number="",
                            image_url=url,
                            filename=filename,
                            success=False,
                            error_message=f"HTTP {response.status}"
                        )
                        
        except asyncio.TimeoutError:
            return DownloadResult(
                part_number="",
                image_url=url,
                filename=filename,
                success=False,
                error_message="Timeout"
            )
        except Exception as e:
            return DownloadResult(
                part_number="",
                image_url=url,
                filename=filename,
                success=False,
                error_message=f"Error: {str(e)[:100]}"
            )
    
    async def download_images_batch(self, images_data: List[tuple]) -> List[DownloadResult]:
        """Download multiple images concurrently with improved error handling"""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = []
        
        async def download_with_semaphore(part_number: str, image_url: str, filename: str):
            async with semaphore:
                try:
                    result = await self.download_image(image_url, filename)
                    result.part_number = part_number
                    return result
                except Exception as e:
                    return DownloadResult(
                        part_number=part_number,
                        image_url=image_url,
                        filename=filename,
                        success=False,
                        error_message=f"Download failed: {str(e)[:100]}"
                    )
        
        # Process in smaller batches to avoid overwhelming the system
        batch_size = 10
        for i in range(0, len(images_data), batch_size):
            batch = images_data[i:i + batch_size]
            
            tasks = [
                download_with_semaphore(part_num, url, filename)
                for part_num, url, filename in batch
            ]
            
            # Execute batch and collect results
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    results.append(DownloadResult(
                        part_number="unknown",
                        image_url="unknown", 
                        filename="",
                        success=False,
                        error_message=f"Batch error: {str(result)[:100]}"
                    ))
                else:
                    results.append(result)
            
            # Small delay between batches
            await asyncio.sleep(0.1)
        
        return results

def generate_filename(part_number: str, image_index: int, url: str) -> str:
    """Generate clean filename with part number and sequential index"""
    # Clean part number for filename (remove special characters, keep alphanumeric and basic separators)
    clean_part = "".join(c if c.isalnum() or c in "._-" else "_" for c in part_number)
    
    # Get file extension from URL, default to .jpg
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        path = parsed_url.path
        extension = Path(path).suffix.lower()
        if extension not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            extension = '.jpg'
    except:
        extension = '.jpg'
    
    # Simple format: partnumber_1.jpg, partnumber_2.jpg, etc.
    return f"{clean_part}_{image_index + 1}{extension}"

def create_zip_file(download_results: List[DownloadResult], zip_filename: str) -> str:
    """Create ZIP file from downloaded images with clean organization"""
    zip_path = DOWNLOADS_DIR / zip_filename
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Group results by part number
        part_groups = {}
        for result in download_results:
            if result.success and result.filename:
                part_num = result.part_number
                if part_num not in part_groups:
                    part_groups[part_num] = []
                part_groups[part_num].append(result)
        
        # Add files to ZIP with clean organization
        for part_number, results in part_groups.items():
            clean_part_folder = "".join(c if c.isalnum() or c in "._-" else "_" for c in part_number)
            
            for i, result in enumerate(results):
                file_path = DOWNLOADS_DIR / result.filename
                if file_path.exists():
                    # Create clean filename for ZIP
                    extension = Path(result.filename).suffix or '.jpg'
                    clean_filename = f"{clean_part_folder}_{i + 1}{extension}"
                    
                    # Add to ZIP: PartNumber/partnumber_1.jpg
                    zip_file.write(file_path, f"{clean_part_folder}/{clean_filename}")
    
    return str(zip_path)

# Global storage for download tasks (in production, use Redis or database)
download_tasks = {}

# Services
search_service = GoogleImageSearchService()
downloader = AsyncImageDownloader()

# API Endpoints
@api_router.post("/reprocess-images", response_model=SearchResponse)
async def reprocess_part_images(request: ReprocessRequest):
    """Re-process specific part numbers with different search strategy"""
    if request.search_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Original search ID not found")
    
    start_time = time.time()
    original_search = download_tasks[request.search_id]["search_results"]
    
    # Get previous image URLs for exclusion
    exclude_urls = []
    for result in original_search:
        if result.part_number in request.part_numbers:
            for img in result.images:
                if img.original_url:
                    exclude_urls.append(img.original_url)
    
    # Re-process selected parts
    results = []
    total_images = 0
    
    for part_number in request.part_numbers:
        # Find original manufacturer info
        manufacturer = None
        for orig_result in original_search:
            if orig_result.part_number == part_number and orig_result.search_query:
                # Try to extract manufacturer from original query
                query_parts = orig_result.search_query.split()
                if len(query_parts) > 1:
                    manufacturer = query_parts[1] if query_parts[1] not in ["OEM", "part", "component"] else None
        
        result = await search_service.reprocess_part_images(
            part_number=part_number,
            manufacturer=manufacturer,
            num_results=4,
            strategy=request.search_strategy or "alternative",
            exclude_urls=exclude_urls
        )
        results.append(result)
        if result.search_success:
            total_images += len(result.images)
    
    processing_time = time.time() - start_time
    
    # Create new search ID for reprocessed results
    new_search_id = str(uuid.uuid4())
    
    response = SearchResponse(
        search_id=new_search_id,
        results=results,
        total_parts=len(request.part_numbers),
        total_images_found=total_images,
        processing_time=processing_time
    )
    
    # Store reprocessed results
    download_tasks[new_search_id] = {
        "search_results": results,
        "created_at": datetime.utcnow(),
        "status": "completed",
        "reprocessed_from": request.search_id,
        "strategy": request.search_strategy
    }
    
    return response

@api_router.post("/search-images", response_model=SearchResponse)
async def search_part_images(request: PartSearchRequest):
    """Search for images of multiple part numbers"""
    start_time = time.time()
    search_id = str(uuid.uuid4())
    
    # Search for each part number
    results = []
    total_images = 0
    
    for part_number in request.part_numbers:
        result = await search_service.search_part_images(
            part_number=part_number,
            manufacturer=request.manufacturer,
            num_results=request.num_images_per_part
        )
        results.append(result)
        if result.search_success:
            total_images += len(result.images)
    
    processing_time = time.time() - start_time
    
    response = SearchResponse(
        search_id=search_id,
        results=results,
        total_parts=len(request.part_numbers),
        total_images_found=total_images,
        processing_time=processing_time
    )
    
    # Store results temporarily for download
    download_tasks[search_id] = {
        "search_results": results,
        "created_at": datetime.utcnow(),
        "status": "completed"
    }
    
    return response

@api_router.post("/download-images", response_model=DownloadResponse)
async def download_images(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Download images from search results"""
    if request.search_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Search ID not found")
    
    search_data = download_tasks[request.search_id]
    search_results = search_data["search_results"]
    
    # Filter results if specific part numbers requested
    if request.part_numbers:
        search_results = [r for r in search_results if r.part_number in request.part_numbers]
    
    # Prepare download data
    images_to_download = []
    for result in search_results:
        if result.search_success:
            for i, image in enumerate(result.images):
                if image.original_url:
                    filename = generate_filename(result.part_number, i, image.original_url)
                    images_to_download.append((result.part_number, image.original_url, filename))
    
    download_id = str(uuid.uuid4())
    
    # Initialize download task
    download_tasks[download_id] = {
        "status": "started",
        "total_images": len(images_to_download),
        "downloaded_images": 0,
        "results": [],
        "created_at": datetime.utcnow()
    }
    
    # Start background download
    background_tasks.add_task(download_images_background, download_id, images_to_download)
    
    return DownloadResponse(
        download_id=download_id,
        status="started",
        total_images=len(images_to_download),
        downloaded_images=0
    )

async def download_images_background(download_id: str, images_to_download: List[tuple]):
    """Background task for downloading images with improved performance"""
    try:
        download_tasks[download_id]["status"] = "processing"
        logger.info(f"Starting download task {download_id} with {len(images_to_download)} images")
        
        # Download images with optimized settings
        downloader_instance = AsyncImageDownloader(max_concurrent=3, timeout=10)
        results = await downloader_instance.download_images_batch(images_to_download)
        
        # Process results
        successful_downloads = []
        failed_downloads = []
        
        for result in results:
            if result.success:
                successful_downloads.append(result)
            else:
                failed_downloads.append(result)
        
        logger.info(f"Download completed: {len(successful_downloads)}/{len(images_to_download)} successful")
        
        # Create ZIP file only if we have successful downloads
        zip_filename = None
        zip_path = None
        if successful_downloads:
            zip_filename = f"parts_images_{download_id}.zip"
            zip_path = create_zip_file(successful_downloads, zip_filename)
            logger.info(f"ZIP file created: {zip_filename}")
        
        # Update task status
        download_tasks[download_id].update({
            "status": "completed",
            "downloaded_images": len(successful_downloads),
            "results": results,
            "zip_file": zip_filename if zip_path else None
        })
        
        logger.info(f"Download task {download_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Download task {download_id} failed: {str(e)}")
        download_tasks[download_id].update({
            "status": "failed",
            "error_message": str(e),
            "downloaded_images": 0
        })

@api_router.get("/download-status/{download_id}", response_model=DownloadResponse)
async def get_download_status(download_id: str):
    """Get status of download task"""
    if download_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Download ID not found")
    
    task_data = download_tasks[download_id]
    
    return DownloadResponse(
        download_id=download_id,
        status=task_data.get("status", "unknown"),
        total_images=task_data.get("total_images", 0),
        downloaded_images=task_data.get("downloaded_images", 0),
        results=task_data.get("results", []),
        zip_file=task_data.get("zip_file")
    )

@api_router.get("/download-zip/{download_id}")
async def download_zip_file(download_id: str):
    """Download ZIP file of images"""
    if download_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Download ID not found")
    
    task_data = download_tasks[download_id]
    zip_filename = task_data.get("zip_file")
    
    if not zip_filename:
        raise HTTPException(status_code=404, detail="ZIP file not available")
    
    zip_path = DOWNLOADS_DIR / zip_filename
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="ZIP file not found")
    
    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type="application/zip"
    )

@api_router.post("/parse-csv")
async def parse_csv_file(file: UploadFile = File(...)):
    """Parse CSV file to extract part numbers"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.reader(io.StringIO(content_str))
        part_numbers = []
        header_indicators = ['part', 'number', 'component', 'item', 'code', 'id']
        
        for row_idx, row in enumerate(csv_reader):
            if row:  # Skip empty rows
                # Check if first row looks like a header
                if row_idx == 0:
                    first_cell = row[0].lower().strip()
                    if any(indicator in first_cell for indicator in header_indicators):
                        continue  # Skip header row
                
                # Take first column or the whole row if single value
                part_number = row[0].strip() if len(row) == 1 else " ".join(row).strip()
                if part_number and part_number not in part_numbers:
                    part_numbers.append(part_number)
        
        return {
            "part_numbers": part_numbers,
            "total_count": len(part_numbers)
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

@api_router.delete("/cleanup/{task_id}")
async def cleanup_task(task_id: str):
    """Clean up downloaded files and task data"""
    if task_id in download_tasks:
        task_data = download_tasks[task_id]
        
        # Clean up downloaded files
        if "results" in task_data:
            for result in task_data["results"]:
                if result.success and result.filename:
                    file_path = DOWNLOADS_DIR / result.filename
                    file_path.unlink(missing_ok=True)
        
        # Clean up ZIP file
        if "zip_file" in task_data and task_data["zip_file"]:
            zip_path = DOWNLOADS_DIR / task_data["zip_file"]
            zip_path.unlink(missing_ok=True)
        
        # Remove task data
        del download_tasks[task_id]
        
        return {"message": "Cleanup completed"}
    
    raise HTTPException(status_code=404, detail="Task not found")

# Health check
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test SerpAPI key
        search = GoogleSearch({"api_key": os.getenv('SERPAPI_KEY'), "engine": "google"})
        # Don't actually make a request to save quota
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "serpapi_configured": bool(os.getenv('SERPAPI_KEY')),
            "downloads_dir": str(DOWNLOADS_DIR)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()