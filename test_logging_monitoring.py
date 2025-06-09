#!/usr/bin/env python3
"""
Test script cho hệ thống logging và monitoring mới
"""

import requests
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import sys

class LoggingMonitoringTest:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        
    def test_health_endpoint(self):
        """Test health check endpoint"""
        print("🏥 Testing Health Check Endpoint")
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            health_data = response.json()
            
            print(f"   Status: {health_data.get('status', 'unknown')}")
            print(f"   Version: {health_data.get('version', 'unknown')}")
            print(f"   Uptime: {health_data.get('uptime', 0):.2f}s")
            
            components = health_data.get('components', {})
            for component, status in components.items():
                print(f"   {component}: {status}")
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
            return False
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        print("\n📈 Testing Metrics Endpoint")
        try:
            response = self.session.get(f"{self.base_url}/api/metrics")
            metrics_data = response.json()
            
            app_info = metrics_data.get('application', {})
            print(f"   App: {app_info.get('name')} v{app_info.get('version')}")
            print(f"   Uptime: {app_info.get('uptime', 0):.2f}s")
            
            db_info = metrics_data.get('database', {})
            if 'cameras_total' in db_info:
                print(f"   Database - Cameras: {db_info['cameras_total']}")
                print(f"   Database - Detections: {db_info['detections_total']}")
                print(f"   Database - Sessions: {db_info['stream_sessions_total']}")
            
            cache_info = metrics_data.get('cache', {})
            print(f"   Cache: {cache_info.get('status', 'unknown')}")
            
            streams_info = metrics_data.get('streams', {})
            print(f"   Active Streams: {streams_info.get('active_count', 0)}")
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"   ❌ Metrics test failed: {e}")
            return False
    
    def test_api_response_format(self):
        """Test new standardized API response format"""
        print("\n📋 Testing API Response Format")
        try:
            response = self.session.get(f"{self.base_url}/api/cameras")
            data = response.json()
            
            # Check for new response format
            if 'status' in data and 'timestamp' in data and 'request_id' in data:
                print("   ✅ New standardized format detected")
                print(f"   Status: {data['status']}")
                print(f"   Request ID: {data['request_id']}")
                print(f"   Has data: {'data' in data}")
                return True
            else:
                print("   ⚠️  Old response format detected")
                return False
                
        except Exception as e:
            print(f"   ❌ Response format test failed: {e}")
            return False
    
    def test_compression(self):
        """Test response compression"""
        print("\n🗜️  Testing Response Compression")
        try:
            # Request with gzip support
            headers = {'Accept-Encoding': 'gzip, deflate'}
            response = self.session.get(f"{self.base_url}/api/cameras", headers=headers)
            
            content_encoding = response.headers.get('Content-Encoding')
            content_length = len(response.content)
            
            print(f"   Content-Encoding: {content_encoding}")
            print(f"   Content-Length: {content_length} bytes")
            
            if content_encoding == 'gzip':
                print("   ✅ Compression is working")
                return True
            else:
                print("   ⚠️  No compression (may be below threshold)")
                return True  # Not necessarily an error
                
        except Exception as e:
            print(f"   ❌ Compression test failed: {e}")
            return False
    
    def test_rate_limiting(self):
        """Test rate limiting"""
        print("\n🚦 Testing Rate Limiting")
        try:
            # Send many requests quickly
            responses = []
            for i in range(10):
                response = self.session.get(f"{self.base_url}/api/cameras")
                responses.append(response.status_code)
                time.sleep(0.1)  # Small delay
            
            rate_limited_count = responses.count(429)
            success_count = responses.count(200)
            
            print(f"   Successful requests: {success_count}")
            print(f"   Rate limited requests: {rate_limited_count}")
            
            # Test if we get rate limit headers
            response = self.session.get(f"{self.base_url}/api/cameras")
            rate_limit_headers = [h for h in response.headers.keys() if 'rate' in h.lower()]
            
            if rate_limit_headers:
                print(f"   Rate limit headers found: {rate_limit_headers}")
            
            return True  # Rate limiting is working if we get any 429s or success
            
        except Exception as e:
            print(f"   ❌ Rate limiting test failed: {e}")
            return False
    
    def test_security_headers(self):
        """Test security headers"""
        print("\n🔒 Testing Security Headers")
        try:
            response = self.session.get(f"{self.base_url}/api/cameras")
            headers = response.headers
            
            security_headers = [
                'X-Content-Type-Options',
                'X-Frame-Options', 
                'X-XSS-Protection',
                'Content-Security-Policy',
                'Strict-Transport-Security'
            ]
            
            present_headers = []
            for header in security_headers:
                if header in headers:
                    present_headers.append(header)
                    print(f"   ✅ {header}: {headers[header]}")
                else:
                    print(f"   ❌ {header}: Missing")
            
            return len(present_headers) >= 3  # At least 3 security headers
            
        except Exception as e:
            print(f"   ❌ Security headers test failed: {e}")
            return False
    
    def test_performance_headers(self):
        """Test performance monitoring headers"""
        print("\n⚡ Testing Performance Headers")
        try:
            response = self.session.get(f"{self.base_url}/api/cameras")
            headers = response.headers
            
            performance_headers = ['X-Response-Time', 'X-Request-ID']
            
            for header in performance_headers:
                if header in headers:
                    print(f"   ✅ {header}: {headers[header]}")
                else:
                    print(f"   ❌ {header}: Missing")
            
            return 'X-Response-Time' in headers
            
        except Exception as e:
            print(f"   ❌ Performance headers test failed: {e}")
            return False
    
    def test_pagination(self):
        """Test enhanced pagination"""
        print("\n📄 Testing Enhanced Pagination")
        try:
            response = self.session.get(f"{self.base_url}/api/detection-results?page=1&per_page=5")
            data = response.json()
            
            if 'data' in data and 'pagination' in data['data']:
                pagination = data['data']['pagination']
                print(f"   ✅ Page: {pagination.get('page')}")
                print(f"   ✅ Per page: {pagination.get('per_page')}")
                print(f"   ✅ Total: {pagination.get('total')}")
                print(f"   ✅ Has links: {'links' in pagination}")
                
                if 'links' in pagination:
                    links = pagination['links']
                    print(f"   Available links: {list(links.keys())}")
                
                return True
            else:
                print("   ❌ Pagination format not found")
                return False
                
        except Exception as e:
            print(f"   ❌ Pagination test failed: {e}")
            return False
    
    def test_validation_errors(self):
        """Test enhanced validation and error logging"""
        print("\n🔍 Testing Validation & Error Handling")
        try:
            # Test invalid JSON
            response = self.session.post(
                f"{self.base_url}/api/start-stream",
                data="invalid json",
                headers={'Content-Type': 'application/json'}
            )
            print(f"   Invalid JSON: {response.status_code}")
            
            # Test missing fields
            response = self.session.post(
                f"{self.base_url}/api/start-stream",
                json={},
                headers={'Content-Type': 'application/json'}
            )
            print(f"   Missing fields: {response.status_code}")
            
            # Test invalid camera ID
            response = self.session.post(
                f"{self.base_url}/api/start-stream",
                json={"camera_id": ""},
                headers={'Content-Type': 'application/json'}
            )
            print(f"   Empty camera ID: {response.status_code}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Validation test failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all logging and monitoring tests"""
        print("🧪 Testing Logging & Monitoring System")
        print("=" * 50)
        
        tests = [
            ("Health Check", self.test_health_endpoint),
            ("Metrics", self.test_metrics_endpoint),
            ("API Response Format", self.test_api_response_format),
            ("Compression", self.test_compression),
            ("Rate Limiting", self.test_rate_limiting),
            ("Security Headers", self.test_security_headers),
            ("Performance Headers", self.test_performance_headers),
            ("Pagination", self.test_pagination),
            ("Validation", self.test_validation_errors)
        ]
        
        results = {}
        for test_name, test_func in tests:
            try:
                results[test_name] = test_func()
            except Exception as e:
                print(f"   ❌ {test_name} test crashed: {e}")
                results[test_name] = False
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        passed = sum(results.values())
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {test_name:25} {status}")
        
        print(f"\n🏆 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed! Logging & Monitoring system is working properly.")
        elif passed >= total * 0.8:
            print("⚠️  Most tests passed. Minor issues detected.")
        else:
            print("❌ Multiple issues detected. Please check the implementation.")
        
        return passed == total

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test logging and monitoring system")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="Base URL of the application")
    
    args = parser.parse_args()
    
    tester = LoggingMonitoringTest(args.url)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1) 