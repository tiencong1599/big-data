/**
 * Violation Dashboard Component
 * Displays speed violation captures with filtering, stats, and management
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, BehaviorSubject } from 'rxjs';
import { takeUntil, debounceTime, distinctUntilChanged, switchMap } from 'rxjs/operators';

import { ViolationService } from '../../services/violation.service';
import { VideoService } from '../../services/video.service';
import {
  ViolationCapture,
  ViolationStats,
  ViolationFilter,
  ViolationListResponse,
  SortField,
  SortOrder,
  ExportFormat,
  getVehicleEmoji,
  getSpeedSeverity,
  getSeverityColor
} from '../../models/violation.model';
import { Video } from '../../models/video.model';

@Component({
  selector: 'app-violation-dashboard',
  templateUrl: './violation-dashboard.component.html',
  styleUrls: ['./violation-dashboard.component.css'],
  standalone: true,
  imports: [CommonModule, FormsModule]
})
export class ViolationDashboardComponent implements OnInit, OnDestroy {
  // Data
  violations: ViolationCapture[] = [];
  videos: Video[] = [];
  stats: ViolationStats | null = null;
  
  // Pagination
  totalViolations = 0;
  currentPage = 1;
  pageSize = 20;
  pageSizeOptions = [10, 20, 50, 100];
  
  // Sorting
  sortBy: SortField = 'violation_timestamp';
  sortOrder: SortOrder = 'desc';
  
  // Filters
  filter: ViolationFilter = {};
  vehicleTypes = ['car', 'truck', 'bus', 'motorcycle'];
  
  // UI State
  loading = false;
  statsLoading = false;
  error: string | null = null;
  selectedViolation: ViolationCapture | null = null;
  showImageModal = false;
  showDeleteConfirm = false;
  deleteTarget: ViolationCapture | null = null;
  
  // Selection for bulk operations
  selectedIds: Set<number> = new Set();
  selectAll = false;
  
  // Reactive streams
  private destroy$ = new Subject<void>();
  private filterChange$ = new BehaviorSubject<ViolationFilter>({});

  // Helper functions exposed to template
  getVehicleEmoji = getVehicleEmoji;
  getSpeedSeverity = getSpeedSeverity;
  getSeverityColor = getSeverityColor;

  constructor(
    private violationService: ViolationService,
    private videoService: VideoService
  ) {}

  ngOnInit(): void {
    console.log('[VIOLATION-DASHBOARD] ngOnInit called');
    this.loadVideos();
    this.loadStats();
    
    // Setup reactive filter handling with debounce
    this.filterChange$.pipe(
      debounceTime(300),
      distinctUntilChanged((prev, curr) => JSON.stringify(prev) === JSON.stringify(curr)),
      takeUntil(this.destroy$)
    ).subscribe(() => {
      this.currentPage = 1;
      this.loadViolations();
      this.loadStats();
    });
    
    // Initial load
    this.loadViolations();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ============================================================================
  // Data Loading
  // ============================================================================

  loadVideos(): void {
    this.videoService.getVideos().pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: (response) => {
        this.videos = response?.videos || [];
        console.log('[VIOLATION-DASHBOARD] Videos loaded:', this.videos.length);
      },
      error: (err) => {
        console.error('Error loading videos:', err);
        this.videos = [];
      }
    });
  }

  loadViolations(): void {
    this.loading = true;
    this.error = null;

    const offset = (this.currentPage - 1) * this.pageSize;

    this.violationService.getViolations(
      this.filter,
      this.pageSize,
      offset,
      this.sortBy,
      this.sortOrder
    ).pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: (response: ViolationListResponse) => {
        this.violations = response.violations;
        this.totalViolations = response.total;
        this.loading = false;
        this.clearSelection();
      },
      error: (err) => {
        this.error = 'Failed to load violations. Please try again.';
        this.loading = false;
        console.error('Error loading violations:', err);
      }
    });
  }

  loadStats(): void {
    console.log('[VIOLATION-DASHBOARD] loadStats called');
    this.statsLoading = true;
    
    this.violationService.getStats(
      this.filter.video_id,
      this.filter.session_start
    ).pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: (stats) => {
        console.log('[VIOLATION-DASHBOARD] Stats received:', stats);
        this.stats = stats;
        this.statsLoading = false;
      },
      error: (err) => {
        console.error('[VIOLATION-DASHBOARD] Error loading stats:', err);
        this.statsLoading = false;
      }
    });
  }

  // ============================================================================
  // Filtering
  // ============================================================================

  onFilterChange(): void {
    this.filterChange$.next({ ...this.filter });
  }

  clearFilters(): void {
    this.filter = {};
    this.onFilterChange();
  }

  setVehicleTypeFilter(type: string | null): void {
    this.filter.vehicle_type = type || undefined;
    this.onFilterChange();
  }

  // ============================================================================
  // Sorting
  // ============================================================================

  sort(field: SortField): void {
    if (this.sortBy === field) {
      // Toggle order
      this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortBy = field;
      this.sortOrder = 'desc';
    }
    this.loadViolations();
  }

  getSortIcon(field: SortField): string {
    if (this.sortBy !== field) return '↕️';
    return this.sortOrder === 'asc' ? '↑' : '↓';
  }

  // ============================================================================
  // Pagination
  // ============================================================================

  get totalPages(): number {
    return Math.ceil(this.totalViolations / this.pageSize);
  }

  get pageNumbers(): number[] {
    const pages: number[] = [];
    const maxVisible = 5;
    let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(this.totalPages, start + maxVisible - 1);
    
    if (end - start < maxVisible - 1) {
      start = Math.max(1, end - maxVisible + 1);
    }
    
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
      this.currentPage = page;
      this.loadViolations();
    }
  }

  onPageSizeChange(): void {
    this.currentPage = 1;
    this.loadViolations();
  }

  // ============================================================================
  // Image Modal
  // ============================================================================

  // Track image loading state
  imageLoading = false;
  imageError = false;

  openImageModal(violation: ViolationCapture): void {
    this.selectedViolation = violation;
    this.showImageModal = true;
    this.imageLoading = true;
    this.imageError = false;
  }

  closeImageModal(): void {
    this.showImageModal = false;
    this.selectedViolation = null;
    this.imageLoading = false;
    this.imageError = false;
  }

  onImageLoad(): void {
    this.imageLoading = false;
    this.imageError = false;
  }

  onImageError(event: Event): void {
    this.imageLoading = false;
    this.imageError = true;
    const img = event.target as HTMLImageElement;
    img.src = this.violationService.getPlaceholderUrl();
  }

  onThumbnailError(event: Event): void {
    const img = event.target as HTMLImageElement;
    img.src = this.violationService.getPlaceholderUrl();
  }

  getImageUrl(violation: ViolationCapture): string {
    return this.violationService.getImageUrl(violation.frame_image_path);
  }

  getThumbnailUrl(violation: ViolationCapture): string {
    return this.violationService.getThumbnailUrl(violation.thumbnail_path);
  }

  // ============================================================================
  // Selection & Bulk Operations
  // ============================================================================

  toggleSelection(violation: ViolationCapture): void {
    if (this.selectedIds.has(violation.id)) {
      this.selectedIds.delete(violation.id);
    } else {
      this.selectedIds.add(violation.id);
    }
    this.updateSelectAll();
  }

  toggleSelectAll(): void {
    if (this.selectAll) {
      this.violations.forEach(v => this.selectedIds.add(v.id));
    } else {
      this.clearSelection();
    }
  }

  private updateSelectAll(): void {
    this.selectAll = this.violations.length > 0 && 
                     this.violations.every(v => this.selectedIds.has(v.id));
  }

  private clearSelection(): void {
    this.selectedIds.clear();
    this.selectAll = false;
  }

  isSelected(violation: ViolationCapture): boolean {
    return this.selectedIds.has(violation.id);
  }

  get hasSelection(): boolean {
    return this.selectedIds.size > 0;
  }

  // ============================================================================
  // Delete Operations
  // ============================================================================

  confirmDelete(violation: ViolationCapture): void {
    this.deleteTarget = violation;
    this.showDeleteConfirm = true;
  }

  cancelDelete(): void {
    this.deleteTarget = null;
    this.showDeleteConfirm = false;
  }

  executeDelete(): void {
    if (!this.deleteTarget) return;
    
    this.violationService.deleteViolation(this.deleteTarget.id).pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: () => {
        this.loadViolations();
        this.loadStats();
        this.cancelDelete();
      },
      error: (err) => {
        this.error = 'Failed to delete violation';
        console.error('Delete error:', err);
        this.cancelDelete();
      }
    });
  }

  bulkDelete(): void {
    if (!this.hasSelection) return;
    
    if (!confirm(`Delete ${this.selectedIds.size} selected violations?`)) {
      return;
    }
    
    this.violationService.bulkDelete(Array.from(this.selectedIds)).pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: (response) => {
        console.log('Bulk delete complete:', response);
        this.loadViolations();
        this.loadStats();
      },
      error: (err) => {
        this.error = 'Failed to delete violations';
        console.error('Bulk delete error:', err);
      }
    });
  }

  // ============================================================================
  // Export
  // ============================================================================

  exportData(format: ExportFormat): void {
    this.violationService.exportViolations(
      format,
      this.filter.video_id,
      this.filter.session_start
    ).pipe(
      takeUntil(this.destroy$)
    ).subscribe({
      next: (blob: Blob) => {
        const timestamp = new Date().toISOString().slice(0, 10);
        const filename = `violations_${this.filter.video_id || 'all'}_${timestamp}.${format}`;
        this.violationService.downloadExport(blob, filename);
      },
      error: (err) => {
        this.error = 'Failed to export data';
        console.error('Export error:', err);
      }
    });
  }

  // ============================================================================
  // Helpers
  // ============================================================================

  formatDate(dateStr: string): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  formatTime(dateStr: string): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleTimeString();
  }

  getVideoName(videoId: number): string {
    if (!this.videos || !Array.isArray(this.videos)) {
      return `Video ${videoId}`;
    }
    const video = this.videos.find(v => v.id === videoId);
    return video?.name || `Video ${videoId}`;
  }

  getSpeedClass(speed: number): string {
    const severity = getSpeedSeverity(speed);
    return `severity-${severity}`;
  }

  getSpeedRangeData(): { range: string; count: number; percentage: number }[] {
    if (!this.stats) return [];
    
    const total = this.stats.total_violations || 1;
    const ranges = ['60-70', '70-80', '80-90', '90-100', '100+'];
    
    return ranges.map(range => ({
      range,
      count: this.stats!.speed_distribution[range] || 0,
      percentage: ((this.stats!.speed_distribution[range] || 0) / total) * 100
    }));
  }

  trackByViolation(index: number, violation: ViolationCapture): number {
    return violation.id;
  }
}
