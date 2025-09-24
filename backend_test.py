#!/usr/bin/env python3
"""
Backend API Testing for Parts Image Downloader
Tests all CRUD operations, SERP API integration, and file handling
"""

import requests
import sys
import time
import json
import tempfile
import csv
from datetime import datetime
from pathlib import Path

class PartsImageDownloaderTester:
    def __init__(self, base_url="https://quickpart-images.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.search_id = None
        self.download_id = None

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"- Status: {data.get('status', 'unknown')}, SERP API: {data.get('serpapi_configured', False)}"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Health Check", success, details)
        except Exception as e:
            return self.log_test("Health Check", False, f"- Error: {str(e)}")

    def test_search_images_single_part(self):
        """Test image search with single part number"""
        try:
            payload = {
                "part_numbers": ["ABC123"],
                "manufacturer": "Toyota",
                "num_images_per_part": 3
            }
            
            response = requests.post(f"{self.api_url}/search-images", json=payload, timeout=30)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                self.search_id = data.get("search_id")
                details = f"- Found {data.get('total_images_found', 0)} images, Search ID: {self.search_id[:8]}..."
            else:
                details = f"- Status Code: {response.status_code}, Response: {response.text[:100]}"
                
            return self.log_test("Search Images (Single Part)", success, details)
        except Exception as e:
            return self.log_test("Search Images (Single Part)", False, f"- Error: {str(e)}")

    def test_search_images_multiple_parts(self):
        """Test image search with multiple part numbers"""
        try:
            payload = {
                "part_numbers": ["DEF456", "GHI789", "JKL012"],
                "manufacturer": None,
                "num_images_per_part": 2
            }
            
            response = requests.post(f"{self.api_url}/search-images", json=payload, timeout=45)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                # Update search_id for download tests
                self.search_id = data.get("search_id")
                details = f"- {data.get('total_parts', 0)} parts, {data.get('total_images_found', 0)} images, Time: {data.get('processing_time', 0):.2f}s"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Search Images (Multiple Parts)", success, details)
        except Exception as e:
            return self.log_test("Search Images (Multiple Parts)", False, f"- Error: {str(e)}")

    def test_search_images_invalid_request(self):
        """Test search with invalid request data"""
        try:
            payload = {
                "part_numbers": [],  # Empty list should fail
                "num_images_per_part": 25  # Over limit
            }
            
            response = requests.post(f"{self.api_url}/search-images", json=payload, timeout=10)
            success = response.status_code == 422  # Validation error expected
            
            details = f"- Status Code: {response.status_code} (Expected 422)"
            return self.log_test("Search Images (Invalid Request)", success, details)
        except Exception as e:
            return self.log_test("Search Images (Invalid Request)", False, f"- Error: {str(e)}")

    def test_download_images(self):
        """Test image download functionality"""
        if not self.search_id:
            return self.log_test("Download Images", False, "- No search_id available")
            
        try:
            payload = {
                "search_id": self.search_id,
                "part_numbers": None  # Download all
            }
            
            response = requests.post(f"{self.api_url}/download-images", json=payload, timeout=15)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                self.download_id = data.get("download_id")
                details = f"- Download ID: {self.download_id[:8]}..., Status: {data.get('status')}, Total: {data.get('total_images')}"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Download Images", success, details)
        except Exception as e:
            return self.log_test("Download Images", False, f"- Error: {str(e)}")

    def test_download_status(self):
        """Test download status polling"""
        if not self.download_id:
            return self.log_test("Download Status", False, "- No download_id available")
            
        try:
            # Poll status multiple times to test the background processing
            max_polls = 10
            for i in range(max_polls):
                response = requests.get(f"{self.api_url}/download-status/{self.download_id}", timeout=10)
                
                if response.status_code != 200:
                    return self.log_test("Download Status", False, f"- Status Code: {response.status_code}")
                
                data = response.json()
                status = data.get("status")
                downloaded = data.get("downloaded_images", 0)
                total = data.get("total_images", 0)
                
                print(f"   Poll {i+1}: Status={status}, Progress={downloaded}/{total}")
                
                if status == "completed":
                    details = f"- Completed: {downloaded}/{total} images, ZIP: {bool(data.get('zip_file'))}"
                    return self.log_test("Download Status", True, details)
                elif status == "failed":
                    details = f"- Failed after {downloaded}/{total} images"
                    return self.log_test("Download Status", False, details)
                elif status in ["started", "processing"]:
                    time.sleep(2)  # Wait before next poll
                    continue
                else:
                    details = f"- Unknown status: {status}"
                    return self.log_test("Download Status", False, details)
            
            # If we reach here, download didn't complete in time
            return self.log_test("Download Status", False, "- Download didn't complete within timeout")
            
        except Exception as e:
            return self.log_test("Download Status", False, f"- Error: {str(e)}")

    def test_download_zip(self):
        """Test ZIP file download"""
        if not self.download_id:
            return self.log_test("Download ZIP", False, "- No download_id available")
            
        try:
            response = requests.get(f"{self.api_url}/download-zip/{self.download_id}", timeout=30)
            success = response.status_code == 200
            
            if success:
                content_type = response.headers.get('content-type', '')
                content_length = len(response.content)
                details = f"- Content-Type: {content_type}, Size: {content_length} bytes"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Download ZIP", success, details)
        except Exception as e:
            return self.log_test("Download ZIP", False, f"- Error: {str(e)}")

    def test_csv_parsing(self):
        """Test CSV file parsing"""
        try:
            # Create a temporary CSV file
            csv_content = "Part Number\nMNO345\nPQR678\nSTU901\n"
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
                f.write(csv_content)
                csv_path = f.name
            
            # Upload the CSV file
            with open(csv_path, 'rb') as f:
                files = {'file': ('test_parts.csv', f, 'text/csv')}
                response = requests.post(f"{self.api_url}/parse-csv", files=files, timeout=10)
            
            # Clean up
            Path(csv_path).unlink(missing_ok=True)
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                part_numbers = data.get("part_numbers", [])
                details = f"- Parsed {len(part_numbers)} parts: {part_numbers}"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("CSV Parsing", success, details)
        except Exception as e:
            return self.log_test("CSV Parsing", False, f"- Error: {str(e)}")

    def test_csv_parsing_invalid(self):
        """Test CSV parsing with invalid file"""
        try:
            # Try to upload a non-CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("This is not a CSV file")
                txt_path = f.name
            
            with open(txt_path, 'rb') as f:
                files = {'file': ('test.txt', f, 'text/plain')}
                response = requests.post(f"{self.api_url}/parse-csv", files=files, timeout=10)
            
            # Clean up
            Path(txt_path).unlink(missing_ok=True)
            
            success = response.status_code == 400  # Should reject non-CSV files
            details = f"- Status Code: {response.status_code} (Expected 400)"
            
            return self.log_test("CSV Parsing (Invalid)", success, details)
        except Exception as e:
            return self.log_test("CSV Parsing (Invalid)", False, f"- Error: {str(e)}")

    def test_cleanup_task(self):
        """Test task cleanup functionality"""
        if not self.download_id:
            return self.log_test("Cleanup Task", False, "- No download_id available")
            
        try:
            response = requests.delete(f"{self.api_url}/cleanup/{self.download_id}", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                details = f"- Message: {data.get('message', 'No message')}"
            else:
                details = f"- Status Code: {response.status_code}"
                
            return self.log_test("Cleanup Task", success, details)
        except Exception as e:
            return self.log_test("Cleanup Task", False, f"- Error: {str(e)}")

    def test_cleanup_invalid_task(self):
        """Test cleanup with invalid task ID"""
        try:
            fake_id = "invalid-task-id-12345"
            response = requests.delete(f"{self.api_url}/cleanup/{fake_id}", timeout=10)
            success = response.status_code == 404  # Should return not found
            
            details = f"- Status Code: {response.status_code} (Expected 404)"
            return self.log_test("Cleanup (Invalid Task)", success, details)
        except Exception as e:
            return self.log_test("Cleanup (Invalid Task)", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Parts Image Downloader Backend Tests")
        print(f"🌐 Testing API at: {self.api_url}")
        print("=" * 60)
        
        # Basic functionality tests
        self.test_health_check()
        
        # Search functionality tests
        self.test_search_images_single_part()
        self.test_search_images_multiple_parts()
        self.test_search_images_invalid_request()
        
        # Download functionality tests
        self.test_download_images()
        self.test_download_status()
        self.test_download_zip()
        
        # File handling tests
        self.test_csv_parsing()
        self.test_csv_parsing_invalid()
        
        # Cleanup tests
        self.test_cleanup_task()
        self.test_cleanup_invalid_task()
        
        # Print summary
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return 1

def main():
    """Main test runner"""
    tester = PartsImageDownloaderTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())