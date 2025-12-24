import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  AnalyticsAggregateResponse,
  AnalyticsSummary,
  AnalyticsSnapshot,
  SpeedingVehicleRecord,
  AnalyticsSession
} from '../models/analytics.model';

@Injectable({
  providedIn: 'root'
})
export class AnalyticsService {
  private apiUrl = 'http://localhost:8686/api/analytics';

  constructor(private http: HttpClient) {}

  /**
   * Get aggregated analytics data (optimized single endpoint)
   */
  getAggregateAnalytics(
    videoId: number,
    includes: string[] = ['summary', 'snapshots', 'speeding', 'trends'],
    sessionStart?: string,
    limit: number = 100
  ): Observable<AnalyticsAggregateResponse> {
    let params = new HttpParams()
      .set('video_id', videoId.toString())
      .set('include', includes.join(','))
      .set('limit', limit.toString());

    // Only add session_start if it's defined and not 'undefined' string
    if (sessionStart && sessionStart !== 'undefined') {
      params = params.set('session_start', sessionStart);
    }

    return this.http.get<AnalyticsAggregateResponse>(`${this.apiUrl}/aggregate`, { params });
  }

  /**
   * Get summary statistics
   */
  getSummary(videoId: number, sessionStart?: string): Observable<{ summaries: AnalyticsSummary[] }> {
    let params = new HttpParams().set('video_id', videoId.toString());
    if (sessionStart && sessionStart !== 'undefined') {
      params = params.set('session_start', sessionStart);
    }
    return this.http.get<{ summaries: AnalyticsSummary[] }>(`${this.apiUrl}/summary`, { params });
  }

  /**
   * Get analytics snapshots
   */
  getSnapshots(
    videoId: number,
    sessionStart?: string,
    limit: number = 100
  ): Observable<{ snapshots: AnalyticsSnapshot[] }> {
    let params = new HttpParams()
      .set('video_id', videoId.toString())
      .set('limit', limit.toString());

    if (sessionStart && sessionStart !== 'undefined') {
      params = params.set('session_start', sessionStart);
    }

    return this.http.get<{ snapshots: AnalyticsSnapshot[] }>(`${this.apiUrl}/snapshots`, { params });
  }

  /**
   * Get speeding vehicles
   */
  getSpeedingVehicles(
    videoId: number,
    sessionStart?: string,
    limit: number = 100
  ): Observable<{ vehicles: SpeedingVehicleRecord[] }> {
    let params = new HttpParams()
      .set('video_id', videoId.toString())
      .set('limit', limit.toString());

    if (sessionStart && sessionStart !== 'undefined') {
      params = params.set('session_start', sessionStart);
    }

    return this.http.get<{ vehicles: SpeedingVehicleRecord[] }>(`${this.apiUrl}/speeding`, { params });
  }

  /**
   * Get available sessions for a video
   */
  getSessions(videoId: number): Observable<{ sessions: AnalyticsSession[] }> {
    const params = new HttpParams().set('video_id', videoId.toString());
    return this.http.get<{ sessions: AnalyticsSession[] }>(`${this.apiUrl}/sessions`, { params });
  }

  /**
   * Export analytics data
   */
  exportData(
    videoId: number,
    format: 'json' | 'csv',
    type: 'speeding' | 'summary',
    sessionStart?: string
  ): Observable<any> {
    let params = new HttpParams()
      .set('video_id', videoId.toString())
      .set('format', format)
      .set('type', type);

    if (sessionStart && sessionStart !== 'undefined') {
      params = params.set('session_start', sessionStart);
    }

    const responseType = format === 'csv' ? 'text' : 'json';
    return this.http.get(`${this.apiUrl}/export`, { params, responseType: responseType as any });
  }
}
