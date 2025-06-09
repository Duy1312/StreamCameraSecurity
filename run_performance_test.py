#!/usr/bin/env python3
"""
Performance testing script for StreamCameraSecurity
Tests database, cache, and API performance
"""

import requests
import time
import concurrent.futures
import statistics
import json
import random
from typing import List, Dict, Any

class PerformanceTest:
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = {}
    
    def test_api_endpoint(self, endpoint: str, method: str = "GET", data: Dict = None, 
                         concurrent_requests: int = 10, total_requests: int = 100) -> Dict[str, Any]:
        """Test API endpoint performance"""
        print(f"\n🧪 Testing {method} {endpoint}")
        print(f"   Concurrent requests: {concurrent_requests}")
        print(f"   Total requests: {total_requests}")
        
        url = f"{self.base_url}{endpoint}"
        response_times = []
        errors = 0
        
        def make_request():
            start_time = time.time()
            try:
                if method == "GET":
                    response = self.session.get(url)
                elif method == "POST":
                    response = self.session.post(url, json=data)
                elif method == "PUT":
                    response = self.session.put(url, json=data)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                return time.time() - start_time
            except Exception as e:
                print(f"   ❌ Request failed: {e}")
                return None
        
        # Warm up
        for _ in range(5):
            make_request()
        
        # Performance test
        start_total = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
            futures = [executor.submit(make_request) for _ in range(total_requests)]
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    response_times.append(result)
                else:
                    errors += 1
        
        total_time = time.time() - start_total
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            median_response_time = statistics.median(response_times)
            p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
            requests_per_second = len(response_times) / total_time
            
            result = {
                "endpoint": endpoint,
                "method": method,
                "total_requests": total_requests,
                "successful_requests": len(response_times),
                "errors": errors,
                "total_time": total_time,
                "avg_response_time": avg_response_time,
                "median_response_time": median_response_time,
                "p95_response_time": p95_response_time,
                "requests_per_second": requests_per_second,
                "min_response_time": min(response_times),
                "max_response_time": max(response_times)
            }
            
            print(f"   ✅ Avg response time: {avg_response_time:.3f}s")
            print(f"   📊 Median: {median_response_time:.3f}s | P95: {p95_response_time:.3f}s")
            print(f"   🚀 Requests/sec: {requests_per_second:.1f}")
            print(f"   ❌ Errors: {errors}")
            
            return result
        else:
            print("   ❌ All requests failed!")
            return {
                "endpoint": endpoint,
                "method": method,
                "errors": errors,
                "total_requests": total_requests,
                "successful_requests": 0
            }
    
    def test_database_performance(self):
        """Test database operations performance"""
        print("\n📊 Testing Database Performance")
        
        # Test camera listing (with cache)
        self.results["get_cameras_cached"] = self.test_api_endpoint(
            "/api/cameras", concurrent_requests=20, total_requests=200
        )
        
        # Test camera listing (cache miss simulation by adding query param)
        self.results["get_cameras_no_cache"] = self.test_api_endpoint(
            f"/api/cameras?_={int(time.time())}", concurrent_requests=5, total_requests=50
        )
        
        # Test detection results with pagination
        self.results["get_detections_page1"] = self.test_api_endpoint(
            "/api/detection-results?page=1", concurrent_requests=10, total_requests=100
        )
        
        self.results["get_detections_page2"] = self.test_api_endpoint(
            "/api/detection-results?page=2", concurrent_requests=10, total_requests=100
        )
    
    def test_cache_performance(self):
        """Test Redis cache performance"""
        print("\n🔄 Testing Cache Performance")
        
        # Test multiple requests to same endpoint (should hit cache)
        self.results["cache_hit_test"] = self.test_api_endpoint(
            "/api/cameras", concurrent_requests=50, total_requests=500
        )
        
        # Test active streams (lightweight cache)
        self.results["active_streams_cache"] = self.test_api_endpoint(
            "/api/active-streams", concurrent_requests=30, total_requests=300
        )
    
    def test_crud_operations(self):
        """Test CRUD operations performance"""
        print("\n📝 Testing CRUD Operations")
        
        camera_data = {
            "name": f"Test Camera {random.randint(1000, 9999)}",
            "ip": f"192.168.1.{random.randint(100, 200)}",
            "location": "Test Location"
        }
        
        # Test creating cameras
        create_results = []
        for i in range(10):
            test_data = camera_data.copy()
            test_data["ip"] = f"192.168.1.{150 + i}"
            test_data["name"] = f"Perf Test Camera {i}"
            
            result = self.test_api_endpoint(
                "/api/cameras", method="POST", data=test_data,
                concurrent_requests=1, total_requests=1
            )
            create_results.append(result)
        
        avg_create_time = statistics.mean([r["avg_response_time"] for r in create_results if "avg_response_time" in r])
        print(f"   📝 Average camera creation time: {avg_create_time:.3f}s")
        
        self.results["camera_creation"] = {
            "avg_response_time": avg_create_time,
            "total_operations": len(create_results)
        }
    
    def test_stream_operations(self):
        """Test streaming operations"""
        print("\n📺 Testing Stream Operations")
        
        # Start multiple streams
        stream_data = {"camera_id": "cam_1"}
        self.results["start_streams"] = self.test_api_endpoint(
            "/api/start-stream", method="POST", data=stream_data,
            concurrent_requests=5, total_requests=20
        )
        
        # Stop streams
        self.results["stop_streams"] = self.test_api_endpoint(
            "/api/stop-stream", method="POST", data=stream_data,
            concurrent_requests=5, total_requests=20
        )
    
    def test_rate_limiting(self):
        """Test rate limiting"""
        print("\n🚦 Testing Rate Limiting")
        
        # Send requests rapidly to trigger rate limiting
        rapid_requests = []
        start_time = time.time()
        
        for i in range(150):  # Above default 100/hour limit
            try:
                response = self.session.get(f"{self.base_url}/api/cameras")
                rapid_requests.append({
                    "status_code": response.status_code,
                    "time": time.time() - start_time
                })
            except Exception as e:
                rapid_requests.append({
                    "error": str(e),
                    "time": time.time() - start_time
                })
        
        rate_limited = len([r for r in rapid_requests if r.get("status_code") == 429])
        successful = len([r for r in rapid_requests if r.get("status_code") == 200])
        
        print(f"   ✅ Successful requests: {successful}")
        print(f"   🚫 Rate limited requests: {rate_limited}")
        
        self.results["rate_limiting"] = {
            "total_requests": len(rapid_requests),
            "successful": successful,
            "rate_limited": rate_limited
        }
    
    def run_all_tests(self):
        """Run all performance tests"""
        print("🚀 Starting Performance Tests for StreamCameraSecurity")
        print("=" * 60)
        
        try:
            # Check if server is running
            response = self.session.get(f"{self.base_url}/api/cameras")
            response.raise_for_status()
            print("✅ Server is running and accessible")
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return
        
        start_time = time.time()
        
        # Run tests
        self.test_database_performance()
        self.test_cache_performance()
        self.test_crud_operations()
        self.test_stream_operations()
        self.test_rate_limiting()
        
        total_time = time.time() - start_time
        
        # Generate report
        self.generate_report(total_time)
    
    def generate_report(self, total_time: float):
        """Generate performance test report"""
        print("\n" + "=" * 60)
        print("📊 PERFORMANCE TEST REPORT")
        print("=" * 60)
        
        print(f"⏱️  Total test time: {total_time:.2f}s")
        print(f"🧪 Total endpoints tested: {len(self.results)}")
        
        # Summary of key metrics
        key_metrics = []
        for test_name, result in self.results.items():
            if "avg_response_time" in result:
                key_metrics.append({
                    "test": test_name,
                    "avg_time": result["avg_response_time"],
                    "rps": result.get("requests_per_second", 0)
                })
        
        if key_metrics:
            print("\n📈 Key Performance Metrics:")
            for metric in sorted(key_metrics, key=lambda x: x["avg_time"]):
                print(f"   {metric['test']:25} | Avg: {metric['avg_time']:.3f}s | RPS: {metric['rps']:.1f}")
        
        # Performance recommendations
        print("\n💡 Performance Recommendations:")
        
        cache_hit_rps = self.results.get("cache_hit_test", {}).get("requests_per_second", 0)
        no_cache_rps = self.results.get("get_cameras_no_cache", {}).get("requests_per_second", 0)
        
        if cache_hit_rps > no_cache_rps * 2:
            print("   ✅ Cache is working effectively")
        else:
            print("   ⚠️  Cache performance could be improved")
        
        avg_response_times = [r.get("avg_response_time", 0) for r in self.results.values() if "avg_response_time" in r]
        if avg_response_times:
            overall_avg = statistics.mean(avg_response_times)
            if overall_avg < 0.1:
                print("   ✅ Excellent response times")
            elif overall_avg < 0.5:
                print("   ✅ Good response times")
            else:
                print("   ⚠️  Response times could be improved")
        
        # Save detailed results
        with open("performance_test_results.json", "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed results saved to: performance_test_results.json")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Performance test for StreamCameraSecurity")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="Base URL of the application (default: http://localhost:5000)")
    
    args = parser.parse_args()
    
    tester = PerformanceTest(args.url)
    tester.run_all_tests() 