import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { Video, ProcessedFrameData, VehicleData, AnalyticsData, FrameStats } from '../models/video.model';
import { WebsocketService } from '../services/websocket.service';
import { VideoService } from '../services/video.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-video-detail',
  templateUrl: './video-detail.component.html',
  styleUrls: ['./video-detail.component.css']
})
export class VideoDetailComponent implements OnInit, OnDestroy, AfterViewInit {
  @Input() video!: Video;
  @Output() close = new EventEmitter<void>();
  
  @ViewChild('videoImage') videoImage!: ElementRef<HTMLImageElement>;
  @ViewChild('canvasOverlay') canvasOverlay!: ElementRef<HTMLCanvasElement>;

  isStreaming = false;
  currentFrame: string | null = null;
  frameNumber = 0;
  roiPolygon: number[][] | null = null;
  error: string | null = null;
  
  // Analytics data (from analytics channel)
  stats: FrameStats = { total_vehicles: 0, speeding_count: 0, current_in_roi: 0 };
  speedingVehicles: VehicleData[] = [];
  private displayedSpeedingIds = new Set<number>();
  
  private canvasContext: CanvasRenderingContext2D | null = null;
  private frameSubscription?: Subscription;
  private analyticsSubscription?: Subscription;
  
  // WATCHDOG MECHANISM (3-second timeout)
  private watchdogTimer: any = null;
  private readonly WATCHDOG_TIMEOUT = 60000;
  private defaultThumbnail = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAwIiBoZWlnaHQ9IjYwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iODAwIiBoZWlnaHQ9IjYwMCIgZmlsbD0iI2YwZjBmMCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMjQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7wn46sIE5vIFN0cmVhbTwvdGV4dD48L3N2Zz4=';

  constructor(
    private videoService: VideoService,
    private wsService: WebsocketService
  ) {}

  ngOnInit() {
    this.subscribeToWebSocket();
  }
  
  ngAfterViewInit() {
    if (this.canvasOverlay) {
      this.canvasContext = this.canvasOverlay.nativeElement.getContext('2d');
    }
  }

  ngOnDestroy() {
    this.unsubscribeFromWebSocket();
    this.stopWatchdog();
  }
  
  subscribeToWebSocket() {
    console.log(`[VIDEO-DETAIL] Subscribing to video ${this.video.id} (dual channels)`);
    
    const { frames, analytics } = this.wsService.subscribeToVideo(this.video.id);
    
    // Frame subscription (canvas updates only)
    this.frameSubscription = frames.subscribe(
      (frameData: ProcessedFrameData) => {
        this.resetWatchdog();
        
        this.currentFrame = `data:image/jpeg;base64,${frameData.processed_frame}`;
        this.frameNumber = frameData.frame_number;
        this.roiPolygon = frameData.roi_polygon;
        
        // Draw ROI only (no bounding boxes)
        setTimeout(() => this.drawROI(), 10);
        
        if (frameData.end_of_stream) {
          this.isStreaming = false;
          this.stopWatchdog();
        }
      },
      (error) => {
        console.error('[VIDEO-DETAIL] Frame channel error:', error);
        this.handleWatchdogTimeout();
      }
    );
    
    // Analytics subscription (stats + speeding vehicles)
    this.analyticsSubscription = analytics.subscribe(
      (analyticsData: AnalyticsData) => {
        // Update stats
        this.stats = analyticsData.stats;
        
        // Append NEW speeding vehicles only
        this.appendNewSpeedingVehicles(analyticsData.speeding_vehicles);
      },
      (error) => {
        console.error('[VIDEO-DETAIL] Analytics channel error:', error);
      }
    );
  }
  
  unsubscribeFromWebSocket() {
    if (this.frameSubscription) {
      console.log(`[VIDEO-DETAIL] Unsubscribing from frame channel`);
      this.frameSubscription.unsubscribe();
      this.frameSubscription = undefined;
    }
    
    if (this.analyticsSubscription) {
      console.log(`[VIDEO-DETAIL] Unsubscribing from analytics channel`);
      this.analyticsSubscription.unsubscribe();
      this.analyticsSubscription = undefined;
    }
    
    this.wsService.disconnect();
  }
  
