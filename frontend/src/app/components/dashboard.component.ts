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
  
  // NEW: Delete confirmation
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
      next: (videos) => {
        this.videos = videos;
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
  
  // NEW: Delete Video Methods
  confirmDelete(video: Video, event: Event) {
    event.stopPropagation(); // Prevent video selection
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
        
        // Remove from local array (no page refresh needed)
        this.videos = this.videos.filter(v => v.id !== videoId);
        
        // Close detail panel if deleted video was selected
        if (this.selectedVideo?.id === videoId) {
          this.selectedVideo = null;
        }
        
        // Close confirmation dialog
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
