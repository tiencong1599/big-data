import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { ProcessedFrameData } from '../models/video.model';

@Injectable({
  providedIn: 'root'
})
export class WebsocketService {
  private socket: WebSocket | null = null;
  private frameSubject = new Subject<ProcessedFrameData>();
  public frames$ = this.frameSubject.asObservable();
  private currentChannel: string | null = null;
  private pendingSubscription: { channel: string } | null = null;

  constructor() { }

  subscribeToChannel(channelName: string, videoId: number): Observable<ProcessedFrameData> {
    // Unsubscribe from previous channel if exists
    if (this.socket && this.currentChannel && this.currentChannel !== channelName) {
      console.log(`[WS-SERVICE] Unsubscribing from old channel: ${this.currentChannel}`);
      this.unsubscribeFromChannel(this.currentChannel);
    }

    // Close existing connection if switching videos
    if (this.socket && this.currentChannel !== channelName) {
      console.log(`[WS-SERVICE] Closing previous connection`);
      this.disconnect();
    }

    // Connect to WebSocket
    const wsUrl = `ws://localhost:8686/ws/client/stream?video_id=${videoId}`;
    console.log(`[WS-SERVICE] Connecting to: ${wsUrl}`);
    
    this.socket = new WebSocket(wsUrl);
    this.currentChannel = channelName;
    
    // Store pending subscription to send after connection opens
    this.pendingSubscription = {
      channel: channelName
    };

    this.socket.onopen = () => {
      console.log(`[WS-SERVICE] ✓ WebSocket connected`);
      
      // CRITICAL FIX: Add delay to ensure connection is fully ready
      setTimeout(() => {
        if (this.socket && this.socket.readyState === WebSocket.OPEN && this.pendingSubscription) {
          const subscribeMessage = {
            action: 'subscribe',
            channel: this.pendingSubscription.channel
          };
          
          console.log(`[WS-SERVICE] 📤 Sending subscription:`, subscribeMessage);
          
          try {
            this.socket.send(JSON.stringify(subscribeMessage));
            console.log(`[WS-SERVICE] ✅ Subscription message sent successfully`);
            this.pendingSubscription = null;
          } catch (error) {
            console.error(`[WS-SERVICE] ❌ Failed to send subscription:`, error);
          }
        } else {
          console.warn(`[WS-SERVICE] ⚠️ WebSocket not ready, state: ${this.socket?.readyState}`);
        }
      }, 100); // 100ms delay to ensure connection is fully established
    };

    this.socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log(`[WS-SERVICE] 📨 Received message:`, {
          type: message.type,
          frame: message.data?.frame_number,
          vehicles: message.data?.total_vehicles
        });
        
        if (message.type === 'placeholder') {
          console.log('[WS-SERVICE] Received placeholder frame');
          this.frameSubject.next(message.data);
        } else if (message.type === 'frame' || message.type === 'processed_frame') {
          console.log(`[WS-SERVICE] Received frame ${message.data.frame_number}`);
          this.frameSubject.next(message.data);
        } else {
          console.warn(`[WS-SERVICE] Unknown message type:`, message.type);
        }
      } catch (error) {
        console.error('[WS-SERVICE] ❌ Error parsing message:', error);
      }
    };

    this.socket.onerror = (error) => {
      console.error('[WS-SERVICE] ❌ WebSocket error:', error);
    };

    this.socket.onclose = (event) => {
      console.log(`[WS-SERVICE] 🔌 WebSocket disconnected (code: ${event.code}, reason: ${event.reason})`);
      this.pendingSubscription = null;
    };

    return this.frameSubject.asObservable();
  }

  private unsubscribeFromChannel(channelName: string) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const unsubscribeMessage = {
        action: 'unsubscribe',
        channel: channelName
      };
      
      console.log(`[WS-SERVICE] 📤 Unsubscribing from:`, channelName);
      
      try {
        this.socket.send(JSON.stringify(unsubscribeMessage));
        console.log(`[WS-SERVICE] ✅ Unsubscribe message sent`);
      } catch (error) {
        console.error(`[WS-SERVICE] ❌ Failed to unsubscribe:`, error);
      }
    }
  }

  disconnect() {
    if (this.socket) {
      if (this.currentChannel) {
        this.unsubscribeFromChannel(this.currentChannel);
      }
      
      console.log('[WS-SERVICE] 🔌 Closing WebSocket connection');
      this.socket.close(1000, 'Client disconnect');
      this.socket = null;
      this.currentChannel = null;
      this.pendingSubscription = null;
    }
  }
}
