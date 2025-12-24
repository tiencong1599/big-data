import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { ProcessedFrameData, AnalyticsData } from '../models/video.model';

@Injectable({
  providedIn: 'root'
})
export class WebsocketService {
  // Dual WebSocket connections
  private frameSocket: WebSocket | null = null;
  private analyticsSocket: WebSocket | null = null;
  
  // Separate observables for each channel
  private frameSubject = new Subject<ProcessedFrameData>();
  private analyticsSubject = new Subject<AnalyticsData>();
  
  public frames$ = this.frameSubject.asObservable();
  public analytics$ = this.analyticsSubject.asObservable();
  
  private currentVideoId: number | null = null;

  constructor() { }

  subscribeToVideo(videoId: number): { frames: Observable<ProcessedFrameData>, analytics: Observable<AnalyticsData> } {
    // Disconnect existing connections if switching videos
    if (this.currentVideoId !== null && this.currentVideoId !== videoId) {
      console.log(`[WS-SERVICE] Switching from video ${this.currentVideoId} to ${videoId}`);
      this.disconnect();
    }

    this.currentVideoId = videoId;
    
    // Connect to BOTH channels
    this.connectFrameChannel(videoId);
    this.connectAnalyticsChannel(videoId);
    
    return {
      frames: this.frames$,
      analytics: this.analytics$
    };
  }
  
  private connectFrameChannel(videoId: number) {
    const wsUrl = `ws://localhost:8686/ws/client/stream`;
    const channelName = `processed_frame_${videoId}`;
    
    console.log(`[WS-FRAME] Connecting to: ${wsUrl}`);
    
    this.frameSocket = new WebSocket(wsUrl);

    this.frameSocket.onopen = () => {
      console.log(`[WS-FRAME] ✓ Connected`);
      
      setTimeout(() => {
        if (this.frameSocket && this.frameSocket.readyState === WebSocket.OPEN) {
          const subscribeMessage = {
            action: 'subscribe',
            channel: channelName
          };
          
          console.log(`[WS-FRAME] 📤 Subscribing to: ${channelName}`);
          this.frameSocket.send(JSON.stringify(subscribeMessage));
          console.log(`[WS-FRAME] ✅ Subscription sent`);
        }
      }, 100);
    };

    this.frameSocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.type === 'subscription_ack') {
          console.log(`[WS-FRAME] ✅ Subscription confirmed: ${message.channel}`);
        } else if (message.type === 'frame') {
          console.log(`[WS-FRAME] 📨 Received frame ${message.data.frame_number}`);
          this.frameSubject.next(message.data);
        } else {
          console.warn(`[WS-FRAME] Unknown message type:`, message.type);
        }
      } catch (error) {
        console.error('[WS-FRAME] ❌ Error parsing message:', error);
      }
    };

    this.frameSocket.onerror = (error) => {
      console.error('[WS-FRAME] ❌ Error:', error);
    };

    this.frameSocket.onclose = (event) => {
      console.log(`[WS-FRAME] 🔌 Disconnected (code: ${event.code})`);
    };
  }
  
  private connectAnalyticsChannel(videoId: number) {
    const wsUrl = `ws://localhost:8686/ws/client/stream`;
    const channelName = `analytics_metrics_${videoId}`;
    
    console.log(`[WS-ANALYTICS] Connecting to: ${wsUrl}`);
    
    this.analyticsSocket = new WebSocket(wsUrl);
    
    this.analyticsSocket.onopen = () => {
      console.log(`[WS-ANALYTICS] ✓ Connected`);
      
      setTimeout(() => {
        if (this.analyticsSocket && this.analyticsSocket.readyState === WebSocket.OPEN) {
          const subscribeMessage = {
            action: 'subscribe',
            channel: channelName
          };
          
          console.log(`[WS-ANALYTICS] 📤 Subscribing to: ${channelName}`);
          this.analyticsSocket.send(JSON.stringify(subscribeMessage));
          console.log(`[WS-ANALYTICS] ✅ Subscription sent`);
        }
      }, 100);
    };
    
    this.analyticsSocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.type === 'subscription_ack') {
          console.log(`[WS-ANALYTICS] ✅ Subscription confirmed: ${message.channel}`);
        } else if (message.type === 'analytics') {
          const speedingCount = message.data.speeding_vehicles?.length || 0;
          console.log(`[WS-ANALYTICS] 📨 Received analytics (frame ${message.data.frame_number}, speeding: ${speedingCount})`);
          this.analyticsSubject.next(message.data);
        } else {
          console.warn(`[WS-ANALYTICS] Unknown message type:`, message.type);
        }
      } catch (error) {
        console.error('[WS-ANALYTICS] ❌ Error parsing message:', error);
      }
    };
    
    this.analyticsSocket.onerror = (error) => {
      console.error('[WS-ANALYTICS] ❌ Error:', error);
    };

    this.analyticsSocket.onclose = (event) => {
      console.log(`[WS-ANALYTICS] 🔌 Disconnected (code: ${event.code})`);
    };
  }

  disconnect() {
    console.log('[WS-SERVICE] 🔌 Disconnecting all channels');
    
    if (this.frameSocket) {
      this.frameSocket.close(1000, 'Client disconnect');
      this.frameSocket = null;
    }
    
    if (this.analyticsSocket) {
      this.analyticsSocket.close(1000, 'Client disconnect');
      this.analyticsSocket = null;
    }
    
    this.currentVideoId = null;
  }
}
