import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { AppComponent } from './app.component';
import { DashboardComponent } from './components/dashboard.component';
import { VideoDetailComponent } from './components/video-detail.component';
import { VideoUploadComponent } from './components/video-upload.component';

import { VideoService } from './services/video.service';
import { WebsocketService } from './services/websocket.service';

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
    FormsModule
  ],
  providers: [
    VideoService,
    WebsocketService
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
