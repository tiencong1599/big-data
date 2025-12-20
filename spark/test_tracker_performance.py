"""
Quick verification script for SORT tracker optimization
Run this to test the new lightweight tracker before full deployment
"""

import numpy as np
import time
import sys
sys.path.append('.')

from tracker import VehicleTracker

def benchmark_tracker():
    """Benchmark the new SORT tracker"""
    
    print("="*70)
    print("TRACKER PERFORMANCE BENCHMARK")
    print("="*70)
    
    # Initialize tracker
    tracker = VehicleTracker()
    
    # Simulate typical detection scenarios
    test_cases = [
        ("Light traffic (6 vehicles)", 6),
        ("Medium traffic (15 vehicles)", 15),
        ("Heavy traffic (30 vehicles)", 30),
        ("Dense traffic (50 vehicles)", 50),
    ]
    
    for scenario_name, num_detections in test_cases:
        # Generate fake detections
        detections = []
        for i in range(num_detections):
            x1 = np.random.randint(100, 800)
            y1 = np.random.randint(100, 500)
            w = np.random.randint(50, 150)
            h = np.random.randint(80, 200)
            x2 = x1 + w
            y2 = y1 + h
            conf = np.random.uniform(0.5, 0.99)
            class_id = 2  # car
            detections.append(([x1, y1, x2, y2], conf, class_id))
        
        # Create dummy frame (tracker doesn't use it in SORT mode)
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        # Warm-up
        tracker.update(dummy_frame, detections)
        
        # Benchmark over multiple frames
        num_iterations = 50
        times = []
        
        for _ in range(num_iterations):
            start = time.time()
            tracks = tracker.update(dummy_frame, detections)
            elapsed = (time.time() - start) * 1000  # ms
            times.append(elapsed)
        
        avg_time = np.mean(times)
        max_time = np.max(times)
        min_time = np.min(times)
        
        print(f"\n{scenario_name}:")
        print(f"  Detections: {num_detections}")
        print(f"  Avg time:   {avg_time:.2f}ms")
        print(f"  Min time:   {min_time:.2f}ms")
        print(f"  Max time:   {max_time:.2f}ms")
        print(f"  FPS impact: ~{1000/avg_time:.1f} FPS capacity")
        
        # Performance check
        if avg_time < 10:
            print(f"  Status:     ✅ EXCELLENT (< 10ms)")
        elif avg_time < 50:
            print(f"  Status:     ✅ GOOD (< 50ms)")
        else:
            print(f"  Status:     ⚠️  SLOW (> 50ms)")
    
    print("\n" + "="*70)
    print("BENCHMARK COMPLETE")
    print("="*70)
    print("\nExpected Results:")
    print("  Light traffic:  < 5ms   ✅")
    print("  Medium traffic: < 10ms  ✅")
    print("  Heavy traffic:  < 20ms  ✅")
    print("  Dense traffic:  < 40ms  ⚠️")
    print("\nPrevious DeepSORT: ~229ms for 6 vehicles ❌")
    print("New SORT: Should be < 5ms for 6 vehicles ✅")
    print("="*70)

if __name__ == "__main__":
    try:
        benchmark_tracker()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\nIf scipy is missing, install it:")
        print("  pip install scipy>=1.10.0")
