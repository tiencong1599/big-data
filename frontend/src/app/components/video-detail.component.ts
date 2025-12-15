import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { Video, ProcessedFrameData, VehicleData } from '../models/video.model';
import { WebsocketService } from '../services/websocket.service';
import { VideoService } from '../services/video.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-video-detail',
  templateUrl: './video-detail.component.html',
  styleUrls: ['./video-detail.component.css']
})
export class VideoDetailComponent implements OnInit, OnDestroy {
  @Input() video!: Video;
  @Output() close = new EventEmitter<void>();

  isStreaming = false;
  currentFrame: string | null = null;
  frameNumber = 0;
  vehicles: VehicleData[] = [];
  totalVehicles = 0;
  roiPolygon: number[][] | null = null;
  error: string | null = null;
  
  private frameSubscription?: Subscription;

  constructor(
    private videoService: VideoService,
    private wsService: WebsocketService
  ) {}

  ngOnInit() {
    const channelName = `processed_frame_${this.video.id}`;
    
    this.wsService.subscribeToChannel(channelName, this.video.id).subscribe(
      (frameData: ProcessedFrameData) => {
        if (frameData.message) {
          // Placeholder frame
          this.currentFrame = `data:image/jpeg;base64,${frameData.processed_frame}`;
        } else {
          // CRITICAL: Ensure proper base64 data URI
          this.currentFrame = `data:image/jpeg;base64,${frameData.processed_frame}`;
          this.frameNumber = frameData.frame_number;
          this.vehicles = frameData.vehicles || [];
          this.totalVehicles = frameData.total_vehicles || 0;
          
          if (frameData.end_of_stream) {
            this.isStreaming = false;
          }
        }
      }
    );
  }

  ngOnDestroy() {
    this.wsService.disconnect();
  }

  startStream() {
    this.isStreaming = true;
    
    // Trigger DAG
    this.videoService.startStream(this.video.id).subscribe({
      next: (response) => {
        console.log('Stream started:', response);
      },
      error: (error) => {
        console.error('Failed to start stream:', error);
        this.isStreaming = false;
      }
    });
  }

  stopStream() {
    this.isStreaming = false;
    // TODO: Add API call to stop streaming if needed
    console.log('Stream stopped');
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
