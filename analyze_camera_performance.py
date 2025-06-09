#!/usr/bin/env python3
"""
Script phân tích performance thực tế cho face detection nhiều camera
"""

import asyncio
import time
import psutil
import threading
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import os
import sys
from typing import List, Dict, Tuple

class PerformanceAnalyzer:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.results = []
        
    def simulate_camera_stream(self, camera_id: str, duration_seconds: int = 10) -> Dict:
        """Simulate camera stream để test performance"""
        start_time = time.time()
        frames_processed = 0
        total_detection_time = 0
        
        while time.time() - start_time < duration_seconds:
            frame_start = time.time()
            
            # Tạo fake frame (giống như nhận từ camera)
            frame = self._generate_test_frame(camera_id)
            
            # Face detection
            detection_start = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            detection_time = time.time() - detection_start
            
            total_detection_time += detection_time
            frames_processed += 1
            
            # Simulate frame rate (30 FPS)
            frame_time = time.time() - frame_start
            if frame_time < 1/30:  # 30 FPS
                time.sleep(1/30 - frame_time)
        
        actual_duration = time.time() - start_time
        
        return {
            "camera_id": camera_id,
            "duration": actual_duration,
            "frames_processed": frames_processed,
            "fps": frames_processed / actual_duration,
            "avg_detection_time": total_detection_time / frames_processed if frames_processed > 0 else 0,
            "total_detection_time": total_detection_time
        }
    
    def _generate_test_frame(self, camera_id: str) -> np.ndarray:
        """Tạo test frame với khả năng có face"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 40% chance có face để test
        if np.random.random() < 0.4:
            # Vẽ fake face
            cv2.circle(frame, (320, 240), 80, (0, 0, 255), -1)
            cv2.circle(frame, (290, 210), 15, (255, 255, 255), -1)  # Eye
            cv2.circle(frame, (350, 210), 15, (255, 255, 255), -1)  # Eye
            cv2.ellipse(frame, (320, 270), (40, 20), 0, 0, 180, (255, 255, 255), -1)  # Mouth
        
        # Add camera label
        cv2.putText(frame, f"CAM_{camera_id}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        return frame
    
    def test_single_camera_performance(self, duration: int = 10) -> Dict:
        """Test performance 1 camera"""
        print("🎥 Testing Single Camera Performance...")
        
        cpu_before = psutil.cpu_percent()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        result = self.simulate_camera_stream("test_cam", duration)
        
        cpu_after = psutil.cpu_percent()
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        result.update({
            "cpu_usage": cpu_after - cpu_before,
            "memory_usage_mb": memory_after - memory_before
        })
        
        return result
    
    def test_multiple_cameras_sequential(self, camera_count: int, duration: int = 10) -> List[Dict]:
        """Test multiple cameras - sequential processing"""
        print(f"📹 Testing {camera_count} Cameras (Sequential)...")
        
        start_time = time.time()
        cpu_before = psutil.cpu_percent()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        results = []
        for i in range(camera_count):
            camera_result = self.simulate_camera_stream(f"cam_{i}", duration)
            results.append(camera_result)
        
        total_time = time.time() - start_time
        cpu_after = psutil.cpu_percent()
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        summary = {
            "method": "sequential",
            "camera_count": camera_count,
            "total_time": total_time,
            "cpu_usage": cpu_after - cpu_before,
            "memory_usage_mb": memory_after - memory_before,
            "avg_fps": sum(r["fps"] for r in results) / len(results),
            "total_frames": sum(r["frames_processed"] for r in results)
        }
        
        return results, summary
    
    def test_multiple_cameras_parallel(self, camera_count: int, duration: int = 10, max_workers: int = 4) -> List[Dict]:
        """Test multiple cameras - parallel processing"""
        print(f"🎬 Testing {camera_count} Cameras (Parallel, {max_workers} workers)...")
        
        start_time = time.time()
        cpu_before = psutil.cpu_percent()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(camera_count):
                future = executor.submit(self.simulate_camera_stream, f"cam_{i}", duration)
                futures.append(future)
            
            results = []
            for future in futures:
                try:
                    result = future.result(timeout=duration + 10)
                    results.append(result)
                except Exception as e:
                    print(f"   ❌ Camera failed: {e}")
        
        total_time = time.time() - start_time
        cpu_after = psutil.cpu_percent()
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        summary = {
            "method": "parallel",
            "camera_count": camera_count,
            "max_workers": max_workers,
            "total_time": total_time,
            "cpu_usage": cpu_after - cpu_before,
            "memory_usage_mb": memory_after - memory_before,
            "avg_fps": sum(r["fps"] for r in results) / len(results) if results else 0,
            "total_frames": sum(r["frames_processed"] for r in results),
            "successful_cameras": len(results)
        }
        
        return results, summary
    
    async def test_multiple_cameras_async(self, camera_count: int, duration: int = 10) -> List[Dict]:
        """Test multiple cameras - async processing"""
        print(f"🚀 Testing {camera_count} Cameras (Async)...")
        
        start_time = time.time()
        cpu_before = psutil.cpu_percent()
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        tasks = []
        for i in range(camera_count):
            task = asyncio.create_task(self._async_camera_simulation(f"cam_{i}", duration))
            tasks.append(task)
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_results = [r for r in results if isinstance(r, dict)]
        except Exception as e:
            print(f"   ❌ Async processing failed: {e}")
            successful_results = []
        
        total_time = time.time() - start_time
        cpu_after = psutil.cpu_percent()
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        
        summary = {
            "method": "async",
            "camera_count": camera_count,
            "total_time": total_time,
            "cpu_usage": cpu_after - cpu_before,
            "memory_usage_mb": memory_after - memory_before,
            "avg_fps": sum(r["fps"] for r in successful_results) / len(successful_results) if successful_results else 0,
            "total_frames": sum(r["frames_processed"] for r in successful_results),
            "successful_cameras": len(successful_results)
        }
        
        return successful_results, summary
    
    async def _async_camera_simulation(self, camera_id: str, duration: int) -> Dict:
        """Async version of camera simulation"""
        loop = asyncio.get_event_loop()
        
        # Run CPU-intensive work in thread pool
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(
                executor,
                self.simulate_camera_stream,
                camera_id,
                duration
            )
        
        return result
    
    def get_system_specs(self) -> Dict:
        """Lấy thông tin system specs"""
        return {
            "cpu_count": psutil.cpu_count(),
            "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else "Unknown",
            "memory_total_gb": psutil.virtual_memory().total / 1024 / 1024 / 1024,
            "memory_available_gb": psutil.virtual_memory().available / 1024 / 1024 / 1024,
            "python_version": sys.version.split()[0],
            "opencv_version": cv2.__version__
        }
    
    def print_results(self, results: List[Dict], summary: Dict, system_specs: Dict):
        """Print performance results"""
        print("\n" + "="*60)
        print("📊 PERFORMANCE ANALYSIS RESULTS")
        print("="*60)
        
        print("\n💻 System Specifications:")
        print(f"   CPU Cores: {system_specs['cpu_count']}")
        print(f"   CPU Frequency: {system_specs['cpu_freq']:.0f} MHz")
        print(f"   Total Memory: {system_specs['memory_total_gb']:.1f} GB")
        print(f"   Available Memory: {system_specs['memory_available_gb']:.1f} GB")
        print(f"   Python: {system_specs['python_version']}")
        print(f"   OpenCV: {system_specs['opencv_version']}")
        
        print(f"\n🎯 Test Summary ({summary['method'].upper()}):")
        print(f"   Cameras Tested: {summary['camera_count']}")
        if 'max_workers' in summary:
            print(f"   Max Workers: {summary['max_workers']}")
        print(f"   Successful Cameras: {summary['successful_cameras']}")
        print(f"   Total Time: {summary['total_time']:.2f}s")
        print(f"   CPU Usage: {summary['cpu_usage']:.1f}%")
        print(f"   Memory Usage: {summary['memory_usage_mb']:.1f} MB")
        print(f"   Average FPS: {summary['avg_fps']:.1f}")
        print(f"   Total Frames: {summary['total_frames']}")
        
        if results:
            print(f"\n📹 Per-Camera Performance:")
            for result in results[:5]:  # Show first 5 cameras
                print(f"   {result['camera_id']}: {result['fps']:.1f} FPS, "
                      f"{result['avg_detection_time']*1000:.1f}ms/detection")
            
            if len(results) > 5:
                print(f"   ... and {len(results)-5} more cameras")
    
    def run_comprehensive_test(self):
        """Chạy comprehensive performance test"""
        print("🧪 Starting Comprehensive Camera Performance Analysis")
        print("="*60)
        
        system_specs = self.get_system_specs()
        
        # Test configurations
        test_configs = [
            {"cameras": 1, "duration": 5},
            {"cameras": 5, "duration": 5},
            {"cameras": 10, "duration": 5},
            {"cameras": 15, "duration": 5},
            {"cameras": 20, "duration": 5},
            {"cameras": 25, "duration": 5},
            {"cameras": 30, "duration": 5}
        ]
        
        print(f"\n📋 Test Plan: {len(test_configs)} configurations")
        for config in test_configs:
            print(f"   - {config['cameras']} cameras for {config['duration']}s")
        
        all_results = []
        
        for config in test_configs:
            camera_count = config["cameras"]
            duration = config["duration"]
            
            print(f"\n" + "-"*40)
            print(f"🎬 Testing {camera_count} cameras...")
            
            # Test parallel processing
            try:
                results, summary = self.test_multiple_cameras_parallel(
                    camera_count, duration, max_workers=4
                )
                
                all_results.append({
                    "config": config,
                    "results": results,
                    "summary": summary
                })
                
                self.print_results(results, summary, system_specs)
                
                # Determine if this is the breaking point
                success_rate = summary['successful_cameras'] / camera_count
                avg_fps = summary['avg_fps']
                cpu_usage = summary['cpu_usage']
                
                print(f"\n📈 Performance Metrics:")
                print(f"   Success Rate: {success_rate*100:.1f}%")
                print(f"   FPS per Camera: {avg_fps:.1f}")
                print(f"   CPU Usage: {cpu_usage:.1f}%")
                
                if success_rate < 0.8 or avg_fps < 10 or cpu_usage > 80:
                    print(f"   ⚠️  Performance degradation detected!")
                    print(f"   📊 Recommended limit: {max(1, camera_count-5)} cameras")
                    break
                    
            except Exception as e:
                print(f"   ❌ Test failed: {e}")
                break
        
        # Final recommendations
        print("\n" + "="*60)
        print("🎯 FINAL RECOMMENDATIONS")
        print("="*60)
        
        if all_results:
            good_results = [r for r in all_results 
                          if r['summary']['successful_cameras'] / r['config']['cameras'] >= 0.8
                          and r['summary']['avg_fps'] >= 10]
            
            if good_results:
                best_result = max(good_results, key=lambda x: x['config']['cameras'])
                max_cameras = best_result['config']['cameras']
                
                print(f"✅ Recommended Maximum: {max_cameras} cameras")
                print(f"   - Success Rate: {best_result['summary']['successful_cameras'] / max_cameras * 100:.1f}%")
                print(f"   - Average FPS: {best_result['summary']['avg_fps']:.1f}")
                print(f"   - CPU Usage: {best_result['summary']['cpu_usage']:.1f}%")
                print(f"   - Memory Usage: {best_result['summary']['memory_usage_mb']:.1f} MB")
            else:
                print("❌ System cannot handle multiple cameras effectively")
                print("   Consider upgrading hardware or optimizing detection algorithm")
        
        print(f"\n🔧 Optimization Suggestions:")
        print(f"   1. Use lower resolution streams (720p instead of 1080p)")
        print(f"   2. Reduce detection frequency (every 2-3 frames)")
        print(f"   3. Use hardware acceleration (GPU/Intel Quick Sync)")
        print(f"   4. Implement frame skipping under high load")
        print(f"   5. Use separate detection servers for scaling")

if __name__ == "__main__":
    analyzer = PerformanceAnalyzer()
    
    try:
        analyzer.run_comprehensive_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc() 
