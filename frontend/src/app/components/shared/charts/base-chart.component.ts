import { Component, OnDestroy, OnInit } from '@angular/core';
import { Chart, ChartConfiguration, ChartType, registerables } from 'chart.js';

// Register Chart.js components
Chart.register(...registerables);

/**
 * Abstract base class for all chart components
 * Provides common lifecycle hooks, throttling, and cleanup
 */
@Component({
  template: ''
})
export abstract class BaseChartComponent implements OnInit, OnDestroy {
  protected chart?: Chart;
  protected readonly CHART_UPDATE_INTERVAL = 1000; // 1 second
  protected lastUpdate = 0;
  protected isFirstRender = true;
  protected updateTimer?: number;

  abstract ngOnInit(): void;

  /**
   * Initialize the chart with configuration
   */
  protected initChart(canvas: HTMLCanvasElement, config: ChartConfiguration): void {
    try {
      this.chart = new Chart(canvas, config);
      this.isFirstRender = false;
    } catch (error) {
      console.error('Failed to initialize chart:', error);
    }
  }

  /**
   * Throttled update method - ensures updates happen at most once per second
   */
  protected throttledUpdate(updateFn: () => void): void {
    const now = Date.now();
    if (now - this.lastUpdate < this.CHART_UPDATE_INTERVAL) {
      // Schedule update for later
      if (this.updateTimer) {
        clearTimeout(this.updateTimer);
      }
      this.updateTimer = window.setTimeout(() => {
        updateFn();
        this.lastUpdate = Date.now();
      }, this.CHART_UPDATE_INTERVAL - (now - this.lastUpdate));
      return;
    }
    
    updateFn();
    this.lastUpdate = now;
  }

  /**
   * Update chart data and re-render
   */
  protected updateChart(): void {
    if (!this.chart) return;
    
    try {
      // Disable animations after first render for performance
      if (this.chart.options.animation) {
        this.chart.options.animation.duration = this.isFirstRender ? 500 : 0;
      }
      this.chart.update('none'); // 'none' mode for fastest update
    } catch (error) {
      console.error('Failed to update chart:', error);
    }
  }

  /**
   * Cleanup chart resources
   */
  ngOnDestroy(): void {
    if (this.updateTimer) {
      clearTimeout(this.updateTimer);
    }
    
    if (this.chart) {
      try {
        this.chart.destroy();
      } catch (error) {
        console.error('Failed to destroy chart:', error);
      }
      this.chart = undefined;
    }
  }
}
