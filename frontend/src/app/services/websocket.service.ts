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

  constructor() { }

  subscribeToChannel(channelName: string, videoId: number): Observable<ProcessedFrameData> {
    if (this.socket) {
      this.disconnect();
    }

    // Connect to client WebSocket with video_id
    const wsUrl = `ws://localhost:8686/ws/client/stream?video_id=${videoId}`;
    console.log(`Subscribing to channel: ${channelName} via ${wsUrl}`);
    
    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      console.log(`WebSocket connected to channel: ${channelName}`);
    };

    this.socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('WebSocket message received:', {
          type: message.type,
          hasData: !!message.data,
          dataKeys: message.data ? Object.keys(message.data) : []
        });
        
        if (message.type === 'placeholder') {
          console.log('Received placeholder frame');
          this.frameSubject.next(message.data);
        } else if (message.type === 'frame') {
          console.log('Received processed frame:', message.data.frame_number);
          this.frameSubject.next(message.data);
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.socket.onclose = () => {
      console.log(`WebSocket disconnected from channel: ${channelName}`);
    };

    return this.frameSubject.asObservable();
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}
