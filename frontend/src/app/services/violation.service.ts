/**
 * Violation Service
 * Handles API communication for speed violation data
 */

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { map, tap, catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import {
  ViolationCapture,
  ViolationStats,
  ViolationListResponse,
  ViolationFilter,
  SortField,
  SortOrder,
  ExportFormat
} from '../models/violation.model';

@Injectable({
  providedIn: 'root'
})
export class ViolationService {
  private apiUrl = `${environment.apiUrl}/violations`;

  constructor(private http: HttpClient) {
    console.log('[VIOLATION-SERVICE] Initialized with API URL:', this.apiUrl);
  }

  /**
   * Get violations with filtering, sorting, and pagination
   */
  getViolations(
    filter: ViolationFilter = {},
    limit: number = 50,
    offset: number = 0,
    sortBy: SortField = 'violation_timestamp',
    sortOrder: SortOrder = 'desc'
  ): Observable<ViolationListResponse> {
    let params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString())
      .set('sort_by', sortBy)
      .set('sort_order', sortOrder);

    // Add optional filters
    if (filter.video_id !== undefined && filter.video_id !== null) {
      params = params.set('video_id', filter.video_id.toString());
    }
    if (filter.session_start) {
      params = params.set('session_start', filter.session_start);
    }
    if (filter.vehicle_type) {
      params = params.set('vehicle_type', filter.vehicle_type);
    }
    if (filter.min_speed !== undefined && filter.min_speed !== null) {
      params = params.set('min_speed', filter.min_speed.toString());
    }
    if (filter.max_speed !== undefined && filter.max_speed !== null) {
      params = params.set('max_speed', filter.max_speed.toString());
    }
    if (filter.date_from) {
      params = params.set('date_from', filter.date_from);
    }
    if (filter.date_to) {
      params = params.set('date_to', filter.date_to);
    }

    console.log('[VIOLATION-SERVICE] Fetching violations with params:', params.toString());

    return this.http.get<ViolationListResponse>(this.apiUrl, { params }).pipe(
      tap(response => console.log('[VIOLATION-SERVICE] Received violations:', response.total)),
      catchError(this.handleError('getViolations'))
    );
  }

  /**
   * Get single violation details
   */
  getViolation(id: number): Observable<{ violation: ViolationCapture }> {
    console.log('[VIOLATION-SERVICE] Fetching violation:', id);
    return this.http.get<{ violation: ViolationCapture }>(`${this.apiUrl}/${id}`).pipe(
      tap(response => console.log('[VIOLATION-SERVICE] Received violation:', response)),
      catchError(this.handleError('getViolation'))
    );
  }

  /**
   * Get violation statistics
   */
  getStats(videoId?: number, sessionStart?: string): Observable<ViolationStats> {
    let params = new HttpParams();
    
    if (videoId !== undefined && videoId !== null) {
      params = params.set('video_id', videoId.toString());
    }
    if (sessionStart) {
      params = params.set('session_start', sessionStart);
    }

    console.log('[VIOLATION-SERVICE] Fetching stats');
    return this.http.get<ViolationStats>(`${this.apiUrl}/stats`, { params }).pipe(
      tap(stats => console.log('[VIOLATION-SERVICE] Received stats:', stats)),
      catchError(this.handleError('getStats'))
    );
  }

  /**
   * Delete a single violation
   */
  deleteViolation(id: number): Observable<{ message: string; files_deleted: string[] }> {
    console.log('[VIOLATION-SERVICE] Deleting violation:', id);
    return this.http.delete<{ message: string; files_deleted: string[] }>(`${this.apiUrl}/${id}`).pipe(
      tap(response => console.log('[VIOLATION-SERVICE] Deleted:', response)),
      catchError(this.handleError('deleteViolation'))
    );
  }

  /**
   * Bulk delete violations
   */
  bulkDelete(
    ids?: number[],
    videoId?: number,
    sessionStart?: string
  ): Observable<{ message: string; records_deleted: number; files_deleted: number }> {
    const body: any = {};
    
    if (ids && ids.length > 0) {
      body.ids = ids;
    } else if (videoId !== undefined) {
      body.video_id = videoId;
      if (sessionStart) {
        body.session_start = sessionStart;
      }
    }

    console.log('[VIOLATION-SERVICE] Bulk deleting:', body);
    return this.http.post<{ message: string; records_deleted: number; files_deleted: number }>(
      `${this.apiUrl}/bulk-delete`,
      body
    ).pipe(
      tap(response => console.log('[VIOLATION-SERVICE] Bulk deleted:', response)),
      catchError(this.handleError('bulkDelete'))
    );
  }

  /**
   * Export violations
   */
  exportViolations(
    format: ExportFormat,
    videoId?: number,
    sessionStart?: string
  ): Observable<Blob | any> {
    let params = new HttpParams().set('format', format);
    
    if (videoId !== undefined && videoId !== null) {
      params = params.set('video_id', videoId.toString());
    }
    if (sessionStart) {
      params = params.set('session_start', sessionStart);
    }

    console.log('[VIOLATION-SERVICE] Exporting violations as', format);

    if (format === 'csv') {
      return this.http.get(`${this.apiUrl}/export`, {
        params,
        responseType: 'blob'
      }).pipe(
        tap(() => console.log('[VIOLATION-SERVICE] CSV export complete')),
        catchError(this.handleError('exportViolations'))
      );
    } else {
      return this.http.get(`${this.apiUrl}/export`, {
        params,
        responseType: 'blob'
      }).pipe(
        tap(() => console.log('[VIOLATION-SERVICE] JSON export complete')),
        catchError(this.handleError('exportViolations'))
      );
    }
  }

  /**
   * Placeholder image as data URI for missing images
   */
  private placeholderImage = 'data:image/svg+xml,' + encodeURIComponent(`<svg width="320" height="180" xmlns="http://www.w3.org/2000/svg">
    <rect width="320" height="180" fill="#f0f0f0"/>
    <text x="50%" y="45%" font-family="Arial" font-size="14" fill="#999" text-anchor="middle">Image Not Available</text>
    <path d="M145 100 L155 100 L155 85 L165 85 L165 80 L135 80 L135 85 L145 85 Z M150 90 C142 90 135 97 135 105 C135 113 142 120 150 120 C158 120 165 113 165 105 C165 97 158 90 150 90 Z M150 115 C144.5 115 140 110.5 140 105 C140 99.5 144.5 95 150 95 C155.5 95 160 99.5 160 105 C160 110.5 155.5 115 150 115 Z" fill="#ccc"/>
  </svg>`);

  /**
   * Get placeholder image URL
   */
  getPlaceholderUrl(): string {
    return this.placeholderImage;
  }

  /**
   * Get full image URL for a violation
   */
  getImageUrl(imagePath: string | null | undefined): string {
    if (!imagePath) return this.placeholderImage;
    // Encode each path segment to handle special characters
    const encodedPath = imagePath.split('/').map(segment => encodeURIComponent(segment)).join('/');
    return `${this.apiUrl}/images/${encodedPath}`;
  }

  /**
   * Get thumbnail URL for a violation
   */
  getThumbnailUrl(thumbnailPath: string | null | undefined): string {
    if (!thumbnailPath) return this.placeholderImage;
    const encodedPath = thumbnailPath.split('/').map(segment => encodeURIComponent(segment)).join('/');
    return `${this.apiUrl}/images/${encodedPath}`;
  }

  /**
   * Download exported file
   */
  downloadExport(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  /**
   * Error handler
   */
  private handleError(operation: string) {
    return (error: any): Observable<never> => {
      console.error(`[VIOLATION-SERVICE] ${operation} failed:`, error);
      return throwError(() => error);
    };
  }
}
