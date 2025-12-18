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
  
  // Delete confirmation
  showDeleteConfirm = false;
  videoToDelete: Video | null = null;

  constructor(private videoService: VideoService) {}

  ngOnInit() {
    this.loadVideos();
  }

  loadVideos() {
    this.loading = true;
    this.error = null;
    
    this.videoService.getVideos().subscribe({
      next: (response: any) => {
        // FIX: Handle both response formats
        if (Array.isArray(response)) {
          // Direct array response
          this.videos = response;
        } else if (response && response.videos) {
          // Object with videos array
          this.videos = response.videos;
        } else {
          this.videos = [];
        }
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Failed to load videos';
        this.loading = false;
        console.error('Error loading videos:', err);
      }
    });
  }

  selectVideo(video: Video) {
    this.selectedVideo = video;
  }

  closeDetail() {
    this.selectedVideo = null;
  }

  onVideoUploaded() {
    this.loadVideos();
  }
  
  confirmDelete(video: Video, event: Event) {
    event.stopPropagation();
    this.videoToDelete = video;
    this.showDeleteConfirm = true;
  }
  
  cancelDelete() {
    this.showDeleteConfirm = false;
    this.videoToDelete = null;
  }
  
  deleteVideo() {
    if (!this.videoToDelete) return;
    
    const videoId = this.videoToDelete.id;
    
    this.videoService.deleteVideo(videoId).subscribe({
      next: () => {
        console.log(`✓ Video ${videoId} deleted successfully`);
        
        this.videos = this.videos.filter(v => v.id !== videoId);
        
        if (this.selectedVideo?.id === videoId) {
          this.selectedVideo = null;
        }
        
        this.showDeleteConfirm = false;
        this.videoToDelete = null;
      },
      error: (err) => {
        console.error('Error deleting video:', err);
        alert(`Failed to delete video: ${err.error?.error || err.message}`);
        this.showDeleteConfirm = false;
        this.videoToDelete = null;
      }
    });
  }
}
