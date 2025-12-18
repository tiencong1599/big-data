import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { Video, ProcessedFrameData, VehicleData } from '../models/video.model';
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
  vehicles: VehicleData[] = [];
  totalVehicles = 0;
  roiPolygon: number[][] | null = null;
  error: string | null = null;
  
  private canvasContext: CanvasRenderingContext2D | null = null;
  private frameSubscription?: Subscription;
  
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
    const channelName = `processed_frame_${this.video.id}`;
    console.log(`[VIDEO-DETAIL] Subscribing to channel: ${channelName}`);
    
    this.frameSubscription = this.wsService.subscribeToChannel(channelName, this.video.id).subscribe(
      (frameData: ProcessedFrameData) => {
        this.resetWatchdog();
        
        if (frameData.message) {
          this.currentFrame = `data:image/jpeg;base64,${frameData.processed_frame}`;
        } else {
          this.currentFrame = `data:image/jpeg;base64,${frameData.processed_frame}`;
          this.frameNumber = frameData.frame_number;
          this.vehicles = frameData.vehicles || [];
          this.totalVehicles = frameData.total_vehicles || 0;
          this.roiPolygon = frameData.roi_polygon;
          
          setTimeout(() => this.drawBoundingBoxes(), 10);
          
          if (frameData.end_of_stream) {
            this.isStreaming = false;
            this.stopWatchdog();
          }
        }
      },
      (error) => {
        console.error('[VIDEO-DETAIL] WebSocket error:', error);
        this.handleWatchdogTimeout();
      }
    );
  }
  
  unsubscribeFromWebSocket() {
    if (this.frameSubscription) {
      console.log(`[VIDEO-DETAIL] Unsubscribing from video ${this.video.id}`);
      this.frameSubscription.unsubscribe();
      this.frameSubscription = undefined;
    }
    this.wsService.disconnect();
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
    this.vehicles = [];
    this.totalVehicles = 0;
    
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
  
  drawBoundingBoxes() {
    if (!this.canvasContext || !this.videoImage || !this.canvasOverlay) return;
    
    const canvas = this.canvasOverlay.nativeElement;
    const img = this.videoImage.nativeElement;
    
    canvas.width = img.width;
    canvas.height = img.height;
    
    this.canvasContext.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw ROI polygon
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
    
    // Draw vehicle bounding boxes
    this.vehicles.forEach(vehicle => {
      const { bbox, track_id, speed, class_id, confidence } = vehicle;
      const { x1, y1, x2, y2 } = bbox;
      
      const colors: { [key: number]: string } = {
        2: '#00ff00', // car
        7: '#ff0000', // truck
        3: '#0000ff', // motorcycle
        5: '#ffff00'  // bus
      };
      const color = colors[class_id] || '#ffffff';
      
      // FIX: Add null checks
      if (!this.canvasContext) return;
      
      this.canvasContext.strokeStyle = color;
      this.canvasContext.lineWidth = 3;
      this.canvasContext.strokeRect(x1, y1, x2 - x1, y2 - y1);
      
      const label = `ID:${track_id} | ${speed.toFixed(1)} km/h | ${(confidence * 100).toFixed(0)}%`;
      this.canvasContext.font = 'bold 14px Arial';
      const textWidth = this.canvasContext.measureText(label).width;
      
      this.canvasContext.fillStyle = color;
      this.canvasContext.fillRect(x1, y1 - 22, textWidth + 10, 22);
      
      this.canvasContext.fillStyle = '#000';
      this.canvasContext.fillText(label, x1 + 5, y1 - 6);
    });
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
