import { Component, Output, EventEmitter, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { VideoService } from '../services/video.service';

interface Point {
  x: number;
  y: number;
}

interface CalibrationPoint extends Point {
  realX: number;
  realY: number;
}

@Component({
  selector: 'app-video-upload',
  templateUrl: './video-upload.component.html',
  styleUrls: ['./video-upload.component.css']
})
export class VideoUploadComponent implements AfterViewInit {
  @Output() videoUploaded = new EventEmitter<void>();
  @ViewChild('videoPreview') videoPreview!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvas') canvas!: ElementRef<HTMLCanvasElement>;

  showUploadForm = false;
  selectedFile: File | null = null;
  videoName = '';
  videoUrl: string | null = null;
  uploading = false;
  error: string | null = null;
  success = false;
  videoLoadError = false;
  uploadProgress = 0;
  uploadStatus = '';
  isCompressing = false;

  // Success/Error popup
  showResultPopup = false;
  resultPopupType: 'success' | 'error' = 'success';
  resultPopupMessage = '';

  // ROI selection (changed to 4 points)
  roiPoints: Point[] = [];
  isSelectingROI = false;
  roiCompleted = false;

  // Calibration selection
  calibrationPoints: CalibrationPoint[] = [];
  isSelectingCalibration = false;
  calibrationCompleted = false;
  showCalibrationPopup = false;

  tempCalibrationPoint: Point | null = null;
  calibrationRealX = '';
  calibrationRealY = '';

  private canvasContext: CanvasRenderingContext2D | null = null;

  constructor(private videoService: VideoService) { }

  ngAfterViewInit(): void {
    // Canvas will be initialized when video is loaded
  }

  toggleUploadForm(): void {
    this.showUploadForm = !this.showUploadForm;
    if (!this.showUploadForm) {
      this.resetForm();
    }
  }

  onFileSelected(event: any): void {
    const file = event.target.files[0];
    if (file) {
      console.log('[VIDEO-UPLOAD] File selected:', {
        name: file.name,
        size: `${(file.size / 1024 / 1024).toFixed(2)} MB`,
        type: file.type,
        lastModified: new Date(file.lastModified).toISOString()
      });
      
      this.selectedFile = file;
      
      // Auto-fill video name from filename
      if (!this.videoName) {
        this.videoName = file.name.replace(/\.[^/.]+$/, '');
        console.log('[VIDEO-UPLOAD] Auto-filled video name:', this.videoName);
      }

      // Create video preview URL
      if (this.videoUrl) {
        URL.revokeObjectURL(this.videoUrl);
      }
      
      this.videoUrl = URL.createObjectURL(file);
      console.log('[VIDEO-UPLOAD] Video preview URL created');
      
      // Reset previous selections
      this.clearROI();
      this.clearCalibration();
      this.videoLoadError = false;
      this.error = null;
      console.log('[VIDEO-UPLOAD] Ready for ROI and calibration selection');
    }
  }

  onVideoLoadError(): void {
    this.videoLoadError = true;
    this.error = 'Cannot preview this video format in browser. The video will still be uploaded and processed. Common issue with MOV files - they will work on the backend.';
    console.warn('Video preview failed, but upload will proceed');
  }

  onVideoLoaded(): void {
    this.videoLoadError = false;
    console.log('Video loaded successfully');
  }

  async compressVideo(file: File): Promise<Blob> {
    console.log(`Skipping client-side compression for ${file.name}`);
    return Promise.resolve(file);
  }

  initializeCanvas(): void {
    if (!this.videoPreview || !this.canvas) return;

    const video = this.videoPreview.nativeElement;
    const canvas = this.canvas.nativeElement;
    
    // Check if video has valid dimensions
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      console.warn('Video dimensions not available yet');
      return;
    }
    
    console.log('Video native dimensions:', video.videoWidth, 'x', video.videoHeight);
    
    // Set canvas to match video's NATIVE resolution (no scaling)
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    this.canvasContext = canvas.getContext('2d');
    
    // Seek to first frame and draw
    video.currentTime = 0.1;
    video.pause();
  }

  drawVideoFrame(): void {
    if (!this.canvasContext || !this.videoPreview) return;

    const video = this.videoPreview.nativeElement;
    const canvas = this.canvas.nativeElement;

    // Clear canvas
    this.canvasContext.clearRect(0, 0, canvas.width, canvas.height);

    // Draw current video frame at native resolution
    if (video.readyState >= video.HAVE_CURRENT_DATA) {
      this.canvasContext.drawImage(video, 0, 0, canvas.width, canvas.height);
    }

    // Draw ROI points
    if (this.roiPoints.length > 0) {
      this.drawPolygon(this.roiPoints, '#00ff00', 'ROI');
    }

    // Draw calibration points
    if (this.calibrationPoints.length > 0) {
      this.drawPolygon(this.calibrationPoints, '#ff0000', 'CAL');
    }
  }

  drawPolygon(points: Point[] | CalibrationPoint[], color: string, label: string): void {
    if (!this.canvasContext || points.length === 0) return;

    const ctx = this.canvasContext;

    // Draw lines connecting points
    ctx.strokeStyle = color;
    ctx.lineWidth = 3; // Increased for better visibility
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    
    // Close the polygon if complete
    if ((label === 'ROI' && this.roiCompleted) || 
        (label === 'CAL' && this.calibrationCompleted)) {
      ctx.closePath();
      ctx.fillStyle = color + '33'; // Semi-transparent fill
      ctx.fill();
    }
    
    ctx.stroke();

    // Draw points (larger for native resolution)
    points.forEach((point, index) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 8, 0, 2 * Math.PI); // Increased size
      ctx.fill();
      
      // Draw point number
      ctx.fillStyle = 'white';
      ctx.font = 'bold 20px Arial'; // Larger font
      ctx.strokeStyle = 'black';
      ctx.lineWidth = 3;
      ctx.strokeText(`${label}${index + 1}`, point.x + 12, point.y - 12);
      ctx.fillText(`${label}${index + 1}`, point.x + 12, point.y - 12);
    });
  }

  onCanvasClick(event: MouseEvent): void {
    if (!this.isSelectingROI && !this.isSelectingCalibration) return;

    const canvas = this.canvas.nativeElement;
    const rect = canvas.getBoundingClientRect();
    
    // NO SCALING - Canvas matches video native resolution
    // Calculate click position in canvas coordinates
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;
    
    // Calculate scale from displayed size to canvas size
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    
    // Map to canvas coordinates (which are already at native resolution)
    const x = clickX * scaleX;
    const y = clickY * scaleY;

    const point: Point = { x, y };

    if (this.isSelectingROI) {
      // Changed from 5 to 4 points
      if (this.roiPoints.length < 4) {
        this.roiPoints.push(point);
        console.log(`[VIDEO-UPLOAD] ROI point ${this.roiPoints.length}/4 added:`, point);
        
        if (this.roiPoints.length === 4) {
          this.roiCompleted = true;
          this.isSelectingROI = false;
          console.log('[VIDEO-UPLOAD] ROI selection completed with 4 points');
        }
        
        this.drawVideoFrame();
      }
    } else if (this.isSelectingCalibration) {
      if (this.calibrationPoints.length < 4) {
        // Store temporary point and show popup for real-world coordinates
        this.tempCalibrationPoint = point;
        this.calibrationRealX = '';
        this.calibrationRealY = '';
        this.showCalibrationPopup = true;
        console.log(`[VIDEO-UPLOAD] Calibration point ${this.calibrationPoints.length + 1}/4 clicked:`, point);
      }
    }
  }

  confirmCalibrationPoint(): void {
    if (!this.tempCalibrationPoint) return;

    const realX = parseFloat(this.calibrationRealX);
    const realY = parseFloat(this.calibrationRealY);

    if (isNaN(realX) || isNaN(realY)) {
      this.error = 'Please enter valid numeric coordinates';
      console.error('[VIDEO-UPLOAD] Invalid calibration coordinates:', { realX: this.calibrationRealX, realY: this.calibrationRealY });
      return;
    }

    const calibrationPoint: CalibrationPoint = {
      x: this.tempCalibrationPoint.x,
      y: this.tempCalibrationPoint.y,
      realX: realX,
      realY: realY
    };

    this.calibrationPoints.push(calibrationPoint);
    console.log(`[VIDEO-UPLOAD] Calibration point ${this.calibrationPoints.length}/4 confirmed:`, calibrationPoint);
    
    if (this.calibrationPoints.length === 4) {
      this.calibrationCompleted = true;
      this.isSelectingCalibration = false;
      console.log('[VIDEO-UPLOAD] Calibration selection completed with 4 points');
    }
    
    this.showCalibrationPopup = false;
    this.tempCalibrationPoint = null;
    this.error = null;
    this.drawVideoFrame();
  }

  cancelCalibrationPoint(): void {
    this.showCalibrationPopup = false;
    this.tempCalibrationPoint = null;
    this.calibrationRealX = '';
    this.calibrationRealY = '';
  }

  onVideoSeeked(): void {
    this.drawVideoFrame();
  }

  startROISelection(): void {
    console.log('[VIDEO-UPLOAD] Starting ROI selection');
    if (!this.videoUrl) {
      this.error = 'Please select a video file first';
      console.error('[VIDEO-UPLOAD] Cannot start ROI selection - no video URL');
      return;
    }

    this.isSelectingROI = true;
    this.isSelectingCalibration = false;
    this.roiPoints = [];
    this.roiCompleted = false;
    this.error = null;
    
    if (this.videoPreview) {
      const video = this.videoPreview.nativeElement;
      video.pause();
      video.currentTime = 0;
      console.log('[VIDEO-UPLOAD] Video paused at frame 0 for ROI selection');
    }
  }

  startCalibrationSelection(): void {
    console.log('[VIDEO-UPLOAD] Starting calibration selection');
    if (!this.videoUrl) {
      this.error = 'Please select a video file first';
      console.error('[VIDEO-UPLOAD] Cannot start calibration - no video URL');
      return;
    }

    this.isSelectingCalibration = true;
    this.isSelectingROI = false;
    this.calibrationPoints = [];
    this.calibrationCompleted = false;
    this.error = null;
    
    if (this.videoPreview) {
      const video = this.videoPreview.nativeElement;
      video.pause();
      video.currentTime = 0;
      console.log('[VIDEO-UPLOAD] Video paused at frame 0 for calibration');
    }
  }

  clearROI(): void {
    this.roiPoints = [];
    this.roiCompleted = false;
    this.isSelectingROI = false;
    this.drawVideoFrame();
  }

  clearCalibration(): void {
    this.calibrationPoints = [];
    this.calibrationCompleted = false;
    this.isSelectingCalibration = false;
    this.showCalibrationPopup = false;
    this.tempCalibrationPoint = null;
    this.drawVideoFrame();
  }

  async uploadVideo(): Promise<void> {
    console.log('[VIDEO-UPLOAD] ========== UPLOAD STARTED ==========');
    console.log('[VIDEO-UPLOAD] Validating inputs...');
    
    if (!this.selectedFile || !this.videoName) {
      this.error = 'Please select a file and enter a video name';
      console.error('[VIDEO-UPLOAD] Validation failed: Missing file or name');
      return;
    }

    // Skip ROI/calibration check if video preview failed (MOV files)
    if (!this.videoLoadError) {
      // Changed from 5 to 4 points
      if (!this.roiCompleted || this.roiPoints.length !== 4) {
        this.error = 'Please select 4 points for ROI';
        console.error('[VIDEO-UPLOAD] Validation failed: ROI incomplete', { completed: this.roiCompleted, points: this.roiPoints.length });
        return;
      }

      if (!this.calibrationCompleted || this.calibrationPoints.length !== 4) {
        this.error = 'Please select 4 points for calibration';
        console.error('[VIDEO-UPLOAD] Validation failed: Calibration incomplete', { completed: this.calibrationCompleted, points: this.calibrationPoints.length });
        return;
      }
    } else {
      console.warn('[VIDEO-UPLOAD] Skipping ROI/Calibration validation - video preview failed');
    }

    console.log('[VIDEO-UPLOAD] Validation passed');
    this.uploading = true;
    this.error = null;
    this.success = false;
    this.uploadProgress = 0;
    this.uploadStatus = 'Preparing upload...';

    try {
      const fileToUpload: File = this.selectedFile;
      const fileSizeMB = this.selectedFile.size / (1024 * 1024);
      
      console.log(`[VIDEO-UPLOAD] Preparing FormData...`);
      console.log(`[VIDEO-UPLOAD] File: ${this.selectedFile.name} (${fileSizeMB.toFixed(2)} MB, ${this.selectedFile.type})`);
      this.uploadProgress = 0;

      const formData = new FormData();
      
      formData.append('video', fileToUpload, this.selectedFile.name);
      formData.append('name', this.videoName);
      console.log('[VIDEO-UPLOAD] Added video file and name to FormData');
      
      // Add ROI only if available
      if (this.roiCompleted && this.roiPoints.length === 4) {
        // NO ROUNDING - use exact coordinates at native resolution
        const roiData = {
          roi_polygon: this.roiPoints.map(p => [p.x, p.y])
        };
        formData.append('roi', JSON.stringify(roiData));
        console.log('[VIDEO-UPLOAD] Added ROI data:', roiData);
      } else {
        console.log('[VIDEO-UPLOAD] No ROI data to add');
      }
      
      // Add calibration points only if available
      if (this.calibrationCompleted && this.calibrationPoints.length === 4) {
        const calibrationData = {
          points: this.calibrationPoints.map(p => ({
            pixel: [p.x, p.y], // NO ROUNDING
            real: [p.realX, p.realY]
          }))
        };
        formData.append('calibrate_coordinates', JSON.stringify(calibrationData));
        console.log('[VIDEO-UPLOAD] Added calibration data:', calibrationData);
      } else {
        console.log('[VIDEO-UPLOAD] No calibration data to add');
      }

      console.log('[VIDEO-UPLOAD] FormData prepared, starting HTTP request...');
      this.uploadStatus = 'Uploading to server...';
      
      this.videoService.uploadVideoWithProgress(formData).subscribe({
        next: (event: any) => {
          console.log('[VIDEO-UPLOAD] Received event:', event);
          
          if (event.type === 'sent') {
            console.log('[VIDEO-UPLOAD] Request sent, waiting for progress...');
            this.uploadStatus = 'Request sent to server...';
          } else if (event.type === 'progress') {
            this.uploadProgress = event.progress;
            this.uploadStatus = `Uploading to server... ${event.progress}%`;
            const loadedMB = (event.loaded / 1024 / 1024).toFixed(2);
            const totalMB = event.total ? (event.total / 1024 / 1024).toFixed(2) : 'unknown';
            console.log(`[VIDEO-UPLOAD] Progress: ${event.progress}% (${loadedMB}/${totalMB} MB)`);
          } else if (event.type === 'headers') {
            console.log('[VIDEO-UPLOAD] Response headers received, waiting for body...');
          } else if (event.type === 'response') {
            console.log('[VIDEO-UPLOAD] ========== UPLOAD COMPLETED ==========');
            console.log('[VIDEO-UPLOAD] Server response:', event.body);
            this.uploading = false;
            this.uploadProgress = 100;
            this.uploadStatus = 'Upload complete!';
            
            // Show success popup
            this.showResultPopup = true;
            this.resultPopupType = 'success';
            this.resultPopupMessage = 'Video uploaded successfully!';
            this.videoUploaded.emit();
            
            // Auto-close popup and form after 2 seconds
            setTimeout(() => {
              this.closeResultPopup();
              this.toggleUploadForm();
            }, 2000);
          } else {
            console.log('[VIDEO-UPLOAD] Other event type:', event.type, event);
          }
        },
        error: (err: any) => {
          console.error('Upload error:', err);
          console.error('Error details:', {
            status: err.status,
            statusText: err.statusText,
            message: err.message,
            error: err.error
          });
          
          this.uploading = false;
          this.uploadProgress = 0;
          this.uploadStatus = '';
          
          // Show error popup based on HTTP status
          this.showResultPopup = true;
          this.resultPopupType = 'error';
          
          if (err.status === 500) {
            this.resultPopupMessage = `Server Error: ${err.error?.error || err.error?.message || 'Internal server error occurred'}`;
          } else if (err.status === 400) {
            this.resultPopupMessage = `Bad Request: ${err.error?.error || err.error?.message || 'Invalid upload data'}`;
          } else if (err.status === 0) {
            this.resultPopupMessage = 'Network Error: Cannot connect to server';
          } else {
            this.resultPopupMessage = `Upload Failed (${err.status}): ${err.error?.error || err.message || 'Unknown error'}`;
          }
          
          console.error('[VIDEO-UPLOAD] Error popup shown:', this.resultPopupMessage);
        }
      });
    } catch (error) {
      console.error('Upload preparation error:', error);
      this.uploading = false;
      this.uploadProgress = 0;
      this.uploadStatus = '';
      
      // Show error popup
      this.showResultPopup = true;
      this.resultPopupType = 'error';
      this.resultPopupMessage = 'Failed to prepare video for upload';
    }
  }

  closeResultPopup(): void {
    this.showResultPopup = false;
  }

  resetForm(): void {
    if (this.videoUrl) {
      URL.revokeObjectURL(this.videoUrl);
    }
    
    this.selectedFile = null;
    this.videoName = '';
    this.videoUrl = null;
    this.roiPoints = [];
    this.calibrationPoints = [];
    this.roiCompleted = false;
    this.calibrationCompleted = false;
    this.isSelectingROI = false;
    this.isSelectingCalibration = false;
    this.uploading = false;
    this.error = null;
    this.success = false;
    this.videoLoadError = false;
    this.showResultPopup = false;
  }
}
