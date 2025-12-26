import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AnalyticsService } from '../../services/analytics.service';
import { AnalyticsCacheService } from '../../services/analytics-cache.service';
import { VideoService } from '../../services/video.service';
import { Video } from '../../models/video.model';
import {
  AnalyticsSummary,
  AnalyticsSession,
  SpeedingVehicleRecord
} from '../../models/analytics.model';
import { VehicleTimelineChartComponent } from '../shared/charts/vehicle-timeline-chart/vehicle-timeline-chart.component';
import { SpeedGaugeChartComponent } from '../shared/charts/speed-gauge-chart/speed-gauge-chart.component';
import { VehicleTypeChartComponent } from '../shared/charts/vehicle-type-chart/vehicle-type-chart.component';

@Component({
  selector: 'app-analytics-dashboard',
  templateUrl: './analytics-dashboard.component.html',
  styleUrls: ['./analytics-dashboard.component.css'],
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    VehicleTimelineChartComponent,
    SpeedGaugeChartComponent,
    VehicleTypeChartComponent
  ]
})
export class AnalyticsDashboardComponent implements OnInit, OnDestroy {
  videos: Video[] = [];
  sessions: AnalyticsSession[] = [];
  summaries: AnalyticsSummary[] = [];
  speedingVehicles: SpeedingVehicleRecord[] = [];

  selectedVideoId?: number;
  selectedSession?: string;
  
  loading = false;
  error: string | null = null;

  // Active tab
  activeTab: 'overview' | 'sessions' | 'vehicles' = 'overview';

  constructor(
    private analyticsService: AnalyticsService,
    private cacheService: AnalyticsCacheService,
    private videoService: VideoService
  ) {}

  ngOnInit(): void {
    this.loadVideos();
  }

  ngOnDestroy(): void {
    // Cleanup cache periodically
    this.cacheService.cleanup();
  }

  loadVideos(): void {
    this.videoService.getVideos().subscribe({
      next: (response: any) => {
        // Handle both response formats
        if (Array.isArray(response)) {
          this.videos = response;
        } else if (response && response.videos) {
          this.videos = response.videos;
        } else {
          this.videos = [];
        }
        
        if (this.videos.length > 0) {
          this.selectedVideoId = this.videos[0].id;
          this.loadSessions();
        }
      },
      error: (err) => {
        this.error = 'Failed to load videos';
        console.error(err);
      }
    });
  }

  loadSessions(): void {
    if (!this.selectedVideoId) return;

    this.loading = true;
    this.error = null;

    this.analyticsService.getSessions(this.selectedVideoId).subscribe({
      next: (response) => {
        this.sessions = response.sessions;
        this.loading = false;
        
        if (this.sessions.length > 0) {
          this.selectedSession = this.sessions[0].session_start;
          this.loadAnalytics();
        }
      },
      error: (err) => {
        this.error = 'Failed to load sessions';
        this.loading = false;
        console.error(err);
      }
    });
  }

  loadAnalytics(): void {
    if (!this.selectedVideoId) return;

    this.loading = true;
    this.error = null;

    // Use cache service for analytics data
    const cacheKey = `analytics_${this.selectedVideoId}_${this.selectedSession || 'all'}`;
    
    this.cacheService.get(
      cacheKey,
      () => this.analyticsService.getAggregateAnalytics(
        this.selectedVideoId!,
        ['summary', 'speeding'],
        this.selectedSession
      )
    ).subscribe({
      next: (response) => {
        this.summaries = response.summary || [];
        this.speedingVehicles = response.speeding || [];
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Failed to load analytics data';
        this.loading = false;
        console.error(err);
      }
    });
  }

  onVideoChange(): void {
    this.selectedSession = undefined;
    this.sessions = [];
    this.summaries = [];
    this.speedingVehicles = [];
    this.loadSessions();
  }

  onSessionChange(): void {
    this.loadAnalytics();
  }

  setActiveTab(tab: 'overview' | 'sessions' | 'vehicles'): void {
    this.activeTab = tab;
  }

  exportCSV(): void {
    if (!this.selectedVideoId) return;

    this.analyticsService.exportData(
      this.selectedVideoId,
      'csv',
      'speeding',
      this.selectedSession
    ).subscribe({
      next: (data) => {
        this.downloadFile(data, 'speeding_vehicles.csv', 'text/csv');
      },
      error: (err) => {
        console.error('Export failed:', err);
      }
    });
  }

  exportJSON(): void {
    if (!this.selectedVideoId) return;

    this.analyticsService.exportData(
      this.selectedVideoId,
      'json',
      'speeding',
      this.selectedSession
    ).subscribe({
      next: (data) => {
        const jsonStr = JSON.stringify(data, null, 2);
        this.downloadFile(jsonStr, 'speeding_vehicles.json', 'application/json');
      },
      error: (err) => {
        console.error('Export failed:', err);
      }
    });
  }

  private downloadFile(content: string, filename: string, mimeType: string): void {
    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  getVehicleTypeName(classId: number): string {
    switch (classId) {
      case 2: return 'Car';
      case 3: return 'Motorcycle';
      case 5: return 'Bus';
      case 7: return 'Truck';
      default: return 'Other';
    }
  }

  formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString();
  }

  clearCache(): void {
    this.cacheService.clear();
    this.loadAnalytics();
  }

  getSpeedDistributionValue(distribution: any, range: '60-70' | '70-80' | '80-90' | '90+'): number {
    if (!distribution) return 0;
    
    // Handle both key formats
    switch (range) {
      case '60-70':
        return distribution['range_60_70'] ?? distribution['60-70'] ?? 0;
      case '70-80':
        return distribution['range_70_80'] ?? distribution['70-80'] ?? 0;
      case '80-90':
        return distribution['range_80_90'] ?? distribution['80-90'] ?? 0;
      case '90+':
        return distribution['range_90_plus'] ?? distribution['90+'] ?? 0;
      default:
        return 0;
    }
  }
}
