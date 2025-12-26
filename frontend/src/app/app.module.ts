import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

import { AppComponent } from './app.component';
import { DashboardComponent } from './components/dashboard.component';
import { VideoDetailComponent } from './components/video-detail.component';
import { VideoUploadComponent } from './components/video-upload.component';

// Chart components
import { VehicleTimelineChartComponent } from './components/shared/charts/vehicle-timeline-chart/vehicle-timeline-chart.component';
import { SpeedGaugeChartComponent } from './components/shared/charts/speed-gauge-chart/speed-gauge-chart.component';
import { VehicleTypeChartComponent } from './components/shared/charts/vehicle-type-chart/vehicle-type-chart.component';
import { AnalyticsDashboardComponent } from './components/analytics-dashboard/analytics-dashboard.component';

// Violation Dashboard (standalone component)
import { ViolationDashboardComponent } from './components/violation-dashboard/violation-dashboard.component';

import { VideoService } from './services/video.service';
import { WebsocketService } from './services/websocket.service';
import { AnalyticsService } from './services/analytics.service';
import { AnalyticsCacheService } from './services/analytics-cache.service';
import { ViolationService } from './services/violation.service';

@NgModule({
  declarations: [
    AppComponent,
    DashboardComponent,
    VideoDetailComponent,
    VideoUploadComponent
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule,
    CommonModule,
    VehicleTimelineChartComponent,
    SpeedGaugeChartComponent,
    VehicleTypeChartComponent,
    AnalyticsDashboardComponent,
    ViolationDashboardComponent  // Standalone component imported here
  ],
  providers: [
    VideoService,
    WebsocketService,
    AnalyticsService,
    AnalyticsCacheService,
    ViolationService
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
