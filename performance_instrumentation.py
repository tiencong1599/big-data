"""
Performance Profiling - Drop-in Timing Instrumentation
Copy these functions into your files to measure performance
"""

import time
import functools

# ============================================================================
# DECORATOR FOR AUTOMATIC TIMING
# ============================================================================

def timeit(func):
    """Decorator to time any function"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = (time.time() - start) * 1000
        print(f"[TIMING] {func.__name__}: {duration:.2f}ms")
        return result
    return wrapper


# ============================================================================
# CONTEXT MANAGER FOR TIMING BLOCKS
# ============================================================================

class Timer:
    """Context manager for timing code blocks"""
    def __init__(self, name="Block"):
        self.name = name
        self.start = None
        
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        duration = (time.time() - self.start) * 1000
        print(f"[TIMING] {self.name}: {duration:.2f}ms")


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

# Example 1: Using decorator
# @timeit
# def my_slow_function():
#     # Your code here
#     pass

# # Example 2: Using context manager
# with Timer("Database Query"):
#     # Your code here
#     pass

# # Example 3: Manual timing
# start = time.time()
# # Your code here
# duration = (time.time() - start) * 1000
# print(f"Operation took: {duration:.2f}ms")