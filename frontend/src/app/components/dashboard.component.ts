import { Component, OnInit } from '@angular/core';
import { VideoService } from '../services/video.service';
import { Video } from '../models/video.model';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {
  videos: Video[] = [];
  selectedVideo: Video | null = null;
  loading = false;
  error: string | null = null;

  constructor(private videoService: VideoService) { }

  ngOnInit(): void {
    this.loadVideos();
  }

  loadVideos(): void {
    this.loading = true;
    this.error = null;
    
    this.videoService.getVideos().subscribe({
      next: (response: { videos: Video[], count: number }) => {
        this.videos = response.videos;
        this.loading = false;
      },
      error: (err: any) => {
        this.error = 'Failed to load videos';
        this.loading = false;
        console.error('Error loading videos:', err);
      }
    });
  }

  selectVideo(video: Video): void {
    this.selectedVideo = video;
  }

  closeVideoPanel(): void {
    this.selectedVideo = null;
  }

  onVideoUploaded(): void {
    this.loadVideos();
  }
}
