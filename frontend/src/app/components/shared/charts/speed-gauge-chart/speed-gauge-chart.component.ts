import { Component, ElementRef, Input, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartComponent } from '../base-chart.component';
import { ChartConfiguration } from 'chart.js';

@Component({
  selector: 'app-speed-gauge-chart',
  templateUrl: './speed-gauge-chart.component.html',
  styleUrls: ['./speed-gauge-chart.component.css'],
  standalone: true,
  imports: [CommonModule]
})
export class SpeedGaugeChartComponent extends BaseChartComponent implements OnInit {
  @ViewChild('chartCanvas', { static: true }) chartCanvas!: ElementRef<HTMLCanvasElement>;
  @Input() set maxSpeed(value: number | undefined) {
    if (value !== undefined) {
      this.updateMaxSpeed(value);
    }
  }

  private currentMaxSpeed = 0;

  ngOnInit(): void {
    const config: ChartConfiguration = {
      type: 'doughnut',
      data: {
        labels: ['Speed', 'Remaining'],
        datasets: [{
          data: [0, 150],
          backgroundColor: [
            this.getSpeedColor(0),
            'rgba(200, 200, 200, 0.2)'
          ],
          borderWidth: 0,
          circumference: 180,
          rotation: 270
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 500
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            enabled: false
          }
        }
      }
    };

    this.initChart(this.chartCanvas.nativeElement, config);
  }

  private updateMaxSpeed(speed: number): void {
    this.throttledUpdate(() => {
      this.currentMaxSpeed = Math.min(speed, 150); // Cap at 150 km/h
      
      if (!this.chart) return;

      // Update data
      this.chart.data.datasets[0].data = [this.currentMaxSpeed, 150 - this.currentMaxSpeed];
      
      // Update color based on speed
      this.chart.data.datasets[0].backgroundColor = [
        this.getSpeedColor(this.currentMaxSpeed),
        'rgba(200, 200, 200, 0.2)'
      ];

      this.updateChart();
    });
  }

  private getSpeedColor(speed: number): string {
    if (speed >= 80) {
      return 'rgba(255, 99, 132, 0.8)'; // Red for speeding
    } else if (speed >= 60) {
      return 'rgba(255, 205, 86, 0.8)'; // Yellow for near speed limit
    } else {
      return 'rgba(75, 192, 192, 0.8)'; // Green for safe speed
    }
  }

  getCurrentSpeed(): number {
    return this.currentMaxSpeed;
  }

  getSpeedStatus(): string {
    if (this.currentMaxSpeed >= 80) {
      return 'Speeding';
    } else if (this.currentMaxSpeed >= 60) {
      return 'Near Limit';
    } else {
      return 'Safe';
    }
  }
}
