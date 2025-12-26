import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  template: `
    <!-- Navigation Bar -->
    <nav class="app-navbar">
      <div class="nav-brand">
        <span class="brand-icon">🎥</span>
        <span class="brand-text">Traffic Analytics</span>
      </div>
      <div class="nav-links">
        <button 
          class="nav-link" 
          [class.active]="currentView === 'dashboard'"
          (click)="setView('dashboard')">
          <span class="nav-icon">📊</span>
          <span>Dashboard</span>
        </button>
        <button 
          class="nav-link" 
          [class.active]="currentView === 'violations'"
          (click)="setView('violations')">
          <span class="nav-icon">🚨</span>
          <span>Violations</span>
        </button>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="app-content">
      <app-dashboard *ngIf="currentView === 'dashboard'"></app-dashboard>
      <app-violation-dashboard *ngIf="currentView === 'violations'"></app-violation-dashboard>
    </main>
  `,
  styles: [`
    :host {
      display: block;
      min-height: 100vh;
      background: #f5f6fa;
    }

    .app-navbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      height: 60px;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .nav-brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .brand-icon {
      font-size: 24px;
    }

    .brand-text {
      font-size: 20px;
      font-weight: 600;
      color: white;
      letter-spacing: 0.5px;
    }

    .nav-links {
      display: flex;
      gap: 8px;
    }

    .nav-link {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 20px;
      border: none;
      border-radius: 8px;
      background: transparent;
      color: rgba(255, 255, 255, 0.7);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .nav-link:hover {
      background: rgba(255, 255, 255, 0.1);
      color: white;
    }

    .nav-link.active {
      background: rgba(102, 126, 234, 0.3);
      color: white;
    }

    .nav-icon {
      font-size: 16px;
    }

    .app-content {
      min-height: calc(100vh - 60px);
    }
  `]
})
export class AppComponent {
  title = 'Video Streaming Application';
  currentView: 'dashboard' | 'violations' = 'dashboard';

  setView(view: 'dashboard' | 'violations'): void {
    this.currentView = view;
  }
}