  appendNewSpeedingVehicles(newVehicles: VehicleData[]) {
    // Only add vehicles we haven't seen before
    for (const vehicle of newVehicles) {
      if (!this.displayedSpeedingIds.has(vehicle.track_id)) {
        vehicle.detectedAt = new Date();
        this.speedingVehicles.push(vehicle);
        this.displayedSpeedingIds.add(vehicle.track_id);
        
        // Auto-scroll to bottom
        setTimeout(() => {
          const list = document.querySelector('.vehicle-list');
          if (list) {
            list.scrollTop = list.scrollHeight;
          }
        }, 50);
      }
    }
  }
  
  clearSpeedingList() {
    this.speedingVehicles = [];
    this.displayedSpeedingIds.clear();
  }
  
  trackByTrackId(index: number, vehicle: VehicleData): number {
    return vehicle.track_id;
  }
  
  startWatchdog() {
    this.stopWatchdog();
    
    this.watchdogTimer = setTimeout(() => {
      console.warn(`[VIDEO-DETAIL] ⏰ Watchdog timeout: No data for ${this.WATCHDOG_TIMEOUT}ms`);
      this.handleWatchdogTimeout();
    }, this.WATCHDOG_TIMEOUT);
  }
  
  resetWatchdog() {
    if (this.isStreaming) {
      this.startWatchdog();
    }
  }
  
  stopWatchdog() {
    if (this.watchdogTimer) {
      clearTimeout(this.watchdogTimer);
      this.watchdogTimer = null;
    }
  }
  
  handleWatchdogTimeout() {
    console.log('[VIDEO-DETAIL] 🔄 Reverting to default thumbnail');
    
    this.currentFrame = this.defaultThumbnail;
    this.stats = { total_vehicles: 0, speeding_count: 0, current_in_roi: 0 };
    
    this.isStreaming = false;
    
    if (this.canvasContext && this.canvasOverlay) {
      const canvas = this.canvasOverlay.nativeElement;
      this.canvasContext.clearRect(0, 0, canvas.width, canvas.height);
    }
    
    this.stopWatchdog();
  }

  startStream() {
    this.error = null;
    this.isStreaming = true;
    
    this.startWatchdog();
    
    this.videoService.startStream(this.video.id).subscribe({
      next: (response) => {
        console.log('Stream started:', response);
      },
      error: (err) => {
        this.error = 'Failed to start stream';
        this.isStreaming = false;
        this.stopWatchdog();
        console.error('Stream error:', err);
      }
    });
  }

  stopStream() {
    this.isStreaming = false;
    this.stopWatchdog();
    
    this.videoService.stopStream(this.video.id).subscribe({
      next: (response) => {
        console.log('Stream stopped:', response);
      },
      error: (err) => {
        console.error('Stop stream error:', err);
      }
    });
  }
  
  drawROI() {
    if (!this.canvasContext || !this.videoImage || !this.canvasOverlay) return;
    
    const canvas = this.canvasOverlay.nativeElement;
    const img = this.videoImage.nativeElement;
    
    // Match canvas size to image
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    
    this.canvasContext.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw ROI polygon only
    if (this.roiPolygon && this.roiPolygon.length > 0) {
      this.canvasContext.strokeStyle = '#ffff00';
      this.canvasContext.lineWidth = 2;
      this.canvasContext.setLineDash([5, 5]);
      this.canvasContext.beginPath();
      this.canvasContext.moveTo(this.roiPolygon[0][0], this.roiPolygon[0][1]);
      for (let i = 1; i < this.roiPolygon.length; i++) {
        this.canvasContext.lineTo(this.roiPolygon[i][0], this.roiPolygon[i][1]);
      }
      this.canvasContext.closePath();
      this.canvasContext.stroke();
      this.canvasContext.setLineDash([]);
    }
  }
  
  formatTime(date: Date): string {
    return date.toLocaleTimeString();
  }

  closePanel() {
    this.unsubscribeFromWebSocket();
    this.stopWatchdog();
    this.close.emit();
  }

  formatJSON(obj: any): string {
    return JSON.stringify(obj, null, 2);
  }

  getVehicleColor(trackId: number): string {
    const colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'];
    return colors[trackId % colors.length];
  }
}
