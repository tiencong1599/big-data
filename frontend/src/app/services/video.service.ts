import { Injectable } from '@angular/core';
import { HttpClient, HttpEvent, HttpEventType } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map, tap } from 'rxjs/operators';
import { Video } from '../models/video.model';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class VideoService {
  private apiUrl = environment.apiUrl;  // Use environment configuration

  constructor(private http: HttpClient) {
    console.log('[VIDEO-SERVICE] Initialized with API URL:', this.apiUrl);
  }

  getVideos(): Observable<{ videos: Video[], count: number }> {
    console.log('[VIDEO-SERVICE] Fetching videos from:', `${this.apiUrl}/videos`);
    return this.http.get<{ videos: Video[], count: number }>(`${this.apiUrl}/videos`).pipe(
      tap((response: { videos: Video[], count: number }) => console.log('[VIDEO-SERVICE] Received videos:', response))
    );
  }

  getVideo(id: number): Observable<{ video: Video }> {
    console.log('[VIDEO-SERVICE] Fetching video:', id);
    return this.http.get<{ video: Video }>(`${this.apiUrl}/videos/${id}`).pipe(
      tap((response: { video: Video }) => console.log('[VIDEO-SERVICE] Received video:', response))
    );
  }

  uploadVideo(formData: FormData): Observable<any> {
    console.log('[VIDEO-SERVICE] Uploading video to:', `${this.apiUrl}/videos/upload`);
    return this.http.post(`${this.apiUrl}/videos/upload`, formData).pipe(
      tap((response: any) => console.log('[VIDEO-SERVICE] Upload response:', response))
    );
  }

  uploadVideoWithProgress(formData: FormData): Observable<any> {
    console.log('[VIDEO-SERVICE] Starting upload with progress to:', `${this.apiUrl}/videos/upload`);
    
    return this.http.post(`${this.apiUrl}/videos/upload`, formData, {
      reportProgress: true,
      observe: 'events'
    }).pipe(
      map((event: HttpEvent<any>) => {
        console.log('[VIDEO-SERVICE] HTTP Event Type:', HttpEventType[event.type]);
        
        switch (event.type) {
          case HttpEventType.Sent:
            console.log('[VIDEO-SERVICE] Request sent to server');
            return { type: 'sent' };
          
          case HttpEventType.UploadProgress:
            if (event.total) {
              const progress = Math.round((100 * event.loaded) / event.total);
              console.log(`[VIDEO-SERVICE] Upload progress: ${progress}%`);
              return {
                type: 'progress',
                progress: progress,
                loaded: event.loaded,
                total: event.total
              };
            }
            return { type: 'progress', progress: 0 };
          
          case HttpEventType.Response:
            console.log('[VIDEO-SERVICE] Upload complete, response:', event.body);
            return { type: 'complete', response: event.body };
          
          default:
            return { type: 'unknown', event: event };
        }
      })
    );
  }

  startStream(videoId: number): Observable<any> {
    console.log('[VIDEO-SERVICE] Starting stream for video:', videoId);
    return this.http.post(`${this.apiUrl}/stream/start`, { video_id: videoId }).pipe(
      tap((response: any) => console.log('[VIDEO-SERVICE] Stream started:', response))
    );
  }

  stopStream(videoId: number): Observable<any> {
    console.log('[VIDEO-SERVICE] Stopping stream for video:', videoId);
    return this.http.post(`${this.apiUrl}/stream/stop`, { video_id: videoId }).pipe(
      tap((response: any) => console.log('[VIDEO-SERVICE] Stream stopped:', response))
    );
  }

  // NEW: Delete Video
  deleteVideo(id: number): Observable<any> {
    console.log('[VIDEO-SERVICE] Deleting video:', id);
    return this.http.delete(`${this.apiUrl}/videos/${id}`).pipe(
      tap((response: any) => console.log('[VIDEO-SERVICE] Video deleted:', response))
    );
  }
}
