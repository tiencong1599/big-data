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
  @ViewChild('videoCanvas', { static: false }) canvasRef!: ElementRef<HTMLCanvasElement>;

  isStreaming = false;
  frameNumber = 0;
  vehicles: VehicleData[] = [];
  totalVehicles = 0;
  roiPolygon: number[][] | null = null;
  error: string | null = null;
  
  // Full CSR: MJPEG stream URL
  mjpegStreamUrl: string | null = null;
  
  private frameSubscription?: Subscription;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private videoImg: HTMLImageElement | null = null;

  constructor(
    private videoService: VideoService,
    private wsService: WebsocketService
  ) {}

  ngOnInit() {
    const channelName = `processed_frame_${this.video.id}`;
    
    // Full CSR: Subscribe to METADATA ONLY (no Base64)
    this.wsService.subscribeToChannel(channelName, this.video.id).subscribe(
      (frameData: ProcessedFrameData) => {
        // Auto-start MJPEG stream if data is already flowing (e.g., after page refresh)
        if (!this.mjpegStreamUrl && !this.isStreaming) {
          console.log('[FULL-CSR] Auto-starting stream (data already flowing)');
          this.isStreaming = true;
          this.startMJPEGStream();
        }
        
        // Update metadata
        this.frameNumber = frameData.frame_number;
        this.vehicles = frameData.vehicles || [];
        this.totalVehicles = frameData.total_vehicles || 0;
        this.roiPolygon = frameData.roi_polygon || (this.video.roi && (this.video.roi as any).roi_polygon) || null;
        
        // Draw bounding boxes and ROI on canvas overlay
        this.drawDetections();
        
        if (frameData.end_of_stream) {
          this.isStreaming = false;
          this.stopMJPEGStream();
        }
      }
    );
  }
  
  ngAfterViewInit() {
    // Initialize canvas overlay after view is loaded
    if (this.canvasRef) {
      this.canvas = this.canvasRef.nativeElement;
      this.ctx = this.canvas.getContext('2d');
    }
  }

  ngOnDestroy() {
    this.wsService.disconnect();
    this.stopMJPEGStream();
  }

  startStream() {
    this.isStreaming = true;
    
    // Full CSR: Start MJPEG stream
    this.startMJPEGStream();
    
    // Trigger processing pipeline (DAG)
    this.videoService.startStream(this.video.id).subscribe({
      next: (response) => {
        console.log('[FULL-CSR] Stream started:', response);
      },
      error: (error) => {
        console.error('[FULL-CSR] Failed to start stream:', error);
        this.isStreaming = false;
        this.stopMJPEGStream();
      }
    });
  }

  stopStream() {
    this.isStreaming = false;
    this.stopMJPEGStream();
    console.log('[FULL-CSR] Stream stopped');
  }
  
  /**
   * Full CSR: Start MJPEG video stream
   * 
   * Load MJPEG stream as <img> element and overlay canvas for detections
   */
  startMJPEGStream() {
    // MJPEG stream URL
    this.mjpegStreamUrl = `http://localhost:8686/api/video/stream/${this.video.id}`;
    
    console.log('[FULL-CSR] MJPEG stream started:', this.mjpegStreamUrl);
    
    // Poll for image element and size canvas when ready
    let attempts = 0;
    const maxAttempts = 20;
    
    const setupCanvas = () => {
      const imgElement = document.querySelector('.video-stream') as HTMLImageElement;
      
      if (!imgElement && attempts < maxAttempts) {
        attempts++;
        setTimeout(setupCanvas, 50);
        return;
      }
      
      if (imgElement && this.canvas) {
        const sizeCanvas = () => {
          if (this.canvas && imgElement.naturalWidth > 0) {
            this.canvas.width = imgElement.naturalWidth;
            this.canvas.height = imgElement.naturalHeight;
            console.log('[FULL-CSR] Canvas sized:', this.canvas.width, 'x', this.canvas.height);
            
            // Redraw with current data
            this.drawDetections();
          } else if (attempts < maxAttempts) {
            attempts++;
            setTimeout(sizeCanvas, 50);
          }
        };
        
        // Handle both load and cached image scenarios
        if (imgElement.complete && imgElement.naturalWidth > 0) {
          sizeCanvas();
        } else {
          imgElement.onload = sizeCanvas;
        }
      }
    };
    
    setTimeout(setupCanvas, 50);
  }
  
  /**
   * Full CSR: Stop MJPEG stream
   */
  stopMJPEGStream() {
    if (this.videoImg) {
      this.videoImg.src = '';
    }
    this.mjpegStreamUrl = null;
    
    // Clear canvas
    if (this.ctx && this.canvas) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
  }
  
  /**
   * Full CSR: Draw bounding boxes and ROI on canvas overlay
   */
  drawDetections() {
    if (!this.ctx || !this.canvas) return;
    if (this.canvas.width === 0 || this.canvas.height === 0) return;
    
    // Clear previous drawings
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    
    // Draw ROI polygon (semi-transparent yellow fill + yellow border)
    if (this.roiPolygon && this.roiPolygon.length > 0) {
      this.ctx.beginPath();
      this.ctx.moveTo(this.roiPolygon[0][0], this.roiPolygon[0][1]);
      for (let i = 1; i < this.roiPolygon.length; i++) {
        this.ctx.lineTo(this.roiPolygon[i][0], this.roiPolygon[i][1]);
      }
      this.ctx.closePath();
      
      // Fill with semi-transparent yellow
      this.ctx.fillStyle = 'rgba(255, 255, 0, 0.1)';
      this.ctx.fill();
      
      // Stroke with solid yellow
      this.ctx.strokeStyle = 'rgba(255, 255, 0, 0.8)';
      this.ctx.lineWidth = 2;
      this.ctx.stroke();
    }
    
    // Draw each vehicle bounding box
    this.vehicles.forEach((vehicle) => {
      const bbox = vehicle.bbox;
      const trackId = vehicle.track_id;
      const speed = vehicle.speed;
      const color = this.getVehicleColor(trackId);
      
      // Draw bounding box
      this.ctx!.strokeStyle = color;
      this.ctx!.lineWidth = 3;
      this.ctx!.strokeRect(bbox.x1, bbox.y1, bbox.x2 - bbox.x1, bbox.y2 - bbox.y1);
      
      // Draw label background
      const label = `ID: ${trackId} | ${speed.toFixed(1)} km/h`;
      this.ctx!.font = '14px Arial';
      const textWidth = this.ctx!.measureText(label).width;
      this.ctx!.fillStyle = color;
      this.ctx!.fillRect(bbox.x1, bbox.y1 - 20, textWidth + 10, 20);
      
      // Draw label text
      this.ctx!.fillStyle = 'white';
      this.ctx!.fillText(label, bbox.x1 + 5, bbox.y1 - 5);
    });
  }

  closePanel() {
    if (this.isStreaming) {
      this.stopStream();
    }
    this.close.emit();
  }

  formatJSON(obj: any): string {
    return JSON.stringify(obj, null, 2);
  }

  getVehicleColor(trackId: number): string {
    const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8'];
    return colors[trackId % colors.length];
  }
}
