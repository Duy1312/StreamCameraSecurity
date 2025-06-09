#!/usr/bin/env python3
"""
Simple Performance Test cho Face Detection nhiều camera
Không cần psutil, chỉ test cơ bản
"""

import time
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Dict

class SimpleCameraPerformanceTest:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.results = []
        
    def generate_test_frame(self, camera_id: str) -> np.ndarray:
        """Tạo test frame với fake face"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 30% chance có face
        if np.random.random() < 0.3:
            # Vẽ fake face
            cv2.circle(frame, (320, 240), 80, (255, 255, 255), 2)
            cv2.circle(frame, (290, 210), 15, (255, 255, 255), -1)  # Eye
            cv2.circle(frame, (350, 210), 15, (255, 255, 255), -1)  # Eye
            cv2.ellipse(frame, (320, 270), (40, 20), 0, 0, 180, (255, 255, 255), 2)  # Mouth
        
        # Camera label
        cv2.putText(frame, f"CAM_{camera_id}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        return frame
    
    def process_single_camera(self, camera_id: str, duration_seconds: int = 5) -> Dict:
        """Process single camera for testing"""
        start_time = time.time()
        frames_processed = 0
        faces_detected = 0
        total_detection_time = 0
        
        print(f"   🎥 Starting camera {camera_id}...")
        
        while time.time() - start_time < duration_seconds:
            # Generate frame
            frame = self.generate_test_frame(camera_id)
            
            # Face detection timing
            detection_start = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
            detection_time = time.time() - detection_start
            
            total_detection_time += detection_time
            frames_processed += 1
            if len(faces) > 0:
                faces_detected += 1
            
            # Simulate 30 FPS
            time.sleep(1/30)
        
        actual_duration = time.time() - start_time
        
        result = {
            "camera_id": camera_id,
            "duration": actual_duration,
            "frames_processed": frames_processed,
            "faces_detected": faces_detected,
            "fps": frames_processed / actual_duration,
            "avg_detection_time_ms": (total_detection_time / frames_processed) * 1000 if frames_processed > 0 else 0,
            "detection_rate": faces_detected / frames_processed if frames_processed > 0 else 0
        }
        
        print(f"   ✅ Camera {camera_id}: {result['fps']:.1f} FPS, {result['avg_detection_time_ms']:.1f}ms/detection")
        return result
    
    def test_sequential_cameras(self, camera_count: int, duration: int = 5) -> Dict:
        """Test cameras sequentially"""
        print(f"\n📹 Testing {camera_count} cameras SEQUENTIALLY...")
        
        start_time = time.time()
        results = []
        
        for i in range(camera_count):
            result = self.process_single_camera(f"seq_{i}", duration)
            results.append(result)
        
        total_time = time.time() - start_time
        
        summary = {
            "method": "sequential",
            "camera_count": camera_count,
            "total_time": total_time,
            "avg_fps": sum(r["fps"] for r in results) / len(results),
            "total_frames": sum(r["frames_processed"] for r in results),
            "avg_detection_time": sum(r["avg_detection_time_ms"] for r in results) / len(results),
            "results": results
        }
        
        print(f"   📊 Sequential Summary: {summary['avg_fps']:.1f} avg FPS, {summary['total_time']:.1f}s total")
        return summary
    
    def test_parallel_cameras(self, camera_count: int, duration: int = 5, max_workers: int = 4) -> Dict:
        """Test cameras in parallel"""
        print(f"\n🎬 Testing {camera_count} cameras PARALLEL ({max_workers} workers)...")
        
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(self.process_single_camera, f"par_{i}", duration): i 
                for i in range(camera_count)
            }
            
            # Collect results
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=duration + 5)
                    results.append(result)
                except Exception as e:
                    camera_id = futures[future]
                    print(f"   ❌ Camera par_{camera_id} failed: {e}")
        
        total_time = time.time() - start_time
        
        if results:
            summary = {
                "method": "parallel",
                "camera_count": camera_count,
                "successful_cameras": len(results),
                "max_workers": max_workers,
                "total_time": total_time,
                "avg_fps": sum(r["fps"] for r in results) / len(results),
                "total_frames": sum(r["frames_processed"] for r in results),
                "avg_detection_time": sum(r["avg_detection_time_ms"] for r in results) / len(results),
                "results": results
            }
        else:
            summary = {
                "method": "parallel",
                "camera_count": camera_count,
                "successful_cameras": 0,
                "max_workers": max_workers,
                "total_time": total_time,
                "avg_fps": 0,
                "total_frames": 0,
                "avg_detection_time": 0,
                "results": []
            }
        
        success_rate = summary['successful_cameras'] / camera_count * 100
        print(f"   📊 Parallel Summary: {summary['successful_cameras']}/{camera_count} cameras ({success_rate:.1f}% success)")
        print(f"      Average FPS: {summary['avg_fps']:.1f}, Total time: {summary['total_time']:.1f}s")
        
        return summary
    
    def run_comprehensive_test(self):
        """Chạy comprehensive test"""
        print("🧪 SIMPLE CAMERA PERFORMANCE TEST")
        print("="*50)
        print("Testing face detection performance với nhiều camera")
        print(f"OpenCV version: {cv2.__version__}")
        
        # Test configurations
        test_configs = [1, 5, 10, 15, 20, 25]
        duration = 3  # 3 seconds per test for speed
        
        print(f"\n📋 Test Plan: {len(test_configs)} configurations")
        for cameras in test_configs:
            print(f"   - {cameras} cameras × {duration}s")
        
        parallel_results = []
        
        for camera_count in test_configs:
            print(f"\n" + "-"*30)
            print(f"🎯 Testing {camera_count} cameras...")
            
            try:
                # Test parallel (main method)
                parallel_summary = self.test_parallel_cameras(camera_count, duration, max_workers=4)
                parallel_results.append(parallel_summary)
                
                # Performance analysis
                success_rate = parallel_summary['successful_cameras'] / camera_count
                avg_fps = parallel_summary['avg_fps']
                avg_detection = parallel_summary['avg_detection_time']
                
                print(f"   📈 Results:")
                print(f"      Success: {success_rate*100:.1f}% ({parallel_summary['successful_cameras']}/{camera_count})")
                print(f"      FPS per camera: {avg_fps:.1f}")
                print(f"      Detection time: {avg_detection:.1f}ms")
                
                # Check if performance is degrading
                if success_rate < 0.8:
                    print(f"   ⚠️  Success rate dropped below 80%!")
                    print(f"   📊 Recommended limit: {max(1, camera_count-5)} cameras")
                    break
                elif avg_fps < 15:
                    print(f"   ⚠️  FPS dropped below 15!")
                    print(f"   📊 Recommended limit: {max(1, camera_count-5)} cameras")
                    break
                elif avg_detection > 100:  # 100ms is quite slow
                    print(f"   ⚠️  Detection time too slow (>100ms)!")
                    print(f"   📊 Recommended limit: {max(1, camera_count-5)} cameras")
                    break
                    
            except Exception as e:
                print(f"   ❌ Test failed: {e}")
                break
        
        # Final analysis
        self.print_final_analysis(parallel_results)
    
    def print_final_analysis(self, results: List[Dict]):
        """Print final analysis and recommendations"""
        print("\n" + "="*50)
        print("🎯 FINAL ANALYSIS & RECOMMENDATIONS")
        print("="*50)
        
        if not results:
            print("❌ No successful tests completed")
            return
        
        # Find best performing configuration
        good_results = [r for r in results 
                       if r['successful_cameras'] / r['camera_count'] >= 0.8 
                       and r['avg_fps'] >= 15]
        
        if good_results:
            best_result = max(good_results, key=lambda x: x['camera_count'])
            
            print(f"✅ RECOMMENDED MAXIMUM: {best_result['camera_count']} cameras")
            print(f"   Success Rate: {best_result['successful_cameras'] / best_result['camera_count'] * 100:.1f}%")
            print(f"   Average FPS: {best_result['avg_fps']:.1f}")
            print(f"   Detection Time: {best_result['avg_detection_time']:.1f}ms")
            print(f"   Total Processing Time: {best_result['total_time']:.1f}s")
            
            # Performance extrapolation
            print(f"\n📊 Performance Metrics for {best_result['camera_count']} cameras:")
            total_fps = best_result['avg_fps'] * best_result['camera_count']
            print(f"   Total FPS: {total_fps:.1f}")
            print(f"   Frames per second system-wide: {total_fps:.1f}")
            print(f"   Estimated CPU usage: {best_result['camera_count'] * 15:.0f}% (rough estimate)")
            print(f"   Estimated memory: {best_result['camera_count'] * 50:.0f}MB (rough estimate)")
        else:
            print("❌ System performance insufficient for reliable multi-camera detection")
            if results:
                last_result = results[-1]
                print(f"   Last successful test: {last_result['camera_count']} cameras")
                print(f"   Success rate: {last_result['successful_cameras'] / last_result['camera_count'] * 100:.1f}%")
        
        print(f"\n🔧 OPTIMIZATION RECOMMENDATIONS:")
        print(f"   1. Resolution: Use 480p instead of 720p/1080p")
        print(f"   2. Frame Rate: Reduce to 15-20 FPS instead of 30 FPS")
        print(f"   3. Detection Interval: Skip frames (detect every 2-3 frames)")
        print(f"   4. Algorithm: Consider lighter detection models")
        print(f"   5. Hardware: Use dedicated GPU or multiple CPU cores")
        print(f"   6. Architecture: Distribute cameras across multiple servers")
        
        print(f"\n💡 SCALING STRATEGIES:")
        print(f"   - For 20+ cameras: Use distributed processing")
        print(f"   - For 50+ cameras: Dedicated detection servers")
        print(f"   - For 100+ cameras: Load balancing + Redis clustering")
        
        # Detailed results table
        print(f"\n📋 Detailed Results:")
        print(f"{'Cameras':<8} {'Success%':<8} {'Avg FPS':<8} {'Detection(ms)':<12} {'Total Time':<10}")
        print("-" * 50)
        for result in results:
            success_pct = result['successful_cameras'] / result['camera_count'] * 100
            print(f"{result['camera_count']:<8} {success_pct:<8.1f} {result['avg_fps']:<8.1f} "
                  f"{result['avg_detection_time']:<12.1f} {result['total_time']:<10.1f}")

if __name__ == "__main__":
    tester = SimpleCameraPerformanceTest()
    
    try:
        tester.run_comprehensive_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc() 