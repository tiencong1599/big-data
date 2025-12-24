import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { tap } from 'rxjs/operators';

interface CacheEntry<T> {
  data: T;
  expiry: number;
}

@Injectable({
  providedIn: 'root'
})
export class AnalyticsCacheService {
  private cache = new Map<string, CacheEntry<any>>();
  private readonly DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes

  constructor() {}

  /**
   * Get data from cache or fetch using provided function
   */
  get<T>(key: string, fetchFn: () => Observable<T>, ttl: number = this.DEFAULT_TTL): Observable<T> {
    const cached = this.cache.get(key);
    const now = Date.now();

    // Return cached data if valid
    if (cached && now < cached.expiry) {
      console.log(`[CACHE HIT] ${key}`);
      return of(cached.data);
    }

    // Cache miss or expired - fetch new data
    console.log(`[CACHE MISS] ${key}`);
    return fetchFn().pipe(
      tap(data => {
        this.cache.set(key, {
          data,
          expiry: now + ttl
        });
      })
    );
  }

  /**
   * Invalidate a specific cache entry
   */
  invalidate(key: string): void {
    this.cache.delete(key);
    console.log(`[CACHE INVALIDATE] ${key}`);
  }

  /**
   * Invalidate all cache entries matching a pattern
   */
  invalidatePattern(pattern: RegExp): void {
    const keysToDelete: string[] = [];
    this.cache.forEach((_, key) => {
      if (pattern.test(key)) {
        keysToDelete.push(key);
      }
    });

    keysToDelete.forEach(key => {
      this.cache.delete(key);
      console.log(`[CACHE INVALIDATE] ${key}`);
    });
  }

  /**
   * Clear all cache
   */
  clear(): void {
    this.cache.clear();
    console.log('[CACHE CLEAR] All cache cleared');
  }

  /**
   * Get cache statistics
   */
  getStats(): { size: number; keys: string[] } {
    return {
      size: this.cache.size,
      keys: Array.from(this.cache.keys())
    };
  }

  /**
   * Remove expired entries
   */
  cleanup(): void {
    const now = Date.now();
    const keysToDelete: string[] = [];

    this.cache.forEach((entry, key) => {
      if (now >= entry.expiry) {
        keysToDelete.push(key);
      }
    });

    keysToDelete.forEach(key => this.cache.delete(key));

    if (keysToDelete.length > 0) {
      console.log(`[CACHE CLEANUP] Removed ${keysToDelete.length} expired entries`);
    }
  }
}
